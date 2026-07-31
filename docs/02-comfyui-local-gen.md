# Fase 06 — Geração local de thumbs e clipes via ComfyUI

Autor: sessão Claude paralela (29/07/2026). Módulo isolado, opt-in, zero mudança no pipeline atual.

## Por que ComfyUI e não API paga

O gargalo do ViralReplicator hoje não é detectar o viral — é **produzir a réplica**.
Thumbnail é o item de maior impacto em CTR e o que mais consome tempo manual.
Rodando local via ComfyUI:

- custo zero por imagem (vs. ~US$0,04/img em API), o que permite gerar 5 variações por vídeo sem pensar;
- sem limite de créditos/rate limit no ciclo de 30 min do `main.py`;
- LoRAs e checkpoints próprios → identidade visual consistente do canal, coisa que API fechada não entrega.

## Setup — JÁ FEITO nesta máquina (29/07/2026)

ComfyUI instalado em **`D:\ComfyUI`** (escolhido o HDD pra não consumir o SSD de 240GB,
que estava com 34,6GB livres):

| Item | Versão / detalhe |
|---|---|
| ComfyUI | clone do `comfyanonymous/ComfyUI`, commit `f73e8cd` |
| venv | Python 3.11.9 em `D:\ComfyUI\venv` |
| PyTorch | 2.11.0+cu128 — `torch.cuda.is_available()` → True, 12GB detectados |
| Checkpoint | `Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors` (6,62GB) |
| Extra | ComfyUI-Manager em `custom_nodes/` |

**Para subir:** `D:\ComfyUI\iniciar_comfyui.bat` → `http://127.0.0.1:8188`.

Confirmar que o batch vê o servidor:
```bash
python -c "from comfy_client import ComfyUIClient; c=ComfyUIClient(); print(c.is_online(), c.available_checkpoints())"
```

Se o ComfyUI mudar de porta/máquina: `set COMFYUI_URL=http://ip:porta`.

Aviso benigno no log: `You need pytorch with cu130 or higher to use optimized CUDA
operations`. O backend otimizado do `comfy_kitchen` fica desabilitado, mas as operações
que ele acelera (nvfp4, mxfp8) são de Blackwell e a 3060 (sm_86) não as suporta de todo
jeito — não vale re-baixar 2,75GB de torch por isso.

## Uso

```bash
python comfy_batch.py --top 5 --dry-run    # revisa os prompts sem gastar GPU
python comfy_batch.py --top 5              # gera de verdade
python comfy_batch.py --top 3 --checkpoint juggernautXL_v9.safetensors --steps 32
```

Saída: `output/thumbs/{video_id}_*.png` + `manifest.json` com id, título original,
`pt_br_title`, prompt usado e arquivos gerados.

No pipeline (opt-in, 2 linhas em `main.py` após `apply_idea_generation`):

```python
from comfy_batch import generate_thumbnails
final = generate_thumbnails(final, limit=5)
```

## Decisões de design

**Texto fora da imagem.** O prompt pede explicitamente `empty space on the right for text`
e o negativo bloqueia `text, letters, typography`. Difusão escreve texto torto; o título
vai depois no editor, sobre o espaço reservado. Isso também deixa a mesma imagem reutilizável
para variações de título (A/B de CTR).

**Prompt vem do título original em inglês**, não do `pt_br_title`. O `pt_br_title` do
`idea_generator.py` hoje é rule-based e truncado (`"A Verdade sobre: Dark Secret of ..."`),
descreve mal a cena. Quando a integração real com LLM entrar no `idea_generator`, o campo
`generated_ideas.sugestoes.thumbnail` passa a ter prioridade automática — o batch já lê ele
primeiro e só cai no `CLUSTER_HINTS` se estiver vazio.

**Seed determinística por `video_id`.** Regerar o mesmo vídeo dá a mesma imagem, então a
única variável entre execuções é o prompt/checkpoint. Facilita comparar workflows.

**Workflows em formato API, patcheados por título de nó.** O grafo não é montado em código
(quebraria a cada mudança de nó do ComfyUI): você exporta do ComfyUI em
*Workflow → Export (API)*, renomeia os nós-chave para `VRP_POSITIVE`, `VRP_NEGATIVE`,
`VRP_LATENT`, `VRP_SAMPLER` e joga em `workflows/`. Qualquer workflow — FLUX, LTX-2.3,
upscale — entra sem tocar em Python.

