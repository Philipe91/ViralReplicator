# ESTADO — onde o projeto parou

_Gerado automaticamente em 31/07/2026 17:14 por `estado.py`. Não edite fora do bloco manual._

**Se você é uma sessão nova do Claude: leia este arquivo primeiro.** Ele diz
o que já está no disco, o que a última conversa estava fazendo e qual é o
próximo comando. Depois leia `PLAYBOOK.md` (como se faz) e `CLAUDE.md` (as
regras que já custaram retrabalho).

## O que fazer agora

<!-- MANUAL:INICIO -->
> Este bloco é o único escrito à mão. Tudo fora dele é regerado do disco e
> qualquer edição se perde. Aqui vai a **intenção**: o próximo passo e o que
> está travado esperando decisão.

## Onde o projeto está (31/07, fim do dia)

A **V3 foi implementada até a etapa 9** e o primeiro vídeo completo saiu:
`de_01_arterien`, 5min57s, 14 cenas, 55 batidas. Etapas 1 a 9 estão no GitHub,
na branch `fix/saneamento-minimo`. Falta só a **etapa 10 (B-roll)**, adiada pelo
dono.

O que cada peça faz está no PLAYBOOK. O resumo: `direcao.py` decide câmera,
energia e cor; `composicao.py` + `compositor.py` tratam o plano como pilha de
camadas; seis executores vetoriais (diagrama, timeline, gráfico, ícone, motion,
parallax) desenham o que a difusão erra; `som.py` sintetiza os efeitos.

## Esperando decisão do dono

1. **O vídeo de 6 min serve, ou alonga para 8?** O alvo da tabela é 8 min; o
   roteiro foi escrito curto. 14 cenas nesse ritmo dão ~6 min, 8 min pediriam ~18.
2. **O gráfico de fibras põe números que a narração não diz** (Gerste 17g,
   Linsen 11g, Haferflocken 10g, Apfel 2,4g). Ou entra fonte no PRONTO.json, ou
   troco por um plano sem números. **Perguntei duas vezes, segue sem resposta.**
3. **Fontes do vídeo.** O protocolo de publicação EXIGE links reais e nós temos
   ZERO. É isso que trava a publicação, mais que qualquer coisa visual.
4. **Impressum** do canal alemão (falta endereço).

## Teste do Gemini Notebook (ex-NotebookLM), em andamento

O dono quis testar aproveitar imagens e takes de vídeo gerado lá. Estado:

- Notebook criado com a narração alemã do `de_01_arterien` como fonte.
  URL: notebook.google.com/notebook/3f68ce44-2c63-4c25-8f4c-8c6e8fee3745
- Video Overview gerado: **9:14, em alemão, estilo personalizado** pedindo a
  nossa paleta. Ele esticou o conteúdo 55% além da nossa narração — o que ele
  ACRESCENTOU precisa ser ouvido antes de aproveitar, pela regra de não afirmar
  mais que o roteiro.
- **TRAVADO NO DOWNLOAD.** Cliquei em Baixar e o arquivo não apareceu em
  Downloads, Desktop nem Documents. É a mesma limitação que o SKILL.md do
  /publicar já registrava para o YouTube Studio — agora confirmada numa segunda
  ferramenta, então não é caso isolado. **Precisa do dono baixar à mão** (Ctrl+J
  no Chrome) e dizer o caminho.
- A ferramenta de importação (`importar_video.py`) está pronta e testada: extrai
  planos e takes, corta marca d'água antes de redimensionar, e o campo
  `plano["arquivo"]` pluga qualquer PNG/MP4 num plano do roteiro.

Minha recomendação técnica sobre isso não mudou: frame extraído vem comprimido,
com texto queimado, e sem controle de qual plano se recebe. O que o Gemini
Notebook faz bem e nós não fazemos é **digerir fontes** — que é justamente o
item 3 acima.
<!-- MANUAL:FIM -->

## Vídeos

| id | cenas | narração | imagens | clipes | montagem | publicação | próxima ação |
|---|---|---|---|---|---|---|---|
| `br_demo3_arterias` | 2 | ✅ 2/2 | ✅ 8/8 | ✅ 2/2 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `casa_da_mae` | 18 | ✅ 18/18 | ✅ 39/18 | ✅ 8/7 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `de_01_arterien` | 14 | ✅ 14/14 | 🟨 52/55 | 🟨 13/14 | ✅ final | ⬜ | `python produce_video.py scripts/de_01_arterien.json --etapa imagens`  (ComfyUI de pé) |
| `de_01_augenfarbe` | 16 | ⬜ 0/16 | ⬜ 0/33 | ⬜ 0/7 | ⬜ | ⬜ | `python produce_video.py scripts/de_01_augenfarbe.json --etapa audio` |
| `de_demo2_arterien` | 2 | ✅ 2/2 | ✅ 8/8 | ✅ 2/2 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `de_demo3_arterien` | 2 | ✅ 2/2 | ✅ 9/8 | ✅ 2/2 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `de_demo4_diagrama` | 2 | ✅ 2/2 | ✅ 8/8 | ✅ 2/2 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `de_demo5_motion` | 2 | ✅ 2/2 | 🟨 7/8 | ✅ 2/2 | ✅ final | ⬜ | `python produce_video.py scripts/de_demo5_motion.json --etapa imagens`  (ComfyUI de pé) |
| `de_demo6_parallax` | 2 | ✅ 2/2 | ✅ 10/8 | ✅ 2/2 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `de_demo_arterien` | 3 | ✅ 3/3 | ✅ 6/6 | ✅ 1/1 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |

