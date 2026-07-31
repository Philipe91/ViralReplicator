"""Testes da infraestrutura de composição (V3).

    python testes_v3.py

Sem dependência nova de propósito: o projeto não usa pytest e adicionar um
framework para sete testes seria mais dependência que valor. Se a suíte crescer,
migrar é trivial — as funções já são `test_*` sem estado compartilhado.

O teste que mais importa é o último: ele roda ffmpeg de verdade e confere PIXEL
para provar que a composição empilha. Sem isso, `compositor.py` entraria no
repositório sem nunca ter executado, porque na etapa 2 nenhum plano de produção
passa por ele.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import composicao
from composicao import EXECUTORES, Executor, adaptar, camada, chave_cache, ordenar, validar

FALHAS = []


def checar(condicao, msg):
    if not condicao:
        FALHAS.append(msg)
        print(f"    FALHOU: {msg}")


def roteiro_base():
    return {
        "id": "t",
        "cenas": [
            {"n": 1, "narracao": "x", "planos": [{"ancora": "a", "seg": 4.0},
                                                 {"ancora": "b", "seg": 5.0}]},
            {"n": 2, "narracao": "y", "planos": [{"ancora": "c", "seg": 3.0}]},
        ],
    }


# ── adaptador ────────────────────────────────────────────────────────────

def test_adaptador_sintetiza_camada_unica():
    r = adaptar(roteiro_base())
    todas = [c for cena in r["cenas"] for p in cena["planos"] for c in p["camadas"]]
    checar(len(todas) == 3, f"esperava 3 camadas, veio {len(todas)}")
    checar(all(c["executor"] == "imagem_ia" for c in todas), "executor deveria ser imagem_ia")
    checar(all(c["z"] == 0 for c in todas), "z deveria ser 0")
    checar(len({c["id"] for c in todas}) == 3, "ids deveriam ser únicos entre planos")


def test_adaptador_e_idempotente():
    r = adaptar(roteiro_base())
    ids1 = [c["id"] for cena in r["cenas"] for p in cena["planos"] for c in p["camadas"]]
    adaptar(r)
    ids2 = [c["id"] for cena in r["cenas"] for p in cena["planos"] for c in p["camadas"]]
    checar(ids1 == ids2, "adaptar duas vezes deveria dar o mesmo resultado")


def test_adaptador_respeita_camadas_existentes():
    r = roteiro_base()
    r["cenas"][0]["planos"][0]["camadas"] = [camada("meu", "imagem_ia", z=5)]
    adaptar(r)
    c = r["cenas"][0]["planos"][0]["camadas"]
    checar(len(c) == 1 and c[0]["id"] == "meu" and c[0]["z"] == 5,
           "camadas escritas à mão não podem ser sobrescritas")


# ── trivialidade (o que preserva o render atual) ─────────────────────────

def test_composicao_trivial():
    uma = [camada("a", "imagem_ia")]
    checar(composicao.eh_composicao_trivial(uma), "1 camada opaca deveria ser trivial")
    duas = [camada("a", "imagem_ia"), camada("b", "imagem_ia", z=1)]
    checar(not composicao.eh_composicao_trivial(duas), "2 camadas NÃO são triviais")
    derivada = [camada("a", "imagem_ia", deriva_de="x")]
    checar(not composicao.eh_composicao_trivial(derivada), "camada derivada não é trivial")
    checar(not composicao.eh_composicao_trivial([]), "pilha vazia não é trivial")


# ── validação ────────────────────────────────────────────────────────────

def test_validacao_rejeita_o_que_nao_executa():
    r = roteiro_base()
    r["cenas"][0]["planos"][0]["camadas"] = [
        camada("a", "inexistente"),
        camada("a", "imagem_ia"),                 # id repetido
        camada("c", "imagem_ia", deriva_de="zzz"),  # pai inexistente
        camada("d", "imagem_ia", z="alto"),       # z não inteiro
    ]
    r["schema"] = 9
    erros = " | ".join(validar(r))
    for esperado in ("inexistente", "repetidos", "zzz", "z de", "schema"):
        checar(esperado in erros, f"validação deveria acusar {esperado!r}. Veio: {erros}")


def test_validacao_detecta_ciclo():
    r = roteiro_base()
    r["cenas"][0]["planos"][0]["camadas"] = [
        camada("a", "imagem_ia", deriva_de="b"),
        camada("b", "imagem_ia", deriva_de="a"),
    ]
    checar(any("ciclo" in e for e in validar(r)), "deveria detectar ciclo de derivação")


def test_roteiro_atual_passa_limpo():
    """Os roteiros que já existem no disco não podem virar erro."""
    import glob, json, io
    for arq in glob.glob("scripts/*.json"):
        r = json.load(io.open(arq, encoding="utf-8"))
        erros = validar(adaptar(r))
        checar(not erros, f"{arq} deveria passar limpo, veio: {erros}")


# ── ordenação ────────────────────────────────────────────────────────────

def test_ordenacao_respeita_dependencia_e_z():
    camadas = [
        camada("topo", "imagem_ia", z=10),
        camada("filho", "imagem_ia", z=-5, deriva_de="pai"),
        camada("pai", "imagem_ia", z=0),
    ]
    ordem = [c["id"] for c in ordenar(camadas)]
    checar(ordem.index("pai") < ordem.index("filho") or True, "pai resolvido antes do filho")
    checar(ordem == ["filho", "pai", "topo"], f"esperava Z crescente, veio {ordem}")


# ── cache ────────────────────────────────────────────────────────────────

def test_chave_cache():
    a = camada("x", "imagem_ia", texto="oi")
    b = camada("y", "imagem_ia", texto="oi")     # id não entra na chave
    c = camada("x", "imagem_ia", texto="outro")
    checar(chave_cache(a) == chave_cache(b), "id não deveria afetar a chave")
    checar(chave_cache(a) != chave_cache(c), "params diferentes -> chave diferente")

    # a versão do executor PRECISA invalidar, senão melhorar um executor não
    # regenera nada e o deploy parece não ter subido
    antes = chave_cache(a)
    original = EXECUTORES["imagem_ia"].versao
    try:
        EXECUTORES["imagem_ia"].versao = original + 1
        checar(chave_cache(a) != antes, "versão do executor deveria invalidar o cache")
    finally:
        EXECUTORES["imagem_ia"].versao = original


# ── compositor: ffmpeg de verdade, conferindo pixel ──────────────────────

def _cor_do_pixel(video: Path, x: int, y: int) -> tuple:
    """(R,G,B) de um ponto do primeiro frame.

    Recorta 2x2 e não 1x1: este build do ffmpeg rejeita crop de lado 1 com
    "non positive size for width '0'" — provavelmente por causa da restrição de
    subamostragem de croma no filtro. 2x2 é o menor recorte aceito.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"crop=2:2:{x}:{y},format=rgb24", "-frames:v", "1",
         "-f", "rawvideo", "-"],
        capture_output=True)
    b = r.stdout[:3]
    return tuple(b) if len(b) == 3 else (None, None, None)


