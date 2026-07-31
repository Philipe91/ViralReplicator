# ESTADO — onde o projeto parou

_Gerado automaticamente em 31/07/2026 10:23 por `estado.py`. Não edite fora do bloco manual._

**Se você é uma sessão nova do Claude: leia este arquivo primeiro.** Ele diz
o que já está no disco, o que a última conversa estava fazendo e qual é o
próximo comando. Depois leia `PLAYBOOK.md` (como se faz) e `CLAUDE.md` (as
regras que já custaram retrabalho).

## O que fazer agora

<!-- MANUAL:INICIO -->
> Este bloco é o único escrito à mão. Tudo fora dele é regerado do disco e
> qualquer edição se perde. Aqui vai a **intenção**: o próximo passo e o que
> está travado esperando decisão.

**Onde estamos:** o dono pediu um **demo de 1 minuto** (`de_demo2_arterien`) para
aprovar a arquitetura nova antes de gastar GPU no vídeo de 8 minutos. Foi a última
coisa pedida, em 30/07 23:41: _"FAÇA UM MODELO AI PRA EU VER DE 1MIN SE TIVER TUDO
CERTO PARTIMOS PARA OS 8MIN"_.

O demo2 foi entregue às 00:16 e ele **aprovou o formato, mas reprovou as imagens**:
"muito interna do corpo humano, temos que misturar imagens de pessoas". Pediu
também **dois vídeos de teste, um em alemão e um em pt-BR, mesma voz**.

**Virada de estilo (31/07 00:35) — a maior descoberta até aqui.** Amostrando os
frames dos dois vídeos de referência descobrimos que o preset `medico_3d` tinha
copiado o vídeo ERRADO: o de artérias, 14 mil views, escuro e 100% interior do
corpo. O vídeo que estourou (5,75 milhões, cor dos olhos) é **ilustração editorial
clara com pessoas na maioria dos planos**. Criado o preset `explicativo_claro` +
`ELENCO`, e o `estudo_frames.py` virou etapa 2 obrigatória do PLAYBOOK.

**Os dois testes foram entregues às 00:42** — `de_demo3_arterien` e
`br_demo3_arterias`, 45s cada. Usam `de-DE-FlorianMultilingualNeural` (voz
multilíngue, a MESMA identidade vocal nos dois idiomas) e **as mesmas imagens**,
copiadas de um para o outro, de modo que a única variável do teste é o idioma.

**Camada de direção entregue (31/07 09:30) — `direcao.py`.** O editor deixou de
sortear movimento por índice (`MOVIMENTOS[i % 6]`, que era repetição de período
fixo) e passou a executar uma direção declarada por plano: 12 câmeras reais,
energia 0–5 governando amplitude, regra anti-repetição por eixo, color script por
ato e ênfase automática em número/data/porcentagem na legenda. Vocabulário
fechado e **validado** — pedir `orbit` para o render com explicação, em vez de ser
ignorado em silêncio. Documentado no PLAYBOOK. Fases seguintes acordadas, ainda
não feitas: profundidade (parallax + rack focus), motion graphics e B-roll real.

**Esperando decisão do dono:**
1. **Qual voz no português:** Florian multilíngue (mesma voz do alemão, pode deixar
   sotaque) ou `pt-BR-AntonioNeural` (nativo, mas outra pessoa). Amostras enviadas.
2. **Aprovar o estilo `explicativo_claro`** nos dois demos.
3. **Nível da trilha** — ver a medição abaixo.
4. **Impressum** do canal alemão (falta o endereço) — trava a descrição definitiva
   do canal. Ver `docs/03-protocolo-publicacao.md` §6.

**Defeito conhecido do estilo novo — 5 dos 8 planos.** Todo prompt que pediu
"pessoa **+** corte anatômico no mesmo quadro" perdeu o corte: o SDXL trata como
uma cena só e descarta o elemento mais fraco. Planos 3, 5, 7 e 8 ficaram só com a
pessoa/cenário; o plano 4 perdeu a bifurcação da trilha. O plano 6, que era
anatomia pura, virou padrão abstrato porque o prompt era conceitual demais
("uma fileira ordenada de células arredondadas").

Correção proposta, **ainda não aplicada, esperando o ok**:
1. **Alternar planos** — um com pessoa, o seguinte só com anatomia — em vez de
   empilhar os dois no mesmo quadro. O ritmo de 4,5s já favorece a alternância.
