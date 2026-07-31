# PLAYBOOK — como fazer um vídeo novo

Abra o Claude Code pelo atalho **ViralReplicator - Claude** (área de trabalho) ou
pelo `ABRIR_CLAUDE.bat` na raiz. O `CLAUDE.md` desta pasta é carregado sozinho,
então a sessão nova já começa sabendo o pipeline e os erros que não devem voltar.

**Antes de qualquer coisa, leia `ESTADO.md`.** Ele diz onde o projeto parou, qual é
o próximo comando de cada vídeo e o que as outras conversas estavam fazendo. É
gerado sozinho ao fim de cada turno, então está sempre atualizado — inclusive
quando a janela anterior fechou sem aviso.

## O projeto em uma frase

Canal alemão de saúde/ciência no formato faceless, replicando o **formato** (não o
texto) do canal de referência **Think Science** (`@ThinkScienceHD`), na ordem
cronológica do catálogo dele.

## Método (definido com o dono do projeto)

Estudar o vídeo de referência como quem assiste a uma aula: aprender o **assunto**,
o **formato**, a **duração** e a **categoria**. Depois escrever roteiro **original**
em alemão, com as próprias palavras. A transcrição serve para análise, nunca como
texto-base. É o que mantém o canal fora da política de conteúdo reutilizado.

## Passo a passo de um vídeo

```bash
# 1. Estudar o que ele FALA (legenda pública -> estrutura do roteiro)
cd estudo/thinkscience
yt-dlp --skip-download --write-auto-sub --sub-lang "en.*" --sub-format vtt -o "%(id)s" <URL>
cd ../..
python estudo_canal.py estudo/thinkscience/<ID>.en.vtt

# 2. Estudar o que ele MOSTRA (frames -> folhas de contato)  <<< NÃO PULE
python estudo_frames.py <ID>            # 1 frame a cada 5s = tempo de tela real
python estudo_frames.py <ID> --planos   # conta os cortes (ritmo de edição)

# 3. Escrever o roteiro ORIGINAL em alemão -> scripts/de_NN_assunto.json
#    (o Claude escreve; ver formato em scripts/de_01_arterien.json)

# 4. Narração primeiro — ela define a duração de cada cena
python produce_video.py scripts/de_NN_assunto.json --etapa audio

# 5. Fatiar a fala em planos ancorados (o texto falado manda)
python planejar_planos.py scripts/de_NN_assunto.json --alvo 4.5 --animar-cada 4
#    -> gera scripts/de_NN_assunto.planejado.json com os planos e as âncoras.
#    O Claude preenche o campo "imagem" de cada plano — a partir das folhas
#    do passo 2, não da imaginação.

# 6. Gerar (ComfyUI precisa estar de pé: D:\ComfyUI\iniciar_comfyui.bat)
python produce_video.py scripts/de_NN_assunto.planejado.json --etapa imagens
python produce_video.py scripts/de_NN_assunto.planejado.json --etapa clipes
python produce_video.py scripts/de_NN_assunto.planejado.json --etapa montagem
```

Cada etapa é **idempotente**: só gera o que ainda não existe. Falha no meio não
custa refazer a GPU inteira.

## Decisões que já estão tomadas (não refazer a discussão)

| tema | decisão | por quê |
|---|---|---|
| Mercado | Alemanha (de-DE) | 8 concorrentes, mas nenhum faz o formato; CPM ~$5,53 |
| Ordem | cronológica do catálogo deles | o vídeo forte (cor dos olhos) é o #6, então cai depois de 5 de calibração |
| Voz | `de-DE-ConradNeural`, ritmo `+8%` | Edge-TTS neural, grátis; aprovada pelo dono |
| Duração alvo | 8 min | mediana dos hits deles é 13,2 min; 8 é o acordo atual |
| Estilo visual | **ilustração editorial clara com pessoas** (`explicativo_claro`) | ver a medição abaixo — é o estilo do vídeo de 5,75M, não o do de 14k |
| Ritmo de corte | plano de ~4,5s | eles cortam a cada ~4s (151 cortes em 598s) |
| Texto na imagem | **nunca** | difusão desenha letra como garatuja; todo texto é vetorial via ffmpeg |
| GPU por vídeo | ~55 min liberados | ~83 planos a 40s cada |

