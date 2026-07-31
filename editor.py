"""
Editor "profissional" — substitui a montagem de slideshow por uma edição com
gramática de corte, legenda queimada e trilha com ducking.

O que mudou em relação à primeira montagem, e POR QUÊ:

1. CORTE SECO É O PADRÃO. A versão anterior fazia crossfade de 0,6s em TODAS as
   18 cenas. Dissolve constante é a assinatura de slideshow — em edição narrativa
   o dissolve significa "passou tempo". Agora o corte seco é o default e o
   dissolve só acontece onde o roteiro marca `"transicao": "dissolve"`
   (flashback, volta ao presente, salto temporal).

2. PUNCH-IN NO HOOK. Os primeiros ~18s eram um plano único parado, que é onde o
   espectador desiste. Agora a cena de abertura é picada em 3 sub-planos (geral →
   médio → close) recortados da MESMA imagem, com corte seco entre eles. Dá ritmo
   sem gastar GPU.

3. KEN BURNS VARIADO. Antes era sempre zoom-in central. Agora alterna zoom in/out
   e direção de pan por cena, e mais devagar (movimento perceptível cansa).

4. LEGENDA QUEIMADA com destaque palavra por palavra, usando os timestamps do
   Edge-TTS. É o formato que segura retenção e o que o YouTube mobile exige na
   prática (a maioria assiste sem som).

5. TRILHA COM DUCKING via sidechaincompress: a música abaixa sozinha quando a
   narração fala. Mesma técnica do mix_bg_music do viral_replicator_video_engine.

6. PASSE DE ACABAMENTO (grão + vinheta) junto com a queima da legenda.

   A COR não está mais aqui: desde 31/07 a grade é aplicada por ATO, dentro de
   cada segmento (ver `direcao.GRADES`). Um vídeo inteiro com uma atmosfera só
   é o que faz parecer que ninguém dirigiu.

   Sobre a cadeia de encodes — este texto afirmava "um único encode, nada de
   re-encodar 3 vezes". Era falso, e a auditoria de 31/07 mediu: o segmento sai
   do `ken_burns` em crf 18, o concat dentro do ato é cópia, o xfade entre atos
   re-encoda em crf 19 e o acabamento re-encoda de novo. São **2 passes no
   melhor caso e 3 quando há mais de um ato** — e agora todo vídeo tem mais de
   um ato, porque o color script depende disso. Reduzir isso com intermediários
   sem perda está previsto na V3, junto do compositor.
"""

import json
import re
import subprocess
from pathlib import Path

import direcao

RAIZ = Path(__file__).parent
FFMPEG = "ffmpeg"

LARGURA, ALTURA = 1920, 1080
FPS = 30
DISSOLVE = 0.8          # só nas quebras marcadas no roteiro
AUDIO_HZ = 48000

# Teto de duração de um plano. Medido no canal de referência com detecção de
# cena: 151 cortes em 598s, ou seja um corte a cada ~4s, com 37% dos planos
# abaixo de 5s. Segurar mais que isso numa imagem é o que faz o vídeo
# automatizado parecer lento. Acima deste teto, o plano é picado em dois
# recortes da mesma imagem.
MAX_SEG_PLANO = 6.0

# ── legenda ──────────────────────────────────────────────────────────────
# Estilo resgatado do viral_replicator_video_engine/stages/stage3c_subtitles.py
# (legenda "viral" estilo CapCut/Hormozi). O que a minha versão tinha perdido:
#   1. MAIÚSCULAS — peso visual muito maior no mobile
#   2. grupos de 3 palavras / 22 chars (eu usava 5 / 34, texto demais na tela)
#   3. efeito POP: a palavra ativa cresce para 118% em 120ms e volta em 120ms
#   4. amarelo puro (&H0000FFFF) em vez de âmbar
#   5. quebra de grupo por PAUSA na fala (> 0,6s), não só por contagem
#   6. Bold real (-1) + sombra 2 + fundo semitransparente
FONTE = "Arial Black"
CORPO = 78
MARGEM_V = 110
MAX_PALAVRAS_BLOCO = 3
MAX_CHARS_BLOCO = 22
PAUSA_QUEBRA = 0.6      # pausa na fala que force quebra de grupo

