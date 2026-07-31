"""
Geração em lote de thumbnails (e clipes) locais via ComfyUI, alimentada pelos
virais já detectados pelo ViralReplicator.

Dois modos de uso:

1) CLI — pega os top N virais do banco e gera as thumbs:
       python comfy_batch.py --top 5
       python comfy_batch.py --top 3 --checkpoint juggernautXL_v9.safetensors
       python comfy_batch.py --top 5 --dry-run        # só imprime os prompts

2) Dentro do pipeline (main.py / app_pro.py), depois do idea_generator:
       from comfy_batch import generate_thumbnails
       videos = generate_thumbnails(videos, limit=5)
       # cada vídeo ganha v['thumb_local_path'] (ou None se falhou)

Requer o ComfyUI rodando em COMFYUI_URL (default http://127.0.0.1:8188).
Nada aqui altera o banco nem os módulos existentes — a saída vai para
output/thumbs/ e o caminho é devolvido em memória.
"""

import argparse
import json
import sqlite3
import sys
import zlib
from pathlib import Path

from comfy_client import ComfyUIClient, ComfyUIError, load_workflow, patch_graph

try:
    from storage import DB_NAME
except Exception:  # storage indisponível → mantém o default do projeto
    DB_NAME = "viral_replicator_v3.db"

OUT_DIR = Path(__file__).parent / "output" / "thumbs"
DEFAULT_WORKFLOW = "sdxl_thumbnail.json"

# Estilo base de thumb dark/faceless — o que faz CTR nesse nicho é contraste
# alto, um único ponto focal e clima de mistério.
STYLE_SUFFIX = (
    "cinematic thumbnail, dramatic rim lighting, high contrast, dark moody atmosphere, "
    "single clear focal point, shallow depth of field, teal and orange grade, "
    "photorealistic, sharp details, 16:9 composition with empty space on the right for text"
)

# Texto dentro da imagem sai torto em difusão — pedimos que NÃO apareça e o
# título vai depois no editor/Canva, em cima do espaço vazio reservado acima.
NEGATIVE_PROMPT = (
    "text, letters, words, numbers, typography, gibberish text, garbled letters, fake writing, "
    "signs, banners, labels, watermark, logo, signature, caption, subtitles, "
    "blurry, low quality, jpeg artifacts, deformed hands, extra fingers, mutated anatomy, "
    "cartoon, anime, flat illustration, cluttered composition, washed out colors"
)

# Dicas visuais por cluster/nicho detectado pelo pattern_detector.
# REGRA: nada de objeto que naturalmente tem escrita (fita de isolamento,
# documento, placa, jornal). SDXL insiste em desenhar letras neles e sai
# rabisco ilegível — testado em 29/07, a fita de "police tape" saiu com
# texto embolado apesar do prompt negativo.
CLUSTER_HINTS = {
    "mistério": "abandoned place at night, fog, one distant light source, unsettling silence",
    "misterio": "abandoned place at night, fog, one distant light source, unsettling silence",
    "true crime": "rain-streaked window at night, single lit doorway down a dark hallway, cold blue light",
    "crime": "rain-streaked window at night, single lit doorway down a dark hallway, cold blue light",
    "documentário": "archival film grain, dust in a beam of light, weathered wooden desk, sepia tone",
    "documentario": "archival film grain, dust in a beam of light, weathered wooden desk, sepia tone",
    "história": "ancient ruins, dramatic sky, weathered stone, epic scale",
    "historia": "ancient ruins, dramatic sky, weathered stone, epic scale",
    "psicologia": "silhouette of a head in shadow, cracked mirror, cold blue light",
    "conspiração": "dark control room, glowing surveillance monitors, tangled cables, cold green light",
    "conspiracao": "dark control room, glowing surveillance monitors, tangled cables, cold green light",
    "ia": "glowing neural structure in the dark, server room, cold cyan light",
    "tecnologia": "glowing neural structure in the dark, server room, cold cyan light",
}


