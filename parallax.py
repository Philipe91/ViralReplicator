"""Parallax 2.5D: desloca cada pixel conforme a profundidade dele.

É a resposta ao maior "cheiro de IA" da auditoria: a fonte é um PNG chapado, e
qualquer movimento afim sobre ele lê como "foto com Ken Burns", não como câmera.
Quando o primeiro plano anda mais que o fundo, o cérebro lê VOLUME.

## Mapeamento inverso, de propósito

Para cada pixel de SAÍDA, busca-se de onde ele veio na origem. O contrário —
empurrar cada pixel da origem para o destino — deixa BURACOS onde o primeiro
plano se afasta e revela o que estava atrás, e nós não temos o que estava atrás.
Buraco exige inpaint; esticar não exige nada.

O preço do mapeamento inverso é estiramento nas bordas de profundidade: onde a
descontinuidade é grande, alguns pixels do fundo viram um rastro na direção do
movimento. Por isso a amplitude é pequena — a 2,2% da largura o estiramento fica
abaixo do limiar de percepção, e o efeito de volume já aparece. Amplitude grande
troca "câmera de verdade" por "borracha derretendo", que é pior que não ter
parallax.

## Não somar com Ken Burns

Já há movimento. Um plano com parallax entra sem câmera, pela mesma razão que o
vetor animado entra sem câmera.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

FPS = 30
AMPLITUDE = 0.022     # fração da largura; ver a nota sobre estiramento
CRF = 18
FFMPEG = "ffmpeg"

# Trajetórias: como o deslocamento evolui ao longo do plano. A profundidade
# multiplica isto, então o fundo quase não anda e a frente anda tudo.
TRAJETORIAS = {
    # varre de um lado ao outro: o movimento mais legível de volume
    "lateral":  lambda t: (t * 2.0 - 1.0),
    # aproxima: tudo cresce, mas o perto cresce mais
    "aproxima": lambda t: (t - 0.5) * 1.4,
    # respiração: vai e volta, para plano longo não terminar longe do começo
    "respira":  lambda t: np.sin(t * np.pi * 2.0) * 0.7,
}


def _carregar(imagem: Path, mapa: Path, largura: int, altura: int):
    with Image.open(imagem) as im:
        img = np.asarray(im.convert("RGB").resize((largura, altura), Image.LANCZOS))
    with Image.open(mapa) as mp:
        dep = np.asarray(mp.convert("L").resize((largura, altura), Image.BILINEAR),
                         dtype=np.float32)
    lo, hi = float(dep.min()), float(dep.max())
    dep = (dep - lo) / (hi - lo) if hi > lo else np.zeros_like(dep)
    return img, dep


def renderizar(imagem: Path, mapa: Path, dur: float, saida: Path,
               trajetoria: str = "lateral", amplitude: float = AMPLITUDE,
               largura: int = 1920, altura: int = 1080, fps: int = FPS,
               grade: str = "") -> Path:
    """Gera o segmento com parallax e grava em `saida`."""
    fn = TRAJETORIAS.get(trajetoria) or TRAJETORIAS["lateral"]
    img, dep = _carregar(Path(imagem), Path(mapa), largura, altura)
    n_frames = max(int(dur * fps), 2)
    desloc_max = amplitude * largura

    xs = np.arange(largura, dtype=np.float32)[None, :]
    grade_x = np.repeat(xs, altura, axis=0)
    linhas = np.arange(altura)[:, None]

    vf = f"{grade}," if grade else ""
    cmd = [FFMPEG, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{largura}x{altura}", "-r", str(fps), "-i", "-",
           *(["-vf", vf.rstrip(",")] if grade else []),
           "-c:v", "libx264", "-preset", "medium", "-crf", str(CRF),
           "-pix_fmt", "yuv420p", str(saida)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for k in range(n_frames):
            t = k / (n_frames - 1)
            d = float(fn(t)) * desloc_max
            # mapeamento INVERSO: de onde veio este pixel de saída
            origem = np.clip(np.rint(grade_x + d * dep), 0, largura - 1).astype(np.int32)
            proc.stdin.write(img[linhas, origem].tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    erro = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        raise RuntimeError(f"parallax falhou:\n{erro[-1200:]}")
    return saida
