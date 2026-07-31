"""Executor TIMELINE — cronologia horizontal com marcos legíveis.

Serve a batida que fala em sequência ou em decurso de tempo: "nach 20 Minuten…
nach 2 Stunden… nach 24 Stunden", ou datas históricas. É informação **ordinal**,
e ordinal se lê num eixo, não numa ilustração.

Mesma razão de existir do `exec_diagrama`: o conteúdo é essencialmente TEXTO
posicionado, e texto é exatamente o que a difusão não desenha. Pedir "uma linha
do tempo mostrando 30 minutos, 2 horas e 6 horas" ao SDXL devolve rabisco no
lugar dos números — que são justamente a informação.

## Revelação progressiva

Desde a etapa 7 a timeline pode ser animada: `"animar": true` nos params faz o
`motion.py` pedir um estado por marco e encadeá-los. Este módulo continua sem
saber animar — ele só recebe `revelados: k` e pinta os k primeiros. A lista
chega sempre inteira, para a geometria não mudar entre os estados.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import vetor_base as vb
from vetor_base import ALTURA, LARGURA, MARGEM_LATERAL, PALETA, RODAPE_PROIBIDO

#   v1 -> primeira versão
#   v2 -> honra `revelados` (geometria estável na animação)
VERSAO = 2


def _quebrar(d, texto: str, f, largura_max: int) -> list:
    """Quebra por palavra dentro da largura do slot.

    Sem isto, descrição comprida de um marco invade o marco vizinho — e como os
    marcos são centralizados no ponto, a invasão fica ambígua: o leitor não sabe
    de quem é o texto.
    """
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        tentativa = f"{atual} {p}".strip()
        if atual and vb.largura_texto(d, tentativa, f) > largura_max:
            linhas.append(atual)
            atual = p
        else:
            atual = tentativa
    if atual:
        linhas.append(atual)
    return linhas


def _centrar(px: int, largura: int) -> int:
    """x para centralizar em `px`, sem deixar o texto sair das margens seguras.

    Sem o limite, os marcos das PONTAS ficam cortados: eles são centralizados no
    ponto, e o primeiro ponto está a 190px da borda enquanto a descrição tem
    ~380px. O primeiro texto vazava para x negativo e o último para fora dos
    1920. Nas pontas, portanto, o texto deixa de ser centralizado e encosta na
    margem — que é o comportamento certo, não uma concessão.
    """
    x = px - largura // 2
    return max(MARGEM_LATERAL, min(x, LARGURA - MARGEM_LATERAL - largura))


def linha_horizontal(d, params: dict):
    pontos = params.get("pontos") or []
    if not pontos:
        return

    eixo_y = int((ALTURA - RODAPE_PROIBIDO) * 0.56)
    # As pontas do eixo recuam meia-largura de rótulo para dentro. Sem esse
    # recuo o primeiro marco fica a 190px da borda, o rótulo dele (~340px)
    # não cabe centralizado, e o limite de margem empurra o texto para cima do
    # marco vizinho — troca-se corte por colisão. Recuar resolve na origem.
    RECUO = 190
    x0, x1 = MARGEM_LATERAL + RECUO, LARGURA - MARGEM_LATERAL - RECUO

    # eixo com seta: a seta é o que diz "isto é tempo, e corre para lá"
    d.line([(x0, eixo_y), (x1, eixo_y)], fill=PALETA["traco"], width=5)
    d.polygon([(x1, eixo_y - 18), (x1 + 34, eixo_y), (x1, eixo_y + 18)],
              fill=PALETA["traco"])

    n = len(pontos)
    slot = (x1 - x0) / max(n - 1, 1) if n > 1 else 0
    f_marco = vb.fonte(52, negrito=True)
    f_texto = vb.fonte(34)
    # a goteira entre marcos vizinhos é o que impede a leitura ambígua de qual
    # descrição pertence a qual ponto
    largura_max = int((slot if n > 1 else (x1 - x0)) * 0.86) or (x1 - x0)

    visiveis = vb.revelados(params, n)
    for i, ponto in enumerate(pontos):
        if i >= visiveis:
            break          # posição já reservada; o item só ainda não apareceu
        px = int(x0 + slot * i) if n > 1 else (x0 + x1) // 2
        destaque = bool(ponto.get("destaque"))
        cor = PALETA["destaque"] if destaque else PALETA["traco"]
        raio = 22 if destaque else 10

        # haste + bolota no eixo
        d.line([(px, eixo_y - 34), (px, eixo_y + 34)], fill=cor, width=4)
        d.ellipse([px - raio, eixo_y - raio, px + raio, eixo_y + raio], fill=cor)

        marco = str(ponto.get("marco", ""))
        if marco:
            lm = vb.largura_texto(d, marco, f_marco)
            d.text((_centrar(px, lm), eixo_y - 130), marco, font=f_marco,
                   fill=PALETA["destaque"] if destaque else PALETA["texto"])

        texto = str(ponto.get("texto", ""))
        if texto:
            linhas = _quebrar(d, texto, f_texto, largura_max)
            for j, linha in enumerate(linhas[:3]):
                lt = vb.largura_texto(d, linha, f_texto)
                d.text((_centrar(px, lt), eixo_y + 66 + j * 46), linha,
                       font=f_texto, fill=PALETA["texto_fraco"])


ARQUETIPOS = {
    "linha_horizontal": linha_horizontal,
}


def chave(params: dict) -> str:
    bruto = json.dumps({"v": VERSAO, "base": vb.VERSAO, "p": params},
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:10]


def desenhar(params: dict, saida: Path) -> Path:
    params = dict(params)
    params.setdefault("tipo", "linha_horizontal")
    return vb.render(ARQUETIPOS, params, saida, "timeline")
