"""Montagem "simples" — SLIDESHOW. Preservada, isolada, congelada.

Este é o primeiro montador do projeto: crossfade em toda cena, sem legenda
queimada, sem trilha, sem grade, sem direção. Ele foi **substituído** pelo
`editor.py` e continua acessível só por `produce_video.py --montagem simples`,
para comparação.

## Por que está num arquivo separado

A auditoria de 31/07 encontrou cinco funções com o mesmo nome nos dois módulos
(`montar`, `segmento_clipe`, `escrever_srt`, `_run`, `ts`). Duas implementações
de montagem convivendo dentro do orquestrador é convite a divergência
silenciosa: alguém corrige um bug numa e não na outra, e o `--montagem simples`
passa a mentir sobre o que o pipeline faz.

Isolar em vez de apagar preserva a funcionalidade — a regra do projeto é nunca
remover o que existe — e ao mesmo tempo tira 180 linhas do orquestrador, que
estava acumulando duas responsabilidades.

## NÃO EVOLUA ESTE ARQUIVO

Correção de bug aqui só se o `--montagem simples` quebrar. Toda melhoria de
montagem vai para o `editor.py`. Este arquivo existe como registro histórico e
base de comparação, não como caminho de produção.
"""

from __future__ import annotations

from pathlib import Path

# Importar de produce_video é seguro: ele NÃO importa este módulo no topo — a
# importação lá é lazy, dentro do main(), só quando --montagem simples é pedido.
# Portanto não há ciclo.
from produce_video import (
    AUDIO_HZ,
    ALTURA,
    CLIP_FPS,
    FADE,
    FFMPEG,
    FPS_FINAL,
    LARGURA,
    LOUDNORM,
    _p,
    _run,
)


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
