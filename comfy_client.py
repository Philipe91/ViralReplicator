"""
Cliente HTTP para a API do ComfyUI local (geração de imagem/vídeo 100% offline).

Não depende de nenhum outro módulo do ViralReplicator — pode ser usado solto.
Configuração via variável de ambiente:

    COMFYUI_URL   → default http://127.0.0.1:8188

Como funciona a API do ComfyUI (resumo):
    POST /prompt            → enfileira um grafo, devolve {"prompt_id": "..."}
    GET  /history/{id}      → quando o job termina, aparece aqui com os "outputs"
    GET  /view?filename=... → baixa o arquivo gerado (png/mp4/webp)

O grafo deve estar no formato "API" — no ComfyUI: menu → Workflow →
Export (API). Os nós que este cliente sabe patchear são identificados pelo
título (_meta.title), por convenção:

    VRP_POSITIVE  → CLIPTextEncode do prompt positivo
    VRP_NEGATIVE  → CLIPTextEncode do prompt negativo
    VRP_LATENT    → EmptyLatentImage (largura/altura)
    VRP_SAMPLER   → KSampler (seed/steps/cfg)

Se os títulos não existirem, cai num fallback por class_type (funciona na
maioria dos workflows txt2img simples).
"""

import io
import json
import os
import time
import urllib.parse
import uuid
from pathlib import Path

import requests

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
WORKFLOWS_DIR = Path(__file__).parent / "workflows"

# Chaves usadas pelo ComfyUI dentro de history[id]["outputs"][node] para
# listar os arquivos produzidos. Varia conforme o nó (imagem x vídeo x áudio).
OUTPUT_KEYS = ("images", "gifs", "videos", "audio")


class ComfyUIError(RuntimeError):
    pass