- `br_demo3_arterias` → vídeo final: `output\producao\br_demo3_arterias\br_demo3_arterias_FINAL.mp4` (28 MB)
- `casa_da_mae` → vídeo final: `output\producao\casa_da_mae\casa_da_mae_FINAL.mp4` (159 MB)
- `de_01_arterien` → vídeo final: `output\producao\de_01_arterien\de_01_arterien_FINAL.mp4` (203 MB)
- `de_demo2_arterien` → vídeo final: `output\producao\de_demo2_arterien\de_demo2_arterien_FINAL.mp4` (36 MB)
- `de_demo3_arterien` → vídeo final: `output\producao\de_demo3_arterien\de_demo3_arterien_FINAL.mp4` (27 MB)
- `de_demo4_diagrama` → vídeo final: `output\producao\de_demo4_diagrama\de_demo4_diagrama_FINAL.mp4` (26 MB)
- `de_demo5_motion` → vídeo final: `output\producao\de_demo5_motion\de_demo5_motion_FINAL.mp4` (25 MB)
- `de_demo6_parallax` → vídeo final: `output\producao\de_demo6_parallax\de_demo6_parallax_FINAL.mp4` (26 MB)
- `de_demo_arterien` → vídeo final: `output\producao\de_demo_arterien\de_demo_arterien_FINAL.mp4` (49 MB)

## Serviços e repositório

- **ComfyUI** (`127.0.0.1:8188`): 🟢 no ar
- **git**: ramo `fix/saneamento-minimo`, 2 arquivo(s) não commitado(s)
- último commit: `25986ab9 feat(importar): traz planos e takes de vídeo externo para o pipeline`

## Conversas em aberto

Sessões do Claude Code que tocaram este projeto nos últimos 14 dias, da mais
recente para a mais antiga. Para reabrir uma: entre na pasta indicada e rode
`claude --resume` (ou `claude --resume <id>`).

### `C:\Users\ph_re\Documents\ViralReplicator` — 31/07 17:13

- retomar: `cd "C:\Users\ph_re\Documents\ViralReplicator"` → `claude --resume 24d147a1-3716-4564-a41c-3b693540a0c8`
- **última fala do dono:** Antes de usar o ClaudeWeb.
- **última resposta do Claude:** Não peguei o que você quis dizer — a frase ficou pela metade. Mas seja qual for, a coisa útil é a mesma: garantir que o estado está salvo. Vou atualizar o `ESTADO.md`:
- últimas ações: [mcp__claude-in-chrome__computer], [Bash] Look for the downloaded file in common locations, [mcp__claude-in-chrome__computer], [Bash] Search for a recently downloaded video file, [Bash] Read the manual block of ESTADO.md

### `C:\Users\ph_re\Documents\ViralReplicator` — 30/07 23:56

- retomar: `cd "C:\Users\ph_re\Documents\ViralReplicator"` → `claude --resume 82636633-43c3-4dc1-8b8b-e435c689aa7a`
- **última fala do dono:** FAÇA UM MODELO AI PRA EU VER DE 1MIN SE TIVER TUDO CERTO PARTIMOS PARA OS 8MIN
- **última resposta do Claude:** Confirmado com número: a trilha dele fica em **-57,4 dBFS** nas pausas, com 33,4 dB de separação da voz. A nossa está em **-30,8 dBFS** com 16,9 dB — ou seja, **26 dB alto demais**. Sua percepção estava certa e é grosseira a diferença. Gerando a trilha calma d…
- últimas ações: [Bash] Generate demo 2 images, [Bash] Measure reference channel music bed level, [Bash] Generate calm focus background track, [Edit] c:\Users\ph_re\Documents\ViralReplicator\editor.py, [Edit] c:\Users\ph_re\Documents\ViralReplicator\editor.py, [Bash] Wire per-channel music and generate clips

### `C:\Users\ph_re\Desktop` — 30/07 23:56

- retomar: `cd "C:\Users\ph_re\Desktop"` → `claude --resume 2a3eebb6-d127-49d6-b951-b824a7607bd8`
- **última fala do dono:** VC VAI FAZER O PAPEL DA POSTAGEM, TEM OUTRO CLAUDE FAZENDO O VIDEO, VOU PEDIR PRA ELE SALVAR UM DOCUMENTO EM UMA PASTA TIPO VIDEO 01, DAI VC LER AS INFORMAÇÕES E PREENCHE CORRETAMENTE REMODELANDO A DESCRIÇÃO DO VIDEO DO CANAL Q ESTAMOS REMODELANDO, ENTENDEU? S…
- **última resposta do Claude:** Agora monto as três peças: o contrato, o atalho e a auto-ativação.
- últimas ações: [PowerShell] Find scripts, roteiros and outputs, [Read] C:\Users\ph_re\Documents\ViralReplicator\scripts\de_0…, [ToolSearch], [Write] c:\Users\ph_re\Documents\ViralReplicator\docs\03-pro…, [PowerShell] Check project .claude and global skills folders, [Write] c:\Users\ph_re\Documents\ViralReplicator\.claude\ski…


---

Mapa de leitura: `ESTADO.md` (onde parou) → `PLAYBOOK.md` (como se faz um
vídeo) → `CLAUDE.md` (regras que não devem voltar) → `docs/03-protocolo-publicacao.md`
(contrato produção↔postagem) → `BRIEFING-CANAL-DE.md` (o canal alemão).