def _p(msg: str):
    """print() à prova de console cp1252 — títulos do YouTube vêm cheios de
    emoji e o terminal do Windows estoura com UnicodeEncodeError."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


def build_thumb_prompt(title: str, cluster: str = "", hint: str = "") -> str:
    """Monta o prompt visual. `hint` vem do idea_generator quando disponível
    (generated_ideas.sugestoes.thumbnail); senão usamos o cluster."""
    parts = []
    if hint:
        parts.append(hint.strip().rstrip("."))
    else:
        key = (cluster or "").strip().lower()
        for k, v in CLUSTER_HINTS.items():
            if k in key:
                parts.append(v)
                break
    # O título entra como assunto/tema, não como texto a ser desenhado.
    if title:
        parts.append(f"scene evoking the theme: {title.strip()}")
    parts.append(STYLE_SUFFIX)
    return ", ".join(p for p in parts if p)


def _seed_for(video_id: str) -> int:
    """Seed determinística por vídeo — regerar dá a mesma imagem, e mudar o
    prompt/checkpoint é a única variável. Facilita comparar workflows."""
    return zlib.crc32(str(video_id).encode()) % (2**31)


def load_top_from_db(limit: int = 5, db_name: str = None) -> list:
    """Top N virais por viral_score, no formato que o batch espera."""
    conn = sqlite3.connect(db_name or DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, title, pt_br_title, cluster, niche, viral_score "
            "FROM videos ORDER BY viral_score DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "pt_br_title": r["pt_br_title"] or "",
            "cluster": r["cluster"] or r["niche"] or "",
            "viral_score": r["viral_score"],
        }
        for r in rows
    ]


def generate_thumbnails(
    videos: list,
    limit: int = None,
    workflow: str = DEFAULT_WORKFLOW,
    checkpoint: str = None,
    width: int = 1344,
    height: int = 768,
    steps: int = None,
    out_dir=OUT_DIR,
    dry_run: bool = False,
    timeout: int = 900,
) -> list:
    """Gera 1 thumb por vídeo. Devolve a mesma lista com 'thumb_local_path'.

    Falha de um vídeo não derruba o lote — o campo fica None e segue.
    """
    targets = videos[:limit] if limit else videos

    if dry_run:
        for v in targets:
            hint = (v.get("generated_ideas", {}).get("sugestoes", {}) or {}).get("thumbnail", "")
            _p(f"\n[{v.get('id')}] {v.get('title', '')[:70]}")
            _p(f"  -> {build_thumb_prompt(v.get('title', ''), v.get('cluster', ''), hint)}")
        return videos

    client = ComfyUIClient()
    if not client.is_online():
        _p(
            f"[ComfyUI] Offline em {client.base_url}. "
            "Suba o ComfyUI (run_nvidia_gpu.bat) e rode de novo."
        )
        for v in targets:
            v["thumb_local_path"] = None
        return videos

    base_graph = load_workflow(workflow)

    # Valida o checkpoint antes de queimar tempo: erro de ckpt_name é o
    # motivo nº1 de 400 no /prompt.
    available = client.available_checkpoints()
    if checkpoint and available and checkpoint not in available:
        _p(f"[ComfyUI] Checkpoint '{checkpoint}' não existe. Disponíveis: {available}")
        return videos
    if not checkpoint and available:
        current = base_graph.get("4", {}).get("inputs", {}).get("ckpt_name")
        if current not in available:
            checkpoint = available[0]
            _p(f"[ComfyUI] Checkpoint do workflow ausente; usando '{checkpoint}'.")

    manifest = []
    for i, v in enumerate(targets, 1):
        vid = str(v.get("id", f"noid{i}"))
        title = v.get("title", "")
        hint = (v.get("generated_ideas", {}).get("sugestoes", {}) or {}).get("thumbnail", "")
        prompt = build_thumb_prompt(title, v.get("cluster", ""), hint)

        graph = patch_graph(
            base_graph,
            positive=prompt,
            negative=NEGATIVE_PROMPT,
            width=width,
            height=height,
            seed=_seed_for(vid),
            steps=steps,
            checkpoint=checkpoint,
            filename_prefix=f"vrp/{vid}",
        )

        _p(f"[{i}/{len(targets)}] Gerando thumb de {vid} - {title[:60]}")
        try:
            # sem prefix: o filename_prefix "vrp/{vid}" já nomeia o arquivo
            paths = client.run(graph, out_dir, timeout=timeout)
        except (ComfyUIError, OSError) as e:
            _p(f"    FALHOU: {e}")
            v["thumb_local_path"] = None
            continue

        v["thumb_local_path"] = str(paths[0]) if paths else None
        _p(f"    OK  {v['thumb_local_path']}")
        manifest.append({
            "id": vid,
            "title": title,
            "pt_br_title": v.get("pt_br_title", ""),
            "prompt": prompt,
            "files": [str(p) for p in paths],
        })

    if manifest:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return videos


def main():
    ap = argparse.ArgumentParser(description="Gera thumbs dos virais via ComfyUI local.")
    ap.add_argument("--top", type=int, default=5, help="quantos virais pegar do banco")
    ap.add_argument("--workflow", default=DEFAULT_WORKFLOW, help="workflow API-format em workflows/")
    ap.add_argument("--checkpoint", default=None, help="ex: juggernautXL_v9.safetensors")
    ap.add_argument("--width", type=int, default=1344)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=900, help="segundos por geração")
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--dry-run", action="store_true", help="só mostra os prompts")
    args = ap.parse_args()

    videos = load_top_from_db(args.top)
    if not videos:
        print("Nenhum viral no banco. Rode `python main.py` primeiro.")
        return

    generate_thumbnails(
        videos,
        workflow=args.workflow,
        checkpoint=args.checkpoint,
        width=args.width,
        height=args.height,
        steps=args.steps,
        out_dir=args.out,
        dry_run=args.dry_run,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
