"""Monta um segmento ANIMADO a partir de estados sucessivos de um gráfico vetorial.

A ideia é simples de propósito: em vez de interpolar propriedades em tempo de
render, o executor vetorial desenha o mesmo quadro em N ESTADOS (a timeline com
1, 2, 3, 4 marcos visíveis) e este módulo encadeia os estados com um
crossfade curto. O resultado lê como "os elementos vão aparecendo".

## Por que estados e não interpolação

Três razões, e a terceira é a que decide:

1. **Determinismo.** Cada estado é um PNG, com a mesma chave de cache do resto.
   Interpolar em ffmpeg dependeria de expressões de tempo cuja saída é mais
   difícil de reproduzir bit a bit.
2. **Reuso.** `estados_por_lista()` serve timeline, gráfico e ícones sem que
   nenhum deles saiba animar — o executor continua só desenhando.
3. **Custo.** Um estado custa ~0,3s de CPU. Quatro estados custam ~1,2s. Não há
   razão para complicar.

## Corte seco vs. crossfade

A doutrina do projeto é corte seco ENTRE PLANOS, e ela continua valendo. Aqui é
outra coisa: é movimento DENTRO de um plano, onde o elemento novo aparecendo com
fade curto é a leitura correta — um corte seco entre dois estados quase idênticos
lê como falha de render, não como revelação.

## Quem NÃO deve receber câmera

Um segmento animado já tem movimento próprio. Somar Ken Burns por cima dá dois
movimentos disputando a atenção. Quem chama este módulo entrega um segmento
pronto e o editor não aplica câmera nele.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

FFMPEG = "ffmpeg"
FPS = 30
FADE = 0.22          # curto: revelação, não transição de cena
CRF = 18


def _run(cmd: list, desc: str, timeout=600):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{desc} travou (>{timeout}s)")
    if r.returncode != 0:
        raise RuntimeError(f"{desc} falhou:\n{r.stderr[-1500:]}")


def _estado_para_video(png: Path, dur: float, saida: Path, largura: int, altura: int):
    _run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-i", str(png),
          "-t", f"{dur:.3f}", "-vf",
          f"scale={largura}:{altura}:force_original_aspect_ratio=increase,"
          f"crop={largura}:{altura},fps={FPS},setsar=1",
          "-c:v", "libx264", "-preset", "medium", "-crf", str(CRF),
          "-pix_fmt", "yuv420p", str(saida)], f"estado {png.name}")


def animar(estados: list, dur: float, saida: Path, tmp: Path,
           largura=1920, altura=1080, fade=FADE) -> Path:
    """Encadeia `estados` (PNGs) num segmento de `dur` segundos.

    Um estado só não é animação: copia direto, sem re-encodar à toa.
    """
    estados = [Path(e) for e in estados]
    if not estados:
        raise ValueError("animar() precisa de pelo menos um estado")
    tmp.mkdir(parents=True, exist_ok=True)

    n = len(estados)
    if n == 1:
        _estado_para_video(estados[0], dur, saida, largura, altura)
        return saida

    # Cada estado ocupa `passo` do tempo visível. O vídeo de cada um leva
    # `passo + fade` de folga, porque o crossfade CONSOME do fim de um e do
    # começo do próximo — sem a folga, o total encolhe e a última revelação
    # fica cortada. É a mesma correção que já existe no editor entre atos.
    passo = dur / n
    if passo <= fade * 1.5:
        # revelação apertada demais: o fade comeria o tempo de leitura
        fade = max(passo / 3.0, 0.05)

    partes = []
    for i, png in enumerate(estados):
        p = tmp / f"{saida.stem}_est{i:02d}.mp4"
        _estado_para_video(png, passo + (fade if i < n - 1 else 0.0), p, largura, altura)
        partes.append(p)

    entradas, filtros = [], []
    for p in partes:
        entradas += ["-i", str(p)]
    atual, off = "0:v", 0.0
    for i in range(1, n):
        off += passo
        rot = f"v{i}"
        filtros.append(f"[{atual}][{i}:v]xfade=transition=fade:duration={fade:.3f}"
                       f":offset={off:.3f}[{rot}]")
        atual = rot
    filtros.append(f"[{atual}]null[vout]")

    _run([FFMPEG, "-y", "-loglevel", "error", *entradas,
          "-filter_complex", ";".join(filtros), "-map", "[vout]",
          "-c:v", "libx264", "-preset", "medium", "-crf", str(CRF),
          "-pix_fmt", "yuv420p", "-r", str(FPS), "-t", f"{dur:.3f}", str(saida)],
         f"animacao de {n} estados")
    return saida


def estados_por_lista(params: dict, campo: str, minimo: int = 1) -> list:
    """Revelação progressiva dos itens de uma lista.

    Serve timeline (`pontos`), gráfico (`itens`) e ícones (`itens`) com a MESMA
    implementação — nenhum executor precisa saber animar, eles só desenham o que
    receberem. É a razão de a animação morar aqui e não dentro deles.

    `minimo` existe porque nem toda revelação começa vazia: uma timeline sem
    nenhum marco é um eixo solto, que não comunica; começar com 1 é mais legível.
    """
    itens = params.get(campo) or []
    if len(itens) <= minimo:
        return [params]
    return [dict(params, **{campo: itens[:k]}) for k in range(minimo, len(itens) + 1)]