## Onde está cada coisa

```
ViralReplicator/
├── ABRIR_CLAUDE.bat        atalho da sessão
├── ESTADO.md               onde o projeto parou (gerado por hook, leia primeiro)
├── estado.py               gera o ESTADO.md a partir do disco
├── PLAYBOOK.md             este arquivo
├── CLAUDE.md               contexto carregado automaticamente na sessão
├── produce_video.py        orquestra: audio -> imagens -> clipes -> montagem
├── planejar_planos.py      fatia a fala em planos ancorados
├── editor.py               montagem: corte seco, legenda ASS, trilha com ducking
├── estudo_canal.py         o que o vídeo de referência FALA (legenda -> estrutura)
├── estudo_frames.py        o que ele MOSTRA (frames -> folhas de contato)
├── comfy_client.py         API do ComfyUI      comfy_musica.py  trilha ACE-Step
├── comfy_batch.py          thumbnails          comfy_video.py   clipes LTXV
├── scripts/                roteiros (.json)
├── workflows/              grafos do ComfyUI em formato API
├── templates/musica/       trilha (o editor usa o 1º arquivo daqui)
├── estudo/thinkscience/    catálogo, 34 legendas, estrutura_34.json
└── output/producao/<id>/   audio, imagens, clipes, legenda, vídeo final
```

