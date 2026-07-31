"""A camada de direção: decide COMO cada plano é editado.

Separação de responsabilidades:

- **Aqui** ficam as decisões artísticas — que câmera, que energia, que grade,
  que ênfase. É vocabulário, não pixel.
- **No `editor.py`** fica a execução em ffmpeg.

A regra que sustenta isso: **o vocabulário é fechado e validado**. Se um roteiro
pedir `"camera": "orbit"`, `validar()` reclama e o render para. Sem isso a
direção vira decoração — o JSON fica bonito e o vídeo sai igual, porque o
executor ignorou o que não entendia.

## O que uma imagem chapada permite, de verdade

A fonte é um PNG 1920x1080. Todo movimento é transformação afim sobre ele. Isso
tem uma consequência que vale dizer em voz alta: **vários termos de cinema
descrevem o mesmo pixel se movendo.** Numa cena real, dolly (câmera anda) e zoom
(lente fecha) mudam a perspectiva de formas diferentes; num quadro plano, não há
perspectiva para mudar. Então `dolly_in` é alias de `push_in`, `truck_left` é
alias de `pan_left`, `pedestal_up` é alias de `tilt_up`. Os aliases existem para
o diretor escrever na língua dele, e estão documentados como aliases para
ninguém esperar diferença.

**Fora de alcance sem outra imagem:** orbit, drone, POV e over-the-shoulder
mudam o ponto de vista — pertencem ao prompt do SDXL, não ao editor.
**Fora de alcance sem profundidade:** rack focus e parallax. Viram possíveis com
mapa de profundidade (Depth Anything no ComfyUI), que é a fase seguinte.
"""

from __future__ import annotations

import re
import statistics

# Centro do quadro dentro do zoompan. Repetido aqui porque toda câmera parte dele.
CX = "iw/2-(iw/zoom/2)"
CY = "ih/2-(ih/zoom/2)"

# ── energia ──────────────────────────────────────────────────────────────
#
# A energia é o botão único que governa intensidade. Um plano de energia 1 e um
# de energia 5 usam a MESMA câmera com amplitudes muito diferentes — é isso que
# faz o vídeo respirar em vez de ter um ritmo só.

ENERGIA = {
    0: {"forca": 0.015, "rotulo": "silêncio",    "efeitos_ok": False},
    1: {"forca": 0.040, "rotulo": "muito calmo", "efeitos_ok": False},
    2: {"forca": 0.060, "rotulo": "calmo",       "efeitos_ok": False},
    3: {"forca": 0.085, "rotulo": "neutro",      "efeitos_ok": True},
    4: {"forca": 0.120, "rotulo": "dinâmico",    "efeitos_ok": True},
    5: {"forca": 0.175, "rotulo": "muito intenso", "efeitos_ok": True},
}
ENERGIA_PADRAO = 3


# ── câmeras ──────────────────────────────────────────────────────────────
#
# Cada função devolve (z, x, y) como expressões do zoompan do ffmpeg.
#
# ATENÇÃO ao escrever expressão nova: o filtergraph do ffmpeg separa filtros por
# vírgula, então função com mais de um argumento (min, max, if, pow) quebra a
# cadeia inteira. Por isso as curvas abaixo usam saturação algébrica
# (1-1/(1+k*t)), que dá aceleração forte sem vírgula nenhuma.


def _static(n, f):
    # Nem "static" é 100% parado: 1,5% de deriva evita o aspecto de slide.
    return f"1+{f * 0.18:.5f}*on/{n}", CX, CY


def _push_in(n, f):
    return f"1+{f:.5f}*on/{n}", CX, CY


def _push_out(n, f):
    return f"{1 + f:.5f}-{f:.5f}*on/{n}", CX, CY


def _pan_right(n, f):
    # Pan de verdade: zoom CONSTANTE e o quadro atravessa. Rampar o zoom junto
    # (como a versão antiga fazia) deixa o início sem margem para deslocar.
    return f"{1 + f:.5f}", f"(iw-iw/zoom)*on/{n}", CY


def _pan_left(n, f):
    return f"{1 + f:.5f}", f"(iw-iw/zoom)*(1-on/{n})", CY


def _tilt_down(n, f):
    return f"{1 + f:.5f}", CX, f"(ih-ih/zoom)*on/{n}"


