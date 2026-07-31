"""Executor GRÁFICO — barras e proporção.

Mesma razão dos outros executores vetoriais: número é texto, e texto é o que a
difusão não desenha. Um "gráfico" pedido ao SDXL volta com barras plausíveis e
rótulos ilegíveis — ou seja, perde exatamente a informação.

## A paleta de DADOS é outra que a de ilustração

Rodei o validador da skill de dataviz na paleta da marca e ela **reprova como
paleta de dados**:

    #A8B6A0 sálvia  chroma 0.035  -> lê como cinza
    #C67A76 rosa    chroma 0.096  -> lê como cinza
    #DE9E4A âmbar   vs rosa: ΔE 12.7 normal  -> abaixo de 15

Ela funciona para ILUSTRAÇÃO, onde a forma carrega o significado (os anéis do
corte de vaso não dependem da cor para serem lidos). Não funciona para CODIFICAR
dado, onde a cor É a identidade da série.

Sálvia, terracota e âmbar ficam todos no eixo vermelho-verde, que é o pior caso
para deutan/protan — qualquer par quente ali colide. A saída é ancorar no eixo
azul-amarelo. Conjunto final, validado:

    node scripts/validate_palette.js "#2A7DB8,#C1553C,#D9A63C" \
         --mode light --surface "#F3EEE4"
    [PASS] faixa de luminosidade · croma · separação CVD (ΔE 17.5 deutan)
           · piso de visão normal (ΔE 20.6)
    [WARN] contraste do âmbar 1.92 < 3:1

O WARN é quitado POR CONSTRUÇÃO, não ignorado: a skill diz que ele "obriga
rótulos visíveis", e em vídeo não existe hover — rótulo direto em cada barra já
era obrigatório. A identidade nunca fica só na cor.

## Formas

- `barras` — comparação de magnitude. HORIZONTAIS, porque rótulo em alemão é
  comprido e barra vertical obriga a girar o texto.
- `proporcao` — um número só. A skill é explícita: às vezes a resposta **não é
  um gráfico**, é um número herói. Pizza de uma fatia seria pior em todos os
  aspectos — área é difícil de julgar e a leitura exige comparar ângulos.

Ordem categórica é FIXA, nunca ciclada: a segunda série é sempre terracota, não
"a próxima da lista". Cor segue a entidade, não a posição.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import vetor_base as vb
from vetor_base import ALTURA, LARGURA, MARGEM_LATERAL, PALETA, RODAPE_PROIBIDO, TOPO_SEGURO

#   v1 -> primeira versão
#   v2 -> honra `revelados` (geometria estável na animação)
VERSAO = 2

# Ordem fixa. Ver a nota do topo sobre a validação.
SERIES = [(42, 125, 184), (193, 85, 60), (217, 166, 60)]
DESTAQUE = (193, 85, 60)      # terracota: separa de qualquer série sob CVD
TRILHO = (226, 220, 208)      # canaleta da barra, recessiva
RAIO = 8                      # ponta arredondada da barra


def _fmt(valor, unidade: str) -> str:
    txt = f"{valor:g}".replace(".", ",")
    return f"{txt}{unidade}" if unidade else txt


def _cor_da_barra(indice: int, item: dict, params: dict, total: int):
    """Cor de uma barra, na ordem categórica FIXA.

    Regra da skill de dataviz que é fácil violar sem perceber: hue categórico se
    atribui em ordem fixa e **nunca ciclada**. `SERIES[i % 3]` com 5 itens faria
    a 4ª barra repetir a cor da 1ª, e aí a cor deixa de identificar — passa a
    mentir que duas categorias são a mesma.

    Acima de 3 itens, portanto, o gráfico volta a ser de série única: a
    identidade fica no rótulo, que já é obrigatório. É a mesma ideia do
    "a 9ª série vira Outros", na escala deste projeto.
    """
    if item.get("destaque"):
        return DESTAQUE
    if params.get("por_serie") and total <= len(SERIES):
        return SERIES[indice]
    return SERIES[0]


def barras(d, params: dict):
    itens = params.get("itens") or []
    if not itens:
        return
    unidade = params.get("unidade", "")
    maximo = max([abs(float(i.get("valor", 0))) for i in itens] + [1e-9])

    f_rot = vb.fonte(40, negrito=True)
    f_val = vb.fonte(40, negrito=True)

    col_rotulo = max((vb.largura_texto(d, str(i.get("rotulo", "")), f_rot) for i in itens),
                     default=0)
    col_rotulo = min(col_rotulo, 560)
    x_barra = MARGEM_LATERAL + col_rotulo + 40
    # espaço reservado à direita para o rótulo de valor, que é obrigatório
    x_fim = LARGURA - MARGEM_LATERAL - 190

    topo = TOPO_SEGURO + 60
    # a folga de 90px é o que separa a última barra do título do quadro; com 40
    # os dois encostavam
    disponivel = (ALTURA - RODAPE_PROIBIDO - 90) - topo
    n = len(itens)
    passo = disponivel / n
    altura = min(int(passo * 0.56), 78)

    visiveis = vb.revelados(params, n)
    for i, item in enumerate(itens):
        y = int(topo + passo * i + (passo - altura) / 2)
        valor = float(item.get("valor", 0))
        if i >= visiveis:
            # o trilho aparece desde o início: ele É a escala, e a escala não
            # pode mudar durante a revelação, senão as barras já mostradas
            # passariam a mentir sobre o próprio tamanho
            d.rounded_rectangle([x_barra, y, x_fim, y + altura], radius=RAIO, fill=TRILHO)
            continue
        largura = int((x_fim - x_barra) * (abs(valor) / maximo))
        cor = _cor_da_barra(i, item, params, n)

        # trilho: dá a escala sem precisar de grade, que seria mais um traço
        d.rounded_rectangle([x_barra, y, x_fim, y + altura], radius=RAIO, fill=TRILHO)
        if largura > RAIO * 2:
            d.rounded_rectangle([x_barra, y, x_barra + largura, y + altura],
                                radius=RAIO, fill=cor)

        rotulo = str(item.get("rotulo", ""))
        if rotulo:
            lr = vb.largura_texto(d, rotulo, f_rot)
            d.text((x_barra - 40 - lr, y + altura // 2 - 24), rotulo,
                   font=f_rot, fill=PALETA["texto"])

        # rótulo de valor SEMPRE visível: é o que quita o aviso de contraste e
        # o que substitui o tooltip que vídeo não tem
        d.text((x_barra + largura + 24, y + altura // 2 - 24), _fmt(valor, unidade),
               font=f_val, fill=PALETA["texto"])


def proporcao(d, params: dict):
    """Um número herói. Não é gráfico, e é de propósito."""
    valor = float(params.get("valor", 0))
    unidade = params.get("unidade", "%")
    legenda = str(params.get("legenda", ""))

    f_num = vb.fonte(230, negrito=True)
    f_leg = vb.fonte(46)

    numero = _fmt(valor, unidade)
    y_num = TOPO_SEGURO + 90
    d.text((MARGEM_LATERAL, y_num), numero, font=f_num, fill=DESTAQUE)

    if legenda:
        d.text((MARGEM_LATERAL + 6, y_num + 260), legenda,
               font=f_leg, fill=PALETA["texto"])

    # barra de proporção: o número diz quanto, a barra diz quanto de quanto
    y_bar = y_num + 350
    x0, x1 = MARGEM_LATERAL, LARGURA - MARGEM_LATERAL
    fracao = max(0.0, min(valor / 100.0, 1.0)) if unidade == "%" else 0.0
    d.rounded_rectangle([x0, y_bar, x1, y_bar + 46], radius=RAIO, fill=TRILHO)
    largura = int((x1 - x0) * fracao)
    if largura > RAIO * 2:
        d.rounded_rectangle([x0, y_bar, x0 + largura, y_bar + 46], radius=RAIO,
                            fill=DESTAQUE)


ARQUETIPOS = {
    "barras": barras,
    "proporcao": proporcao,
}


def chave(params: dict) -> str:
    bruto = json.dumps({"v": VERSAO, "base": vb.VERSAO, "p": params},
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:10]


def desenhar(params: dict, saida: Path) -> Path:
    params = dict(params)
    params.setdefault("tipo", "barras")
    return vb.render(ARQUETIPOS, params, saida, "grafico")