DESTAQUE = r"{\c&H0000FFFF&\t(0,120,\fscx118\fscy118)\t(120,240,\fscx100\fscy100)}"
# Palavra que carrega o DADO (número, porcentagem, data, unidade) ou que o
# roteiro marcou em `direcao.enfase`. O canal de referência reforça o número na
# tela o tempo todo; aqui isso sai na camada vetorial, sem depender da difusão
# desenhar texto — que é justamente o que ela faz mal.
DESTAQUE_FORTE = r"{\c&H0000FFFF&\b1\t(0,140,\fscx140\fscy140)\t(140,320,\fscx100\fscy100)}"
# Mesmo quando não é a palavra corrente, o dado fica em negrito: o olho acha o
# número antes de a narração chegar nele.
DADO = r"{\b1}"
RESET = r"{\r}"

# ── trilha ───────────────────────────────────────────────────────────────
DIR_MUSICA = RAIZ / "templates" / "musica"
# Nível ALVO da cama, não ganho relativo. Ganho relativo é armadilha: a trilha
# gerada saiu com média -26,6 dBFS e um volume=0.22 por cima jogou a música para
# -45 dBFS, inaudível. Normalizar para um alvo fixo torna o resultado igual
# independente do arquivo que estiver em templates/musica/.
# Medido no canal de referência: o bed dele fica em -57 dBFS nas pausas, com
# 33 dB de separação da fala. Com MUSICA_LUFS=-26 a nossa cama saía em -31 dBFS,
# 26 dB alto demais — a trilha competia com a narração em vez de sustentá-la.
# -42 põe a cama na faixa de "quase não se percebe, mas faz falta se tirar".
MUSICA_LUFS = -42
# ratio baixo e release curto: com ratio 9 + release 450ms a música não voltava
# nas pausas de 0,35s entre cenas e o ducking virava mute.
DUCK = dict(threshold=0.05, ratio=4, attack=15, release=250)

# ── acabamento ───────────────────────────────────────────────────────────
# Só o acabamento fica global. A COR saiu daqui e foi para `direcao.GRADES`,
# aplicada por ato dentro de cada segmento — um vídeo inteiro com uma atmosfera
# só é o que faz parecer que ninguém dirigiu. Grão e vinheta continuam num
# passe único no fim, junto com a queima da legenda, para não empilhar perda.
LOOK = "vignette=PI/5,noise=alls=5:allf=t+u"


def _run(cmd, desc):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{desc} falhou:\n{r.stderr[-1800:]}")
    return r


def _p(msg):
    import sys
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


# ─────────────────────────────────────────────────────────────────────────
#  LEGENDA ASS com destaque por palavra
# ─────────────────────────────────────────────────────────────────────────

CABECALHO_ASS = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LARGURA}
PlayResY: {ALTURA}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Viral,{FONTE},{CORPO},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,5,2,2,80,80,{MARGEM_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts_ass(t):
    t = max(t, 0)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):d}:{int(m):02d}:{s:05.2f}"


def _limpar(txt: str) -> str:
    """Chaves e barra invertida são sintaxe de tag no ASS — têm que sair."""
    return txt.strip().replace("{", "").replace("}", "").replace("\\", "")


def coletar_palavras(audios) -> list:
    """Achata todas as cenas numa lista única de palavras com tempo absoluto.

    Usa o token do texto original (com pontuação) em vez do texto do evento
    WordBoundary, que vem sem pontuação.
    """
    todas, offset = [], 0.0
    for cena, _wav, dur, palavras in audios:
        tokens = cena["narracao"].split()
        usar_original = len(tokens) == len(palavras)
        for i, w in enumerate(palavras):
            txt = _limpar(tokens[i] if usar_original else w["p"])
            if txt:
                todas.append({"txt": txt,
                              "ini": offset + w["ini"],
                              "fim": offset + w["fim"]})
        offset += dur
    return todas


