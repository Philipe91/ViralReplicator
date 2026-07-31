"""
Transforma uma thumb gerada em clipe curto (<= 5s) via LTXV 2B distilled no
ComfyUI local. Serve de intro/hook animado para o vídeo dark.

Uso:
    python comfy_video.py --top 1                  # anima a thumb do viral #1
    python comfy_video.py --thumb output/thumbs/x.png --title "..."
    python comfy_video.py --top 3 --seconds 4      # 3 clipes de 4s

Regra fixa do projeto: **teto de 5 segundos por clipe**. O LTXV exige que o
número de frames seja múltiplo de 8 mais 1 (121, 113, 97...), então a duração
real é arredondada PARA BAIXO até caber no teto — nunca estoura.

Requer no ComfyUI (D:\\ComfyUI\\models\\):
    checkpoints/ltxv-2b-0.9.8-distilled.safetensors
    text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors
"""

import argparse
import json
from pathlib import Path

from comfy_batch import _p, _seed_for, load_top_from_db
from comfy_client import ComfyUIClient, ComfyUIError, load_workflow, patch_graph

OUT_DIR = Path(__file__).parent / "output" / "clips"
WORKFLOW = "ltxv_i2v_5s.json"

MAX_SECONDS = 5.0
FPS = 25.0
STEPS = 8  # modelo distilled: 8 passos bastam, cfg 1.0

# ATENÇÃO (aprendido na prática, 29/07): com cfg=1.0 — obrigatório no distilled —
# o prompt NEGATIVO é totalmente ignorado (não há guidance para subtrair). Então
# tudo que você não quer tem que ser dito no POSITIVO, e o positivo NÃO pode
# descrever nada que já não esteja na imagem: o LTXV obedece o texto acima da
# imagem de referência e reinventa a cena. Na 1ª tentativa o prompt trazia o tema
# do vídeo ("stepmother... inheritance") e em 2,4s o modelo tinha inventado uma
# mulher andando, luz de dia e um card de texto embolado.
# Sem "névoa se movendo" aqui de propósito: quando não há cena para ancorar, o
# modelo obedece só o movimento e o frame inteiro vira parede de fumaça (foi o
# que aconteceu com o clipe de forex na 1ª rodada).
MOTION_SUFFIX = (
    "the camera slowly pushes in, almost imperceptible movement, "
    "the scene stays exactly as it is, the light flickers softly, "
    "nothing else moves, no people appear, no text and no titles on screen, "
    "locked-off tripod shot, cinematic film grain, photorealistic, consistent lighting"
)

# Mantido por completude; com cfg=1.0 não tem efeito prático.
NEGATIVE_PROMPT = (
    "static image, frozen frame, jerky motion, warped geometry, morphing faces, "
    "distorted, flickering artifacts, blurry, low quality, watermark, text, letters"
)


