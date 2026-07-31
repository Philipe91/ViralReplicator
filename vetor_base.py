"""Base comum dos executores vetoriais: paleta, fontes, zonas seguras e fundo.

Extraído quando o segundo executor vetorial (timeline) nasceu. Manter cada
executor com sua própria cópia da paleta produziria exatamente a divergência
silenciosa que a auditoria de 31/07 encontrou entre `editor.py` e
`produce_video.py`: alguém ajusta a cor num e não no outro, e os cortes entre
diagrama e timeline passam a denunciar a costura.

## VERSAO entra na chave de cache dos executores

Mudança AQUI muda o desenho de TODOS os executores vetoriais. Se a versão da
base não entrasse na chave, um ajuste de paleta deixaria todos os PNGs antigos
no disco — o mesmo modo de falha silencioso que já me pegou uma vez no
`exec_diagrama` (nada falha, o vídeo só não muda).

    v1 -> extração inicial a partir de exec_diagrama v2
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

VERSAO = 1

LARGURA, ALTURA = 1920, 1080

# Paleta do preset `explicativo_claro`, tirada dos frames do vídeo de 5,75M do
# canal de referência: bege quente, verde-sálvia, luz de dia. O vetor tem que
# parecer da mesma família das imagens geradas, senão o corte entre eles
# denuncia a costura.
PALETA = {
    "fundo":        (243, 238, 228, 255),
    "fundo_sombra": (232, 225, 212, 255),
    "traco":        (74, 84, 79, 255),
    "texto":        (52, 60, 56, 255),
    "texto_fraco":  (118, 126, 120, 255),
    "musculo":      (168, 182, 160, 255),
    "musculo_esc":  (140, 156, 134, 255),
    "parede_fina":  (247, 250, 245, 255),
    "lumen":        (198, 122, 118, 255),
    "lumen_esc":    (176, 100, 96, 255),
    "celula":       (156, 74, 72, 255),
    "destaque":     (222, 158, 74, 255),
}

# Zona morta de baixo. Duas coisas a acomodar, não uma:
#
# 1. a legenda queimada ocupa a faixa inferior (MARGEM_V=110 + corpo 78 em
#    editor.py);
# 2. a CÂMERA corta as bordas. Um `push_in` com força 0,175 (energia 5) mostra
#    só ~82% do quadro, o que come mais ~95px em cima e embaixo.
#
# A primeira versão do diagrama ignorou o item 2 e o título ficou colado na
# legenda depois do zoom. 330px cobrem os dois casos com folga.
RODAPE_PROIBIDO = 330
MARGEM_LATERAL = 150
TOPO_SEGURO = 120

_FONTES = ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf")


def fonte(tamanho: int, negrito: bool = False):
    alvo = _FONTES[0] if negrito else _FONTES[1]
    try:
        return ImageFont.truetype(alvo, tamanho)
    except OSError:
        try:
            return ImageFont.truetype(_FONTES[1 - int(negrito)], tamanho)
        except OSError:
            # sem TTF o texto sai bitmap e feio, mas o render não pode morrer
            return ImageFont.load_default()


def largura_texto(d: ImageDraw.ImageDraw, txt: str, f) -> int:
    esq, _, dir_, _ = d.textbbox((0, 0), txt, font=f)
    return dir_ - esq


def desenhar_fundo(d: ImageDraw.ImageDraw):
    """Fundo bege com sombra esfumada na base.

    A cor é INTERPOLADA à mão em vez de usar alfa. Armadilha do Pillow que
    custou uma medição: numa imagem que já é RGBA, o `fill` com alfa NÃO mescla
    — ele substitui o pixel, alfa incluído, e o valor desaparece no
    `convert("RGB")` do fim, deixando a faixa 100% opaca. O sintoma foi um
    degrau horizontal duro em y=704 (medido: 243,238,228 -> 232,225,212 sólido)
    em vez de um esfumado.
    """
    d.rectangle([0, 0, LARGURA, ALTURA], fill=PALETA["fundo"])
    base, sombra = PALETA["fundo"][:3], PALETA["fundo_sombra"][:3]
    faixas = 130
    for i in range(faixas):
        t = (1 - i / faixas) ** 2          # 1 na base, 0 subindo
        cor = tuple(int(b + (s - b) * t) for b, s in zip(base, sombra))
        y = ALTURA - (i + 1) * 4
        d.rectangle([0, y, LARGURA, y + 4], fill=cor)


def titulo_do_quadro(d: ImageDraw.ImageDraw, texto: str):
    """Título no rodapé seguro, acima da faixa da legenda."""
    if not texto:
        return
    d.text((MARGEM_LATERAL, ALTURA - RODAPE_PROIBIDO - 20), texto,
           font=fonte(58, negrito=True), fill=PALETA["texto"])


def render(arquetipos: dict, params: dict, saida, rotulo_executor: str):
    """Esqueleto comum: cria o quadro, pinta o fundo, despacha, grava.

    `arquetipos` é o registro do executor que chamou — é o que mantém cada
    executor dono dos seus próprios desenhos enquanto compartilha a moldura.
    """
    tipo = params.get("tipo")
    if tipo not in arquetipos:
        raise ValueError(
            f"arquétipo de {rotulo_executor} '{tipo}' não existe. "
            f"Conhecidos: {', '.join(sorted(arquetipos))}")
    img = Image.new("RGBA", (LARGURA, ALTURA), PALETA["fundo"])
    d = ImageDraw.Draw(img, "RGBA")
    desenhar_fundo(d)
    arquetipos[tipo](d, params)
    titulo_do_quadro(d, params.get("titulo", ""))
    saida.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(saida, "PNG", optimize=True)
    return saida