def agrupar_palavras(palavras: list) -> list:
    """Grupos curtos estilo CapCut. Quebra por contagem, por largura OU por
    pausa na fala — a pausa é o que faz a legenda respirar junto com a narração
    em vez de cortar no meio da frase."""
    grupos, atual = [], []
    for w in palavras:
        if atual:
            chars = sum(len(x["txt"]) + 1 for x in atual) + len(w["txt"])
            pausa = w["ini"] - atual[-1]["fim"]
            if (len(atual) >= MAX_PALAVRAS_BLOCO
                    or chars > MAX_CHARS_BLOCO
                    or pausa > PAUSA_QUEBRA):
                grupos.append(atual)
                atual = []
        atual.append(w)
    if atual:
        grupos.append(atual)
    return grupos


def escrever_ass(audios, dest: Path) -> Path:
    """Um Dialogue por palavra ativa: o grupo inteiro fica visível e a palavra
    corrente recebe amarelo + pop (118% em 120ms, volta em 120ms).

    Um evento por palavra em vez da tag \\k porque o suporte a \\k no libass
    varia por versão, e o pop escalado dá leitura melhor que o wipe do karaokê.
    """
    # Palavras marcadas à mão no roteiro. O conjunto é do vídeo inteiro, não por
    # cena: se uma palavra merece destaque, merece em toda aparição — e assim a
    # marcação não precisa ser repetida plano a plano.
    enfase = set()
    for cena, *_ in audios:
        for p in cena.get("planos") or []:
            for w in (p.get("direcao") or {}).get("enfase") or []:
                enfase.add(str(w).strip().lower())

    grupos = agrupar_palavras(coletar_palavras(audios))
    eventos, n_fortes = [], 0
    for grupo in grupos:
        fim_grupo = grupo[-1]["fim"]
        fortes = [direcao.merece_enfase(w["txt"], enfase) for w in grupo]
        n_fortes += sum(fortes)
        for i, alvo in enumerate(grupo):
            ini = alvo["ini"]
            # ativa até a próxima começar — evita piscada entre palavras
            fim = grupo[i + 1]["ini"] if i + 1 < len(grupo) else fim_grupo
            if fim <= ini:
                fim = ini + 0.05
            partes = []
            for j, w in enumerate(grupo):
                txt = w["txt"].upper()
                if j == i:
                    partes.append(f"{DESTAQUE_FORTE if fortes[j] else DESTAQUE}{txt}{RESET}")
                elif fortes[j]:
                    partes.append(f"{DADO}{txt}{RESET}")
                else:
                    partes.append(txt)
            eventos.append(
                f"Dialogue: 0,{_ts_ass(ini)},{_ts_ass(fim)},Viral,,0,0,0,," + " ".join(partes)
            )
    dest.write_text(CABECALHO_ASS + "\n".join(eventos) + "\n", encoding="utf-8")
    _p(f"[LEGENDA] {len(grupos)} grupos / {len(eventos)} eventos ASS "
       f"(maiúsculas + pop, {n_fortes} palavra(s) com ênfase)")
    return dest


