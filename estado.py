"""Gera ESTADO.md — a foto de onde o projeto parou.

Regra de ouro: **nada aqui depende de alguém lembrar de anotar.** Tudo é derivado
do disco. Se a conversa fechar sem aviso (já aconteceu em 30/07), o ESTADO.md do
último turno continua correto, porque um hook roda este script ao fim de cada
resposta do Claude.

    python estado.py            # regenera ESTADO.md
    python estado.py --print    # regenera e imprime no console

Três fontes, nesta ordem de confiabilidade:

1. **O disco de produção** (`output/producao/<id>/`) — o que existe existe.
   Contagem de arquivos por etapa, comparada com o que o roteiro pede.
2. **Os transcripts das sessões** (`~/.claude/projects/*/*.jsonl`) — as últimas
   falas de cada conversa aberta sobre o projeto. É o que responde "a gente
   estava falando de quê" sem depender de ninguém ter escrito um resumo.
3. **O bloco manual** do próprio ESTADO.md, entre os marcadores MANUAL — o único
   pedaço escrito à mão, preservado a cada regeneração. É onde vai a intenção
   ("o próximo passo é X"), que o disco não tem como saber.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ROTEIROS = RAIZ / "scripts"
PRODUCAO = RAIZ / "output" / "producao"
DESTINO = RAIZ / "ESTADO.md"

MARCA_INI = "<!-- MANUAL:INICIO -->"
MARCA_FIM = "<!-- MANUAL:FIM -->"

MARCAS_DO_PIPELINE = (
    "output/producao", "output\\producao",
    "produce_video", "planejar_planos", "estudo_canal",
    "scripts/de_", "scripts\\de_",
    "PLAYBOOK.md", "03-protocolo-publicacao",
)

MANUAL_PADRAO = """\
> Este bloco é o único escrito à mão. Tudo fora dele é regerado do disco e
> qualquer edição se perde. Aqui vai a **intenção**: o próximo passo e o que
> está travado esperando decisão.

**Próximo passo:** _(ainda não definido)_

**Esperando decisão do dono:** _(nada)_
"""


def _out(msg: str) -> None:
    """Console do Windows é cp1252 e engasga com acento/emoji vindo do roteiro."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


# ── 1. estado da produção, derivado do disco ─────────────────────────────


def _porta_aberta(host: str, porta: int, timeout: float = 0.4) -> bool:
    """Teste de socket, não HTTP: precisa ser barato o bastante pra rodar a
    cada turno sem o usuário sentir."""
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            return True
    except OSError:
        return False


def carregar_roteiros() -> list[dict]:
    """Um roteiro por id. Se existir `.planejado.json`, ele ganha — é o que tem
    os planos ancorados na fala, então é o que descreve o trabalho real."""
    porid: dict[str, dict] = {}
    for arq in sorted(ROTEIROS.glob("*.json")):
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        vid = dados.get("id") or arq.stem
        planejado = arq.name.endswith(".planejado.json")
        if vid in porid and not planejado:
            continue
        porid[vid] = {"id": vid, "arquivo": arq, "dados": dados, "planejado": planejado}
    return [porid[k] for k in sorted(porid)]


def medir(roteiro: dict) -> dict:
    """Compara o que o roteiro pede com o que está gravado na pasta."""
    dados = roteiro["dados"]
    cenas = dados.get("cenas") or []
    pasta = PRODUCAO / roteiro["id"]

    planos_pedidos = sum(len(c.get("planos") or []) or 1 for c in cenas)
    clipes_pedidos = sum(1 for c in cenas if c.get("movimento"))

    def conta(sub: str, padrao: str) -> int:
        d = pasta / sub
        return len(list(d.glob(padrao))) if d.is_dir() else 0

    finais = list(pasta.glob("*_FINAL.mp4")) if pasta.is_dir() else []
    return {
        "pasta": pasta,
        "existe": pasta.is_dir(),
        "cenas": len(cenas),
        "audio": conta("audio", "cena_*.mp3"),
        "imagens": conta("imagens", "*.png"),
        "planos_pedidos": planos_pedidos,
        "clipes": conta("clipes", "*.mp4"),
        "clipes_pedidos": clipes_pedidos,
        "mudo": (pasta / "video_mudo.mp4").exists(),
        "final": finais[0] if finais else None,
        "pronto": (pasta / "PRONTO.json").exists(),
        "publicado": (pasta / "PUBLICADO.json").exists(),
    }


def selo(feito: int, pedido: int) -> str:
    if pedido == 0:
        return "—"
    if feito == 0:
        return f"⬜ 0/{pedido}"
    if feito >= pedido:
        return f"✅ {feito}/{pedido}"
    return f"🟨 {feito}/{pedido}"


