"""Extrai os frames de um vídeo do canal de referência e monta folhas de contato.

É o passo que responde **"o que eles põem na tela"** — o `estudo_canal.py` já
responde "o que eles falam", lendo a legenda. Sem este passo os prompts de imagem
são chute; com ele são cópia de formato medida.

    python estudo_frames.py zRMtp04VHLQ                 # amostra a cada 5s
    python estudo_frames.py <URL> --cada 3
    python estudo_frames.py zRMtp04VHLQ --planos        # conta os cortes

Saída em `output/ref_thinkscience/frames/<id>/folha_NN.png`. Cada folha é uma
grade — o Claude abre elas com o Read e classifica o que aparece.

## Por que amostragem uniforme é o padrão

O modo `--planos` usa detecção de cena e responde *quantos cortes* o vídeo tem
(validado: deu 151 em `zRMtp04VHLQ`, batendo com os 151 cortes em 598s que já
tínhamos medido pela legenda). Mas ele **superdispara dentro de animação lenta** —
um travelling de 40s dentro de uma artéria vira 30 "planos" quase idênticos, e a
folha de contato passa a impressão de que o vídeo inteiro é aquilo.

Para decidir **estilo visual** o que importa é tempo de tela, e aí o certo é
amostrar em intervalo fixo. Foi essa diferença que revelou, em 31/07, que os dois
vídeos de referência usam linguagens visuais opostas — ver `PLAYBOOK.md`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CACHE = RAIZ / "output" / "ref_thinkscience" / "video"
FOLHAS = RAIZ / "output" / "ref_thinkscience" / "frames"


def _p(msg: str) -> None:
    """Título de vídeo do YouTube tem emoji e o console cp1252 do Windows estoura."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _run(cmd: list[str], desc: str) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        _p(f"  ! {desc} falhou (codigo {r.returncode})")
        _p((r.stderr or "")[-600:])
        raise SystemExit(r.returncode)
    return r


def id_do_video(alvo: str) -> str:
    if len(alvo) == 11 and re.fullmatch(r"[\w-]{11}", alvo):
        return alvo
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{11})", alvo)
    if not m:
        raise SystemExit(f"nao consegui extrair o id de: {alvo}")
    return m.group(1)


def baixar(vid: str) -> Path:
    """480p basta: a folha de contato reduz para 320px de largura de qualquer jeito."""
    CACHE.mkdir(parents=True, exist_ok=True)
    achados = list(CACHE.glob(f"{vid}.*"))
    if achados:
        _p(f"[VIDEO] {achados[0].name} ja em cache")
        return achados[0]
    _p(f"[VIDEO] baixando {vid} em <=480p...")
    _run(
        ["yt-dlp", "-f", "bv*[height<=480]/b[height<=480]", "--no-playlist",
         "-o", str(CACHE / "%(id)s.%(ext)s"), f"https://www.youtube.com/watch?v={vid}"],
        "yt-dlp",
    )
    achados = list(CACHE.glob(f"{vid}.*"))
    if not achados:
        raise SystemExit("yt-dlp terminou mas nao gravou arquivo")
    return achados[0]


def duracao(arq: Path) -> float:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", str(arq)], "ffprobe")
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def extrair(arq: Path, dest: Path, cada: float, planos: bool) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    for velho in dest.glob("f*.png"):
        velho.unlink()
    if planos:
        # limiar 0.30 calibrado contra zRMtp04VHLQ: deu 151, igual aos 151 cortes
        # que a analise da legenda ja tinha medido
        vf = "select='gt(scene,0.30)',scale=320:-2"
        extra = ["-vsync", "vfr"]
    else:
        vf = f"fps=1/{cada},scale=320:-2"
        extra = []
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(arq),
          "-vf", vf, *extra, str(dest / "f%03d.png")], "ffmpeg extract")
    return len(list(dest.glob("f*.png")))


def montar_folhas(dir_frames: Path, dest: Path, grade: str) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    for velho in dest.glob("folha_*.png"):
        velho.unlink()
    # ATENCAO: o ffmpeg desta maquina foi compilado SEM suporte a glob
    # ("Pattern type 'glob' was selected but globbing is not supported").
    # Por isso a sequencia numerada f%03d.png em vez de f*.png.
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
          "-start_number", "1", "-i", str(dir_frames / "f%03d.png"),
          "-filter_complex", f"tile={grade}:margin=6:padding=6:color=0x202020",
          str(dest / "folha_%02d.png")], "ffmpeg tile")
    return sorted(dest.glob("folha_*.png"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("alvo", help="id de 11 caracteres ou URL do YouTube")
    ap.add_argument("--cada", type=float, default=5.0,
                    help="segundos entre amostras (padrao 5)")
    ap.add_argument("--grade", default="6x5", help="grade da folha de contato (padrao 6x5)")
    ap.add_argument("--planos", action="store_true",
                    help="detecta cortes em vez de amostrar; conta planos, NAO mede tempo de tela")
    args = ap.parse_args()

    vid = id_do_video(args.alvo)
    arq = baixar(vid)
    seg = duracao(arq)

    dir_frames = FOLHAS / vid / ("planos" if args.planos else "amostras")
    n = extrair(arq, dir_frames, args.cada, args.planos)
    if args.planos:
        cortes_min = n / (seg / 60) if seg else 0
        _p(f"[PLANOS] {n} cortes detectados em {seg:.0f}s ({cortes_min:.0f}/min, "
           f"1 a cada {seg / n:.1f}s)" if n else "[PLANOS] nenhum corte detectado")
    else:
        _p(f"[AMOSTRAS] {n} frames, 1 a cada {args.cada:g}s de {seg:.0f}s")

    folhas = montar_folhas(dir_frames, FOLHAS / vid, args.grade)
    _p(f"[FOLHAS] {len(folhas)} em {(FOLHAS / vid).relative_to(RAIZ)}")
    for f in folhas:
        _p(f"  {f.relative_to(RAIZ)}")
    _p("")
    _p("Agora abra cada folha com o Read e responda, por escrito, no roteiro:")
    _p("  1. que fracao dos planos tem PESSOA na tela")
    _p("  2. claro ou escuro; ilustracao ou fotorreal")
    _p("  3. como a anatomia entra (dentro da cena, ou plano proprio)")
    _p("  4. que objetos/lugares reconheciveis aparecem")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
