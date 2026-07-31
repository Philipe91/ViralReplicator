"""Empilha as camadas de um plano num único segmento de vídeo.

Estratégia: **cada camada vira um intermediário próprio e a composição é um
passe de `overlay`.** É mais lento que montar um filtergraph gigante de uma vez,
e vale por três motivos que importam mais que velocidade:

1. cada asset fica cacheável de forma independente — que é o objetivo da V3;
2. defeito fica isolável: dá para abrir a camada sozinha e ver o que ela é;
3. a ordem Z vira dado ordenado, não posição numa string de filtro.

## O caso de uma camada só

`composicao.eh_composicao_trivial()` reconhece a pilha de uma camada opaca de
quadro cheio, e o editor NEM CHAMA este módulo nesse caso — segue pelo caminho
de sempre. Não é atalho: compor uma camada opaca sozinha é a identidade, e é
essa propriedade que preserva o render atual bit a bit enquanto a infraestrutura
nova entra por baixo.

## Estado na etapa 2

Nenhum plano de produção passa por aqui ainda — só existe o executor
`imagem_ia`, que é sempre trivial. O módulo é exercitado pelos testes com
camadas sintéticas, para não entrar código não testado no repositório. O
primeiro uso real chega com o executor de diagrama, na etapa 3.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def _run(cmd: list, desc: str, timeout=900):
    """`timeout` é rede de segurança, não otimismo: um filtergraph mal formado
    com entrada em loop trava para sempre, e travar sem mensagem é o pior modo
    de falha possível num pipeline em lote."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{desc} travou (>{timeout}s) — provável entrada sem fim no filtergraph")
    if r.returncode != 0:
        raise RuntimeError(f"{desc} falhou:\n{r.stderr[-1500:]}")


def duracao(arq: Path) -> float:
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(arq)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def _tempo(v) -> str:
    return f"{float(v):.3f}"


def compor(base: Path, sobreposicoes: list, saida: Path, tmp: Path,
           fps: int = 30, crf: int = 18) -> Path:
    """Empilha `sobreposicoes` sobre `base` e grava em `saida`.

    `base` é o fundo já renderizado (o segmento que sai do ken_burns, por
    exemplo). Cada sobreposição é um dicionário:

        {"arquivo": Path,        # PNG com alpha, ou vídeo com alpha
         "ini": 0.0,             # segundo em que entra, relativo ao segmento
         "fim": 3.5,             # segundo em que sai
         "x": "(W-w)/2",         # expressão do overlay; padrão: centralizado
         "y": "(H-h)/2"}

    Sem sobreposições, copia a base sem re-encodar — de novo, compor nada é a
    identidade, e re-encodar aqui só somaria perda.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    if not sobreposicoes:
        _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(base),
              "-c", "copy", str(saida)], "composicao sem camadas (copia)")
        return saida

    # Imagem parada precisa de -loop 1 para durar, e precisa de -t para PARAR.
    # Sem o -t, o `-shortest` não resolve: uma entrada em loop dentro de
    # filter_complex nunca sinaliza fim, e o ffmpeg fica preso para sempre —
    # aconteceu na primeira versão deste módulo e travou a suíte de testes.
    dur_base = duracao(base)
    entradas = ["-i", str(base)]
    for s in sobreposicoes:
        if str(s["arquivo"]).lower().endswith(".png"):
            entradas += ["-loop", "1", "-t", _tempo(dur_base or 1.0), "-i", str(s["arquivo"])]
        else:
            entradas += ["-i", str(s["arquivo"])]

    filtros, atual = [], "0:v"
    for i, s in enumerate(sobreposicoes, 1):
        x = s.get("x", "(W-w)/2")
        y = s.get("y", "(H-h)/2")
        rot = f"c{i}"
        janela = ""
        if s.get("ini") is not None and s.get("fim") is not None:
            # aspas simples dentro do filtro: o enable é uma expressão e a
            # vírgula do between() precisa estar protegida do separador de
            # filtros — a mesma armadilha documentada em direcao.py
            janela = f":enable='between(t\\,{_tempo(s['ini'])}\\,{_tempo(s['fim'])})'"
        filtros.append(f"[{atual}][{i}:v]overlay=x={x}:y={y}{janela}[{rot}]")
        atual = rot
    filtros.append(f"[{atual}]null[vout]")

    _run([FFMPEG, "-y", "-loglevel", "error", *entradas,
          "-filter_complex", ";".join(filtros), "-map", "[vout]",
          "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
          "-pix_fmt", "yuv420p", "-r", str(fps), "-shortest", str(saida)],
         f"composicao de {len(sobreposicoes)} camada(s)")
    return saida
