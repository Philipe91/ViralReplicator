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

6. PASSE DE ACABAMENTO (grade + grão + vinheta) junto com a queima da legenda,
   num único encode — nada de re-encodar 3 vezes e empilhar perda.
"""

import json
import re
import subprocess
from pathlib import Path

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
LOOK = "eq=contrast=1.06:saturation=1.04:gamma=0.98,vignette=PI/5,noise=alls=5:allf=t+u"


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
    grupos = agrupar_palavras(coletar_palavras(audios))
    eventos = []
    for grupo in grupos:
        fim_grupo = grupo[-1]["fim"]
        for i, alvo in enumerate(grupo):
            ini = alvo["ini"]
            # ativa até a próxima começar — evita piscada entre palavras
            fim = grupo[i + 1]["ini"] if i + 1 < len(grupo) else fim_grupo
            if fim <= ini:
                fim = ini + 0.05
            partes = [
                f"{DESTAQUE}{w['txt'].upper()}{RESET}" if j == i else w["txt"].upper()
                for j, w in enumerate(grupo)
            ]
            eventos.append(
                f"Dialogue: 0,{_ts_ass(ini)},{_ts_ass(fim)},Viral,,0,0,0,," + " ".join(partes)
            )
    dest.write_text(CABECALHO_ASS + "\n".join(eventos) + "\n", encoding="utf-8")
    _p(f"[LEGENDA] {len(grupos)} grupos / {len(eventos)} eventos ASS (maiúsculas + pop)")
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
MOVIMENTOS = [
    ("in", "centro"), ("out", "centro"), ("in", "esq_dir"),
    ("in", "dir_esq"), ("out", "cima_baixo"), ("in", "baixo_cima"),
]


def ken_burns(img: Path, dur: float, saida: Path, movimento=("in", "centro"), forca=0.085,
              recorte=1.0):
    """Zoom/pan lento. `forca` menor que a versão anterior (0.12): movimento
    perceptível em imagem estática cansa e denuncia o slideshow."""
    frames = max(int(dur * FPS), 2)
    tipo, direcao = movimento
    z = f"1+{forca}*on/{frames}" if tipo == "in" else f"{1 + forca}-{forca}*on/{frames}"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if direcao == "esq_dir":
        x = f"(iw-iw/zoom)*on/{frames}"; y = cy
    elif direcao == "dir_esq":
        x = f"(iw-iw/zoom)*(1-on/{frames})"; y = cy
    elif direcao == "cima_baixo":
        x = cx; y = f"(ih-ih/zoom)*on/{frames}"
    elif direcao == "baixo_cima":
        x = cx; y = f"(ih-ih/zoom)*(1-on/{frames})"
    else:
        x, y = cx, cy
    # recorte > 1 fecha o enquadramento na mesma imagem (sub-plano mais fechado)
    lado_w = int(LARGURA * 2 / recorte) // 2 * 2
    lado_h = int(ALTURA * 2 / recorte) // 2 * 2
    vf = (
        f"scale={LARGURA * 2}:{ALTURA * 2}:force_original_aspect_ratio=increase,"
        f"crop={lado_w}:{lado_h},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={LARGURA}x{ALTURA}:fps={FPS},setsar=1"
    )
    _run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-i", str(img), "-vf", vf,
          "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
          "-pix_fmt", "yuv420p", str(saida)], f"ken burns {img.name}")


def punch_in(img: Path, dur: float, saida: Path, tmp: Path, cortes=None):
    """Pica uma imagem em N sub-planos (geral → médio → close) com corte seco.
    Usado no hook: plano único de 18s é onde o espectador vaza."""
    import math
    cortes = cortes or max(3, min(math.ceil(dur / MAX_SEG_PLANO), 5))
    escalas = [1.0, 1.15, 1.32, 1.50, 1.68][:cortes]
    partes, fatia = [], dur / cortes
    for i, esc in enumerate(escalas):
        p = tmp / f"{saida.stem}_pi{i}.mp4"
        lado_w, lado_h = int(LARGURA * 2 / esc) // 2 * 2, int(ALTURA * 2 / esc) // 2 * 2
        frames = max(int(fatia * FPS), 2)
        vf = (
            f"scale={LARGURA * 2}:{ALTURA * 2}:force_original_aspect_ratio=increase,"
            f"crop={lado_w}:{lado_h},"
            f"zoompan=z='1+0.05*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={LARGURA}x{ALTURA}:fps={FPS},setsar=1"
        )
        _run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-i", str(img), "-vf", vf,
              "-t", f"{fatia:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
              "-pix_fmt", "yuv420p", str(p)], f"punch-in {i}")
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


def multi_plano(planos, dur: float, saida: Path, tmp: Path, offset_mov=0, duracoes=None):
    """Divide a cena entre N planos DIFERENTES com corte seco.

    É o que separa vídeo automatizado de edição de verdade: dentro de um plano
    de 20s, imagem única só com zoom denuncia. Cada sub-plano ganha seu próprio
    movimento, tirado da roda de MOVIMENTOS para não repetir o mesmo gesto.
    """
    duracoes = duracoes or [dur / len(planos)] * len(planos)
    partes = []
    for i, img in enumerate(planos):
        mov = MOVIMENTOS[(offset_mov + i) % len(MOVIMENTOS)]
        d = duracoes[i]
        # Plano longo demais vira 2 sub-planos da MESMA imagem, em recortes
        # diferentes (geral -> fechado), com corte seco entre eles. O canal de
        # referência corta a cada ~4s; segurar 12s numa imagem é o que faz o
        # nosso parecer lento. Isso dobra o número de cortes sem gerar imagem
        # nova, que é onde está o custo de GPU.
        if d > MAX_SEG_PLANO:
            metade = d / 2
            for k, esc in enumerate((1.0, 1.22)):
                p = tmp / f"{saida.stem}_mp{i}_{k}.mp4"
                ken_burns(img, metade, p,
                          movimento=MOVIMENTOS[(offset_mov + i + k) % len(MOVIMENTOS)],
                          recorte=esc)
                partes.append(p)
        else:
            p = tmp / f"{saida.stem}_mp{i}.mp4"
            ken_burns(img, d, p, movimento=mov)
            partes.append(p)
    concat_seco(partes, saida, tmp)


def segmento_clipe(clip: Path, dur: float, saida: Path, tmp: Path, movimento,
                   extras=None, duracoes=None):
    """Clipe LTXV em velocidade natural, depois corta para os planos extras da
    cena (se houver) ou continua no último frame do clipe.

    Esticar o clipe para cobrir a cena inteira daria 4x de slow motion e
    travaria; e continuar no último frame do clipe emenda invisível, porque é
    literalmente o mesmo frame.
    """
    from comfy_video import FPS as CLIP_FPS
    dur_clip = 121 / CLIP_FPS
    escala = (f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
              f"crop={LARGURA}:{ALTURA},fps={FPS},setsar=1")
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
        multi_plano(list(extras), resto, b, tmp, offset_mov=1, duracoes=durs_extras)
    else:
        ult = tmp / f"{saida.stem}_last.png"
        _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(clip), "-vf", escala,
              "-update", "1", str(ult)], "ultimo frame")
        ken_burns(ult, resto, b, movimento=movimento, forca=0.06)
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

    # cenas que ABREM com dissolve => a cena anterior precisa de folga
    abre_dissolve = {c["n"] for c in roteiro["cenas"] if c.get("transicao") == "dissolve"}
    ns = [c["n"] for c in roteiro["cenas"]]
    precisa_folga = {ns[i] for i in range(len(ns) - 1) if ns[i + 1] in abre_dissolve}

    segmentos = []
    for i, (cena, _wav, dur, palavras) in enumerate(audios):
        n = cena["n"]
        ultimo = i == len(audios) - 1
        folga = 1.0 if ultimo else (DISSOLVE if n in precisa_folga else 0.0)
        dur_seg = dur + folga
        seg = tmp / f"seg_{n:02d}.mp4"
        if not seg.exists():
            mov = MOVIMENTOS[i % len(MOVIMENTOS)]
            planos = imagens.get(n, [])
            durs = cortes_ancorados(cena, palavras, dur_seg, len(planos)) if planos else []
            if cena.get("punch_in") and planos:
                punch_in(planos[0], dur_seg, seg, tmp)
            elif n in clipes:
                segmento_clipe(clipes[n], dur_seg, seg, tmp, mov,
                               extras=planos[1:], duracoes=durs)
            elif len(planos) > 1:
                multi_plano(planos, dur_seg, seg, tmp, i, duracoes=durs)
            elif planos:
                ken_burns(planos[0], dur_seg, seg, movimento=mov)
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
