"""
Produz o vídeo COMPLETO a partir de um roteiro JSON: narração (Piper) +
imagens (SDXL) + clipes de movimento (LTXV) + montagem (ffmpeg) + legendas.

    python produce_video.py scripts/roteiro_01_casa_da_mae.json
    python produce_video.py <roteiro> --etapa audio      # só narração
    python produce_video.py <roteiro> --etapa imagens
    python produce_video.py <roteiro> --etapa clipes
    python produce_video.py <roteiro> --etapa montagem

Cada etapa é idempotente: só gera o que ainda não existe em output/producao/<id>/.
Assim uma falha no meio não obriga a refazer 20 minutos de GPU.

Formato do roteiro: ver scripts/roteiro_01_casa_da_mae.json
    cenas[]: {n, narracao (pt-BR), imagem (prompt EN), movimento (bool)}

Cadeia de ferramentas, tudo local e gratuito:
    Piper TTS  -> D:\\ComfyUI\\models\\piper\\pt_BR-jeff-medium.onnx
    SDXL       -> workflows/sdxl_thumbnail.json  (via comfy_batch)
    LTXV       -> workflows/ltxv_i2v_5s.json     (via comfy_video, teto de 5s)
    ffmpeg     -> montagem, Ken Burns nas estáticas, crossfade, mux, legenda
"""

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

from comfy_batch import NEGATIVE_PROMPT as IMG_NEGATIVE
from comfy_batch import _p, _seed_for
from comfy_client import ComfyUIClient, ComfyUIError, load_workflow, patch_graph
from comfy_video import FPS as CLIP_FPS
from comfy_video import MOTION_SUFFIX, NEGATIVE_PROMPT, frames_for

RAIZ = Path(__file__).parent
PY_COMFY = Path("D:/ComfyUI/venv/Scripts/python.exe")
FFMPEG = "ffmpeg"

# ── NARRAÇÃO ─────────────────────────────────────────────────────────────
# Edge-TTS (vozes neurais da Microsoft, grátis, sem conta). Mesmos parâmetros
# do viral_replicator_video_engine, que é o que produziu a narração boa.
#
# Piper foi descartado: medium em 22kHz mono sai com chiado audível e prosódia
# chapada. Edge-TTS entrega 24kHz neural + eventos WordBoundary, que dão
# timestamp por palavra e legenda alinhada de verdade (o SRT antigo dividia o
# tempo igualmente dentro da cena, o que desencaixa em frase longa).
#
# Contrapartida honesta: Edge-TTS é serviço ONLINE. Sem internet, não roda.
EDGE_VOICE = "pt-BR-ThalitaMultilingualNeural"
# O projeto anterior usava +8% ("ritmo YouTube"). Para história dark narrada em
# primeira pessoa isso dá ~194 palavras/min: atropela a pausa dramática e joga o
# vídeo para 4,5min, abaixo do piso de 5min que o core_intelligence_prompt usa no
# Retenção Score. -10% mantém a MESMA voz e só desacelera. Trocar aqui é 1 linha.
EDGE_RATE = "-10%"
EDGE_PITCH = "+0Hz"
PAUSA_ENTRE_CENAS = 0.35  # segundos de silêncio somados ao fim de cada cena
AUDIO_HZ = 48000
# loudnorm padrão de streaming (-14 LUFS): mesma calibragem do projeto anterior
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"

LARGURA, ALTURA = 1920, 1080
FPS_FINAL = 30
FADE = 0.6  # segundos de crossfade entre cenas


# ── etapa 1: narração ────────────────────────────────────────────────────


SCRIPT_EDGE = '''
import asyncio, json, sys
import edge_tts

texto, saida, voz, rate, pitch = sys.argv[1:6]

async def main():
    try:
        c = edge_tts.Communicate(text=texto, voice=voz, rate=rate, pitch=pitch,
                                 boundary="WordBoundary")
    except TypeError:  # edge-tts <= 6 já emitia WordBoundary por padrão
        c = edge_tts.Communicate(text=texto, voice=voz, rate=rate, pitch=pitch)
    palavras = []
    with open(saida, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                palavras.append({
                    "p": ch["text"],
                    "ini": round(ch["offset"] / 1e7, 3),
                    "fim": round((ch["offset"] + ch["duration"]) / 1e7, 3),
                })
    print(json.dumps(palavras, ensure_ascii=False))

asyncio.run(main())
'''


