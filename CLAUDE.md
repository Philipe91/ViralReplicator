# ViralReplicator — notas para o Claude

## 👉 Comece pelo `ESTADO.md`

Este arquivo tem as **regras**; o `ESTADO.md` tem **onde o projeto parou** — qual
etapa falta em cada vídeo, o que as outras conversas estavam fazendo e como
reabri-las. Ele é regerado por um hook ao fim de cada turno (`estado.py`), então
sobrevive à janela sendo fechada sem aviso. Só edite dentro do bloco
`<!-- MANUAL:INICIO -->`; o resto é sobrescrito.

## ⚠️ AVISO DE SESSÃO PARALELA (29/07/2026)

Outra sessão do Claude Code (rodando fora desta pasta, em `C:\WINDOWS\system32`)
adicionou o **módulo de geração local via ComfyUI**. Arquivos NOVOS, nada existente
foi tocado:

- `editor.py` — **montagem profissional**: corte seco por padrão, dissolve só em quebra de ato, punch-in no hook, Ken Burns variado, legenda ASS queimada com destaque por palavra, trilha com ducking, passe de grade/grão/vinheta
- `produce_video.py` — orquestra o roteiro JSON → narração → imagens → clipes → montagem (`--etapa`, `--montagem pro|simples`)
- `comfy_musica.py` + `workflows/acestep_musica.json` — gera a trilha dark local via ACE-Step
- `comfy_client.py` — cliente da API HTTP do ComfyUI (fila, polling, upload, download, patch de grafo)
- `comfy_batch.py` — batch de thumbnails a partir dos virais do banco
- `comfy_video.py` — anima a thumb num clipe de **até 5s** (LTXV 2B distilled)
- `workflows/sdxl_thumbnail.json` — workflow txt2img SDXL em formato API
- `workflows/ltxv_i2v_5s.json` — workflow image-to-video LTXV em formato API
- `docs/02-comfyui-local-gen.md` — doc de setup, handoff e as armadilhas do LTXV
- `output/thumbs/` e `output/clips/` — saída (+ `manifest.json`), ignorados no git

**Não houve alteração em** `main.py`, `app_pro.py`, `config.py`, `storage.py`,
`idea_generator.py` nem em nenhum outro módulo do pipeline. O plug no pipeline
foi deixado de propósito como opt-in de 2 linhas (ver doc) para não conflitar com
o trabalho em andamento nessas telas.

Se você (Claude da sessão do projeto) precisar mexer nesses arquivos, pode —
só evite duplicar o cliente: a integração com ComfyUI toda passa por
`comfy_client.ComfyUIClient`.

## Como plugar no pipeline (opt-in)

Em `main.py`, depois de `apply_idea_generation`:

```python
from comfy_batch import generate_thumbnails
final = generate_thumbnails(final, limit=5)   # v['thumb_local_path']
```

Se o ComfyUI estiver offline o batch avisa e devolve `thumb_local_path=None` —
nunca derruba o ciclo do bot.

## Teto de 5 segundos por clipe (regra do projeto)

Definido pelo dono do projeto em 30/07. `comfy_video.MAX_SECONDS = 5.0` e
`frames_for()` arredonda **para baixo** até o frame count válido do LTXV
(≡ 1 mod 8) → 121 frames @ 25fps = 4,84s. `--seconds` acima de 5 é rebaixado
com aviso. Não aumente esse teto sem pedir.

## Linguagem visual do canal (medido em 31/07 — não reabrir sem dado novo)

O canal de referência tem **dois** estilos, com resultados opostos:
o vídeo de artérias (14 mil views) é 3D fotorreal escuro e quase 100% interior do
corpo; o de cor dos olhos (**5,75 milhões**) é ilustração editorial clara, com
**pessoas na maioria dos planos** e a anatomia entrando como corte estilizado
dentro da cena.

O preset `medico_3d` tinha copiado o de 14k por engano. **O padrão do canal é
`explicativo_claro`.** Regra prática de mistura: a maioria dos planos tem gente,
luz de dia ou lugar reconhecível; anatomia pura é tempero, não a base. Use o
dicionário `ELENCO` de `produce_video.py` para descrever as mesmas pessoas com as
mesmas palavras em todos os planos.

**Antes de escrever prompt de imagem, rode `python estudo_frames.py <ID>`** e abra
as folhas de contato que ele gera em `output/ref_thinkscience/frames/<ID>/`. O
prompt sai do que eles põem na tela, não do que a gente imagina que eles põem —
foi exatamente esse pulo que produziu a primeira leva errada. O passo está no
`PLAYBOOK.md` como etapa 2, com as quatro perguntas que precisam ser respondidas
por escrito no `nota_metodo` do roteiro. Escolha o vídeo de referência pelo
**desempenho**, não pelo assunto.

