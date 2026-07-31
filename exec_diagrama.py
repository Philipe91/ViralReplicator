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

O nome do arquivo carrega uma chave curta de `versão + params`. Mudar o desenho
ou o texto muda a chave, o arquivo velho é apagado e o novo é gerado.

## Extensão

`ARQUETIPOS` é um registro. Diagrama novo = função nova + entrada no dicionário,
sem tocar no resto. O primeiro é `corte_tubo`, porque é o que quebrou.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import vetor_base as vb
from vetor_base import ALTURA, LARGURA, PALETA, RODAPE_PROIBIDO

# SUBA ISTO sempre que o DESENHO mudar, mesmo sem mudar os params.
#
# A chave de cache é hash(VERSAO + versão da base + params). Mexer no layout e
# esquecer de subir a versão deixa o PNG antigo no disco e o render sai com o
# desenho velho — aconteceu comigo na primeira revisão de margem e o sintoma é
# traiçoeiro: nada falha, o vídeo só não muda.
#   v1 -> primeira versão
#   v2 -> zona morta de baixo de 250 para 330 (a câmera corta as bordas) e
#         raio/centro reequilibrados
#   v3 -> paleta, fontes, fundo e título movidos para vetor_base (refatoração
#         pura: o PNG sai idêntico ao de v2, só a chave muda)
VERSAO = 3


def corte_tubo(d, params: dict):
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

    f_rot = vb.fonte(44, negrito=True)
    ancoras = {
        "musculo":   (cx, cy - int(r_ext * 0.965)),
        "parede":    (cx, cy - int(r_ext * 0.645)),
        "endotelio": (cx, cy - int(r_ext * 0.645)),
        "lumen":     (cx + int(r_ext * 0.30), cy + int(r_ext * 0.30)),
        "sangue":    (cx + int(r_ext * 0.30), cy + int(r_ext * 0.30)),
    }
    coluna = cx + r_ext + 90
    for i, rot in enumerate(params.get("rotulos") or []):
        alvo = ancoras.get(rot.get("aponta", "parede"), ancoras["parede"])
        y = 190 + i * 140
        cor = PALETA["destaque"] if rot.get("destaque") else PALETA["texto"]
        _rotulo(d, rot.get("texto", ""), coluna, y, alvo[0], alvo[1], f_rot, cor)


def _rotulo(d, texto, x, y, ancora_x, ancora_y, f, cor=None, lado="dir"):
    """Texto com linha-guia até o ponto que ele nomeia.

    Guia primeiro horizontal e depois diagonal (estilo "cotovelo") porque linha
    reta em diagonal cruzando o desenho polui; o cotovelo lê como técnico.
    """
    cor = cor or PALETA["texto"]
    d.line([(ancora_x, ancora_y), (x, ancora_y)], fill=PALETA["traco"], width=3)
    d.line([(x, ancora_y), (x, y)], fill=PALETA["traco"], width=3)
    d.ellipse([ancora_x - 7, ancora_y - 7, ancora_x + 7, ancora_y + 7],
              fill=PALETA["traco"])
    largura = vb.largura_texto(d, texto, f)
    tx = x + 18 if lado == "dir" else x - 18 - largura
    d.text((tx, y - 26), texto, font=f, fill=cor)


ARQUETIPOS = {
    "corte_tubo": corte_tubo,
}


def chave(params: dict) -> str:
    bruto = json.dumps({"v": VERSAO, "base": vb.VERSAO, "p": params},
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:10]


def desenhar(params: dict, saida: Path) -> Path:
    params = dict(params)
    params.setdefault("tipo", "corte_tubo")
    return vb.render(ARQUETIPOS, params, saida, "diagrama")