# Vozes neurais por idioma. Mesma tabela do viral_replicator_video_engine,
# que é onde a narração boa foi calibrada.
VOZES = {
    "de-DE": "de-DE-ConradNeural",
    "pt-BR": "pt-BR-ThalitaMultilingualNeural",
    "en-US": "en-US-GuyNeural",
    "es-ES": "es-ES-AlvaroNeural",
    "it-IT": "it-IT-DiegoNeural",
    "fr-FR": "fr-FR-HenriNeural",
    "nl-NL": "nl-NL-MaartenNeural",
}


def voz_e_ritmo(roteiro: dict):
    """O roteiro manda; os defaults do módulo são só fallback.

    O ritmo é decisão por gênero, não global: história dark pede -10% (pausa
    dramática), explicativo de saúde pede +8% (os vídeos do canal de referência
    que passaram de 1M falam mais rápido que os que floparam).
    """
    idioma = roteiro.get("idioma", "pt-BR")
    voz = roteiro.get("voz") or VOZES.get(idioma) or VOZES.get(idioma.split("-")[0]) or EDGE_VOICE
    return voz, roteiro.get("ritmo", EDGE_RATE), roteiro.get("tom", EDGE_PITCH)


def _tts_edge(texto: str, mp3: Path, voz=None, ritmo=None, tom=None) -> list:
    """Sintetiza um bloco e devolve os timestamps por palavra."""
    runner = mp3.parent / "_edge_runner.py"
    runner.write_text(SCRIPT_EDGE, encoding="utf-8")
    r = subprocess.run(
        [str(PY_COMFY), str(runner), texto, str(mp3),
         voz or EDGE_VOICE, ritmo or EDGE_RATE, tom or EDGE_PITCH],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0 or not mp3.exists() or mp3.stat().st_size == 0:
        raise RuntimeError(
            f"Edge-TTS falhou (precisa de internet): {(r.stderr or '')[-500:]}"
        )
    return json.loads(r.stdout.strip().splitlines()[-1])


def gerar_audio(roteiro: dict, dest: Path) -> list:
    """Uma faixa por cena, via Edge-TTS. Devolve [(cena, wav, duracao, palavras)].

    O .wav de cada cena já inclui PAUSA_ENTRE_CENAS de silêncio no fim, então a
    duração devolvida é exatamente o tempo que aquela cena ocupa no vídeo.
    """
    dest.mkdir(parents=True, exist_ok=True)
    voz, ritmo, tom = voz_e_ritmo(roteiro)
    saida = []
    for cena in roteiro["cenas"]:
        mp3 = dest / f"cena_{cena['n']:02d}.mp3"
        wav = dest / f"cena_{cena['n']:02d}.wav"
        jsw = dest / f"cena_{cena['n']:02d}_palavras.json"

        if not wav.exists() or not jsw.exists():
            palavras = _tts_edge(cena["narracao"], mp3, voz, ritmo, tom)
            jsw.write_text(json.dumps(palavras, ensure_ascii=False), encoding="utf-8")
            _run([FFMPEG, "-y", "-i", str(mp3),
                  "-af", f"apad=pad_dur={PAUSA_ENTRE_CENAS}",
                  "-ar", str(AUDIO_HZ), "-ac", "1", str(wav)],
                 f"wav cena {cena['n']}")
        else:
            palavras = json.loads(jsw.read_text(encoding="utf-8"))

        with wave.open(str(wav)) as f:
            dur = f.getnframes() / f.getframerate()
        saida.append((cena, wav, dur, palavras))
        _p(f"  cena {cena['n']:02d}  {dur:>5.1f}s  {len(cena['narracao'].split()):>3} palavras"
           f"  ({len(palavras)} timestamps)")
    total = sum(d for _, _, d, _ in saida)
    _p(f"[AUDIO] {len(saida)} faixas ({voz} {ritmo}), total {total / 60:.2f} min")
    return saida


# ── etapa 2: imagens ─────────────────────────────────────────────────────

# Sufixo de estilo — 16:9 cheio (a thumb reserva espaço pro título, o vídeo não)
# e coerência de série: a mesma paleta em todas as cenas do canal.
# O roteiro pode sobrescrever com "estilo"; sem isso vale o default abaixo.
ESTILO = (
    "cinematic still, dramatic side lighting, high contrast, muted teal and amber grade, "
    "photorealistic, 35mm film grain, shallow depth of field, brazilian suburban setting"
)

# Estilos nomeados. "medico" replica a linguagem visual do nicho de saúde:
# ilustração anatômica chapada sobre fundo claro, que é o que o canal de
# referência usa e o que o SDXL consegue reproduzir com fidelidade.
ESTILOS = {
    # Validado contra frames do canal de referência: o INTERIOR dos vídeos deles
    # é render 3D com fundo escuro e luz dramática — a thumbnail chapada de fundo
    # branco é outra linguagem, feita à parte. Fundo escuro também é o que evita
    # o texto rabiscado: fundo branco de diagrama convida o modelo a desenhar
    # rótulo, e rótulo em difusão sai como garatuja.
    "medico_3d": (
        "3d medical visualization render, dramatic cinematic lighting, dark background, "
        "subsurface scattering, glossy wet surfaces, volumetric light, "
        "shallow depth of field, high detail"
    ),
    # O estilo do VÍDEO QUE ESTOUROU. Medido em 31/07 amostrando os dois vídeos
    # do canal de referência a cada 5s:
    #   - zRMtp04VHLQ (artérias, 14k views)  -> 3D fotorreal escuro, quase 100%
    #     interior do corpo. É o que o `medico_3d` copia.
    #   - SnWbe1P1l3s (cor dos olhos, 5,75M) -> ilustração editorial clara, luz de
    #     dia, e PESSOAS na maioria dos planos. Rosto, gente andando no parque,
    #     cozinha com plantas, mapa, e a anatomia entra como corte estilizado
    #     DENTRO da cena, não como túnel fotorreal.
    # 5,75M contra 14k: o formato que vale copiar é o segundo.
    "explicativo_claro": (
        "flat editorial vector illustration, soft warm daylight, bright airy background, "
        "clean rounded shapes, gentle even shading, muted sage green and warm beige palette, "
        "modern explainer illustration, friendly approachable people, subtle paper texture, "
        "no harsh shadows, no text, no labels, no watermark"
    ),
    # Mantido só como registro do que NÃO funcionou: diagrama chapado sobre fundo
    # branco produziu rótulo ilegível em quase todo frame. Não usar.
    "medico_diagrama_NAO_USAR": (
        "clean medical illustration style, bright saturated colors, crisp outlines, "
        "textbook anatomy art, light neutral background, even lighting, no text, no labels"
    ),
    "dark_br": ESTILO,
}

# Elenco recorrente. No vídeo de 5,75M a MESMA mulher de cabelo grisalho e jaqueta
# azul reaparece em dezenas de planos — é o que dá liga de série. SDXL puro não
# garante o mesmo rosto entre gerações (isso exigiria LoRA ou IP-Adapter), mas
# descrever a pessoa com as mesmas palavras em todos os planos chega perto o
# bastante para não parecer gente diferente a cada corte.
ELENCO = {
    "ela": "a friendly woman in her forties with short grey hair, wearing a blue jacket over a white shirt",
    "ele": "a friendly man in his forties with short dark hair and light stubble, wearing a grey-blue sweater",
}


def estilo_do_roteiro(roteiro: dict) -> str:
    e = roteiro.get("estilo", "")
    return ESTILOS.get(e, e or ESTILO)


# Um plano por ~8s de narração. Cena longa com imagem única é o que mais
# denuncia vídeo automatizado: o canal profissional do nicho corta 3-5x por
# cena. As variações de enquadramento são derivadas do prompt base, então não
# é preciso escrever prompt novo para cada plano.
SEGUNDOS_POR_PLANO = 5.5
MAX_PLANOS = 4
ENQUADRAMENTOS = [
    "",                                                              # plano base
    "medium shot, closer framing, slightly different angle",
    "extreme close-up detail, macro, very shallow focus",
    "wide establishing shot, more of the surroundings visible",
]


def planos_da_cena(cena: dict, dur: float) -> int:
    """Quantos planos essa cena merece.

    Cena com clipe: o clipe LTXV cobre só os primeiros 4,84s; o que sobra é que
    precisa ser dividido. Descontar 1 do total (como eu fazia antes) deixava
    13s de imagem parada numa cena de 18s.
    """
    if cena.get("planos"):
        return min(len(cena["planos"]), MAX_PLANOS)   # roteiro manda
    if cena.get("punch_in"):
        return 1  # punch_in já pica a própria imagem em 3 sub-planos
    if cena.get("movimento"):
        resto = max(dur - 121 / 25, 0.0)   # 4,84s de clipe
        return max(1, min(1 + int(round(resto / SEGUNDOS_POR_PLANO)), MAX_PLANOS))
    return max(1, min(int(round(dur / SEGUNDOS_POR_PLANO)), MAX_PLANOS))


def gerar_imagens(roteiro: dict, dest: Path, duracoes: dict = None,
                  largura=1344, altura=768) -> dict:
    """Devolve {n_cena: [path_plano1, path_plano2, ...]}."""
    dest.mkdir(parents=True, exist_ok=True)
    duracoes = duracoes or {}

    # migração: arquivos antigos "cena_NN_*.png" viram o plano 1
    for c in roteiro["cenas"]:
        for velho in dest.glob(f"cena_{c['n']:02d}_*.png"):
            if "_p" not in velho.name.split("cena_")[1][:6]:
                novo = dest / velho.name.replace(f"cena_{c['n']:02d}_",
                                                 f"cena_{c['n']:02d}_p1_", 1)
                if not novo.exists():
                    velho.rename(novo)

    faltando = []
    for c in roteiro["cenas"]:
        alvo = planos_da_cena(c, duracoes.get(c["n"], 12.0))
        for p in range(1, alvo + 1):
            if not list(dest.glob(f"cena_{c['n']:02d}_p{p}_*.png")):
                faltando.append((c, p))

    if not faltando:
        _p(f"[IMAGENS] todos os planos já existem, pulando.")
    else:
        client = ComfyUIClient()
        if not client.is_online():
            raise RuntimeError(f"ComfyUI offline em {client.base_url} (rode iniciar_comfyui.bat)")
        grafo = load_workflow("sdxl_thumbnail.json")
        disp = client.available_checkpoints()
        ckpt = "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
        if disp and ckpt not in disp:
            ckpt = disp[0]
        estilo = estilo_do_roteiro(roteiro)
        for i, (cena, plano) in enumerate(faltando, 1):
            # roteiro com "planos" traz prompt proprio por plano; sem isso,
            # deriva enquadramentos a partir do prompt unico da cena
            explicitos = cena.get("planos") or []
            if plano <= len(explicitos) and explicitos[plano - 1].get("imagem"):
                base = explicitos[plano - 1]["imagem"]
                prompt = f"{base}, {estilo}"
            else:
                enq = ENQUADRAMENTOS[(plano - 1) % len(ENQUADRAMENTOS)]
                base = cena.get("imagem") or (explicitos[0]["imagem"] if explicitos else "")
                prompt = f"{base}, {enq}, {estilo}" if enq else f"{base}, {estilo}"
            # plano 1 mantém a seed da cena (e o seed_de, quando houver) para
            # não quebrar a continuidade já conquistada; os outros variam
            base_seed = f"{roteiro['id']}_{cena.get('seed_de', cena['n'])}"
            chave = base_seed if plano == 1 else f"{base_seed}_p{plano}"
            g = patch_graph(
                grafo,
                positive=prompt,
                negative=IMG_NEGATIVE,
                width=largura,
                height=altura,
                seed=_seed_for(chave),
                checkpoint=ckpt,
                filename_prefix=f"vrp/prod_{roteiro['id']}_{cena['n']:02d}_p{plano}",
                # 16:9 cheio: a thumb reserva espaço pro título, o vídeo não
                extra={"VRP_RESIZE_YOUTUBE": {"width": LARGURA, "height": ALTURA}},
            )
            _p(f"[{i}/{len(faltando)}] cena {cena['n']:02d} plano {plano}")
            paths = client.run(g, dest, timeout=900)
            if paths:
                paths[0].rename(dest / f"cena_{cena['n']:02d}_p{plano}_{paths[0].name}")

    out = {}
    for c in roteiro["cenas"]:
        planos = []
        for p in range(1, MAX_PLANOS + 1):
            achados = sorted(dest.glob(f"cena_{c['n']:02d}_p{p}_*.png"))
            if achados:
                planos.append(achados[-1])
        if planos:
            out[c["n"]] = planos
    return out


# ── etapa 3: clipes de movimento ─────────────────────────────────────────


def gerar_clipes(roteiro: dict, imagens: dict, dest: Path, segundos=5.0) -> dict:
    """Só nas cenas marcadas movimento=true. As outras usam Ken Burns."""
    dest.mkdir(parents=True, exist_ok=True)
    alvos = [c for c in roteiro["cenas"] if c.get("movimento") and c["n"] in imagens]
    pend = [c for c in alvos if not list(dest.glob(f"cena_{c['n']:02d}_*.mp4"))]
    if pend:
        client = ComfyUIClient()
        if not client.is_online():
            raise RuntimeError("ComfyUI offline")
        grafo = load_workflow("ltxv_i2v_5s.json")
        length = frames_for(segundos)
        _p(f"[CLIPES] {length} frames @ {CLIP_FPS:g}fps = {length / CLIP_FPS:.2f}s cada")
        for i, cena in enumerate(pend, 1):
            img = imagens[cena["n"]][0]   # clipe sempre parte do plano 1
            nome = client.upload_image(img)
            # mesma regra do comfy_video: descrever a cena que JÁ está no frame
            # o clipe parte do plano 1; o roteiro pode trazer o prompt em
            # cena["imagem"] (formato antigo) ou em planos[0]["imagem"]
            base_img = cena.get("imagem") or (cena.get("planos") or [{}])[0].get("imagem", "")
            prompt = f"{base_img}, {MOTION_SUFFIX}"
            g = patch_graph(
                grafo,
                positive=prompt,
                negative=NEGATIVE_PROMPT,
                width=768,
                height=448,
                seed=_seed_for(f"{roteiro['id']}_clip_{cena['n']}"),
                filename_prefix=f"vrp/prodclip_{roteiro['id']}_{cena['n']:02d}",
                extra={
                    "VRP_INPUT_IMAGE": {"image": nome},
                    "VRP_LATENT": {"length": length},
                    "VRP_SCHEDULER": {"steps": 8},
                    "VRP_FRAMERATE": {"frame_rate": CLIP_FPS},
                },
            )
            _p(f"[{i}/{len(pend)}] clipe cena {cena['n']:02d}")
            try:
                paths = client.run(g, dest, timeout=1800)
            except ComfyUIError as e:
                _p(f"    FALHOU (segue com Ken Burns): {e}")
                continue
            if paths:
                paths[0].rename(dest / f"cena_{cena['n']:02d}_{paths[0].name}")
    return {c["n"]: sorted(dest.glob(f"cena_{c['n']:02d}_*.mp4"))[-1] for c in alvos
            if list(dest.glob(f"cena_{c['n']:02d}_*.mp4"))}


# ── etapa 4: montagem ────────────────────────────────────────────────────


def _run(cmd: list, desc: str):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{desc} falhou:\n{r.stderr[-1500:]}")


def segmento_ken_burns(img: Path, dur: float, saida: Path, zoom_in=True):
    """Estática -> vídeo com zoom lento. Sem zoom o olho abandona em 3s."""
    frames = max(int(dur * FPS_FINAL), 1)
    # zoompan trabalha em cima de um upscale pra não pixelar no zoom
    z = "1+0.12*on/{}".format(frames) if zoom_in else "1.12-0.12*on/{}".format(frames)
    vf = (
        f"scale={LARGURA * 2}:{ALTURA * 2}:force_original_aspect_ratio=increase,"
        f"crop={LARGURA * 2}:{ALTURA * 2},"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={LARGURA}x{ALTURA}:fps={FPS_FINAL},"
        f"setsar=1"
    )
    _run([FFMPEG, "-y", "-loop", "1", "-i", str(img), "-vf", vf, "-t", f"{dur:.3f}",
          "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
          str(saida)], f"ken burns {img.name}")


def segmento_clipe(clip: Path, dur: float, saida: Path, tmp: Path = None):
    """Clipe LTXV (4,84s) em velocidade natural + Ken Burns no ÚLTIMO frame dele
    para cobrir o resto da narração da cena.

    Por que não esticar o clipe: uma cena de 21s a partir de 4,84s daria 4,4x de
    slow motion — 121 frames em 21s são 5,7fps efetivos, e o resultado trava na
    tela. Continuar do último frame emenda invisível (o frame é o mesmo) e o
    movimento restante fica no zoom, que é suave por construção.
    """
    tmp = tmp or saida.parent
    tmp.mkdir(parents=True, exist_ok=True)
    dur_clip = 121 / CLIP_FPS

    escala = (f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
              f"crop={LARGURA}:{ALTURA},fps={FPS_FINAL},setsar=1")

    if dur <= dur_clip + 0.3:
        _run([FFMPEG, "-y", "-i", str(clip), "-vf", escala, "-an", "-t", f"{dur:.3f}",
              "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
              str(saida)], f"clipe {clip.name}")
        return

    parte_a = tmp / f"{saida.stem}_a.mp4"
    ultimo = tmp / f"{saida.stem}_last.png"
    parte_b = tmp / f"{saida.stem}_b.mp4"

    _run([FFMPEG, "-y", "-i", str(clip), "-vf", escala, "-an",
          "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
          str(parte_a)], f"clipe parte A {clip.name}")
    # -update 1 sobrescreve até o fim => sobra o último frame decodificado
    _run([FFMPEG, "-y", "-i", str(clip), "-vf", escala, "-update", "1",
          str(ultimo)], f"ultimo frame {clip.name}")
    segmento_ken_burns(ultimo, dur - dur_clip, parte_b, zoom_in=True)

    lista = tmp / f"{saida.stem}_concat.txt"
    lista.write_text(f"file '{parte_a.as_posix()}'\nfile '{parte_b.as_posix()}'\n", encoding="utf-8")
    _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
          "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
          "-r", str(FPS_FINAL), str(saida)], f"concat clipe+kenburns {clip.name}")