def _tilt_up(n, f):
    return f"{1 + f:.5f}", CX, f"(ih-ih/zoom)*(1-on/{n})"


def _slow_zoom(n, f):
    return f"1+{f * 0.5:.5f}*on/{n}", CX, CY


def _fast_zoom(n, f):
    return f"1+{f * 2.0:.5f}*on/{n}", CX, CY


def _crash_zoom(n, f):
    # Quase todo o movimento nos primeiros ~25% e depois segura. É o gesto de
    # ênfase; usar fora de energia 4-5 fica gratuito.
    return f"1+{f * 2.5:.5f}*(1-1/(1+9*on/{n}))", CX, CY


def _whip_pan(n, f):
    # Varredura que satura cedo. Sem motion blur — o ffmpeg não borra dentro do
    # zoompan, então isso lê como pan muito rápido, não como whip de verdade.
    return f"{1 + f:.5f}", f"(iw-iw/zoom)*(1-1/(1+12*on/{n}))", CY


def _handheld(n, f):
    # Respiração senoidal em X e Y com períodos diferentes, senão vira círculo.
    amp = max(2.0, f * 60)
    return (f"{1 + f * 0.6:.5f}",
            f"{CX}+{amp:.2f}*sin(on/{max(n / 7.0, 1):.2f})",
            f"{CY}+{amp * 0.7:.2f}*cos(on/{max(n / 5.0, 1):.2f})")


# eixo/sentido alimentam a regra anti-repetição
CAMERAS = {
    "static":     {"fn": _static,     "eixo": "nenhum",     "sentido": "nenhum"},
    "push_in":    {"fn": _push_in,    "eixo": "profundidade", "sentido": "dentro"},
    "push_out":   {"fn": _push_out,   "eixo": "profundidade", "sentido": "fora"},
    "slow_zoom":  {"fn": _slow_zoom,  "eixo": "profundidade", "sentido": "dentro"},
    "fast_zoom":  {"fn": _fast_zoom,  "eixo": "profundidade", "sentido": "dentro"},
    "crash_zoom": {"fn": _crash_zoom, "eixo": "profundidade", "sentido": "dentro"},
    "pan_left":   {"fn": _pan_left,   "eixo": "horizontal", "sentido": "esquerda"},
    "pan_right":  {"fn": _pan_right,  "eixo": "horizontal", "sentido": "direita"},
    "whip_pan":   {"fn": _whip_pan,   "eixo": "horizontal", "sentido": "direita"},
    "tilt_up":    {"fn": _tilt_up,    "eixo": "vertical",   "sentido": "cima"},
    "tilt_down":  {"fn": _tilt_down,  "eixo": "vertical",   "sentido": "baixo"},
    "handheld":   {"fn": _handheld,   "eixo": "organico",   "sentido": "nenhum"},
}

# Mesma execução, nome diferente. Ver a nota do topo sobre imagem chapada.
ALIASES = {
    "dolly_in": "push_in",
    "dolly_out": "push_out",
    "pull_back": "push_out",
    "truck_left": "pan_left",
    "truck_right": "pan_right",
    "pedestal_up": "tilt_up",
    "pedestal_down": "tilt_down",
}

# Termos que o diretor pode pedir e que NÃO têm execução. Listados de propósito
# para o erro de validação explicar o porquê em vez de só dizer "desconhecido".
FORA_DE_ALCANCE = {
    "orbit": "muda o ponto de vista; peça outra imagem ao SDXL, não outro movimento",
    "drone": "idem orbit",
    "pov": "idem orbit",
    "over_shoulder": "idem orbit",
    "rack_focus": "precisa de mapa de profundidade (fase 2)",
    "macro": "é enquadramento de geração, não movimento: escreva no prompt da imagem",
}


# ── color script ─────────────────────────────────────────────────────────
#
# Aplicado POR ATO, não no vídeo inteiro. Cada segmento já re-encoda, então a
# grade entra ali e sai de graça. O acabamento global (grão + vinheta) fica no
# editor e continua sendo um passe só, no fim.

