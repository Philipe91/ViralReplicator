"""
Gera a trilha de fundo localmente com ACE-Step no ComfyUI.

    python comfy_musica.py                     # bed dark de 130s
    python comfy_musica.py --segundos 200 --tags "..." --seed 7

A saída vai para templates/musica/, que é a pasta que o editor.py varre. O
primeiro arquivo encontrado ali é usado como trilha (com ducking).

Por que gerar em vez de baixar: qualquer trilha "royalty free" da internet vem
com risco de Content ID no YouTube. Áudio gerado localmente é original e não
dispara claim.
"""

import argparse
from pathlib import Path

from comfy_batch import _p, _seed_for
from comfy_client import ComfyUIClient, ComfyUIError, load_workflow, patch_graph

DEST = Path(__file__).parent / "templates" / "musica"
WORKFLOW = "acestep_musica.json"

# ACE-Step é dirigido por TAGS de estilo, não por descrição em prosa.
# "instrumental" é obrigatório senão ele inventa voz cantando por cima da narração.
TAGS_DARK = (
    "instrumental, dark ambient, cinematic underscore, slow tempo, 60 bpm, "
    "low drone, sustained strings, sparse piano, minor key, tense, melancholic, "
    "no drums, no vocals, no percussion, subtle, background score, lo-fi tape hiss"
)
TAGS_NEGATIVAS = (
    "vocals, singing, voice, choir, drums, percussion, upbeat, energetic, "
    "dance, edm, distorted guitar, brass, applause, sound effects"
)


def gerar(segundos=130.0, tags=TAGS_DARK, seed_key="dark_bed_01", steps=50, cfg=5.0):
    client = ComfyUIClient()
    if not client.is_online():
        raise RuntimeError(f"ComfyUI offline em {client.base_url}")

    disp = client.available_checkpoints()
    if "ace_step_v1_3.5b.safetensors" not in disp:
        raise RuntimeError(f"ace_step_v1_3.5b.safetensors ausente. Tem: {disp}")

    grafo = load_workflow(WORKFLOW)
    g = patch_graph(
        grafo,
        seed=_seed_for(seed_key),
        steps=steps,
        cfg=cfg,
        extra={
            "VRP_LATENT_AUDIO": {"seconds": float(segundos)},
            "VRP_POSITIVE": {"tags": tags},
            "VRP_NEGATIVE": {"tags": TAGS_NEGATIVAS},
        },
    )
    DEST.mkdir(parents=True, exist_ok=True)
    _p(f"[MUSICA] gerando {segundos:g}s | seed_key={seed_key} | steps={steps}")
    paths = client.run(g, DEST, timeout=2400)
    for p in paths:
        _p(f"[MUSICA] OK  {p}")
    return paths


def main():
    ap = argparse.ArgumentParser(description="Gera trilha dark local via ACE-Step.")
    ap.add_argument("--segundos", type=float, default=130.0)
    ap.add_argument("--tags", default=TAGS_DARK)
    ap.add_argument("--seed", default="dark_bed_01", help="chave de seed (texto)")
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--cfg", type=float, default=5.0)
    args = ap.parse_args()
    try:
        gerar(args.segundos, args.tags, args.seed, args.steps, args.cfg)
    except (ComfyUIError, RuntimeError) as e:
        _p(f"[MUSICA] FALHOU: {e}")


if __name__ == "__main__":
    main()