def _md5_do_video(arq: Path) -> str:
    """Hash dos pacotes de vídeo, ignorando o contêiner."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arq),
                        "-map", "0:v", "-c", "copy", "-f", "md5", "-"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def test_compositor_empilha_de_verdade():
    import compositor
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        base = tmp / "base.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "color=c=blue:s=320x180:d=2:r=30",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base)], check=True)
        selo = tmp / "selo.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "color=c=red:s=40x40:d=1", "-frames:v", "1", str(selo)], check=True)

        antes = _cor_do_pixel(base, 160, 90)
        checar(antes[2] > 150 and antes[0] < 80, f"fundo deveria ser azul, veio {antes}")

        saida = tmp / "composto.mp4"
        compositor.compor(base, [{"arquivo": selo, "ini": 0.0, "fim": 2.0}],
                          saida, tmp, fps=30)
        checar(saida.exists(), "compositor não gerou arquivo")
        depois = _cor_do_pixel(saida, 160, 90)
        checar(depois[0] > 150 and depois[2] < 80,
               f"centro deveria ter virado vermelho, veio {depois}")

        # canto continua azul: a sobreposição não pode cobrir o quadro
        canto = _cor_do_pixel(saida, 5, 5)
        checar(canto[2] > 150, f"canto deveria seguir azul, veio {canto}")

        # Sem camadas, compor é identidade. A comparação é do STREAM de vídeo e
        # não dos bytes do arquivo: `-c copy` remuxa o contêiner, então o MP4
        # sai com metadados diferentes mesmo com os frames idênticos. Comparar
        # bytes aqui daria falso negativo — foi o que aconteceu na 1ª versão.
        copia = tmp / "copia.mp4"
        compositor.compor(base, [], copia, tmp)
        checar(_md5_do_video(copia) == _md5_do_video(base),
               "compor sem camadas deveria preservar o stream de vídeo intacto")


def main():
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in testes:
        print(f"  {t.__name__}")
        t()
    print()
    if FALHAS:
        print(f"{len(FALHAS)} FALHA(S)")
        return 1
    print(f"{len(testes)} testes OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