Ainda não resolvido: SDXL puro **não garante o mesmo rosto** entre gerações
(precisaria de LoRA/IP-Adapter), e os rótulos na tela que eles usam têm que sair
por `drawtext`, nunca pela difusão.

## Regras de edição (aprendidas na prática, 30/07)

Tudo isso já está codado em `editor.py`; não reintroduza os erros:

- **Dissolve não é transição padrão.** Crossfade em toda cena = slideshow. Corte
  seco dentro do ato; dissolve só onde o roteiro marca `"transicao": "dissolve"`
  (salto temporal). Implementado como: concat sem re-encode dentro do ato, xfade
  apenas entre atos.
- **Nível de trilha é ALVO, não ganho relativo.** `volume=0.22` sobre uma música
  que já vinha a -26 dBFS jogou a cama para -45 dBFS (inaudível). Use `loudnorm`
  com alvo fixo e o resultado fica igual pra qualquer arquivo.
- **O alvo é `MUSICA_LUFS = -42`** (recalibrado em 30/07). Medido no canal de
  referência: o bed dele fica a **-57 dBFS** nas pausas, 33 dB abaixo da voz. Com
  o alvo antigo de -26 a nossa cama saía a -31 dBFS — **26 dB alta demais**,
  competindo com a narração em vez de sustentá-la. Se achar -26 em algum lugar,
  é resíduo.
- **`amix` precisa de `normalize=0`.** Sem isso ele divide pelo nº de entradas e
  derruba a cama de novo.
- **Ducking com ratio alto vira mute.** `ratio=9` + `release=450ms` não deixava a
  música voltar nas pausas de 0,35s. Use `ratio=4`, `release=250ms`.
- **Legenda: pontuação é quebra preferencial, não obrigatória.** Quebrar sempre no
  ponto gerava bloco de 1 palavra piscando ("conquista."). Mínimo de 3 palavras
  por bloco e órfão funde no anterior.
- **WordBoundary vem sem pontuação.** Use o token do texto original e só o tempo
  do evento.
- **Não esticar clipe LTXV** para cobrir a cena (4x slow motion trava). Clipe em
  velocidade natural + Ken Burns no último frame dele.

## Convenções do módulo ComfyUI

- Workflows ficam em `workflows/`, **formato API** (ComfyUI → Workflow → Export (API)).
- Nós patcheáveis são identificados por `_meta.title`: `VRP_POSITIVE`,
  `VRP_NEGATIVE`, `VRP_LATENT`, `VRP_SAMPLER`. Sem título, há fallback por `class_type`.
- URL do ComfyUI vem de `COMFYUI_URL` (default `http://127.0.0.1:8188`), **não** de `config.py`.
- Seed é determinística por `video_id` (`zlib.crc32`) — regerar dá a mesma imagem.
- Prints do módulo passam por `_p()` porque títulos do YouTube têm emoji e o
  console cp1252 do Windows estoura com `UnicodeEncodeError`.

## Estado do teste (29/07/2026) — FUNCIONANDO PONTA A PONTA

ComfyUI foi instalado nesta máquina em **`D:\ComfyUI`** (venv Python 3.11,
torch 2.11.0+cu128, CUDA OK na RTX 3060). Sobe com `D:\ComfyUI\iniciar_comfyui.bat`
em `http://127.0.0.1:8188`. Checkpoint instalado:
`Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors` (6,62GB).

- `python comfy_batch.py --top 2` → 2 thumbs 1280x720 geradas em `output/thumbs/`.
- Tempo: ~2min37 para 2 imagens (inclui ~1min de load do checkpoint do HDD);
  **~40s por imagem** depois que o modelo está em cache.
- `patch_graph` validado com e sem os títulos `VRP_*`, template não é mutado.

Dois ajustes vieram do teste real:
1. **Nó `ImageScale` (VRP_RESIZE_YOUTUBE)** no fim do workflow. SDXL gera no bucket
   nativo 1344x768 (1.75:1, não é 16:9) — o nó faz crop central pra 1280x720 exato.
2. **`CLUSTER_HINTS` sem objeto que tem escrita.** A dica antiga de true crime pedia
   "police tape" e "evidence board"; SDXL desenhou letras emboladas neles apesar do
   prompt negativo. Regra: nada de fita de isolamento, documento, placa ou jornal.

## Hardware alvo

RTX 3060 12GB / i5-10400F / **16GB RAM (stick único, sem dual channel)**.
SDXL roda tranquilo. FLUX só em GGUF Q4/Q5. Vídeo (LTX-2.3) é o gargalo real:
os workflows de 12GB VRAM assumem 32GB de RAM pro offload — com 16GB vai sofrer.