2. **Descrever a anatomia como objeto concreto** ("um tubo cortado ao meio,
   mostrando o forro interno"), não como conceito.
O canal de referência combina os dois no mesmo quadro sem problema, mas as
ilustrações deles são feitas à mão; com difusão, separar é o que funciona.

Rosto consistente entre planos saiu melhor que o esperado (a mulher de jaqueta
azul se manteve), mas segue sem garantia sem LoRA/IP-Adapter.

**Calibração da trilha (medida no demo, 31/07):** `editor.py` foi de
`MUSICA_LUFS=-26` para `-42` em 30/07 23:52. Resultado medido no mix final: cama a
**-43,2 dBFS** nas pausas, **25,6 dB** abaixo da voz — contra -30,8 dBFS / 16,9 dB
antes. Ganhou 9 dB de separação, mas o canal de referência fica a **-57 dBFS com
33 dB**, ou seja ainda estamos ~14 dB acima dele. O `-42` foi meio-termo escolhido,
não o valor medido da referência. Para colar na referência seria `MUSICA_LUFS ≈ -56`.
<!-- MANUAL:FIM -->

## Vídeos

| id | cenas | narração | imagens | clipes | montagem | publicação | próxima ação |
|---|---|---|---|---|---|---|---|
| `br_demo3_arterias` | 2 | ✅ 2/2 | ✅ 8/8 | ✅ 2/2 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `casa_da_mae` | 18 | ✅ 18/18 | ✅ 39/18 | ✅ 8/7 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `de_01_arterien` | 14 | ✅ 14/14 | ⬜ 0/55 | ⬜ 0/14 | ⬜ | ⬜ | `python produce_video.py scripts/de_01_arterien.json --etapa imagens`  (ComfyUI de pé) |
| `de_01_augenfarbe` | 16 | ⬜ 0/16 | ⬜ 0/33 | ⬜ 0/7 | ⬜ | ⬜ | `python produce_video.py scripts/de_01_augenfarbe.json --etapa audio` |
| `de_demo2_arterien` | 2 | ✅ 2/2 | ✅ 8/8 | ✅ 2/2 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `de_demo3_arterien` | 2 | ✅ 2/2 | ✅ 8/8 | ✅ 2/2 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |
| `de_demo_arterien` | 3 | ✅ 3/3 | ✅ 6/6 | ✅ 1/1 | ✅ final | ⬜ | vídeo montado — falta thumb + `PRONTO.json` |

- `br_demo3_arterias` → vídeo final: `output\producao\br_demo3_arterias\br_demo3_arterias_FINAL.mp4` (28 MB)
- `casa_da_mae` → vídeo final: `output\producao\casa_da_mae\casa_da_mae_FINAL.mp4` (159 MB)
- `de_demo2_arterien` → vídeo final: `output\producao\de_demo2_arterien\de_demo2_arterien_FINAL.mp4` (36 MB)
- `de_demo3_arterien` → vídeo final: `output\producao\de_demo3_arterien\de_demo3_arterien_FINAL.mp4` (27 MB)
- `de_demo_arterien` → vídeo final: `output\producao\de_demo_arterien\de_demo_arterien_FINAL.mp4` (49 MB)

## Serviços e repositório

- **ComfyUI** (`127.0.0.1:8188`): 🟢 no ar
- **git**: ramo `fix/saneamento-minimo`, 6 arquivo(s) não commitado(s)
- último commit: `9d2d6b52 feat(continuidade): ESTADO.md gerado por hook para nenhuma sessão perder o fio`

## Conversas em aberto

Sessões do Claude Code que tocaram este projeto nos últimos 14 dias, da mais
recente para a mais antiga. Para reabrir uma: entre na pasta indicada e rode
`claude --resume` (ou `claude --resume <id>`).

### `C:\Users\ph_re\Documents\ViralReplicator` — 31/07 10:23

- retomar: `cd "C:\Users\ph_re\Documents\ViralReplicator"` → `claude --resume 24d147a1-3716-4564-a41c-3b693540a0c8`
- **última fala do dono:** A auditoria foi excelente. Concordo com sua análise e principalmente com o ponto mais importante: O VisualBrain não pertence ao editor. Ele pertence antes da geração de assets. Sua observação mudou completamente minha visão da arquitetura. Quero evoluir o proj…
- **última resposta do Claude:** Vou atuar como arquiteto e discordar onde acho que devo. Três das suas propostas eu acho que **pioram** o sistema, e uma peça crítica está faltando no desenho. --- ## 1 — O que está certo e muda o projeto para melhor **"Um plano é uma composição, não uma image…
- últimas ações: [Edit] C:\Users\ph_re\Documents\ViralReplicator\ESTADO.md, [Bash] Measure module sizes and find duplicated functions, [Bash] Inspect produce_video main and montage selection, [Bash] Find idle constants and count encode passes, [Bash] Check which features roteiros actually use and verify…, [Bash] Check which roteiro fields are actually read by code

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