Modelos ficam fora do projeto, em `D:\ComfyUI\models\` (~32GB).

## O estilo visual, medido (31/07/2026)

Amostramos os dois vídeos de referência a cada 5s e olhamos os frames. Eles usam
**duas linguagens visuais diferentes**, e a diferença de audiência é brutal:

| vídeo | views | o que aparece na tela |
|---|---|---|
| `zRMtp04VHLQ` artérias | 14 mil | 3D fotorreal escuro, quase 100% interior do corpo — túnel de artéria, hemácias, bactérias. Pessoas só num plano (mãos cortando pimenta). |
| `SnWbe1P1l3s` cor dos olhos | **5,75 milhões** | ilustração editorial clara, luz de dia, **pessoas na maioria dos planos** — rosto em close, gente no parque, cozinha com plantas, mapa-múndi. A anatomia entra como corte estilizado **dentro da cena**, nunca como túnel fotorreal. |

O preset `medico_3d` tinha sido calibrado contra o de 14k. **O que vale copiar é o
de 5,75M** → preset `explicativo_claro`, e o dicionário `ELENCO` em
`produce_video.py` mantém as mesmas pessoas descritas igual em todos os planos.

Duas ressalvas honestas:

- **Rosto consistente entre planos não é garantido.** SDXL puro gera uma pessoa
  nova a cada imagem; descrever igual chega perto, mas o mesmo rosto exigiria
  LoRA ou IP-Adapter. É o próximo upgrade se o estilo for aprovado.
- **Eles põem rótulo na tela o tempo todo** ("Retina", "90% ABSORPTION", "<1%
  POPULATION"). A gente não pode pedir isso à difusão — sai garatuja. Tem que ser
  a camada vetorial (`drawtext`), que ainda está pendente aqui embaixo.

### Como refazer isso para cada vídeo novo

O passo 2 do roteiro acima **não é opcional**. Antes de escrever qualquer prompt de
imagem, rode `estudo_frames.py` no vídeo de referência daquele assunto e abra as
folhas de contato em `output/ref_thinkscience/frames/<ID>/`. Depois responda, por
escrito, dentro do `nota_metodo` do roteiro:

1. **Que fração dos planos tem pessoa na tela?** É o número que mais muda o
   resultado. No vídeo de 5,75M é a maioria; foi por não ter medido isso que a
   primeira leva saiu 100% interior de artéria.
2. **Claro ou escuro? Ilustração ou fotorreal?**
3. **Como a anatomia entra** — corte estilizado dentro de uma cena com gente, ou
   plano fechado só dela?
4. **Que lugares e objetos reconhecíveis aparecem** (cozinha, parque, mapa,
   balança). São eles que dão o "mundo real" que o assunto sozinho não dá.

Dois modos, e eles respondem perguntas diferentes:

| comando | responde | cuidado |
|---|---|---|
| `estudo_frames.py <ID>` | **tempo de tela** — o que domina o vídeo | é o que vale para decidir estilo |
| `estudo_frames.py <ID> --planos` | **quantos cortes** e o ritmo | superdispara dentro de animação lenta: um travelling de 40s vira 30 "planos" iguais e engana |

Escolha o vídeo de referência pelo **desempenho**, não pelo assunto. Foi copiando o
vídeo errado — o de 14 mil views, só porque o assunto batia com o nosso — que o
estilo saiu escuro e sem gente.

## A camada de direção (`direcao.py`)

O roteiro pode dirigir cada plano. Tudo é opcional — o que faltar, o diretor
preenche sozinho.

```jsonc
{
  "ancora": "Es gibt kein Lebensmittel",
  "seg": 5.02,
  "imagem": "...",
  "direcao": {
    "energia": 4,                 // 0-5; sem isso vem da duração do plano
    "camera": "push_in",          // sem isso, escolha automática sem repetir eixo
    "enfase": ["nunca", "Endothel"]  // palavras que ganham destaque na legenda
  }
}
```

E no nível do roteiro: `"color_script": ["frio", "neutro", "ambar", "claro"]` —
uma grade por ato. Ato é quebrado por `"transicao": "dissolve"` numa cena.

**Câmeras executáveis:** `static`, `push_in`, `push_out`, `slow_zoom`,
`fast_zoom`, `crash_zoom`, `pan_left`, `pan_right`, `whip_pan`, `tilt_up`,
`tilt_down`, `handheld`.
Aliases que renderizam **igual** (imagem chapada não tem perspectiva para
mudar): `dolly_in`=`push_in`, `dolly_out`/`pull_back`=`push_out`,
`truck_*`=`pan_*`, `pedestal_*`=`tilt_*`.

**Grades:** `frio`, `neutro`, `quente`, `ambar`, `verde`, `claro`.

**O que NÃO existe, e por quê:** `orbit`, `drone`, `pov`, `over_shoulder` mudam
o ponto de vista — isso é prompt de imagem, não movimento. `rack_focus` e
parallax precisam de mapa de profundidade (fase seguinte). `macro` e os
enquadramentos (close, wide) são decisão de geração: escreva no prompt.

Pedir qualquer um desses **para o render**, com uma mensagem explicando o
motivo. Direção ignorada em silêncio é pior que direção ausente, porque dá a
impressão de ter sido aplicada.

### Regras que o diretor aplica sozinho

- **Nunca dois planos seguidos no mesmo eixo** (profundidade / horizontal /
  vertical / orgânico), e o sentido não repete num intervalo de três. A versão
  antiga fazia `MOVIMENTOS[i % 6]` — repetição com período fixo, que é a
  definição de slideshow.
- **Energia governa a amplitude.** Sem declaração, ela sai da duração do plano
  comparada à mediana do vídeo: plano curto é corte rápido, e taxa de corte é
  energia. Gesto forte (`crash_zoom`, `whip_pan`) é bloqueado em energia ≤ 2 e
  `static` é bloqueado em energia ≥ 4.
- **Número, porcentagem, data e unidade viram ênfase na legenda** sem precisar
  marcar nada.
- **A cor é por ato**, aplicada dentro do segmento. Grão e vinheta continuam
  num passe único no fim.

> Cuidado ao escrever expressão de câmera nova: o filtergraph do ffmpeg separa
> filtros por vírgula, então `min()`, `if()` e `pow()` quebram a cadeia inteira.
> As curvas de aceleração usam saturação algébrica (`1-1/(1+k*t)`) por isso.

## O que ainda não está resolvido

- **Rótulo técnico flutuante** (tipo "NO", "LDL" sobre a cena) ainda não implementado.
  Vai ser `drawtext` do ffmpeg, na mesma camada da legenda.
- **Anatomia**: SDXL não sabe anatomia. Prompt tem que pedir cena **abstrata ou
  fotográfica**, nunca diagrama preciso.
- **Wan 2.2 I2V** é o upgrade de qualidade dos clipes, mas é lento na RTX 3060.
  Só vale nos 3-4 momentos-chave, não no volume.

## Prompt de imagem: conceito não vira imagem (medido em 31/07)

Na produção real do `de_01_arterien`, **7 dos 43 prompts SDXL falharam**, todos
pela mesma causa: descreviam um CONCEITO em vez de um OBJETO. "Macro de membrana
celular", "corte de fígado", "camada de células" voltaram como manchas verdes
abstratas — bonitas e sem informação.

A regra já estava escrita aqui e eu mesmo a violei. Então vale reforçá-la com o
que a correção ensinou, que é mais forte que a regra original:

> Quando o assunto é um **mecanismo invisível**, o concreto não é uma versão mais
> detalhada do conceito. É **outro objeto**, do mundo que uma câmera alcança.

| batida | conceito que falhou | objeto que funcionou |
|---|---|---|
| "quanto um vaso se abre" | corte de tubo com paredes flexionando | mão abrindo uma torneira |
| "não dá para lavar o que está na parede" | escova dentro de um tubo de vidro | pano na bancada, mancha permanece **dentro** da pedra |
| "ômega-3 entra na membrana" | macro de membrana celular | macro de filé de salmão com as fibras |
| "fibra prende ácidos biliares" | corte de fígado | colher erguendo aveia encharcada, viscosa |

Dois outros modos de falha vistos na mesma leva:

- **Quebra de estilo.** Um plano voltou em cartoon vetorial chapado no meio de um
  vídeo semi-fotográfico. Ancorar com termo fotográfico (`shallow depth of
  field`, `close view`) trouxe de volta.
- **Objeto que some.** "Escova dentro de um tubo de vidro" desenhou a escova e
  não o tubo — mesma família do problema de dois sujeitos no quadro.

**Antes de gerar uma leva, releia cada prompt e pergunte: uma câmera conseguiria
filmar isto?** Se a resposta for não, o plano é vetorial ou precisa de outro
objeto.

## Pegadinha: color script é inerte sem quebra de ato

Aconteceu na produção do `de_01_arterien`: o roteiro declarava seis grades e
nenhuma cena tinha `"transicao": "dissolve"`. Resultado — **1 ato, e o vídeo
inteiro saiu com a primeira grade**. Nada falhou, nada avisou.

Os dois campos são acoplados e ficam longe um do outro no JSON:

- `color_script` (nível do roteiro) diz QUAIS grades existem;
- `"transicao": "dissolve"` (nível da cena) diz ONDE um ato termina.

**Verificação antes de montar:** se o log diz `[DIREÇÃO] 1 ato(s)` e o roteiro
declara mais de uma grade, é erro de quem escreveu — não do editor.

E a grade entra DENTRO do segmento, então corrigir os atos depois obriga a
apagar `tmp_edit/`: os segmentos em cache carregam a cor errada.

## Duração real x alvo

O `de_01_arterien` tem 14 cenas e fechou em **5min57s**, não nos 8 min do alvo
da tabela de decisões. Narração de ~6 min pede ~18 cenas nesse ritmo. Não é
defeito do pipeline — é o roteiro que foi escrito curto. Vale medir antes de
gerar: `--etapa audio` já imprime o total em minutos.