def proxima_acao(m: dict, vid: str) -> str:
    """A etapa que falta. É isto que uma sessão nova lê primeiro."""
    if m["publicado"]:
        return "publicado — ciclo fechado"
    if m["pronto"]:
        return "`/publicar` (PRONTO.json na mesa)"
    if not m["cenas"]:
        return "roteiro sem cenas"
    if m["audio"] < m["cenas"]:
        return f"`python produce_video.py scripts/{vid}.json --etapa audio`"
    if m["imagens"] < m["planos_pedidos"]:
        return f"`python produce_video.py scripts/{vid}.json --etapa imagens`  (ComfyUI de pé)"
    if m["clipes"] < m["clipes_pedidos"]:
        return f"`python produce_video.py scripts/{vid}.json --etapa clipes`  (ComfyUI de pé)"
    if not m["final"]:
        return f"`python produce_video.py scripts/{vid}.json --etapa montagem`"
    return "vídeo montado — falta thumb + `PRONTO.json`"


# ── 2. o fio da conversa, lido dos transcripts ───────────────────────────


def _cauda(arq: Path, bytes_max: int = 400_000) -> list[str]:
    """Lê só o fim do arquivo. O transcript da produção passa de 17 MB e este
    script roda a cada turno — ler inteiro custaria segundos."""
    try:
        tamanho = arq.stat().st_size
        with arq.open("rb") as f:
            if tamanho > bytes_max:
                f.seek(tamanho - bytes_max)
                f.readline()  # descarta a linha partida ao meio
            bruto = f.read()
    except OSError:
        return []
    return bruto.decode("utf-8", "replace").splitlines()


def _texto_da_mensagem(d: dict) -> tuple[str, str]:
    msg = d.get("message") or {}
    conteudo = msg.get("content")
    partes: list[str] = []
    if isinstance(conteudo, str):
        partes.append(conteudo)
    elif isinstance(conteudo, list):
        for b in conteudo:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                partes.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                e = b.get("input", {})
                rot = e.get("description") or e.get("file_path") or e.get("command") or ""
                partes.append(f"[{b.get('name')}] {str(rot)[:120]}")
    return d.get("type", ""), " ".join(p for p in partes if p).strip()


def _normalizar_cwd(cwd: str) -> str:
    """Um `cd` dentro de um comando Bash muda o cwd gravado no transcript, e a
    sessão passaria a ser "retomável" de uma subpasta qualquer de output/. Se o
    caminho está dentro do projeto, a raiz é a resposta certa."""
    if not cwd:
        return ""
    try:
        p = Path(cwd).resolve()
    except (OSError, ValueError):
        return cwd
    if p == RAIZ or RAIZ in p.parents:
        return str(RAIZ)
    return str(p)


def sessoes_do_projeto(dias: int = 14) -> list[dict]:
    """Toda conversa recente que fala deste projeto — inclusive as que rodam de
    outra pasta (a produção rodava de C:\\WINDOWS\\system32)."""
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return []
    corte = time.time() - dias * 86400
    achadas = []
    for arq in base.glob("*/*.jsonl"):
        try:
            if arq.stat().st_mtime < corte:
                continue
        except OSError:
            continue
        linhas = _cauda(arq)
        if not linhas:
            continue
        bloco = "\n".join(linhas)
        # citar o nome do projeto não basta: uma conversa sobre outro repositório
        # que só consultou um commit daqui apareceria como se fosse do pipeline.
        # O crivo é ter mexido no pipeline de verdade.
        if not any(p in bloco for p in MARCAS_DO_PIPELINE):
            continue

        ultimo_usuario, ultimo_claude, acoes, cwd = "", "", [], ""
        for linha in linhas:
            linha = linha.strip()
            if not linha:
                continue
            try:
                d = json.loads(linha)
            except json.JSONDecodeError:
                continue
            # o próprio transcript guarda a pasta em que a sessão roda; o nome da
            # pasta em ~/.claude/projects não serve, porque '-' ali codifica tanto
            # '\' quanto '_' (ph-re é ph_re) e a volta é ambígua
            if d.get("cwd"):
                cwd = d["cwd"]
            tipo, txt = _texto_da_mensagem(d)
            if not txt or "<system-reminder>" in txt:
                continue
            if tipo == "user" and not txt.startswith("["):
                ultimo_usuario = txt
            elif tipo == "assistant":
                if txt.startswith("["):
                    acoes.append(txt)
                else:
                    ultimo_claude = txt
        achadas.append(
            {
                "arquivo": arq,
                "id": arq.stem,
                "pasta": _normalizar_cwd(cwd) or arq.parent.name,
                "quando": datetime.fromtimestamp(arq.stat().st_mtime),
                "usuario": ultimo_usuario,
                "claude": ultimo_claude,
                "acoes": acoes[-6:],
            }
        )
    return sorted(achadas, key=lambda s: s["quando"], reverse=True)


def _resumir(txt: str, limite: int = 260) -> str:
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt if len(txt) <= limite else txt[:limite].rstrip() + "…"


# ── 3. montagem do documento ─────────────────────────────────────────────


def bloco_manual() -> str:
    """Preserva o que foi escrito à mão entre os marcadores."""
    if DESTINO.exists():
        texto = DESTINO.read_text(encoding="utf-8")
        i, j = texto.find(MARCA_INI), texto.find(MARCA_FIM)
        if i != -1 and j > i:
            return texto[i + len(MARCA_INI) : j].strip("\n")
    return MANUAL_PADRAO