## Vídeo — IMPLEMENTADO (`comfy_video.py`)

Anima a thumb já gerada num clipe de até 5s. Modelo: **LTXV 2B 0.9.8 distilled**
(`ltxv-2b-0.9.8-distilled.safetensors` + `t5xxl_fp8_e4m3fn_scaled.safetensors`),
workflow em `workflows/ltxv_i2v_5s.json`.

```bash
python comfy_video.py --top 6 --seconds 5
python comfy_video.py --thumb output/thumbs/x.png
```

**Teto rígido de 5s.** O LTXV só aceita nº de frames ≡ 1 (mod 8), então
`frames_for()` arredonda **para baixo**: 121 frames @ 25fps = **4,84s**. Nunca estoura.

Custo medido na RTX 3060: **~40s por clipe** de 4,84s em 768x448, 8 passos.
6 clipes em 3min50. Não colocar no ciclo de 30min do `main.py`.

### As três armadilhas do LTXV (todas custaram clipe perdido)

1. **cfg=1.0 mata o prompt negativo.** O distilled exige cfg 1.0, e sem guidance
   não há o que subtrair — `text, letters` no negativo é decoração. Tudo que você
   NÃO quer tem que estar no positivo, afirmativo: "no people appear, no text and
   no titles on screen".
2. **O texto vence a imagem de referência.** Se o prompt descreve algo que não está
   no frame, o LTXV reinventa a cena em ~2s. A 1ª tentativa passou o título do vídeo
   ("stepmother... inheritance") e virou uma mulher andando em plena luz do dia com
   card de texto embolado. Por isso `build_motion_prompt()` **corta o trecho
   `scene evoking the theme: <título>`** do prompt herdado da thumb — o título é
   justamente o veneno.
3. **Movimento sem cena para ancorar consome o frame.** O sufixo antigo pedia
   "fog and haze drift through the frame"; num clipe sem descrição de cena o modelo
   obedeceu só isso e o vídeo inteiro virou parede de fumaça. O sufixo atual diz
   "the scene stays exactly as it is" em vez de pedir névoa.

Também **não há fallback por cluster no vídeo** (diferente da thumb): uma dica que
não bate com a imagem (ex. "abandoned place at night" numa tela de forex) empurra o
modelo pra outra cena. Prompt curto é ruim, prompt errado é pior.

### Resultado da rodada de 30/07 (6 virais)

5 de 6 clipes coerentes do 1º ao último frame. O único problema remanescente é
`U9IclothABU` (tela de gráfico de forex): a cena se mantém mas uma silhueta de
pessoa aparece no meio. Cenas de interface/tela são o caso mais frágil — o LTXV
foi treinado em vídeo de mundo real e tende a "povoar" o quadro. Para esses, o
caminho é encurtar (`--seconds 3`) ou trocar a thumb por uma cena física.

## Resultado medido (29/07/2026)

`python comfy_batch.py --top 2` → 2 PNGs 1280x720 em `output/thumbs/`, em 2min37
(inclui ~1min de load do checkpoint vindo do HDD). **~40s por imagem** com o modelo
já em cache. Qualidade: cinematográfica, dark, sem texto rabiscado, com área vazia
utilizável pro título.

Dois problemas apareceram só no teste real e já estão corrigidos:

1. **Resolução**: SDXL gera no bucket nativo 1344x768, que é 1.75:1 — **não é 16:9**.
   Entrou um nó `ImageScale` (`VRP_RESIZE_YOUTUBE`) no fim do workflow fazendo crop
   central pra 1280x720 exato. Se você trocar de workflow, replique esse nó.
2. **Letras emboladas**: a dica de true crime pedia `police tape` e `evidence board`.
   SDXL desenha letras nesses objetos por definição e o prompt negativo não segura.
   Reescrito para props sem escrita (janela com chuva, corredor com porta iluminada).
   Regra pra novas dicas em `CLUSTER_HINTS`: nada de fita de isolamento, documento,
   placa, jornal ou monitor com texto.

## Pendências
- [ ] Botão "Gerar thumb" no `app_pro.py` (dialog do Playbook) — não feito para não conflitar com a sessão que mexe na UI.
- [ ] Persistir `thumb_local_path` no banco (exige `ALTER TABLE` em `storage.init_db`) — hoje só em memória + `manifest.json`.
- [ ] Gerar 3–5 variações por vídeo (`batch_size` no `VRP_LATENT`) e escolher a melhor.