def escrever_srt(audios, dest: Path) -> Path:
    """SRT agrupado para subir como CC no YouTube. Aqui SEM maiúsculas: o
    all-caps é escolha visual da legenda queimada, mas em CC atrapalha leitura
    e é sinalizado como grito por leitores de tela."""
    def ts(t):
        h, r = divmod(max(t, 0), 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")

    grupos = agrupar_palavras(coletar_palavras(audios))
    partes = []
    for i, g in enumerate(grupos, 1):
        partes.append(f"{i}\n{ts(g[0]['ini'])} --> {ts(g[-1]['fim'])}\n"
                      + " ".join(w["txt"] for w in g) + "\n")
    dest.write_text("\n".join(partes), encoding="utf-8")
    return dest


# ─────────────────────────────────────────────────────────────────────────
#  SEGMENTOS
# ─────────────────────────────────────────────────────────────────────────

# (zoom_final, x_ini→x_fim, y_ini→y_fim) — 6 movimentos que se alternam por cena
def ken_burns(img: Path, dur: float, saida: Path, camera: str = "push_in",
              forca: float = 0.085, recorte: float = 1.0, grade: str = "neutro"):
    """Renderiza um plano estático com a câmera e a grade que o diretor mandou.

    O vocabulário de câmera e as expressões do zoompan vivem em `direcao.py`;
    aqui só se executa. A grade entra NESTE ponto, e não num passe global no
    fim, porque cada segmento já re-encoda — colorir por ato sai de graça e é o
    que dá identidade visual a cada parte do vídeo. O acabamento (grão +
    vinheta) continua sendo um passe único no final.
    """
    frames = max(int(dur * FPS), 2)
    z, x, y = direcao.expressoes(camera, frames, forca)
    # recorte > 1 fecha o enquadramento na mesma imagem (sub-plano mais fechado)
    lado_w = int(LARGURA * 2 / recorte) // 2 * 2
    lado_h = int(ALTURA * 2 / recorte) // 2 * 2
    vf = (
        f"scale={LARGURA * 2}:{ALTURA * 2}:force_original_aspect_ratio=increase,"
        f"crop={lado_w}:{lado_h},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={LARGURA}x{ALTURA}:fps={FPS},"
        f"{direcao.GRADES.get(grade, direcao.GRADES['neutro'])},setsar=1"
    )
    _run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-i", str(img), "-vf", vf,
          "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
          "-pix_fmt", "yuv420p", str(saida)], f"ken burns {img.name}")


def punch_in(img: Path, dur: float, saida: Path, tmp: Path, cortes=None, grade="neutro"):
    """Pica uma imagem em N sub-planos (geral → médio → close) com corte seco.
    Usado no hook: plano único de 18s é onde o espectador vaza.

    Cada degrau alterna a câmera para o punch não virar uma escada de zooms
    iguais — a mesma regra de alternância que vale no resto do vídeo.
    """
    import math
    cortes = cortes or max(3, min(math.ceil(dur / MAX_SEG_PLANO), 5))
    escalas = [1.0, 1.15, 1.32, 1.50, 1.68][:cortes]
    alternancia = ["push_in", "static", "pan_right", "push_in", "tilt_down"]
    partes, fatia = [], dur / cortes
    for i, esc in enumerate(escalas):
        p = tmp / f"{saida.stem}_pi{i}.mp4"
        ken_burns(img, fatia, p, camera=alternancia[i % len(alternancia)],
                  forca=0.05, recorte=esc, grade=grade)
        partes.append(p)
    concat_seco(partes, saida, tmp)


