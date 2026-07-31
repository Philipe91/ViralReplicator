"""Executor DIAGRAMA — desenha o que a difusão não sabe desenhar.

Motivo de existir, com evidência medida em 31/07: dos 8 planos do `de_demo3`,
**5 perderam o corte anatômico**. Todo prompt que pedia "pessoa + corte do vaso
no mesmo quadro" voltou só com a pessoa — o SDXL trata como uma cena só e
descarta o elemento mais fraco. E o plano que pedia anatomia pura
("uma fileira ordenada de células arredondadas") virou padrão decorativo, porque
era conceito, não objeto.

A conclusão não é "melhorar o prompt". É **não usar difusão para isto**. Um corte
esquemático com rótulo legível é vetor: exato, barato, determinístico e — o que
mais importa — **aceita texto**, que é justamente o que a difusão faz pior.

## Como ele entra no pipeline

O diagrama gera um PNG de **quadro cheio**, com o mesmo nome que o SDXL geraria
para aquele plano (`cena_NN_pP_*.png`). Ou seja: ele SUBSTITUI a imagem daquela
batida, não se sobrepõe a ela.

Isso é de propósito e vem da mesma evidência: quando pessoa e diagrama disputam
o quadro, alguém perde. Separar em planos alternados foi o que funcionou. Como
efeito colateral, o `editor.py` não muda em nada — ele continua encontrando um
PNG onde sempre encontrou.

## Cache

O nome do arquivo carrega uma chave curta de `versão do executor + params`.
Mudar o desenho ou o texto muda a chave, o arquivo velho é apagado e o novo é
gerado. É o mesmo contrato do resto do pipeline: idempotente, mas invalidável.

## Extensão

`ARQUETIPOS` é um registro. Diagrama novo = função nova + entrada no dicionário,
sem tocar no resto. O primeiro é `corte_tubo`, porque é o que quebrou.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# SUBA ISTO sempre que o DESENHO mudar, mesmo sem mudar os params.
#
# A chave de cache é hash(VERSAO + params). Mexer no layout e esquecer de subir
# a versão deixa o PNG antigo no disco e o render sai com o desenho velho —
# aconteceu comigo na primeira revisão de margem e o sintoma é traiçoeiro:
# nada falha, o vídeo só não muda.
#   v1 -> primeira versão
#   v2 -> zona morta de baixo de 250 para 330 (a câmera corta as bordas) e
#         raio/centro reequilibrados
VERSAO = 2
LARGURA, ALTURA = 1920, 1080

# Paleta do preset `explicativo_claro`, tirada dos frames do vídeo de 5,75M:
# bege quente, verde-sálvia, luz de dia. O diagrama tem que parecer da mesma
# família das imagens geradas, senão o corte entre eles denuncia a costura.
PALETA = {
    "fundo":        (243, 238, 228, 255),
    "fundo_sombra": (232, 225, 212, 255),
    "traco":        (74, 84, 79, 255),
    "texto":        (52, 60, 56, 255),
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
# O primeiro teste ignorou o item 2 e o título ficou colado na legenda depois do
# zoom. 330px cobrem os dois casos com folga.
RODAPE_PROIBIDO = 330

# Margem lateral pela mesma razão: o pan leva o quadro para os lados.
MARGEM_LATERAL = 150

_FONTES = ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf")


def _fonte(tamanho: int, negrito: bool = False):
    alvo = _FONTES[0] if negrito else _FONTES[1]
    try:
        return ImageFont.truetype(alvo, tamanho)
    except OSError:
        try:
            return ImageFont.truetype(_FONTES[1 - int(negrito)], tamanho)
        except OSError:
            # sem TTF o texto sai bitmap e feio, mas o render não pode morrer
            return ImageFont.load_default()


def _texto_largura(d: ImageDraw.ImageDraw, txt: str, fonte) -> int:
    esq, _, dir_, _ = d.textbbox((0, 0), txt, font=fonte)
    return dir_ - esq


def _fundo(d: ImageDraw.ImageDraw):
    d.rectangle([0, 0, LARGURA, ALTURA], fill=PALETA["fundo"])
    # Sombra de base esfumada, com a cor INTERPOLADA à mão em vez de alfa.
    #
    # Armadilha do Pillow que custou uma medição: numa imagem que já é RGBA, o
    # `fill` com alfa NÃO mescla — ele substitui o pixel, alfa incluído. O valor
    # vai para o canal alfa e desaparece no `convert("RGB")` do fim, deixando a
    # faixa 100% opaca. O sintoma foi um degrau horizontal duro em y=704
    # (medido: 243,238,228 -> 232,225,212 sólido) em vez de um esfumado.
    # Interpolar a cor resolve e ainda tira a dependência da semântica de alfa.
    base, sombra = PALETA["fundo"][:3], PALETA["fundo_sombra"][:3]
    faixas = 130
    for i in range(faixas):
        t = (1 - i / faixas) ** 2          # 1 na base, 0 subindo
        cor = tuple(int(b + (s - b) * t) for b, s in zip(base, sombra))
        y = ALTURA - (i + 1) * 4
        d.rectangle([0, y, LARGURA, y + 4], fill=cor)


def _rotulo(d, texto, x, y, ancora_x, ancora_y, fonte, cor=None, lado="dir"):
    """Texto com linha-guia até o ponto que ele nomeia.

    Guia primeiro horizontal e depois diagonal (estilo "cotovelo") porque linha
    reta em diagonal cruzando o desenho polui; o cotovelo lê como técnico.
    """
    cor = cor or PALETA["texto"]
    d.line([(ancora_x, ancora_y), (x, ancora_y)], fill=PALETA["traco"], width=3)
    d.line([(x, ancora_y), (x, y)], fill=PALETA["traco"], width=3)
    d.ellipse([ancora_x - 7, ancora_y - 7, ancora_x + 7, ancora_y + 7],
              fill=PALETA["traco"])
    largura = _texto_largura(d, texto, fonte)
    tx = x + 18 if lado == "dir" else x - 18 - largura
    d.text((tx, y - 26), texto, font=fonte, fill=cor)


def corte_tubo(d: ImageDraw.ImageDraw, params: dict):
    """Corte transversal de um vaso: anéis concêntricos + rótulos.

    É o arquétipo que a difusão errou. Aqui cada camada é um anel explícito e a
    espessura do endotélio é literalmente uma linha fina — que era a informação
    que o roteiro pedia ("a espessura de uma célula só") e que saía como padrão
    abstrato quando pedida ao SDXL.
    """
    cx = int(LARGURA * 0.36)
    cy = int((ALTURA - RODAPE_PROIBIDO) * 0.54)
    r_ext = params.get("raio", 310)

    aneis = [
        (r_ext,             PALETA["musculo_esc"]),
        (int(r_ext * 0.93), PALETA["musculo"]),
        (int(r_ext * 0.66), PALETA["parede_fina"]),   # o endotélio: linha fina
        (int(r_ext * 0.63), PALETA["lumen_esc"]),
        (int(r_ext * 0.60), PALETA["lumen"]),
    ]
    for raio, cor in aneis:
        d.ellipse([cx - raio, cy - raio, cx + raio, cy + raio], fill=cor)

    # hemácias no lume, em posições FIXAS derivadas do raio — nada de random,
    # senão o mesmo JSON geraria imagens diferentes e o cache viraria mentira
    r_lumen = int(r_ext * 0.60)
    passo = max(int(r_lumen / 2.6), 30)
    for i, (dx, dy) in enumerate([(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1), (0, -2), (0, 2)]):
        px, py = cx + dx * passo, cy + dy * passo
        rr = 26 if i % 2 == 0 else 21
        if (px - cx) ** 2 + (py - cy) ** 2 < (r_lumen - rr - 8) ** 2:
            d.ellipse([px - rr, py - rr * 0.72, px + rr, py + rr * 0.72],
                      fill=PALETA["celula"])

    fonte_rot = _fonte(44, negrito=True)
    ancoras = {
        "musculo":      (cx, cy - int(r_ext * 0.965)),
        "parede":       (cx, cy - int(r_ext * 0.645)),
        "endotelio":    (cx, cy - int(r_ext * 0.645)),
        "lumen":        (cx + int(r_ext * 0.30), cy + int(r_ext * 0.30)),
        "sangue":       (cx + int(r_ext * 0.30), cy + int(r_ext * 0.30)),
    }
    coluna = cx + r_ext + 90
    for i, rot in enumerate(params.get("rotulos") or []):
        alvo = ancoras.get(rot.get("aponta", "parede"), ancoras["parede"])
        y = 190 + i * 140
        cor = PALETA["destaque"] if rot.get("destaque") else PALETA["texto"]
        _rotulo(d, rot.get("texto", ""), coluna, y, alvo[0], alvo[1], fonte_rot, cor)

    titulo = params.get("titulo")
    if titulo:
        d.text((MARGEM_LATERAL, ALTURA - RODAPE_PROIBIDO - 20), titulo,
               font=_fonte(58, negrito=True), fill=PALETA["texto"])


ARQUETIPOS = {
    "corte_tubo": corte_tubo,
}


def chave(params: dict) -> str:
    bruto = json.dumps({"v": VERSAO, "p": params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:10]


def desenhar(params: dict, saida: Path) -> Path:
    tipo = params.get("tipo", "corte_tubo")
    if tipo not in ARQUETIPOS:
        raise ValueError(
            f"arquétipo de diagrama '{tipo}' não existe. "
            f"Conhecidos: {', '.join(sorted(ARQUETIPOS))}")
    img = Image.new("RGBA", (LARGURA, ALTURA), PALETA["fundo"])
    d = ImageDraw.Draw(img, "RGBA")
    _fundo(d)
    ARQUETIPOS[tipo](d, params)
    saida.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(saida, "PNG", optimize=True)
    return saida
