"""Modelo da composição: um plano é uma pilha de camadas, não uma imagem.

Este módulo é **puro**: não chama ffmpeg, não escreve vídeo, não gera nada. Ele
define o schema, o registro de executores, o adaptador do formato antigo, a
validação e a chave de cache. Tudo aqui é testável sem GPU e sem disco.

O empilhamento em si mora em `compositor.py`.

## Por que camadas ordenadas e não grafo

As dependências reais entre assets de um mesmo plano têm profundidade 2: só o
que **deriva** de outro asset (parallax a partir da imagem, split a partir de
dois frames) depende de alguém. Todo o resto é ordem Z, que não é dependência.
Chamar isso de grafo levaria a construir ordenação topológica e detecção de
ciclo para um problema que não existe — e uma lista é um DAG degenerado válido,
então se um dia a dependência aparecer, ela cresce sem reescrita.

## A fronteira que sustenta o determinismo

    AUTORIA   julgamento, LLM, humano no loop — roda uma vez, é revisável
    ─────────────── ponto de congelamento: o .json ───────────────
    RENDER    100% determinístico, reproduzível, incremental, cacheável

Nada abaixo da linha decide coisa nenhuma. Se um campo obriga julgamento em
tempo de render, ele está do lado errado da linha.

## Compatibilidade

Plano sem `camadas` é **schema 2** e passa pelo `adaptar()`, que sintetiza uma
composição de camada única com exatamente o comportamento de hoje. Nenhum dos
73 planos que já existem é migrado, e nenhum muda de resultado.
"""

from __future__ import annotations

import hashlib
import json

SCHEMA_VERSAO = 3

# Origem do pixel. É o eixo primário porque é o que determina custo, capacidade
# e cache — e não o "tipo visual", que é o segundo nível.
FONTES = {
    "difusao":  "SDXL na GPU. NÃO aceita texto (difusão desenha letra como garatuja).",
    "vetor":    "desenhado por ffmpeg na CPU. ACEITA texto. Barato e exato.",
    "externo":  "vem de fora (banco de vídeo). Depende de rede e licença.",
    "derivado": "calculado a partir de outra camada do mesmo plano.",
    "audio":    "não tem pixel; entra na mixagem, não na pilha visual.",
}


class Executor:
    """Um produtor de asset, com as capacidades declaradas em vez de presumidas.

    `versao` entra na chave de cache de propósito: sem isso, melhorar um
    executor não regeneraria nada — todos os vídeos continuariam com a saída
    velha e o deploy pareceria não ter subido.
    """

    def __init__(self, nome, fonte, versao=1, aceita_texto=False, usa_gpu=False,
                 usa_rede=False, deterministico=True, custo_seg=0.0,
                 opaco_quadro_cheio=False, aceita_camera=True, descricao=""):
        if fonte not in FONTES:
            raise ValueError(f"fonte desconhecida: {fonte!r}. Conhecidas: {sorted(FONTES)}")
        self.nome = nome
        self.fonte = fonte
        self.versao = versao
        self.aceita_texto = aceita_texto
        self.usa_gpu = usa_gpu
        self.usa_rede = usa_rede
        self.deterministico = deterministico
        self.custo_seg = custo_seg
        # uma camada opaca que cobre o quadro inteiro pode ser o FUNDO da pilha,
        # e — quando é a única — dispensa composição: compor uma camada só é
        # identidade. É essa propriedade que preserva o render atual bit a bit.
        self.opaco_quadro_cheio = opaco_quadro_cheio
        # gráfico vetorial com handheld parece defeito de render, não câmera
        self.aceita_camera = aceita_camera
        self.descricao = descricao

    def __repr__(self):
        return f"<Executor {self.nome} v{self.versao} fonte={self.fonte}>"


EXECUTORES: dict[str, Executor] = {}


def registrar(executor: Executor) -> Executor:
    if executor.nome in EXECUTORES:
        raise ValueError(f"executor '{executor.nome}' já registrado")
    EXECUTORES[executor.nome] = executor
    return executor


# O único executor da etapa 2. Ele NÃO gera imagem — a geração continua em
# `produce_video.gerar_imagens`, que já é idempotente e cacheada por existência
# de arquivo. Aqui ele apenas RESOLVE qual arquivo é o frame desta camada.
registrar(Executor(
    nome="imagem_ia",
    fonte="difusao",
    versao=1,
    aceita_texto=False,
    usa_gpu=True,
    custo_seg=40.0,
    opaco_quadro_cheio=True,
    descricao="PNG gerado pelo SDXL. Fundo padrão de um plano.",
))


# ── construção e adaptação ───────────────────────────────────────────────


def camada(id_: str, executor: str, z: int = 0, deriva_de: str | None = None,
           **params) -> dict:
    d = {"id": id_, "executor": executor, "z": z}
    if deriva_de:
        d["deriva_de"] = deriva_de
    if params:
        d["params"] = params
    return d


def adaptar(roteiro: dict) -> dict:
    """Garante `camadas` em todo plano, sem migrar nada no disco.

    Plano que já traz `camadas` é respeitado. Plano sem — que é o caso dos 73
    que existem hoje — recebe uma composição de camada única `imagem_ia`, que é
    literalmente o comportamento atual descrito no vocabulário novo.

    Muta em memória de propósito, como `direcao.dirigir()`: o editor chama uma
    vez no início e depois lê o campo já resolvido.
    """
    for cena in roteiro.get("cenas", []):
        planos = cena.get("planos") or []
        for i, p in enumerate(planos, 1):
            if p.get("camadas"):
                continue
            p["camadas"] = [camada(f"base_{cena['n']:02d}_{i}", "imagem_ia", z=0)]
        # cena no formato antigo (prompt único em cena["imagem"], sem planos)
        # não tem onde pendurar camadas; ela continua pelo caminho legado do
        # editor, que não passa por aqui.
    return roteiro