def _normalizar(txt: str) -> list:
    """Tokens minúsculos e sem pontuação/acento, para casar âncora com fala."""
    import unicodedata
    t = unicodedata.normalize("NFD", txt.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", t)


def _achar_frase(tokens: list, alvo: list, a_partir=0):
    """Índice do token onde a frase-âncora começa. None se não achar.

    Casamento exato primeiro; se falhar, tenta o maior prefixo da âncora — a
    narração pode ter sido editada depois que a âncora foi escrita, e é melhor
    cortar perto do lugar certo do que voltar para a divisão em fatias iguais.
    """
    if not alvo:
        return None
    for tam in range(len(alvo), 1, -1):
        pedaco = alvo[:tam]
        for i in range(a_partir, len(tokens) - tam + 1):
            if tokens[i:i + tam] == pedaco:
                return i
    return None


def cortes_ancorados(cena: dict, palavras: list, dur: float, n: int) -> list:
    """Duração de cada plano DENTRO da cena, cortando na palavra falada.

    Cada plano do roteiro pode trazer `"ancora": "trecho exato da narração"`.
    O corte acontece no instante em que aquele trecho começa a ser dito, em vez
    de dividir a cena em n fatias iguais — que é o que fazia a imagem trocar no
    meio de uma frase, desencontrada do que a narração estava falando.

    Sem âncora (ou âncora não encontrada), cai na divisão proporcional.
    """
    iguais = [dur / n] * n
    planos = cena.get("planos") or []
    ancoras = [(p or {}).get("ancora", "") for p in planos][:n]
    if len(ancoras) < n or not any(ancoras[1:]):
        return iguais

    tokens = _normalizar(cena["narracao"])
    if len(tokens) != len(palavras):
        # tokenização divergiu do WordBoundary; sem correspondência 1:1 o
        # índice não vira tempo confiável
        return iguais

    inicios, cursor = [0.0], 0
    for a in ancoras[1:]:
        idx = _achar_frase(tokens, _normalizar(a), cursor)
        if idx is None or idx <= cursor:
            inicios.append(None)
        else:
            inicios.append(float(palavras[idx]["ini"]))
            cursor = idx

    # preenche os não encontrados espalhando entre os vizinhos conhecidos
    for i, v in enumerate(inicios):
        if v is not None:
            continue
        ant = next((inicios[j] for j in range(i - 1, -1, -1) if inicios[j] is not None), 0.0)
        prox = next((inicios[j] for j in range(i + 1, len(inicios)) if inicios[j] is not None), dur)
        inicios[i] = ant + (prox - ant) / 2

    # monotônico e dentro da cena, com no mínimo 1,2s por plano
    limpos = [0.0]
    for v in inicios[1:]:
        limpos.append(min(max(v, limpos[-1] + 1.2), dur - 1.2))
    duracoes = [limpos[i + 1] - limpos[i] for i in range(n - 1)] + [dur - limpos[-1]]
    if any(d < 0.5 for d in duracoes):
        return iguais
    return duracoes


def multi_plano(imagens, dur: float, saida: Path, tmp: Path, direcoes=None,
                duracoes=None, grade="neutro"):
    """Divide a cena entre N planos DIFERENTES com corte seco.

    É o que separa vídeo automatizado de edição de verdade: dentro de um plano
    de 20s, imagem única só com zoom denuncia. Cada sub-plano executa a direção
    que `direcao.dirigir()` já resolveu para ele — inclusive a regra de nunca
    repetir o eixo do movimento anterior.
    """
    duracoes = duracoes or [dur / len(imagens)] * len(imagens)
    direcoes = direcoes or [{}] * len(imagens)
    partes = []
    for i, img in enumerate(imagens):
        d = duracoes[i]
        dir_i = direcoes[i] if i < len(direcoes) else {}
        cam = dir_i.get("camera", "push_in")
        forca = dir_i.get("forca", 0.085)
        # Plano longo demais vira 2 sub-planos da MESMA imagem, em recortes
        # diferentes (geral -> fechado), com corte seco entre eles. O canal de
        # referência corta a cada ~4s; segurar 12s numa imagem é o que faz o
        # nosso parecer lento. Isso dobra o número de cortes sem gerar imagem
        # nova, que é onde está o custo de GPU.
        if d > MAX_SEG_PLANO:
            metade = d / 2
            # o segundo pedaço troca de eixo, senão o corte fica invisível
            segundo = direcao.contraste_de(cam)
            for k, (esc, c) in enumerate(((1.0, cam), (1.22, segundo))):
                p = tmp / f"{saida.stem}_mp{i}_{k}.mp4"
                ken_burns(img, metade, p, camera=c, forca=forca, recorte=esc, grade=grade)
                partes.append(p)
        else:
            p = tmp / f"{saida.stem}_mp{i}.mp4"
            ken_burns(img, d, p, camera=cam, forca=forca, grade=grade)
            partes.append(p)
    concat_seco(partes, saida, tmp)


def segmento_clipe(clip: Path, dur: float, saida: Path, tmp: Path, direcoes=None,
                   extras=None, duracoes=None, grade="neutro"):
    """Clipe LTXV em velocidade natural, depois corta para os planos extras da
    cena (se houver) ou continua no último frame do clipe.

    Esticar o clipe para cobrir a cena inteira daria 4x de slow motion e
    travaria; e continuar no último frame do clipe emenda invisível, porque é
    literalmente o mesmo frame.
    """
    from comfy_video import FPS as CLIP_FPS
    dur_clip = 121 / CLIP_FPS
    # a grade do ato entra também no clipe: sem isso o ato fica com duas cores,
    # porque as imagens estáticas já saem coloridas do ken_burns
    escala = (f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
              f"crop={LARGURA}:{ALTURA},fps={FPS},"
              f"{direcao.GRADES.get(grade, direcao.GRADES['neutro'])},setsar=1")
    if dur <= dur_clip + 0.3:
        _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(clip), "-vf", escala, "-an",
              "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
              "-pix_fmt", "yuv420p", str(saida)], "clipe curto")
        return
    a = tmp / f"{saida.stem}_a.mp4"
    _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(clip), "-vf", escala, "-an",
          "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
          str(a)], "clipe parte A")

    resto = dur - dur_clip
    b = tmp / f"{saida.stem}_b.mp4"
    if extras:
        # o clipe ocupa o 1º plano; as âncoras dos planos seguintes viram os
        # cortes de dentro do resto da cena
        durs_extras = None
        if duracoes and len(duracoes) == len(extras) + 1:
            sobra = [d for d in duracoes[1:]]
            fator = resto / sum(sobra) if sum(sobra) > 0 else 1.0
            durs_extras = [d * fator for d in sobra]
        multi_plano(list(extras), resto, b, tmp,
                    direcoes=(direcoes or [])[1:], duracoes=durs_extras, grade=grade)
    else:
        ult = tmp / f"{saida.stem}_last.png"
        # o último frame já sai graduado pela `escala`; o ken_burns aplicaria a
        # grade de novo, então aqui ele recebe a neutra para não dobrar
        _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(clip), "-vf", escala,
              "-update", "1", str(ult)], "ultimo frame")
        seguinte = (direcoes or [{}])[0].get("camera") if direcoes else None
        ken_burns(ult, resto, b, camera=direcao.contraste_de(seguinte or "push_in"),
                  forca=0.06, grade="neutro")
    concat_seco([a, b], saida, tmp)


