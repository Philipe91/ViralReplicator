"""
Estuda a ESTRUTURA de um vídeo de referência a partir das legendas públicas.

Filosofia (definida com o dono do projeto): a transcrição serve para APRENDER —
que assuntos entram, em que ordem, em que ritmo — do mesmo jeito que se estuda
uma aula para depois apresentar o trabalho com as próprias palavras. O texto do
outro canal nunca vira texto do nosso roteiro; o que atravessa é o esqueleto:
onde está o gancho, quantos blocos, quanto dura cada um, onde abrem e fecham os
loops de curiosidade.

    python estudo_canal.py estudo/thinkscience/zRMtp04VHLQ.en.vtt
    python estudo_canal.py <vtt> --blocos 12

Saída: <id>_estrutura.json com o mapa de blocos e as métricas de ritmo.
"""

import argparse
import json
import re
from pathlib import Path

# marcadores de virada de assunto típicos de vídeo explicativo em inglês
VIRADAS = re.compile(
    r"^(but|now|so|here'?s|that'?s why|the (first|second|third|next|last)|"
    r"number \w+|let'?s|imagine|think about|and this is|which means|"
    r"in fact|studies show|research|scientists|the problem|the good news)\b",
    re.I,
)
PERGUNTA = re.compile(r"\?")
SEGUNDA_PESSOA = re.compile(r"\b(you|your|you'?re|you'?ll|yourself)\b", re.I)


def ler_vtt(caminho: Path):
    """Devolve [(inicio_seg, fim_seg, texto)] limpo e sem duplicata.

    Legenda automática do YouTube repete a linha anterior a cada cue (efeito
    rolagem). Sem deduplicar, a contagem de palavras dobra.
    """
    txt = caminho.read_text(encoding="utf-8", errors="replace")
    blocos, visto = [], set()
    padrao = re.compile(
        r"(\d\d:\d\d:\d\d\.\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d\.\d\d\d)[^\n]*\n(.*?)(?=\n\n|\n\d\d:|\Z)",
        re.S,
    )

    def seg(t):
        h, m, s = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    for ini, fim, corpo in padrao.findall(txt):
        linhas = []
        for ln in corpo.strip().splitlines():
            ln = re.sub(r"<[^>]+>", "", ln).strip()          # tags de karaokê
            ln = re.sub(r"\[[^\]]*\]", "", ln).strip()        # [Music], [Applause]
            if ln and ln not in visto:
                visto.add(ln)
                linhas.append(ln)
        if linhas:
            blocos.append((seg(ini), seg(fim), " ".join(linhas)))
    return blocos


def frases(blocos):
    """Junta os cues e reparte em frases com tempo aproximado de início."""
    texto, marcas = "", []
    for ini, _fim, t in blocos:
        marcas.append((len(texto), ini))
        texto += t + " "
    saida = []
    for m in re.finditer(r"[^.!?]+[.!?]+|\S[^.!?]*$", texto):
        pos = m.start()
        t = next((tt for p, tt in reversed(marcas) if p <= pos), 0.0)
        f = m.group().strip()
        if f:
            saida.append((t, f))
    return saida


def analisar(caminho: Path, n_blocos=10):
    cues = ler_vtt(caminho)
    if not cues:
        raise SystemExit("Nenhuma legenda lida — o arquivo tem cues?")
    fr = frases(cues)
    dur = cues[-1][1]
    palavras = sum(len(t.split()) for _, _, t in cues)

    # candidatos a virada de assunto
    viradas = [(t, f) for t, f in fr if VIRADAS.match(f)]

    # divide a linha do tempo em N blocos iguais e mede cada um
    passo = dur / n_blocos
    mapa = []
    for i in range(n_blocos):
        ini, fim = i * passo, (i + 1) * passo
        dentro = [f for t, f in fr if ini <= t < fim]
        txt = " ".join(dentro)
        n_pal = len(txt.split())
        mapa.append({
            "bloco": i + 1,
            "ini": round(ini, 1),
            "fim": round(fim, 1),
            "frases": len(dentro),
            "palavras": n_pal,
            "ppm": round(n_pal / (passo / 60), 1) if passo else 0,
            "perguntas": len(PERGUNTA.findall(txt)),
            "voce_por_100pal": round(100 * len(SEGUNDA_PESSOA.findall(txt)) / max(n_pal, 1), 1),
            "viradas": [round(t, 1) for t, _ in viradas if ini <= t < fim],
        })

    gancho = [f for t, f in fr if t < 30]
    return {
        "arquivo": caminho.name,
        "duracao_seg": round(dur, 1),
        "duracao_min": round(dur / 60, 2),
        "palavras": palavras,
        "palavras_por_minuto": round(palavras / (dur / 60), 1),
        "frases": len(fr),
        "palavras_por_frase": round(palavras / max(len(fr), 1), 1),
        "perguntas_total": sum(b["perguntas"] for b in mapa),
        "densidade_voce_por_100pal": round(
            100 * sum(len(SEGUNDA_PESSOA.findall(f)) for _, f in fr) / max(palavras, 1), 1),
        "viradas_de_assunto": len(viradas),
        "gancho_30s": {"frases": len(gancho),
                       "palavras": sum(len(f.split()) for f in gancho),
                       "perguntas": sum(len(PERGUNTA.findall(f)) for f in gancho)},
        "mapa_de_blocos": mapa,
    }


def main():
    ap = argparse.ArgumentParser(description="Mapa estrutural de um vídeo de referência.")
    ap.add_argument("vtt")
    ap.add_argument("--blocos", type=int, default=10)
    args = ap.parse_args()
    p = Path(args.vtt)
    r = analisar(p, args.blocos)
    dest = p.with_name(p.stem.split(".")[0] + "_estrutura.json")
    dest.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"duracao      : {r['duracao_min']} min ({r['duracao_seg']}s)")
    print(f"palavras     : {r['palavras']}  ({r['palavras_por_minuto']} ppm)")
    print(f"frases       : {r['frases']}  ({r['palavras_por_frase']} palavras/frase)")
    print(f"perguntas    : {r['perguntas_total']}")
    print(f"'voce'/100pal: {r['densidade_voce_por_100pal']}")
    print(f"viradas      : {r['viradas_de_assunto']}")
    print(f"gancho 30s   : {r['gancho_30s']}")
    print()
    print(f"{'bl':>3} {'ini':>6} {'pal':>5} {'ppm':>6} {'?':>2} {'voce':>5}  viradas")
    for b in r["mapa_de_blocos"]:
        print(f"{b['bloco']:>3} {b['ini']:>6.0f} {b['palavras']:>5} {b['ppm']:>6.0f} "
              f"{b['perguntas']:>2} {b['voce_por_100pal']:>5.1f}  {len(b['viradas'])}")
    print(f"\n-> {dest}")


if __name__ == "__main__":
    main()
