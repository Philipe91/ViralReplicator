"""Executor ÍCONE — grade de símbolos com rótulo.

Serve a batida que ENUMERA: "seis coisas que mudam suas artérias", "três sinais
de alerta", "o que ajuda e o que atrapalha". Enumeração é estrutura, e estrutura
se lê numa grade — não numa foto de comida.

Mesma razão dos irmãos vetoriais: o rótulo de cada item é TEXTO, e o SDXL não
escreve. Pedir "seis ícones de alimentos com os nomes embaixo" devolve seis
formas plausíveis com garatuja no lugar dos nomes.

## Por que ícone desenhado à mão e não fonte de símbolo

Fonte de emoji no Pillow é frágil: a colorida (Segoe UI Emoji) exige camada
CBDT/COLR que o Pillow só rasteriza em condições específicas, e a monocromática
muda de desenho entre versões do Windows — ou seja, quebraria o determinismo,
que é a base do cache deste pipeline. Biblioteca de ícone traria dependência e
licença para resolver o que aqui são vinte linhas de geometria.

O conjunto é curado para o nicho de saúde, de propósito: ícone genérico demais
não comunica, e ícone que não existe no dicionário FALHA em vez de virar um
quadrado vazio.

## Ícone é ilustração, não dado

Usa a paleta da MARCA, não a de dados do `exec_grafico`. A distinção vale
lembrar: ali a cor É a identidade da série e precisa passar no validador de CVD;
aqui a cor é decoração e quem carrega o significado é a forma mais o rótulo.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import vetor_base as vb
from vetor_base import ALTURA, LARGURA, MARGEM_LATERAL, PALETA, RODAPE_PROIBIDO, TOPO_SEGURO

#   v1 -> primeira versão
VERSAO = 1


# ── o dicionário de formas ───────────────────────────────────────────────
#
# Cada função desenha dentro de um quadrado de lado 2*r centrado em (cx, cy).
# Nada de random: mesma entrada, mesmos pixels.

def _coracao(d, cx, cy, r, cor):
    d.ellipse([cx - r, cy - r * 0.85, cx, cy + r * 0.15], fill=cor)
    d.ellipse([cx, cy - r * 0.85, cx + r, cy + r * 0.15], fill=cor)
    d.polygon([(cx - r * 0.98, cy - r * 0.2), (cx + r * 0.98, cy - r * 0.2),
               (cx, cy + r * 0.92)], fill=cor)


def _gota(d, cx, cy, r, cor):
    d.ellipse([cx - r * 0.72, cy - r * 0.15, cx + r * 0.72, cy + r * 0.85], fill=cor)
    d.polygon([(cx - r * 0.62, cy + r * 0.12), (cx + r * 0.62, cy + r * 0.12),
               (cx, cy - r * 0.95)], fill=cor)


def _folha(d, cx, cy, r, cor):
    """Lente (dois arcos que se encontram em ponta), girada 45°, com nervura.

    A primeira versão usava dois `pieslice` de quadrantes OPOSTOS e o resultado
    lia como pizza quebrada, não como folha. O que dá a leitura de folha é a
    PONTA nas duas extremidades — e ponta sai de parábola, não de arco de
    círculo, que termina arredondado.
    """
    import math
    passos, k = 28, 0.58
    borda = ([(x := -r + 2 * r * i / passos, -k * r * (1 - (x / r) ** 2)) for i in range(passos + 1)]
             + [(x := r - 2 * r * i / passos, k * r * (1 - (x / r) ** 2)) for i in range(passos + 1)])
    ang = math.radians(-45)
    cos_a, sin_a = math.cos(ang), math.sin(ang)
    pts = [(cx + px * cos_a - py * sin_a, cy + px * sin_a + py * cos_a) for px, py in borda]
    d.polygon(pts, fill=cor)
    # nervura central, na direção do eixo maior
    d.line([(cx - r * 0.68 * cos_a, cy - r * 0.68 * sin_a),
            (cx + r * 0.68 * cos_a, cy + r * 0.68 * sin_a)],
           fill=PALETA["fundo"][:3], width=max(int(r * 0.10), 3))


def _relogio(d, cx, cy, r, cor):
    g = max(int(r * 0.14), 4)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=cor, width=g)
    d.line([(cx, cy), (cx, cy - r * 0.55)], fill=cor, width=g)
    d.line([(cx, cy), (cx + r * 0.42, cy + r * 0.24)], fill=cor, width=g)


def _chama(d, cx, cy, r, cor):
    """Chama ASSIMÉTRICA, com lóbulo secundário.

    Duas correções, ambas de legibilidade e não de estética:

    1. A 1ª versão abria um vazio no meio para sugerir o núcleo e lia como
       lâmpada — num ícone de 60px o vazio só cria ambiguidade.
    2. A 2ª versão virou uma silhueta simétrica de ponta para cima… idêntica ao
       ícone de GOTA. Duas formas indistinguíveis no dicionário anulam o motivo
       de existirem as duas.

    O que separa fogo de líquido é a assimetria: a ponta lambe para um lado e há
    um lóbulo menor na base.
    """
    # corpo principal, ponta pendendo para a direita
    d.ellipse([cx - r * 0.58, cy + r * 0.02, cx + r * 0.66, cy + r * 0.95], fill=cor)
    d.polygon([(cx + r * 0.20, cy - r),
               (cx + r * 0.66, cy + r * 0.30),
               (cx - r * 0.36, cy + r * 0.42)], fill=cor)
    # lóbulo menor à esquerda: a segunda língua de fogo
    d.ellipse([cx - r * 0.86, cy + r * 0.30, cx - r * 0.24, cy + r * 0.95], fill=cor)
    d.polygon([(cx - r * 0.62, cy - r * 0.28),
               (cx - r * 0.22, cy + r * 0.52),
               (cx - r * 0.88, cy + r * 0.52)], fill=cor)


def _alerta(d, cx, cy, r, cor):
    d.polygon([(cx, cy - r), (cx + r, cy + r * 0.72), (cx - r, cy + r * 0.72)], fill=cor)
    g = max(int(r * 0.16), 5)
    d.line([(cx, cy - r * 0.3), (cx, cy + r * 0.22)],
           fill=PALETA["fundo"][:3], width=g)
    d.ellipse([cx - g * 0.6, cy + r * 0.38, cx + g * 0.6, cy + r * 0.38 + g * 1.2],
              fill=PALETA["fundo"][:3])


def _check(d, cx, cy, r, cor):
    g = max(int(r * 0.22), 6)
    d.line([(cx - r * 0.7, cy), (cx - r * 0.15, cy + r * 0.55)], fill=cor, width=g)
    d.line([(cx - r * 0.15, cy + r * 0.55), (cx + r * 0.72, cy - r * 0.6)],
           fill=cor, width=g)


def _proibido(d, cx, cy, r, cor):
    g = max(int(r * 0.18), 5)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=cor, width=g)
    d.line([(cx - r * 0.55, cy + r * 0.55), (cx + r * 0.55, cy - r * 0.55)],
           fill=cor, width=g)


def _seta_cima(d, cx, cy, r, cor):
    d.polygon([(cx, cy - r), (cx + r * 0.75, cy - r * 0.05), (cx - r * 0.75, cy - r * 0.05)],
              fill=cor)
    d.rectangle([cx - r * 0.28, cy - r * 0.05, cx + r * 0.28, cy + r * 0.85], fill=cor)


def _seta_baixo(d, cx, cy, r, cor):
    d.polygon([(cx, cy + r), (cx + r * 0.75, cy + r * 0.05), (cx - r * 0.75, cy + r * 0.05)],
              fill=cor)
    d.rectangle([cx - r * 0.28, cy - r * 0.85, cx + r * 0.28, cy + r * 0.05], fill=cor)


def _lua(d, cx, cy, r, cor):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cor)
    d.ellipse([cx - r * 0.45, cy - r * 1.05, cx + r * 1.35, cy + r * 0.85],
              fill=PALETA["fundo"][:3])


def _haltere(d, cx, cy, r, cor):
    d.rectangle([cx - r * 0.85, cy - r * 0.16, cx + r * 0.85, cy + r * 0.16], fill=cor)
    for s in (-1, 1):
        d.rounded_rectangle([cx + s * r * 0.62 - r * 0.2, cy - r * 0.62,
                             cx + s * r * 0.62 + r * 0.2, cy + r * 0.62],
                            radius=max(int(r * 0.12), 3), fill=cor)


def _pessoa(d, cx, cy, r, cor):
    d.ellipse([cx - r * 0.34, cy - r, cx + r * 0.34, cy - r * 0.32], fill=cor)
    d.pieslice([cx - r * 0.78, cy - r * 0.28, cx + r * 0.78, cy + r * 1.3], 180, 360, fill=cor)


FORMAS = {
    "coracao": _coracao, "gota": _gota, "folha": _folha, "relogio": _relogio,
    "chama": _chama, "alerta": _alerta, "check": _check, "proibido": _proibido,
    "seta_cima": _seta_cima, "seta_baixo": _seta_baixo, "lua": _lua,
    "haltere": _haltere, "pessoa": _pessoa,
}


# ── arquétipo ────────────────────────────────────────────────────────────


def grade_icones(d, params: dict):
    itens = params.get("itens") or []
    if not itens:
        return
    desconhecidos = [i.get("forma") for i in itens if i.get("forma") not in FORMAS]
    if desconhecidos:
        # falhar alto em vez de desenhar quadrado vazio: ícone que não comunica
        # é pior que ícone ausente, porque ocupa a tela fingindo informação
        raise ValueError(
            f"forma(s) de ícone desconhecida(s): {desconhecidos}. "
            f"Conhecidas: {', '.join(sorted(FORMAS))}")

    n = len(itens)
    colunas = n if n <= 4 else (n + 1) // 2
    linhas = 1 if n <= 4 else 2

    area_topo = TOPO_SEGURO + 40
    area_alt = (ALTURA - RODAPE_PROIBIDO - 70) - area_topo
    passo_y = area_alt / linhas
    largura_util = LARGURA - 2 * MARGEM_LATERAL
    passo_x = largura_util / colunas

    raio_chip = int(min(passo_x * 0.30, passo_y * 0.30, 108))
    raio_icone = int(raio_chip * 0.55)
    f_rot = vb.fonte(36, negrito=True)

    for i, item in enumerate(itens):
        col, lin = i % colunas, i // colunas
        # a última linha incompleta fica centralizada, senão sobra um buraco
        nesta_linha = min(colunas, n - lin * colunas)
        recuo = (colunas - nesta_linha) * passo_x / 2
        cx = int(MARGEM_LATERAL + recuo + passo_x * (col + 0.5))
        cy = int(area_topo + passo_y * (lin + 0.42))

        destaque = bool(item.get("destaque"))
        cor_chip = PALETA["destaque"] if destaque else PALETA["musculo"]
        cor_icone = PALETA["fundo"][:3] if destaque else PALETA["traco"]

        d.ellipse([cx - raio_chip, cy - raio_chip, cx + raio_chip, cy + raio_chip],
                  fill=cor_chip)
        FORMAS[item["forma"]](d, cx, cy, raio_icone, cor_icone)

        rotulo = str(item.get("rotulo", ""))
        if rotulo:
            for j, linha_txt in enumerate(_quebrar(d, rotulo, f_rot, int(passo_x * 0.86))[:2]):
                lt = vb.largura_texto(d, linha_txt, f_rot)
                d.text((cx - lt // 2, cy + raio_chip + 28 + j * 44), linha_txt,
                       font=f_rot, fill=PALETA["texto"])


def _quebrar(d, texto: str, f, largura_max: int) -> list:
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


ARQUETIPOS = {
    "grade_icones": grade_icones,
}


def chave(params: dict) -> str:
    bruto = json.dumps({"v": VERSAO, "base": vb.VERSAO, "p": params},
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:10]


def desenhar(params: dict, saida: Path) -> Path:
    params = dict(params)
    params.setdefault("tipo", "grade_icones")
    return vb.render(ARQUETIPOS, params, saida, "icone")