def escrever_srt(audios: list, dest: Path, max_chars=42, max_linhas=2):
    """Legenda a partir dos timestamps por palavra do Edge-TTS.

    Substitui a versão antiga, que dividia a duração da cena em partes iguais —
    isso desencaixa em frase longa, porque palavra não tem duração uniforme.
    Aqui cada bloco começa no início real da 1ª palavra e termina no fim real
    da última.
    """
    def ts(t):
        h, r = divmod(t, 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")

    blocos, offset = [], 0.0
    for cena, _, dur, palavras in audios:
        if not palavras:
            continue
        # O evento WordBoundary devolve a palavra SEM pontuação ("na UTI Ele").
        # Os tokens batem 1:1 com o texto original separado por espaço, então
        # usamos o token original (com vírgula e ponto) e só o tempo do evento.
        tokens = cena["narracao"].split()
        usar_original = len(tokens) == len(palavras)
        linhas_atual, texto_linha, ini_bloco, fim_bloco = [], "", None, None
        for idx, w in enumerate(palavras):
            p = tokens[idx] if usar_original else w["p"]
            if ini_bloco is None:
                ini_bloco = offset + w["ini"]
            if len(texto_linha) + len(p) + 1 > max_chars:
                linhas_atual.append(texto_linha)
                texto_linha = p
                if len(linhas_atual) == max_linhas:
                    blocos.append((ini_bloco, fim_bloco, list(linhas_atual)))
                    linhas_atual, ini_bloco = [], offset + w["ini"]
            else:
                texto_linha = f"{texto_linha} {p}".strip()
            fim_bloco = offset + w["fim"]
        if texto_linha:
            linhas_atual.append(texto_linha)
        if linhas_atual:
            blocos.append((ini_bloco, fim_bloco, linhas_atual))
        offset += dur

    partes = []
    for i, (ini, fim, linhas) in enumerate(blocos, 1):
        partes.append(f"{i}\n{ts(ini)} --> {ts(max(fim, ini + 0.4))}\n" + "\n".join(linhas) + "\n")
    dest.write_text("\n".join(partes), encoding="utf-8")
    _p(f"[LEGENDA] {len(blocos)} blocos com timestamp real de palavra")
    return dest


def montar(roteiro: dict, audios: list, imagens: dict, clipes: dict, base: Path) -> Path:
    tmp = base / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    # CADA segmento é gerado com a duração da narração + FADE. Sem essa folga o
    # crossfade come 0,6s por transição (10,2s em 18 cenas) e o -shortest do mux
    # corta o final da narração. Com a folga, o tempo VISÍVEL de cada cena é
    # exatamente a duração da sua narração e os offsets viram a soma acumulada.
    segmentos = []
    for i, (cena, _, dur, _palavras) in enumerate(audios):
        n = cena["n"]
        ultimo = i == len(audios) - 1
        dur_seg = dur + (1.0 if ultimo else FADE)
        seg = tmp / f"seg_{n:02d}.mp4"
        if not seg.exists():
            if n in clipes:
                segmento_clipe(clipes[n], dur_seg, seg, tmp=tmp)
            elif n in imagens:
                segmento_ken_burns(imagens[n][0], dur_seg, seg, zoom_in=(n % 2 == 1))
            else:
                raise RuntimeError(f"cena {n} sem imagem nem clipe")
        segmentos.append(seg)
        _p(f"  segmento {n:02d} pronto (narracao {dur:.1f}s + folga)")

    # vídeo: crossfade encadeado; offset = soma das narrações anteriores
    filtro, entradas = [], []
    for s in segmentos:
        entradas += ["-i", str(s)]
    if len(segmentos) == 1:
        filtro.append("[0:v]null[vout]")
    else:
        atual, offset = "0:v", 0.0
        for i in range(1, len(segmentos)):
            offset += audios[i - 1][2]
            rotulo = f"v{i}"
            filtro.append(
                f"[{atual}][{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[{rotulo}]"
            )
            atual = rotulo
        filtro.append(f"[{atual}]null[vout]")

    video_mudo = base / "video_mudo.mp4"
    if not video_mudo.exists():
        _run([FFMPEG, "-y", *entradas, "-filter_complex", ";".join(filtro),
              "-map", "[vout]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
              "-pix_fmt", "yuv420p", "-r", str(FPS_FINAL), str(video_mudo)], "concat/xfade")

    # áudio: concat das faixas + loudnorm (-14 LUFS, padrão de streaming)
    lista = tmp / "audios.txt"
    lista.write_text("\n".join(f"file '{w.as_posix()}'" for _, w, _, _ in audios), encoding="utf-8")
    narracao = base / "narracao.wav"
    if not narracao.exists():
        cru = tmp / "narracao_cru.wav"
        _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
              "-c", "copy", str(cru)], "concat audio")
        _run([FFMPEG, "-y", "-i", str(cru), "-af", LOUDNORM,
              "-ar", str(AUDIO_HZ), "-ac", "1", str(narracao)], "loudnorm")

    srt = escrever_srt(audios, base / "legenda.srt")

    final = base / f"{roteiro['id']}_FINAL.mp4"
    # estéreo 48kHz 192k: o mux antigo saía mono 22kHz, que soma chiado ao já
    # chiado do Piper. Aqui a fonte é neural 24kHz e o container fica padrão.
    _run([FFMPEG, "-y", "-i", str(video_mudo), "-i", str(narracao),
          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
          "-ar", str(AUDIO_HZ), "-ac", "2", "-shortest", str(final)], "mux")
    _p(f"[MONTAGEM] {final}")
    _p(f"[MONTAGEM] legenda separada em {srt} (subir no YouTube como CC)")
    return final