GRADES = {
    "frio":   "colorbalance=rs=-0.04:bs=0.06,eq=contrast=1.06:saturation=0.94",
    "neutro": "eq=contrast=1.06:saturation=1.02",
    "quente": "colorbalance=rs=0.05:bs=-0.03,eq=contrast=1.05:saturation=1.08",
    "ambar":  "colorbalance=rs=0.07:gs=0.02:bs=-0.06,eq=contrast=1.07:saturation=1.06",
    "verde":  "colorbalance=gs=0.05:bs=-0.02,eq=contrast=1.04:saturation=0.98",
    "claro":  "eq=brightness=0.035:contrast=0.98:saturation=1.05",
}

# Arco padrão quando o roteiro não declara. Abre frio (distância), passa por
# neutro (explicação), esquenta no drama e fecha claro (resolução).
ARCO_PADRAO = ["frio", "neutro", "ambar", "claro"]


def grade_dos_atos(n_atos: int, roteiro: dict) -> list:
    """Uma grade por ato. `color_script` no roteiro tem precedência."""
    pedido = roteiro.get("color_script") or []
    saida = []
    for i in range(n_atos):
        if i < len(pedido):
            saida.append(pedido[i])
        elif n_atos == 1:
            saida.append("neutro")
        else:
            # estica o arco padrão sobre o número real de atos
            pos = i / max(n_atos - 1, 1)
            saida.append(ARCO_PADRAO[min(int(pos * len(ARCO_PADRAO)), len(ARCO_PADRAO) - 1)])
    return saida


# ── ênfase de legenda ────────────────────────────────────────────────────

# Número, porcentagem, data, unidade. São as palavras que o olho procura e que
# o canal de referência reforça na tela o tempo todo.
RE_NUMERO = re.compile(r"^[^\w]*\d[\d.,:%°/-]*\s*(%|mg|g|kg|km|cm|mm|h|min|s)?[^\w]*$", re.I)


def merece_enfase(token: str, extras: set) -> bool:
    limpo = token.strip().lower().strip(".,;:!?—-\"'()")
    if limpo in extras:
        return True
    return bool(RE_NUMERO.match(token))


# ── o diretor ────────────────────────────────────────────────────────────


def resolver(nome: str) -> str:
    """Nome do roteiro -> chave real de CAMERAS."""
    n = (nome or "").strip().lower().replace(" ", "_").replace("-", "_")
    return ALIASES.get(n, n)


def _candidatas(anterior: dict | None, penultima: dict | None, energia: int) -> list:
    """A regra anti-repetição de verdade.

    A versão antiga do editor fazia `MOVIMENTOS[i % 6]`, que é repetição com
    período fixo — exatamente a sensação de slideshow que se quer evitar. Aqui a
    escolha é por EIXO: dois planos seguidos nunca se movem no mesmo eixo, e o
    sentido não pode repetir num intervalo de três.
    """
    proibido_eixo = {anterior["eixo"]} if anterior else set()
    proibido_sentido = set()
    for d in (anterior, penultima):
        if d:
            proibido_sentido.add(d["sentido"])

    nomes = [k for k, v in CAMERAS.items()
             if v["eixo"] not in proibido_eixo and v["sentido"] not in proibido_sentido]
    if not nomes:  # relaxa o sentido antes de relaxar o eixo
        nomes = [k for k, v in CAMERAS.items() if v["eixo"] not in proibido_eixo]
    if not nomes:
        nomes = list(CAMERAS)

    # gestos fortes só onde a energia justifica; em energia baixa eles gritam
    if energia <= 2:
        calmos = [k for k in nomes if k not in ("crash_zoom", "fast_zoom", "whip_pan", "handheld")]
        nomes = calmos or nomes
    if energia >= 4:
        fortes = [k for k in nomes if k not in ("static", "slow_zoom")]
        nomes = fortes or nomes
    return nomes


def _energia_do_ritmo(plano: dict, mediana_seg: float) -> int:
    """Energia default derivada da DURAÇÃO do plano, comparada à mediana do vídeo.

    O raciocínio: taxa de corte é energia. Um plano de 3s dentro de um vídeo que
    corta a cada 5s é uma aceleração deliberada, e a câmera deve acompanhar;
    um plano de 8s é uma pausa, e movimento forte ali briga com a intenção.

    Tentei antes derivar de palavras por segundo usando a âncora — não funciona,
    e vale registrar para ninguém repetir: a âncora tem sempre 5 palavras por
    construção (`PALAVRAS_ANCORA` em planejar_planos.py), então a conta divide
    uma constante e devolve o mesmo valor para todo plano. O sintoma foi o vídeo
    inteiro sair com energia 4.

    Isto é um piso, não um teto. A energia que vem do SENTIDO do texto — uma
    revelação, um alerta, um número que assusta — só sai de leitura humana (ou
    minha), escrevendo `direcao.energia` no roteiro. O automático só garante que
    o vídeo respire em vez de ter um ritmo só.
    """
    seg = plano.get("seg") or 0
    if seg <= 0 or mediana_seg <= 0:
        return ENERGIA_PADRAO
    razao = seg / mediana_seg
    if razao < 0.70:
        return 5
    if razao < 0.90:
        return 4
    if razao < 1.15:
        return 3
    if razao < 1.45:
        return 2
    return 1