def git(*args: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], cwd=RAIZ, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def gerar() -> str:
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    comfy = _porta_aberta("127.0.0.1", 8188)
    ramo = git("rev-parse", "--abbrev-ref", "HEAD") or "?"
    sujos = len([l for l in git("status", "--porcelain").splitlines() if l.strip()])

    L: list[str] = []
    L.append("# ESTADO — onde o projeto parou")
    L.append("")
    L.append(f"_Gerado automaticamente em {agora} por `estado.py`. Não edite fora do bloco manual._")
    L.append("")
    L.append("**Se você é uma sessão nova do Claude: leia este arquivo primeiro.** Ele diz")
    L.append("o que já está no disco, o que a última conversa estava fazendo e qual é o")
    L.append("próximo comando. Depois leia `PLAYBOOK.md` (como se faz) e `CLAUDE.md` (as")
    L.append("regras que já custaram retrabalho).")
    L.append("")

    L.append("## O que fazer agora")
    L.append("")
    L.append(MARCA_INI)
    L.append(bloco_manual())
    L.append(MARCA_FIM)
    L.append("")

    L.append("## Vídeos")
    L.append("")
    L.append("| id | cenas | narração | imagens | clipes | montagem | publicação | próxima ação |")
    L.append("|---|---|---|---|---|---|---|---|")
    roteiros = carregar_roteiros()
    for r in roteiros:
        m = medir(r)
        montagem = "✅ final" if m["final"] else ("🟨 mudo" if m["mudo"] else "⬜")
        pub = "✅ no ar" if m["publicado"] else ("🟨 PRONTO" if m["pronto"] else "⬜")
        L.append(
            f"| `{r['id']}` | {m['cenas']} | {selo(m['audio'], m['cenas'])} "
            f"| {selo(m['imagens'], m['planos_pedidos'])} "
            f"| {selo(m['clipes'], m['clipes_pedidos'])} "
            f"| {montagem} | {pub} | {proxima_acao(m, r['id'])} |"
        )
    if not roteiros:
        L.append("| _nenhum roteiro em `scripts/`_ | | | | | | | |")
    L.append("")
    for r in roteiros:
        m = medir(r)
        if m["final"]:
            try:
                mb = m["final"].stat().st_size / 1_048_576
                L.append(f"- `{r['id']}` → vídeo final: `{m['final'].relative_to(RAIZ)}` ({mb:.0f} MB)")
            except (OSError, ValueError):
                pass
    L.append("")

    L.append("## Serviços e repositório")
    L.append("")
    L.append(f"- **ComfyUI** (`127.0.0.1:8188`): {'🟢 no ar' if comfy else '🔴 fora'}"
             + ("" if comfy else " — sobe com `D:\\ComfyUI\\iniciar_comfyui.bat`."
                                 " Etapas `imagens` e `clipes` falham sem ele."))
    L.append(f"- **git**: ramo `{ramo}`, {sujos} arquivo(s) não commitado(s)")
    ultimo = git("log", "-1", "--format=%h %s")
    if ultimo:
        L.append(f"- último commit: `{ultimo}`")
    L.append("")

    L.append("## Conversas em aberto")
    L.append("")
    L.append("Sessões do Claude Code que tocaram este projeto nos últimos 14 dias, da mais")
    L.append("recente para a mais antiga. Para reabrir uma: entre na pasta indicada e rode")
    L.append("`claude --resume` (ou `claude --resume <id>`).")
    L.append("")
    for s in sessoes_do_projeto():
        L.append(f"### `{s['pasta']}` — {s['quando'].strftime('%d/%m %H:%M')}")
        L.append("")
        L.append(f"- retomar: `cd \"{s['pasta']}\"` → `claude --resume {s['id']}`")
        if s["usuario"]:
            L.append(f"- **última fala do dono:** {_resumir(s['usuario'])}")
        if s["claude"]:
            L.append(f"- **última resposta do Claude:** {_resumir(s['claude'])}")
        if s["acoes"]:
            L.append(f"- últimas ações: {', '.join(_resumir(a, 60) for a in s['acoes'])}")
        L.append("")
    L.append("")

    L.append("---")
    L.append("")
    L.append("Mapa de leitura: `ESTADO.md` (onde parou) → `PLAYBOOK.md` (como se faz um")
    L.append("vídeo) → `CLAUDE.md` (regras que não devem voltar) → `docs/03-protocolo-publicacao.md`")
    L.append("(contrato produção↔postagem) → `BRIEFING-CANAL-DE.md` (o canal alemão).")
    return "\n".join(L) + "\n"


def main() -> int:
    texto = gerar()
    DESTINO.write_text(texto, encoding="utf-8")
    if "--print" in sys.argv:
        _out(texto)
    else:
        _out(f"ESTADO.md atualizado ({len(texto.splitlines())} linhas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