def concat_seco(partes, saida: Path, tmp: Path):
    """Corte seco de verdade: concat demuxer com stream copy quando possível."""
    lista = tmp / f"{saida.stem}_lista.txt"
    lista.write_text("\n".join(f"file '{p.as_posix()}'" for p in partes), encoding="utf-8")
    _run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
          "-c", "copy", str(saida)], f"concat {saida.name}")


# ─────────────────────────────────────────────────────────────────────────
#  TRILHA
# ─────────────────────────────────────────────────────────────────────────

def achar_musica(subpasta: str = "") -> Path | None:
    """Trilha do canal. `subpasta` vem do roteiro (campo "musica"), para que
    cada canal tenha a sua — o bed de um canal de saúde não é o mesmo de um
    canal de história dark."""
    for d in ([DIR_MUSICA / subpasta] if subpasta else []) + [DIR_MUSICA]:
        if not d.exists():
            continue
        for ext in ("*.mp3", "*.wav", "*.flac", "*.m4a", "*.ogg"):
            achados = sorted(d.glob(ext))
            if achados:
                return achados[0]
    return None


def mixar(narracao: Path, musica: Path | None, dur_total: float, saida: Path) -> Path:
    """Narração + trilha com ducking. Sem trilha, só copia a narração."""
    if musica is None:
        _p("[TRILHA] nenhum arquivo em templates/musica/ — saindo só com narração")
        _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(narracao),
              "-ar", str(AUDIO_HZ), "-ac", "2", str(saida)], "audio sem trilha")
        return saida

    d = DUCK
    filtro = (
        # trilha: loop até cobrir o vídeo, normalizada para o alvo fixo da cama
        f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{dur_total + 1:.2f},"
        f"aformat=sample_fmts=fltp:sample_rates={AUDIO_HZ}:channel_layouts=stereo,"
        f"loudnorm=I={MUSICA_LUFS}:TP=-6:LRA=7[mus];"
        # voz: highpass corta ronco abaixo de 85Hz; asplit manda uma cópia
        # como chave lateral do compressor
        f"[0:a]aformat=sample_fmts=fltp:sample_rates={AUDIO_HZ}:channel_layouts=stereo,"
        f"highpass=f=85,asplit=2[voz][chave];"
        f"[mus][chave]sidechaincompress=threshold={d['threshold']}:ratio={d['ratio']}"
        f":attack={d['attack']}:release={d['release']}[mus_duck];"
        # normalize=0: sem isso o amix divide tudo pelo nº de entradas e derruba
        # a cama de novo. Aqui os níveis já vêm calibrados, então só somamos.
        f"[voz][mus_duck]amix=inputs=2:duration=first:normalize=0,"
        f"alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[out]"
    )
    _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(narracao), "-i", str(musica),
          "-filter_complex", filtro, "-map", "[out]",
          "-ar", str(AUDIO_HZ), "-ac", "2", str(saida)], "mix com ducking")
    _p(f"[TRILHA] {musica.name} com ducking (sidechaincompress)")
    return saida