def frames_for(seconds: float, fps: float = FPS) -> int:
    """Maior contagem de frames valida no LTXV (n % 8 == 1) que caiba no teto."""
    seconds = min(seconds, MAX_SECONDS)
    target = int(seconds * fps)
    n = ((target - 1) // 8) * 8 + 1
    return max(n, 9)


def load_image_prompts(thumbs_dir=None) -> dict:
    """Lê output/thumbs/manifest.json → {video_id: prompt usado na imagem}.

    Reusar o prompt da imagem é o que mantém o clipe fiel à thumb: o texto
    passa a descrever exatamente a cena que já está no frame de referência,
    em vez de competir com ela.
    """
    d = Path(thumbs_dir) if thumbs_dir else (Path(__file__).parent / "output" / "thumbs")
    mf = d / "manifest.json"
    if not mf.exists():
        return {}
    try:
        return {e["id"]: e.get("prompt", "") for e in json.loads(mf.read_text(encoding="utf-8"))}
    except Exception:
        return {}


def build_motion_prompt(scene: str = "") -> str:
    """`scene` = descrição da cena que JÁ está na imagem (prompt da thumb).
    Nunca receba o título do vídeo aqui — ver comentário do MOTION_SUFFIX."""
    parts = []
    if scene:
        # 1) fora o trecho "scene evoking the theme: <TÍTULO>" — é o título do
        #    vídeo disfarçado, e é exatamente ele que faz o LTXV inventar
        #    pessoas e cards de texto (comprovado: 2 dos 6 clipes da 1ª rodada).
        # 2) fora o sufixo de estilo de thumbnail — fala de composição, não de
        #    movimento, e rouba atenção do que importa em vídeo.
        scene = scene.split("scene evoking the theme")[0]
        scene = scene.split(", cinematic thumbnail")[0].strip().strip(",").rstrip(".")
        if scene:
            parts.append(scene)
    # Sem fallback por cluster de propósito: em vídeo a cena JÁ é a imagem de
    # referência, e uma dica de cluster que não bate com ela (ex: "lugar
    # abandonado à noite" numa tela de forex) empurra o modelo pra outra cena.
    # Prompt curto é pior que prompt errado — mas prompt errado é pior ainda.
    parts.append(MOTION_SUFFIX)
    return ", ".join(p for p in parts if p)


def animate(
    items: list,
    seconds: float = MAX_SECONDS,
    width: int = 768,
    height: int = 448,
    workflow: str = WORKFLOW,
    out_dir=OUT_DIR,
    timeout: int = 1800,
) -> list:
    """items = [{'id','title','cluster','thumb_local_path'}]. Devolve os paths."""
    client = ComfyUIClient()
    if not client.is_online():
        _p(f"[ComfyUI] Offline em {client.base_url}.")
        return []

    length = frames_for(seconds)
    _p(f"[LTXV] {length} frames @ {FPS:g}fps = {length / FPS:.2f}s (teto {MAX_SECONDS:g}s)")

    base_graph = load_workflow(workflow)
    image_prompts = load_image_prompts()
    results = []

    for i, it in enumerate(items, 1):
        thumb = it.get("thumb_local_path")
        if not thumb or not Path(thumb).exists():
            _p(f"[{i}/{len(items)}] sem thumb para {it.get('id')}, pulando.")
            continue

        vid = str(it.get("id", f"noid{i}"))
        # a cena vem do prompt da própria thumb; título do vídeo NUNCA entra aqui
        scene = it.get("scene_prompt") or image_prompts.get(vid, "")
        prompt = build_motion_prompt(scene)

        server_name = client.upload_image(thumb)
        graph = patch_graph(
            base_graph,
            positive=prompt,
            negative=NEGATIVE_PROMPT,
            width=width,
            height=height,
            seed=_seed_for(vid),
            filename_prefix=f"vrp/{vid}_clip",
            extra={
                "VRP_INPUT_IMAGE": {"image": server_name},
                "VRP_LATENT": {"length": length},
                "VRP_SCHEDULER": {"steps": STEPS},
                "VRP_FRAMERATE": {"frame_rate": FPS},
            },
        )

        _p(f"[{i}/{len(items)}] Animando {vid} - {it.get('title', '')[:55]}")
        try:
            paths = client.run(graph, out_dir, timeout=timeout)
        except (ComfyUIError, OSError) as e:
            _p(f"    FALHOU: {e}")
            continue

        for p in paths:
            _p(f"    OK  {p}")
        it["clip_local_path"] = str(paths[0]) if paths else None
        results.extend(paths)

    return results


def main():
    ap = argparse.ArgumentParser(description="Anima thumbs em clipes de ate 5s (LTXV).")
    ap.add_argument("--top", type=int, default=1, help="quantos virais do banco animar")
    ap.add_argument("--thumb", default=None, help="animar um PNG especifico")
    ap.add_argument(
        "--scene",
        default="",
        help="descricao da cena JA presente na imagem (nao o titulo do video)",
    )
    ap.add_argument("--seconds", type=float, default=MAX_SECONDS)
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=448)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    if args.seconds > MAX_SECONDS:
        _p(f"[LTXV] {args.seconds}s excede o teto do projeto; usando {MAX_SECONDS:g}s.")
        args.seconds = MAX_SECONDS

    if args.thumb:
        # id do arquivo "9vsv4LL1_Ok_00001_.png" -> "9vsv4LL1_Ok" (casa com o manifest)
        stem = Path(args.thumb).stem
        vid = stem.split("_000")[0]
        items = [
            {"id": vid, "scene_prompt": args.scene, "thumb_local_path": args.thumb}
        ]
    else:
        items = load_top_from_db(args.top)
        # casa cada viral com a thumb ja gerada em output/thumbs/
        thumbs = sorted((Path(__file__).parent / "output" / "thumbs").glob("*.png"))
        for it in items:
            match = [t for t in thumbs if t.name.startswith(str(it["id"]))]
            it["thumb_local_path"] = str(match[-1]) if match else None

    animate(
        items,
        seconds=args.seconds,
        width=args.width,
        height=args.height,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