# ── orquestração ─────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(description="Produz o video completo de um roteiro JSON.")
    ap.add_argument("roteiro")
    ap.add_argument("--etapa", default="tudo",
                    choices=["tudo", "audio", "imagens", "clipes", "montagem"])
    ap.add_argument("--segundos-clipe", type=float, default=5.0)
    ap.add_argument("--montagem", default="pro", choices=["pro", "simples"],
                    help="pro = editor.py (corte seco, legenda queimada, trilha)")
    args = ap.parse_args()

    roteiro = json.loads(Path(args.roteiro).read_text(encoding="utf-8"))
    base = RAIZ / "output" / "producao" / roteiro["id"]
    base.mkdir(parents=True, exist_ok=True)

    _p(f"=== {roteiro['titulo']}")
    _p(f"=== {len(roteiro['cenas'])} cenas | nicho: {roteiro.get('nicho', '-')}")

    audios = gerar_audio(roteiro, base / "audio")
    if args.etapa == "audio":
        return

    duracoes = {c["n"]: d for c, _w, d, _p in audios}
    imagens = gerar_imagens(roteiro, base / "imagens", duracoes)
    if args.etapa == "imagens":
        return

    clipes = gerar_clipes(roteiro, imagens, base / "clipes", segundos=args.segundos_clipe)
    if args.etapa == "clipes":
        return

    if args.montagem == "simples":
        # slideshow: crossfade em toda cena, sem legenda queimada nem trilha.
        # Mantido só para comparação — não usar em vídeo de publicação.
        montar(roteiro, audios, imagens, clipes, base)
    else:
        from editor import montar as montar_pro
        montar_pro(roteiro, audios, imagens, clipes, base)


if __name__ == "__main__":
    main()