# ─────────────────────────────────────────────────────────────────────────
#  MONTAGEM
# ─────────────────────────────────────────────────────────────────────────

def montar(roteiro: dict, audios: list, imagens: dict, clipes: dict, base: Path) -> Path:
    tmp = base / "tmp_edit"
    tmp.mkdir(parents=True, exist_ok=True)

    # A direção vem antes de qualquer pixel. `validar` para o render se o
    # roteiro pedir algo que não tem execução — direção ignorada em silêncio é
    # pior que direção ausente, porque dá a impressão de que foi aplicada.
    erros = direcao.validar(roteiro)
    if erros:
        raise RuntimeError("direção inválida:\n  - " + "\n  - ".join(erros))
    direcao.dirigir(roteiro)

    # cenas que ABREM com dissolve => a cena anterior precisa de folga
    abre_dissolve = {c["n"] for c in roteiro["cenas"] if c.get("transicao") == "dissolve"}
    ns = [c["n"] for c in roteiro["cenas"]]
    precisa_folga = {ns[i] for i in range(len(ns) - 1) if ns[i + 1] in abre_dissolve}

    # o ato de cada cena precisa ser conhecido ANTES de renderizar, porque a
    # grade entra dentro do segmento
    ato_da_cena, ato = {}, 0
    for k, n in enumerate(ns):
        if n in abre_dissolve and k > 0:
            ato += 1
        ato_da_cena[n] = ato
    grades = direcao.grade_dos_atos(ato + 1, roteiro)
    _p(f"[DIREÇÃO] {ato + 1} ato(s), color script: {' -> '.join(grades)}")

    segmentos = []
    for i, (cena, _wav, dur, palavras) in enumerate(audios):
        n = cena["n"]
        ultimo = i == len(audios) - 1
        folga = 1.0 if ultimo else (DISSOLVE if n in precisa_folga else 0.0)
        dur_seg = dur + folga
        seg = tmp / f"seg_{n:02d}.mp4"
        grade = grades[ato_da_cena.get(n, 0)]
        dirs = [p.get("direcao", {}) for p in (cena.get("planos") or [])]
        if not seg.exists():
            planos = imagens.get(n, [])
            durs = cortes_ancorados(cena, palavras, dur_seg, len(planos)) if planos else []
            if cena.get("punch_in") and planos:
                punch_in(planos[0], dur_seg, seg, tmp, grade=grade)
            elif n in clipes:
                segmento_clipe(clipes[n], dur_seg, seg, tmp, direcoes=dirs,
                               extras=planos[1:], duracoes=durs, grade=grade)
            elif len(planos) > 1:
                multi_plano(planos, dur_seg, seg, tmp, direcoes=dirs,
                            duracoes=durs, grade=grade)
            elif planos:
                d0 = dirs[0] if dirs else {}
                ken_burns(planos[0], dur_seg, seg, camera=d0.get("camera", "push_in"),
                          forca=d0.get("forca", 0.085), grade=grade)
            else:
                raise RuntimeError(f"cena {n} sem imagem nem clipe")
            if len(planos) > 1 and durs:
                _p(f"    cena {n:02d}: cortes em {[round(sum(durs[:k+1]), 1) for k in range(len(durs) - 1)]}s")
        segmentos.append((n, seg, dur))

    # 1) atos: sequências de corte seco, concatenadas sem re-encode
    atos, atual = [], []
    for n, seg, dur in segmentos:
        if n in abre_dissolve and atual:
            atos.append(atual); atual = []
        atual.append((n, seg, dur))
    if atual:
        atos.append(atual)
    _p(f"[EDICAO] {len(segmentos)} planos em {len(atos)} atos "
       f"(corte seco dentro do ato, dissolve entre atos: {sorted(abre_dissolve) or 'nenhum'})")

    arqs_ato = []
    for idx, ato in enumerate(atos):
        a = tmp / f"ato_{idx:02d}.mp4"
        if not a.exists():
            concat_seco([s for _, s, _ in ato], a, tmp)
        arqs_ato.append((a, sum(d for _, _, d in ato)))

    # 2) dissolve entre atos
    video_mudo = base / "video_mudo.mp4"
    if not video_mudo.exists():
        if len(arqs_ato) == 1:
            arqs_ato[0][0].replace(video_mudo)
        else:
            entradas, filtro, atualr, off = [], [], "0:v", 0.0
            for a, _ in arqs_ato:
                entradas += ["-i", str(a)]
            for i in range(1, len(arqs_ato)):
                off += arqs_ato[i - 1][1]
                rot = f"v{i}"
                filtro.append(
                    f"[{atualr}][{i}:v]xfade=transition=fade:duration={DISSOLVE}"
                    f":offset={off:.3f}[{rot}]")
                atualr = rot
            filtro.append(f"[{atualr}]null[vout]")
            _run([FFMPEG, "-y", "-loglevel", "error", *entradas,
                  "-filter_complex", ";".join(filtro), "-map", "[vout]",
                  "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                  "-pix_fmt", "yuv420p", "-r", str(FPS), str(video_mudo)], "dissolve entre atos")

    # 3) áudio: concatena as faixas das cenas, normaliza, depois mistura trilha
    dur_total = sum(d for _, _, d in segmentos)
    narracao = base / "narracao.wav"
    if not narracao.exists():
        lista = tmp / "faixas.txt"
        lista.write_text("\n".join(f"file '{w.as_posix()}'" for _, w, _, _ in audios),
                         encoding="utf-8")
        cru = tmp / "narracao_cru.wav"
        _run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
              "-i", str(lista), "-c", "copy", str(cru)], "concat narracao")
        _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(cru),
              "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
              "-ar", str(AUDIO_HZ), "-ac", "1", str(narracao)], "loudnorm narracao")
        _p(f"[AUDIO] narracao.wav montada ({dur_total / 60:.2f} min, -14 LUFS)")

    audio_final = base / "audio_final.wav"
    if not audio_final.exists():
        mixar(narracao, achar_musica(roteiro.get("musica", "")), dur_total, audio_final)

    # 4) legenda + acabamento + mux, num único encode
    ass = escrever_ass(audios, base / "legenda.ass")
    escrever_srt(audios, base / "legenda.srt")   # CC para upload no YouTube
    final = base / f"{roteiro['id']}_FINAL.mp4"
    ass_ff = ass.as_posix().replace(":", "\\:")
    vf = f"{LOOK},ass='{ass_ff}'"
    _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(video_mudo), "-i", str(audio_final),
          "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "19",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
          "-ar", str(AUDIO_HZ), "-ac", "2",
          # faststart: move o moov atom pro início; player web começa a tocar
          # sem baixar o arquivo inteiro (detalhe herdado do stage4 antigo)
          "-movflags", "+faststart", "-shortest", str(final)],
         "acabamento + legenda + mux")
    _p(f"[FINAL] {final}")
    return final