def eh_composicao_trivial(camadas: list) -> bool:
    """Verdadeiro quando a pilha dispensa composição.

    Uma camada só, opaca e de quadro cheio, sem derivação: empilhar isso é a
    identidade. Reconhecer o caso é o que permite manter o caminho de render
    atual intocado — e é também a otimização correta, não um atalho.
    """
    if len(camadas) != 1:
        return False
    c = camadas[0]
    if c.get("deriva_de"):
        return False
    ex = EXECUTORES.get(c.get("executor", ""))
    return bool(ex and ex.opaco_quadro_cheio)


def ordenar(camadas: list) -> list:
    """Ordem de renderização: dependência antes do dependente, depois Z.

    `sorted` é estável, então camadas de mesmo Z preservam a ordem em que o
    autor escreveu — o que torna a saída previsível para quem escreve o JSON.
    """
    resolvidas, pendentes, prontos = [], list(camadas), set()
    while pendentes:
        avancou = False
        for c in list(pendentes):
            pai = c.get("deriva_de")
            if pai is None or pai in prontos:
                resolvidas.append(c)
                prontos.add(c["id"])
                pendentes.remove(c)
                avancou = True
        if not avancou:
            # ciclo ou pai inexistente; `validar` já reclama disso com mensagem
            # melhor, então aqui só evitamos laço infinito
            resolvidas.extend(pendentes)
            break
    return sorted(resolvidas, key=lambda c: c.get("z", 0))


# ── validação ────────────────────────────────────────────────────────────


def validar(roteiro: dict) -> list:
    """Lista de erros. Vazia = pode renderizar.

    Mesma regra do `direcao.validar`: executor sem execução DERRUBA o render.
    Camada ignorada em silêncio é pior que camada ausente, porque o JSON passa a
    impressão de ter sido aplicada.
    """
    erros = []
    versao = roteiro.get("schema", 2)
    if versao not in (2, 3):
        erros.append(f"schema '{versao}' desconhecido (esperado 2 ou 3)")

    for cena in roteiro.get("cenas", []):
        for j, p in enumerate(cena.get("planos") or [], 1):
            camadas = p.get("camadas")
            if not camadas:
                continue
            onde = f"cena {cena.get('n')} plano {j}"
            ids = [c.get("id") for c in camadas]
            if len(ids) != len(set(ids)):
                erros.append(f"{onde}: ids de camada repetidos: {ids}")
            for c in camadas:
                nome = c.get("executor")
                if nome not in EXECUTORES:
                    erros.append(
                        f"{onde}: executor '{nome}' não existe. "
                        f"Registrados: {', '.join(sorted(EXECUTORES)) or '(nenhum)'}")
                if not isinstance(c.get("z", 0), int):
                    erros.append(f"{onde}: z de '{c.get('id')}' deve ser inteiro")
                pai = c.get("deriva_de")
                if pai is not None:
                    if pai not in ids:
                        erros.append(f"{onde}: '{c.get('id')}' deriva de '{pai}', que não existe")
                    elif pai == c.get("id"):
                        erros.append(f"{onde}: '{c.get('id')}' deriva de si mesmo")
            erros.extend(_erros_de_ciclo(camadas, onde))
    return erros


def _erros_de_ciclo(camadas: list, onde: str) -> list:
    pai_de = {c["id"]: c.get("deriva_de") for c in camadas if c.get("id")}
    erros = []
    for inicio in pai_de:
        visto, atual = set(), inicio
        while atual is not None:
            if atual in visto:
                erros.append(f"{onde}: ciclo de derivação envolvendo '{inicio}'")
                break
            visto.add(atual)
            atual = pai_de.get(atual)
    return erros


# ── cache ────────────────────────────────────────────────────────────────


def chave_cache(camada_: dict, extra: dict | None = None) -> str:
    """Identidade reproduzível de um asset.

    Derivada, nunca declarada: se o JSON *declarasse* estar cacheado, ele
    poderia mentir sobre o disco. A versão do executor entra na conta para que
    melhorar um executor invalide o que ele produziu.
    """
    ex = EXECUTORES.get(camada_.get("executor", ""))
    material = {
        "executor": camada_.get("executor"),
        "versao": ex.versao if ex else 0,
        "params": camada_.get("params") or {},
        "deriva_de": camada_.get("deriva_de"),
        "extra": extra or {},
    }
    bruto = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]


def resumo(roteiro: dict) -> dict:
    """Contagem por fonte — serve para prever custo antes de renderizar."""
    total = {"camadas": 0, "gpu": 0, "cpu": 0, "rede": 0}
    for cena in roteiro.get("cenas", []):
        for p in cena.get("planos") or []:
            for c in p.get("camadas") or []:
                ex = EXECUTORES.get(c.get("executor", ""))
                total["camadas"] += 1
                if not ex:
                    continue
                if ex.usa_gpu:
                    total["gpu"] += 1
                elif ex.usa_rede:
                    total["rede"] += 1
                else:
                    total["cpu"] += 1
    return total
