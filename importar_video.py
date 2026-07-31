"""Extrai planos e takes de um vídeo externo para reuso no pipeline.

Nasceu para testar o aproveitamento de material gerado fora (NotebookLM), e
serve igual para B-roll de banco de imagens — é a mesma operação: pegar um vídeo
pronto, quebrar em planos utilizáveis e deixá-los no formato que o editor
consome.

    python importar_video.py entrada.mp4 --nome nlm_arterias
    python importar_video.py entrada.mp4 --nome x --cortar 0,90,0,0   # tira rodapé
    python importar_video.py entrada.mp4 --nome x --takes             # + trechos de vídeo

Saída em `output/importado/<nome>/`:
    plano_001.png ...   um frame por plano detectado, resolução original
    take_001.mp4  ...   (com --takes) o trecho de vídeo daquele plano
    folha_01.png  ...   folhas de contato para inspeção
    manifesto.json      origem, corte aplicado, duração de cada plano

## O que inspecionar antes de usar

**Resolução e compressão.** Frame extraído de H.264 já vem com artefato, e no
pipeline ele ainda passa por 2-3 encodes. O manifesto registra a resolução real
para a decisão ser informada.

**Texto queimado.** Slide com rótulo escrito na imagem é inutilizável num canal
em alemão — não dá para traduzir nem reposicionar. É o motivo de existirem os
executores vetoriais. Nas folhas de contato isso salta à vista.

**Marca d'água.** `--cortar` remove margens; o corte é aplicado ANTES de qualquer
redimensionamento, e o manifesto registra o que foi cortado.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DEST = RAIZ / "output" / "importado"
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
LARGURA, ALTURA = 1920, 1080


def _p(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _run(cmd: list, desc: str, timeout=1800):
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{desc} falhou:\n{(r.stderr or '')[-1200:]}")
    return r


def sonda(arq: Path) -> dict:
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate",
                        "-show_entries", "format=duration",
                        "-of", "default=nw=1", str(arq)],
                       capture_output=True, text=True)
    d = {}
    for linha in r.stdout.splitlines():
        if "=" in linha:
            k, v = linha.split("=", 1)
            d[k] = v
    return d


def instantes_de_corte(arq: Path, limiar: float = 0.30) -> list:
    """Segundos em que a imagem muda de plano.

    Mesmo limiar do `estudo_frames.py`, e a mesma ressalva: ele superdispara
    dentro de animação lenta. Para material de slide isso é bom — cada slide
    novo é um corte de verdade.
    """
    r = subprocess.run(
        [FFMPEG, "-hide_banner", "-nostats", "-i", str(arq),
         "-filter_complex", f"select='gt(scene,{limiar})',metadata=print",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def _filtro(cortar: str | None, escalar: bool) -> str:
    partes = []
    if cortar:
        t, b, e, d = (int(x) for x in cortar.split(","))
        # corte ANTES de escalar: cortar depois espalharia a marca pelos pixels
        partes.append(f"crop=iw-{e + d}:ih-{t + b}:{e}:{t}")
    if escalar:
        partes.append(f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase")
        partes.append(f"crop={LARGURA}:{ALTURA}")
    return ",".join(partes) or "null"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("entrada")
    ap.add_argument("--nome", required=True, help="pasta de saída em output/importado/")
    ap.add_argument("--cortar", help="margens a remover em px: topo,base,esq,dir")
    ap.add_argument("--takes", action="store_true", help="exporta também o trecho de vídeo")
    ap.add_argument("--limiar", type=float, default=0.30)
    ap.add_argument("--min-seg", type=float, default=1.2,
                    help="plano mais curto que isto é descartado")
    ap.add_argument("--sem-escala", action="store_true",
                    help="mantém a resolução original em vez de ajustar para 1920x1080")
    args = ap.parse_args()

    entrada = Path(args.entrada)
    if not entrada.exists():
        _p(f"não encontrei {entrada}")
        return 1
    saida = DEST / args.nome
    saida.mkdir(parents=True, exist_ok=True)

    info = sonda(entrada)
    dur = float(info.get("duration", 0) or 0)
    _p(f"[ORIGEM] {entrada.name} — {info.get('width')}x{info.get('height')}, {dur:.0f}s")

    cortes = instantes_de_corte(entrada, args.limiar)
    marcos = [0.0] + cortes + [dur]
    planos = [(marcos[i], marcos[i + 1]) for i in range(len(marcos) - 1)
              if marcos[i + 1] - marcos[i] >= args.min_seg]
    _p(f"[PLANOS] {len(planos)} com pelo menos {args.min_seg:g}s "
       f"(de {len(cortes)} cortes detectados)")

    vf = _filtro(args.cortar, not args.sem_escala)
    manifesto = {"origem": str(entrada), "resolucao": f"{info.get('width')}x{info.get('height')}",
                 "cortar": args.cortar, "escalado": not args.sem_escala, "planos": []}

    for i, (ini, fim) in enumerate(planos, 1):
        meio = ini + (fim - ini) / 2      # o meio evita o frame de transição
        png = saida / f"plano_{i:03d}.png"
        _run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{meio:.3f}",
              "-i", str(entrada), "-vf", vf, "-frames:v", "1", str(png)],
             f"frame {i}")
        item = {"n": i, "ini": round(ini, 2), "fim": round(fim, 2),
                "seg": round(fim - ini, 2), "png": png.name}
        if args.takes:
            mp4 = saida / f"take_{i:03d}.mp4"
            _run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{ini:.3f}",
                  "-t", f"{fim - ini:.3f}", "-i", str(entrada), "-vf", vf, "-an",
                  "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                  "-pix_fmt", "yuv420p", str(mp4)], f"take {i}")
            item["mp4"] = mp4.name
        manifesto["planos"].append(item)

    (saida / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")

    # folhas de contato: é olhando que se decide o que presta
    for velho in saida.glob("folha_*.png"):
        velho.unlink()
    _run([FFMPEG, "-y", "-loglevel", "error", "-start_number", "1",
          "-i", str(saida / "plano_%03d.png"),
          "-filter_complex", "scale=320:-2,tile=5x4:margin=6:padding=6:color=0x202020",
          str(saida / "folha_%02d.png")], "folhas de contato")

    _p(f"[SAIDA] {saida.relative_to(RAIZ)}")
    _p("")
    _p("Abra as folhas de contato e descarte: slide com TEXTO queimado (não dá")
    _p("para traduzir), frame com marca d'água sobrando, e qualquer plano cuja")
    _p("compressão apareça. O que sobrar entra num plano do roteiro pelo campo")
    _p('"arquivo".')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
