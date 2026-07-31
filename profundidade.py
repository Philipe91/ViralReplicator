"""Estima o mapa de profundidade de uma imagem. Cacheado, determinístico.

Modelo: **Depth Anything V2 Small** (~100MB), via `transformers`. Roda na venv
do ComfyUI, que é onde há torch com CUDA — mesmo padrão já usado pelo Edge-TTS
em `produce_video.PY_COMFY`. O projeto principal continua sem depender de torch.

Custo medido na RTX 3060: ~9s para carregar o modelo (uma vez por processo) e
**~3,8s por imagem** a 1920x1080. Como o resultado é cacheado ao lado da imagem,
o custo é pago uma vez por plano.

## Por que um modelo, e não um truque

Parallax convincente precisa saber o que está perto e o que está longe. Dá para
inventar isso a partir de luminância ou de desfoque, e o resultado é
sistematicamente errado: céu claro vira "perto", sombra no primeiro plano vira
"longe". Antes de estimar profundeza de verdade, o honesto era não fazer
parallax — foi o que ficou registrado quando esta etapa foi planejada.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

RAIZ = Path(__file__).parent
PY_TORCH = Path("D:/ComfyUI/venv/Scripts/python.exe")
MODELO = "depth-anything/Depth-Anything-V2-Small-hf"
VERSAO = 1

_SCRIPT = '''
import sys
from PIL import Image
from transformers import pipeline

entrada, saida, modelo = sys.argv[1:4]
try:
    import torch
    dev = 0 if torch.cuda.is_available() else -1
except Exception:
    dev = -1
p = pipeline("depth-estimation", model=modelo, device=dev)
im = Image.open(entrada).convert("RGB")
p(im)["depth"].save(saida)
print("OK")
'''


def disponivel() -> bool:
    return PY_TORCH.exists()


def caminho_do_mapa(imagem: Path) -> Path:
    """O mapa vive ao lado da imagem, com a versão no nome.

    Versão no nome, e não num arquivo de controle à parte, pela mesma razão dos
    executores vetoriais: trocar de modelo tem que invalidar o que o modelo
    antigo produziu, sem ninguém precisar lembrar de limpar nada.
    """
    imagem = Path(imagem)
    marca = hashlib.sha256(f"{MODELO}|{VERSAO}".encode()).hexdigest()[:6]
    return imagem.with_name(f"{imagem.stem}__depth{marca}.png")


def estimar(imagem: Path, forcar: bool = False) -> Path | None:
    """Devolve o mapa (L, mesmo tamanho da imagem). None se não der para rodar.

    Devolver None em vez de estourar é deliberado: profundidade é MELHORIA, não
    requisito. Sem torch, ou sem rede na primeira execução, o plano cai no Ken
    Burns de sempre — nunca é melhor derrubar um vídeo inteiro por causa de um
    efeito opcional.
    """
    imagem = Path(imagem)
    alvo = caminho_do_mapa(imagem)
    if alvo.exists() and not forcar:
        return alvo
    if not disponivel():
        return None
    runner = imagem.parent / "_depth_runner.py"
    runner.write_text(_SCRIPT, encoding="utf-8")
    r = subprocess.run([str(PY_TORCH), str(runner), str(imagem), str(alvo), MODELO],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    runner.unlink(missing_ok=True)
    if r.returncode != 0 or not alvo.exists():
        return None
    return alvo
