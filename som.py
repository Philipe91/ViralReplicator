"""Sound design: efeitos SINTETIZADOS, sem biblioteca e sem licença.

O canal não tem banco de efeitos, e baixar um traria licença para gerenciar. Os
quatro sons que este pipeline precisa — whoosh, impacto, riser, sub-boom — são
ruído e senoide moldados por envelope, ou seja, vinte linhas de numpy cada.
Sintetizar também garante o que download nenhum garante: **determinismo**. O
ruído usa semente fixa, então o mesmo vídeo rende o mesmo arquivo.

## Nível é ALVO ABSOLUTO, nunca ganho relativo

É a lição mais cara já aprendida neste projeto, e ela vale igual para efeito:
a trilha ficou 26 dB alta demais porque alguém aplicou `volume=0.22` sobre um
arquivo cujo nível de origem era desconhecido. Aqui a amplitude de cada efeito é
definida na síntese, em dBFS de pico, e não depende de nada externo.

## Efeito NÃO é duckado

A cama de música abaixa quando a voz entra, porque ela é fundo. Efeito é
pontuação: ele existe exatamente no instante em que deve ser ouvido, dura
frações de segundo e some. Duckar o efeito o mataria justamente onde ele serve.
Por isso ele entra DEPOIS da compressão sidechain, e não dentro dela.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

HZ = 48000
# Pico de cada efeito. A narração fica em -14 LUFS; -20 dBFS de pico põe o
# efeito presente sem disputar a fala. É valor medido em dBFS, não fator de
# multiplicação sobre uma origem desconhecida.
PICO_DBFS = -20.0
FFMPEG = "ffmpeg"


def _amplitude() -> float:
    return 10.0 ** (PICO_DBFS / 20.0)


def _envelope(n: int, ataque: float, decaimento: float) -> np.ndarray:
    """Envelope de ataque rápido e cauda exponencial."""
    t = np.linspace(0.0, 1.0, n, endpoint=False)
    sobe = np.clip(t / max(ataque, 1e-6), 0.0, 1.0)
    desce = np.exp(-t / max(decaimento, 1e-6))
    return sobe * desce


def _ruido(n: int, semente: int) -> np.ndarray:
    """Ruído com SEMENTE FIXA — sem isso o cache viraria mentira."""
    return np.random.default_rng(semente).standard_normal(n)


def _passa_baixa(x: np.ndarray, corte_hz: float) -> np.ndarray:
    """Um polo, aplicado como média exponencial. Suficiente para moldar timbre e
    barato o bastante para não justificar dependência de scipy."""
    a = np.exp(-2.0 * np.pi * corte_hz / HZ)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(x.size):
        acc = a * acc + (1.0 - a) * x[i]
        y[i] = acc
    return y


def whoosh(dur: float = 0.55) -> np.ndarray:
    """Ruído filtrado com varredura de corte: fecha e abre, o gesto de passagem."""
    n = int(dur * HZ)
    base = _ruido(n, semente=11)
    # varredura: o corte sobe até o meio e cai — é ela que dá o "shhhwoo"
    t = np.linspace(0.0, 1.0, n, endpoint=False)
    corte = 400.0 + 5200.0 * np.sin(np.pi * t)
    saida = np.empty(n)
    a_ant, acc = 0.0, 0.0
    for i in range(n):
        a = np.exp(-2.0 * np.pi * corte[i] / HZ)
        acc = a * acc + (1.0 - a) * base[i]
        saida[i] = base[i] - acc          # passa-alta = original menos passa-baixa
        a_ant = a
    env = np.sin(np.pi * t) ** 1.5        # entra e sai suave: whoosh não bate
    return saida * env


def impacto(dur: float = 0.45) -> np.ndarray:
    """Senoide grave com queda de tom + estalo curto. O 'hit' de corte."""
    n = int(dur * HZ)
    t = np.arange(n) / HZ
    # tom caindo de 120 para 45 Hz: a queda é o que dá peso
    freq = 120.0 * np.exp(-t * 6.0) + 45.0
    fase = 2.0 * np.pi * np.cumsum(freq) / HZ
    corpo = np.sin(fase) * _envelope(n, 0.004, 0.10)
    estalo = _passa_baixa(_ruido(n, semente=23), 2500.0) * _envelope(n, 0.001, 0.012)
    return corpo * 0.9 + estalo * 0.5


def riser(dur: float = 1.6) -> np.ndarray:
    """Ruído subindo de tom e de volume: prepara uma revelação."""
    n = int(dur * HZ)
    t = np.linspace(0.0, 1.0, n, endpoint=False)
    base = _ruido(n, semente=37)
    corte = 300.0 + 4000.0 * t ** 2
    saida, acc = np.empty(n), 0.0
    for i in range(n):
        a = np.exp(-2.0 * np.pi * corte[i] / HZ)
        acc = a * acc + (1.0 - a) * base[i]
        saida[i] = base[i] - acc
    return saida * (t ** 2)               # crescendo, não rampa linear


def sub_boom(dur: float = 1.1) -> np.ndarray:
    """Só grave. Marca abertura de ato sem chamar atenção para si."""
    n = int(dur * HZ)
    t = np.arange(n) / HZ
    freq = 58.0 * np.exp(-t * 1.2) + 32.0
    fase = 2.0 * np.pi * np.cumsum(freq) / HZ
    return np.sin(fase) * _envelope(n, 0.02, 0.28)


EFEITOS = {
    "whoosh": whoosh,
    "impacto": impacto,
    "riser": riser,
    "sub_boom": sub_boom,
}


def _normalizar(x: np.ndarray) -> np.ndarray:
    pico = float(np.max(np.abs(x))) or 1.0
    return x / pico * _amplitude()


def sintetizar(tipo: str, dur: float | None = None) -> np.ndarray:
    if tipo not in EFEITOS:
        raise ValueError(f"efeito '{tipo}' não existe. Conhecidos: {', '.join(sorted(EFEITOS))}")
    fn = EFEITOS[tipo]
    return _normalizar(fn(dur) if dur else fn())


def trilha(eventos: list, dur_total: float, saida: Path) -> Path:
    """Uma faixa de `dur_total` com os efeitos posicionados no tempo.

    `eventos`: [{"t": 12.34, "tipo": "whoosh", "dur": 0.6, "ganho": 1.0}]

    Evento fora da faixa é ignorado em silêncio de propósito: as âncoras podem
    mudar de lugar quando a narração é regerada, e derrubar o render inteiro por
    causa de um efeito 0,2s além do fim seria desproporcional.
    """
    n = int(dur_total * HZ) + 1
    faixa = np.zeros(n, dtype=np.float64)
    for ev in eventos:
        t = float(ev.get("t", 0.0))
        if t < 0 or t >= dur_total:
            continue
        som = sintetizar(ev.get("tipo", "whoosh"), ev.get("dur"))
        som = som * float(ev.get("ganho", 1.0))
        i = int(t * HZ)
        j = min(i + som.size, n)
        faixa[i:j] += som[: j - i]
    # soma de efeitos pode estourar; limita sem distorcer o que não estoura
    pico = float(np.max(np.abs(faixa)))
    if pico > 0.99:
        faixa *= 0.99 / pico
    saida.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(saida), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(HZ)
        f.writeframes((faixa * 32767).astype("<i2").tobytes())
    return saida


def eventos_dos_atos(inicios_de_ato: list, dur_total: float) -> list:
    """Efeito automático em toda quebra de ato.

    A quebra de ato já é um corte com dissolve; sem som ela passa muda, e mudo
    num corte marcado é o que faz o vídeo soar amador. O whoosh entra um pouco
    ANTES do corte, porque o som antecipa a imagem — é assim que se lê como
    intenção e não como eco.
    """
    eventos = []
    for t in inicios_de_ato:
        if t <= 0.05 or t >= dur_total:
            continue
        eventos.append({"t": max(t - 0.28, 0.0), "tipo": "whoosh", "dur": 0.55})
        eventos.append({"t": t, "tipo": "sub_boom", "dur": 1.1, "ganho": 0.7})
    return eventos