class ComfyUIClient:
    def __init__(self, base_url: str = COMFYUI_URL, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    # ── infraestrutura ────────────────────────────────────────────────────

    def is_online(self) -> bool:
        """True se o ComfyUI está de pé. Use antes de qualquer batch pesado."""
        try:
            r = requests.get(f"{self.base_url}/system_stats", timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def object_info(self, class_type: str = "") -> dict:
        """Introspecção: quais nós/checkpoints o ComfyUI tem instalado."""
        url = f"{self.base_url}/object_info"
        if class_type:
            url += f"/{class_type}"
        r = requests.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def available_checkpoints(self) -> list:
        """Lista os .safetensors visíveis pelo CheckpointLoaderSimple."""
        try:
            info = self.object_info("CheckpointLoaderSimple")
            opts = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
            return list(opts)
        except Exception:
            return []

    # ── fila e espera ─────────────────────────────────────────────────────

    def queue(self, graph: dict) -> str:
        payload = {"prompt": graph, "client_id": self.client_id}
        r = requests.post(f"{self.base_url}/prompt", json=payload, timeout=self.timeout)
        if r.status_code != 200:
            # O ComfyUI devolve o erro de validação do grafo no corpo — é a
            # informação mais útil quando um nó/checkpoint não existe.
            raise ComfyUIError(f"POST /prompt falhou ({r.status_code}): {r.text[:800]}")
        prompt_id = r.json().get("prompt_id")
        if not prompt_id:
            raise ComfyUIError(f"Resposta sem prompt_id: {r.text[:300]}")
        return prompt_id

    def wait(self, prompt_id: str, timeout: int = 900, poll: float = 2.0) -> dict:
        """Bloqueia até o job sair da fila. Devolve o dict de outputs.

        timeout generoso de propósito: numa RTX 3060 um clipe de vídeo passa
        fácil de 5 minutos.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=self.timeout)
                if r.status_code == 200:
                    hist = r.json().get(prompt_id)
                    if hist:
                        status = hist.get("status", {})
                        if status.get("status_str") == "error":
                            raise ComfyUIError(
                                f"Execução falhou no ComfyUI: "
                                f"{json.dumps(status.get('messages', []))[:800]}"
                            )
                        return hist.get("outputs", {})
            except requests.RequestException:
                pass  # ComfyUI ocupado/reiniciando — segue tentando até o deadline
            time.sleep(poll)
        raise ComfyUIError(f"Timeout de {timeout}s esperando o prompt {prompt_id}.")

    # ── download ──────────────────────────────────────────────────────────

    def fetch_file(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        params = urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": type_}
        )
        r = requests.get(f"{self.base_url}/view?{params}", timeout=120)
        r.raise_for_status()
        return r.content

    def upload_image(self, path, overwrite: bool = True) -> str:
        """Sobe uma imagem para a pasta input/ do ComfyUI e devolve o nome que
        o nó LoadImage deve usar. Necessário para img2video: o LoadImage só lê
        de dentro do input/ do servidor, não aceita caminho absoluto."""
        p = Path(path)
        with open(p, "rb") as fh:
            files = {"image": (p.name, fh, "image/png")}
            data = {"overwrite": "true" if overwrite else "false", "type": "input"}
            r = requests.post(
                f"{self.base_url}/upload/image", files=files, data=data, timeout=120
            )
        if r.status_code != 200:
            raise ComfyUIError(f"upload_image falhou ({r.status_code}): {r.text[:300]}")
        j = r.json()
        sub = j.get("subfolder") or ""
        return f"{sub}/{j['name']}" if sub else j["name"]

    def save_outputs(self, outputs: dict, dest_dir, prefix: str = "") -> list:
        """Baixa tudo que o job produziu para dest_dir. Devolve os paths."""
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        saved = []
        for node_id, node_out in outputs.items():
            for key in OUTPUT_KEYS:
                for i, item in enumerate(node_out.get(key, []) or []):
                    fname = item.get("filename")
                    if not fname:
                        continue
                    data = self.fetch_file(
                        fname, item.get("subfolder", ""), item.get("type", "output")
                    )
                    ext = Path(fname).suffix or ".png"
                    out_name = f"{prefix}{Path(fname).stem}{ext}" if prefix else fname
                    path = dest / out_name
                    path.write_bytes(data)
                    saved.append(path)
        return saved

    # ── atalho de alto nível ──────────────────────────────────────────────

    def run(self, graph: dict, dest_dir, prefix: str = "", timeout: int = 900) -> list:
        prompt_id = self.queue(graph)
        outputs = self.wait(prompt_id, timeout=timeout)
        return self.save_outputs(outputs, dest_dir, prefix)


# ─────────────────────────────────────────────────────────────────────────
#  Manipulação do grafo (workflow no formato API)
# ─────────────────────────────────────────────────────────────────────────


def load_workflow(name_or_path) -> dict:
    """Carrega um workflow API-format de workflows/ ou de um path absoluto."""
    p = Path(name_or_path)
    if not p.exists():
        p = WORKFLOWS_DIR / name_or_path
    if not p.exists() and p.suffix != ".json":
        p = WORKFLOWS_DIR / f"{name_or_path}.json"
    if not p.exists():
        raise FileNotFoundError(f"Workflow não encontrado: {name_or_path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _find_nodes(graph: dict, title: str = "", class_type: str = "") -> list:
    """Acha ids de nó por título (_meta.title) e/ou class_type."""
    hits = []
    for node_id, node in graph.items():
        if title and node.get("_meta", {}).get("title") != title:
            continue
        if class_type and node.get("class_type") != class_type:
            continue
        hits.append(node_id)
    return hits


def patch_graph(
    graph: dict,
    positive: str = None,
    negative: str = None,
    width: int = None,
    height: int = None,
    seed: int = None,
    steps: int = None,
    cfg: float = None,
    checkpoint: str = None,
    filename_prefix: str = None,
    extra: dict = None,
) -> dict:
    """Devolve uma CÓPIA do grafo com os campos trocados.

    Nunca muta o original — o batch reusa o mesmo template para N vídeos.
    """
    g = json.loads(json.dumps(graph))

    def set_input(node_ids, field, value):
        for nid in node_ids:
            g[nid].setdefault("inputs", {})[field] = value

    if positive is not None:
        ids = _find_nodes(g, title="VRP_POSITIVE")
        if not ids:
            # Fallback: em workflow txt2img padrão o positivo é o primeiro
            # CLIPTextEncode referenciado pelo KSampler.
            ids = _positive_by_sampler(g)
        set_input(ids, "text", positive)

    if negative is not None:
        ids = _find_nodes(g, title="VRP_NEGATIVE") or _negative_by_sampler(g)
        set_input(ids, "text", negative)

    latent_ids = _find_nodes(g, title="VRP_LATENT") or _find_nodes(
        g, class_type="EmptyLatentImage"
    )
    if width is not None:
        set_input(latent_ids, "width", width)
    if height is not None:
        set_input(latent_ids, "height", height)

    sampler_ids = _find_nodes(g, title="VRP_SAMPLER") or _find_nodes(g, class_type="KSampler")
    if seed is not None:
        for nid in sampler_ids:
            inputs = g[nid].setdefault("inputs", {})
            # KSampler usa "seed"; KSamplerAdvanced usa "noise_seed".
            inputs["noise_seed" if "noise_seed" in inputs else "seed"] = seed
    if steps is not None:
        set_input(sampler_ids, "steps", steps)
    if cfg is not None:
        set_input(sampler_ids, "cfg", cfg)

    if checkpoint is not None:
        set_input(_find_nodes(g, class_type="CheckpointLoaderSimple"), "ckpt_name", checkpoint)

    if filename_prefix is not None:
        for cls in ("SaveImage", "SaveAnimatedWEBP", "VHS_VideoCombine", "SaveVideo"):
            set_input(_find_nodes(g, class_type=cls), "filename_prefix", filename_prefix)

    # extra = {"node_id_ou_titulo": {"campo": valor}} para casos específicos
    for target, fields in (extra or {}).items():
        ids = [target] if target in g else _find_nodes(g, title=target)
        for nid in ids:
            g[nid].setdefault("inputs", {}).update(fields)

    return g


def _sampler_link(graph: dict, slot: str):
    """Ids dos CLIPTextEncode ligados ao slot 'positive'/'negative' do sampler."""
    out = []
    for nid, node in graph.items():
        if node.get("class_type") not in ("KSampler", "KSamplerAdvanced"):
            continue
        link = node.get("inputs", {}).get(slot)
        if isinstance(link, list) and link:
            out.append(str(link[0]))
    return out


def _positive_by_sampler(graph):
    return _sampler_link(graph, "positive")


def _negative_by_sampler(graph):
    return _sampler_link(graph, "negative")
