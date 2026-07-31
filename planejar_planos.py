"""
Fatia a narração em BATIDAS e monta o plano de edição a partir do texto falado.

A regra do projeto: o texto falado manda. Cada batida de ~5s de fala vira um
plano, e cada plano recebe uma âncora — o trecho exato que a narração diz
naquele instante. O editor usa a âncora para trocar a imagem no momento certo,
em vez de dividir a cena em fatias iguais.

    python planejar_planos.py scripts/de_01_arterien.json
    python planejar_planos.py <roteiro> --alvo 5.0 --animar-cada 4

Escreve <roteiro>.planejado.json com os planos já montados. Os prompts de
imagem ficam em branco para serem preenchidos — o corte e o tempo são
mecânicos, a escolha visual não é.

REGRA DE OURO das imagens: nunca pedir texto, rótulo, diagrama ou legenda
dentro da imagem. Difusão desenha letra como garatuja. Todo texto do vídeo
(legenda e rótulo técnico) é desenhado depois, por ffmpeg, em vetor.
"""

import argparse
import json
import wave
from pathlib import Path

RAIZ = Path(__file__).parent

ALVO_SEG = 5.0          # duração alvo de uma batida
MIN_SEG = 2.5           # abaixo disso a batida é fundida na anterior
PAUSA_FORTE = 0.28      # respiração da narração: ponto natural de corte
PALAVRAS_ANCORA = 5     # quantas palavras entram na âncora


def carregar_palavras(base: Path, n: int):
    js = base / "audio" / f"cena_{n:02d}_palavras.json"
    wav = base / "audio" / f"cena_{n:02d}.wav"
    if not js.exists() or not wav.exists():
        return None, None
    with wave.open(str(wav)) as f:
        dur = f.getnframes() / f.getframerate()
    return json.loads(js.read_text(encoding="utf-8")), dur


def fatiar(cena: dict, palavras: list, dur: float, alvo=ALVO_SEG) -> list:
    """Corta a cena em batidas de ~alvo segundos, preferindo respiro e pontuação.

    Não corta em qualquer palavra: procura o fim de frase ou uma pausa real na
    fala. Trocar de imagem no meio de uma oração fica pior que segurar mais um
    segundo.
    """
    tokens = cena["narracao"].split()
    usar_original = len(tokens) == len(palavras)
    itens = [{"txt": (tokens[i] if usar_original else w["p"]),
              "ini": w["ini"], "fim": w["fim"]} for i, w in enumerate(palavras)]

    batidas, atual = [], []
    for i, w in enumerate(itens):
        atual.append(w)
        decorrido = w["fim"] - atual[0]["ini"]
        prox = itens[i + 1] if i + 1 < len(itens) else None
        pausa = (prox["ini"] - w["fim"]) if prox else 99.0
        fim_frase = w["txt"].endswith((".", "!", "?", ":", ";"))
        virgula = w["txt"].endswith(",")

        bom_corte = fim_frase or pausa >= PAUSA_FORTE or virgula
        # teto duro em 1,4x o alvo: com 1,8x apareciam planos de 9s, que é
        # justamente o que faz o vídeo parecer lento. Preferir corte em respiro,
        # mas nunca segurar além do teto.
        if prox is None or (decorrido >= alvo and bom_corte) or decorrido >= alvo * 1.4:
            batidas.append(atual)
            atual = []
    if atual:
        batidas.append(atual)

    # funde batida curta demais na anterior
    fundidas = []
    for b in batidas:
        d = b[-1]["fim"] - b[0]["ini"]
        if fundidas and d < MIN_SEG:
            fundidas[-1].extend(b)
        else:
            fundidas.append(b)

    saida = []
    for b in fundidas:
        saida.append({
            "ancora": " ".join(w["txt"] for w in b[:PALAVRAS_ANCORA]),
            "fala": " ".join(w["txt"] for w in b),
            "ini": round(b[0]["ini"], 2),
            "dur": round(b[-1]["fim"] - b[0]["ini"], 2),
        })
    return saida


def planejar(roteiro: dict, base: Path, alvo=ALVO_SEG, animar_cada=4) -> dict:
    novo = json.loads(json.dumps(roteiro))
    total_planos = total_clipes = 0
    faltando_audio = []

    for cena in novo["cenas"]:
        palavras, dur = carregar_palavras(base, cena["n"])
        if not palavras:
            faltando_audio.append(cena["n"])
            continue
        batidas = fatiar(cena, palavras, dur, alvo)
        planos = []
        for i, b in enumerate(batidas):
            # a 1ª batida da cena e depois a cada `animar_cada` viram clipe
            animar = (i % animar_cada == 0) and b["dur"] >= 3.5
            planos.append({
                "ancora": b["ancora"],
                "fala": b["fala"],          # referência para escrever o prompt
                "seg": b["dur"],
                "animar": animar,
                "imagem": "",               # a preencher
            })
            total_planos += 1
            total_clipes += 1 if animar else 0
        cena["planos"] = planos
        cena.pop("imagem", None)
        cena["movimento"] = any(p["animar"] for p in planos)

    novo["_plano_de_edicao"] = {
        "alvo_segundos_por_plano": alvo,
        "planos": total_planos,
        "clipes_animados": total_clipes,
        "imagens_estaticas": total_planos - total_clipes,
    }
    if faltando_audio:
        novo["_plano_de_edicao"]["cenas_sem_audio"] = faltando_audio
    return novo


def main():
    ap = argparse.ArgumentParser(description="Fatia a narração em planos ancorados na fala.")
    ap.add_argument("roteiro")
    ap.add_argument("--alvo", type=float, default=ALVO_SEG)
    ap.add_argument("--animar-cada", type=int, default=4,
                    help="1 clipe animado a cada N planos (0 = nenhum)")
    ap.add_argument("--saida", default=None)
    args = ap.parse_args()

    p = Path(args.roteiro)
    roteiro = json.loads(p.read_text(encoding="utf-8"))
    base = RAIZ / "output" / "producao" / roteiro["id"]
    novo = planejar(roteiro, base, args.alvo, args.animar_cada or 10**6)

    dest = Path(args.saida) if args.saida else p.with_suffix(".planejado.json")
    dest.write_text(json.dumps(novo, ensure_ascii=False, indent=2), encoding="utf-8")

    info = novo["_plano_de_edicao"]
    print(f"alvo por plano   : {info['alvo_segundos_por_plano']}s")
    print(f"planos totais    : {info['planos']}")
    print(f"  animados (LTXV): {info['clipes_animados']}")
    print(f"  estaticos      : {info['imagens_estaticas']}")
    if "cenas_sem_audio" in info:
        print(f"  SEM AUDIO      : cenas {info['cenas_sem_audio']} (rode --etapa audio antes)")
    print()
    for cena in novo["cenas"][:3]:
        print(f"-- cena {cena['n']}")
        for pl in cena.get("planos", []):
            tipo = "CLIPE" if pl["animar"] else "img  "
            print(f"   {tipo} {pl['seg']:>5.1f}s  ancora: {pl['ancora'][:46]}")
    print(f"\n-> {dest}")


if __name__ == "__main__":
    main()