def dirigir(roteiro: dict) -> dict:
    """Preenche a direção que faltar. Não sobrescreve nada declarado à mão.

    Muta o roteiro em memória de propósito: o editor chama isso uma vez no
    início e depois lê `plano["direcao"]` já resolvido.
    """
    planos = [p for c in roteiro.get("cenas", []) for p in (c.get("planos") or [])]
    if not planos:
        return roteiro

    segs = [p["seg"] for p in planos if (p.get("seg") or 0) > 0]
    mediana = statistics.median(segs) if segs else 0.0

    anterior = penultima = None
    for i, p in enumerate(planos):
        d = p.setdefault("direcao", {})
        energia = int(d.get("energia", _energia_do_ritmo(p, mediana)))
        energia = max(0, min(5, energia))
        d["energia"] = energia

        if d.get("camera"):
            nome = resolver(d["camera"])
        else:
            opcoes = _candidatas(anterior, penultima, energia)
            # determinístico: o mesmo roteiro sempre dá a mesma direção, senão
            # dois renders do mesmo vídeo divergem e a comparação fica inútil
            nome = opcoes[(i * 7 + energia * 3) % len(opcoes)]
        d["camera"] = nome
        d.setdefault("forca", round(ENERGIA[energia]["forca"], 4))
        penultima, anterior = anterior, CAMERAS[nome]
    return roteiro


def validar(roteiro: dict) -> list:
    """Devolve a lista de erros. Vazia = pode renderizar."""
    erros = []
    for c in roteiro.get("cenas", []):
        for j, p in enumerate(c.get("planos") or [], 1):
            d = p.get("direcao") or {}
            cam = d.get("camera")
            if cam:
                nome = resolver(cam)
                if nome in FORA_DE_ALCANCE:
                    erros.append(f"cena {c['n']} plano {j}: câmera '{cam}' não é executável — "
                                 f"{FORA_DE_ALCANCE[nome]}")
                elif nome not in CAMERAS:
                    erros.append(f"cena {c['n']} plano {j}: câmera '{cam}' desconhecida. "
                                 f"Conhecidas: {', '.join(sorted(CAMERAS))}")
            e = d.get("energia")
            if e is not None and (not isinstance(e, int) or not 0 <= e <= 5):
                erros.append(f"cena {c['n']} plano {j}: energia '{e}' fora de 0..5")
    for g in roteiro.get("color_script") or []:
        if g not in GRADES:
            erros.append(f"color_script: grade '{g}' desconhecida. "
                         f"Conhecidas: {', '.join(sorted(GRADES))}")
    return erros


def contraste_de(camera: str) -> str:
    """Uma câmera de eixo diferente da que veio.

    Usado quando um plano longo é picado em dois sub-planos da mesma imagem: se
    os dois pedaços se movem no mesmo eixo, o corte no meio some e o espectador
    só vê um movimento comprido.
    """
    atual = CAMERAS.get(resolver(camera))
    eixo = atual["eixo"] if atual else "profundidade"
    ordem = ["profundidade", "horizontal", "vertical", "nenhum"]
    for e in ordem:
        if e != eixo:
            for nome, spec in CAMERAS.items():
                if spec["eixo"] == e and nome not in ("whip_pan", "crash_zoom"):
                    return nome
    return "static"


def expressoes(camera: str, frames: int, forca: float) -> tuple:
    """(z, x, y) para o zoompan. É o único ponto que o editor precisa chamar."""
    nome = resolver(camera)
    spec = CAMERAS.get(nome) or CAMERAS["push_in"]
    return spec["fn"](max(frames, 2), forca)
