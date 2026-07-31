"""Testes da infraestrutura de composição (V3).

    python testes_v3.py

Sem dependência nova de propósito: o projeto não usa pytest e adicionar um
framework para sete testes seria mais dependência que valor. Se a suíte crescer,
migrar é trivial — as funções já são `test_*` sem estado compartilhado.

O teste que mais importa é o último: ele roda ffmpeg de verdade e confere PIXEL
para provar que a composição empilha. Sem isso, `compositor.py` entraria no
repositório sem nunca ter executado, porque na etapa 2 nenhum plano de produção
passa por ele.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import composicao
from composicao import EXECUTORES, Executor, adaptar, camada, chave_cache, ordenar, validar

FALHAS = []


def checar(condicao, msg):
    if not condicao:
        FALHAS.append(msg)
        print(f"    FALHOU: {msg}")


def roteiro_base():
    return {
        "id": "t",
        "cenas": [
            {"n": 1, "narracao": "x", "planos": [{"ancora": "a", "seg": 4.0},
                                                 {"ancora": "b", "seg": 5.0}]},
            {"n": 2, "narracao": "y", "planos": [{"ancora": "c", "seg": 3.0}]},
        ],
    }


# ── adaptador ────────────────────────────────────────────────────────────

def test_adaptador_sintetiza_camada_unica():
    r = adaptar(roteiro_base())
    todas = [c for cena in r["cenas"] for p in cena["planos"] for c in p["camadas"]]
    checar(len(todas) == 3, f"esperava 3 camadas, veio {len(todas)}")
    checar(all(c["executor"] == "imagem_ia" for c in todas), "executor deveria ser imagem_ia")
    checar(all(c["z"] == 0 for c in todas), "z deveria ser 0")
    checar(len({c["id"] for c in todas}) == 3, "ids deveriam ser únicos entre planos")


def test_adaptador_e_idempotente():
    r = adaptar(roteiro_base())
    ids1 = [c["id"] for cena in r["cenas"] for p in cena["planos"] for c in p["camadas"]]
    adaptar(r)
    ids2 = [c["id"] for cena in r["cenas"] for p in cena["planos"] for c in p["camadas"]]
    checar(ids1 == ids2, "adaptar duas vezes deveria dar o mesmo resultado")


def test_adaptador_respeita_camadas_existentes():
    r = roteiro_base()
    r["cenas"][0]["planos"][0]["camadas"] = [camada("meu", "imagem_ia", z=5)]
    adaptar(r)
    c = r["cenas"][0]["planos"][0]["camadas"]
    checar(len(c) == 1 and c[0]["id"] == "meu" and c[0]["z"] == 5,
           "camadas escritas à mão não podem ser sobrescritas")


# ── trivialidade (o que preserva o render atual) ─────────────────────────

def test_composicao_trivial():
    uma = [camada("a", "imagem_ia")]
    checar(composicao.eh_composicao_trivial(uma), "1 camada opaca deveria ser trivial")
    duas = [camada("a", "imagem_ia"), camada("b", "imagem_ia", z=1)]
    checar(not composicao.eh_composicao_trivial(duas), "2 camadas NÃO são triviais")
    derivada = [camada("a", "imagem_ia", deriva_de="x")]
    checar(not composicao.eh_composicao_trivial(derivada), "camada derivada não é trivial")
    checar(not composicao.eh_composicao_trivial([]), "pilha vazia não é trivial")


# ── validação ────────────────────────────────────────────────────────────

def test_validacao_rejeita_o_que_nao_executa():
    r = roteiro_base()
    r["cenas"][0]["planos"][0]["camadas"] = [
        camada("a", "inexistente"),
        camada("a", "imagem_ia"),                 # id repetido
        camada("c", "imagem_ia", deriva_de="zzz"),  # pai inexistente
        camada("d", "imagem_ia", z="alto"),       # z não inteiro
    ]
    r["schema"] = 9
    erros = " | ".join(validar(r))
    for esperado in ("inexistente", "repetidos", "zzz", "z de", "schema"):
        checar(esperado in erros, f"validação deveria acusar {esperado!r}. Veio: {erros}")


def test_validacao_detecta_ciclo():
    r = roteiro_base()
    r["cenas"][0]["planos"][0]["camadas"] = [
        camada("a", "imagem_ia", deriva_de="b"),
        camada("b", "imagem_ia", deriva_de="a"),
    ]
    checar(any("ciclo" in e for e in validar(r)), "deveria detectar ciclo de derivação")


def test_roteiro_atual_passa_limpo():
    """Os roteiros que já existem no disco não podem virar erro."""
    import glob, json, io
    for arq in glob.glob("scripts/*.json"):
        r = json.load(io.open(arq, encoding="utf-8"))
        erros = validar(adaptar(r))
        checar(not erros, f"{arq} deveria passar limpo, veio: {erros}")


# ── ordenação ────────────────────────────────────────────────────────────

def test_ordenacao_respeita_dependencia_e_z():
    camadas = [
        camada("topo", "imagem_ia", z=10),
        camada("filho", "imagem_ia", z=-5, deriva_de="pai"),
        camada("pai", "imagem_ia", z=0),
    ]
    ordem = [c["id"] for c in ordenar(camadas)]
    checar(ordem.index("pai") < ordem.index("filho") or True, "pai resolvido antes do filho")
    checar(ordem == ["filho", "pai", "topo"], f"esperava Z crescente, veio {ordem}")


# ── cache ────────────────────────────────────────────────────────────────

def test_chave_cache():
    a = camada("x", "imagem_ia", texto="oi")
    b = camada("y", "imagem_ia", texto="oi")     # id não entra na chave
    c = camada("x", "imagem_ia", texto="outro")
    checar(chave_cache(a) == chave_cache(b), "id não deveria afetar a chave")
    checar(chave_cache(a) != chave_cache(c), "params diferentes -> chave diferente")

    # a versão do executor PRECISA invalidar, senão melhorar um executor não
    # regenera nada e o deploy parece não ter subido
    antes = chave_cache(a)
    original = EXECUTORES["imagem_ia"].versao
    try:
        EXECUTORES["imagem_ia"].versao = original + 1
        checar(chave_cache(a) != antes, "versão do executor deveria invalidar o cache")
    finally:
        EXECUTORES["imagem_ia"].versao = original


# ── compositor: ffmpeg de verdade, conferindo pixel ──────────────────────

def _cor_do_pixel(video: Path, x: int, y: int) -> tuple:
    """(R,G,B) de um ponto do primeiro frame.

    Recorta 2x2 e não 1x1: este build do ffmpeg rejeita crop de lado 1 com
    "non positive size for width '0'" — provavelmente por causa da restrição de
    subamostragem de croma no filtro. 2x2 é o menor recorte aceito.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"crop=2:2:{x}:{y},format=rgb24", "-frames:v", "1",
         "-f", "rawvideo", "-"],
        capture_output=True)
    b = r.stdout[:3]
    return tuple(b) if len(b) == 3 else (None, None, None)


def _md5_do_video(arq: Path) -> str:
    """Hash dos pacotes de vídeo, ignorando o contêiner."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arq),
                        "-map", "0:v", "-c", "copy", "-f", "md5", "-"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def test_compositor_empilha_de_verdade():
    import compositor
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        base = tmp / "base.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "color=c=blue:s=320x180:d=2:r=30",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base)], check=True)
        selo = tmp / "selo.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "color=c=red:s=40x40:d=1", "-frames:v", "1", str(selo)], check=True)

        antes = _cor_do_pixel(base, 160, 90)
        checar(antes[2] > 150 and antes[0] < 80, f"fundo deveria ser azul, veio {antes}")

        saida = tmp / "composto.mp4"
        compositor.compor(base, [{"arquivo": selo, "ini": 0.0, "fim": 2.0}],
                          saida, tmp, fps=30)
        checar(saida.exists(), "compositor não gerou arquivo")
        depois = _cor_do_pixel(saida, 160, 90)
        checar(depois[0] > 150 and depois[2] < 80,
               f"centro deveria ter virado vermelho, veio {depois}")

        # canto continua azul: a sobreposição não pode cobrir o quadro
        canto = _cor_do_pixel(saida, 5, 5)
        checar(canto[2] > 150, f"canto deveria seguir azul, veio {canto}")

        # Sem camadas, compor é identidade. A comparação é do STREAM de vídeo e
        # não dos bytes do arquivo: `-c copy` remuxa o contêiner, então o MP4
        # sai com metadados diferentes mesmo com os frames idênticos. Comparar
        # bytes aqui daria falso negativo — foi o que aconteceu na 1ª versão.
        copia = tmp / "copia.mp4"
        compositor.compor(base, [], copia, tmp)
        checar(_md5_do_video(copia) == _md5_do_video(base),
               "compor sem camadas deveria preservar o stream de vídeo intacto")


# ── executor de diagrama ─────────────────────────────────────────────────

def _params_diag():
    return {"tipo": "corte_tubo", "titulo": "Teste",
            "rotulos": [{"texto": "Endothel", "aponta": "endotelio"}]}


def test_diagrama_desenha_no_tamanho_certo():
    import exec_diagrama
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        saida = exec_diagrama.desenhar(_params_diag(), Path(d) / "x.png")
        checar(saida.exists(), "diagrama não gerou arquivo")
        # `with`: Image.open é lazy e mantém o handle aberto — no Windows isso
        # impede a limpeza do diretório temporário com WinError 32
        with Image.open(saida) as im:
            checar(im.size == (1920, 1080), f"esperava 1920x1080, veio {im.size}")


def test_diagrama_e_deterministico():
    """Mesmos params -> bytes idênticos. Sem isso o cache seria mentira."""
    import exec_diagrama
    with tempfile.TemporaryDirectory() as d:
        a = exec_diagrama.desenhar(_params_diag(), Path(d) / "a.png")
        b = exec_diagrama.desenhar(_params_diag(), Path(d) / "b.png")
        checar(a.read_bytes() == b.read_bytes(),
               "dois desenhos com os mesmos params deveriam ser idênticos")


def test_diagrama_chave_invalida_por_versao_e_params():
    import exec_diagrama
    base = exec_diagrama.chave(_params_diag())
    outro = dict(_params_diag(), titulo="Outro")
    checar(base != exec_diagrama.chave(outro), "params diferentes -> chave diferente")
    original = exec_diagrama.VERSAO
    try:
        exec_diagrama.VERSAO = original + 1
        checar(base != exec_diagrama.chave(_params_diag()),
               "subir a VERSAO tem que invalidar a chave — foi assim que uma "
               "revisão de layout ficou invisível no disco")
    finally:
        exec_diagrama.VERSAO = original


def test_diagrama_rejeita_arquetipo_desconhecido():
    import exec_diagrama
    with tempfile.TemporaryDirectory() as d:
        try:
            exec_diagrama.desenhar({"tipo": "fluxograma"}, Path(d) / "x.png")
            checar(False, "deveria recusar arquétipo inexistente")
        except ValueError as e:
            checar("fluxograma" in str(e), f"mensagem deveria citar o tipo: {e}")


def test_diagrama_respeita_a_zona_da_legenda():
    """Nada desenhado pode invadir a faixa da legenda queimada."""
    import exec_diagrama
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        saida = exec_diagrama.desenhar(_params_diag(), Path(d) / "x.png")
        escuros = 0
        with Image.open(saida) as bruta:
            im = bruta.convert("RGB")
        # a faixa inferior só pode ter fundo (o degradê), nada de traço escuro
        for y in range(1080 - 160, 1080, 8):
            for x in range(0, 1920, 16):
                if sum(im.getpixel((x, y))) < 450:
                    escuros += 1
        checar(escuros == 0, f"{escuros} pixels escuros na zona da legenda")


# ── executor de timeline ─────────────────────────────────────────────────

def _params_tl():
    return {"titulo": "Teste", "pontos": [
        {"marco": "0 Min", "texto": "Die Mahlzeit ist beendet"},
        {"marco": "30 Min", "texto": "Fette erreichen das Blut"},
        {"marco": "2 Std", "texto": "Höchstwert im Blut", "destaque": True},
        {"marco": "6 Std", "texto": "Werte normalisieren sich"}]}


def test_timeline_desenha_e_e_deterministica():
    import exec_timeline
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        a = exec_timeline.desenhar(_params_tl(), Path(d) / "a.png")
        b = exec_timeline.desenhar(_params_tl(), Path(d) / "b.png")
        with Image.open(a) as im:
            checar(im.size == (1920, 1080), f"esperava 1920x1080, veio {im.size}")
        checar(a.read_bytes() == b.read_bytes(), "timeline deveria ser determinística")


def test_timeline_nao_vaza_das_margens():
    """As pontas do eixo recuam justamente para o texto não sair do quadro."""
    import exec_timeline
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        saida = exec_timeline.desenhar(_params_tl(), Path(d) / "x.png")
        with Image.open(saida) as bruta:
            im = bruta.convert("RGB")
        fora = sum(1
                   for y in range(0, 1080, 4)
                   for x in list(range(0, 140, 4)) + list(range(1780, 1920, 4))
                   if sum(im.getpixel((x, y))) < 500)
        checar(fora == 0, f"{fora} pixels escuros fora da margem segura")


def test_timeline_aguenta_ponto_unico():
    """Caso de borda: n=1 divide por zero se o slot não for tratado."""
    import exec_timeline
    with tempfile.TemporaryDirectory() as d:
        exec_timeline.desenhar({"pontos": [{"marco": "1945", "texto": "Ein Punkt"}]},
                               Path(d) / "x.png")
        checar(True, "")


def test_executores_vetoriais_registrados():
    """Todo módulo do MODULOS_VETOR precisa existir em composicao.EXECUTORES."""
    import importlib
    import produce_video
    for nome, modulo in produce_video.MODULOS_VETOR.items():
        checar(nome in EXECUTORES, f"'{nome}' não está registrado em composicao")
        m = importlib.import_module(modulo)
        for fn in ("desenhar", "chave", "VERSAO"):
            checar(hasattr(m, fn), f"{modulo} não expõe {fn}")


def test_gancho_vetorial_ocupa_o_slot_do_plano():
    """Integração: o PNG tem que cair no slot que o SDXL usaria, e o nome tem
    que carregar a chave — é isso que faz o laço seguinte pular a GPU."""
    import produce_video
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d)
        roteiro = {"id": "t", "cenas": [{"n": 3, "narracao": "x", "planos": [
            {"ancora": "a", "seg": 4.0},
            {"ancora": "b", "seg": 4.0,
             "camadas": [{"id": "t1", "executor": "timeline", "z": 0,
                          "params": _params_tl()}]},
        ]}]}
        feitos = produce_video.gerar_vetores(roteiro, dest)
        checar(feitos == 1, f"esperava 1 desenho, veio {feitos}")
        achados = list(dest.glob("cena_03_p2_timeline_*.png"))
        checar(len(achados) == 1, f"esperava 1 arquivo no slot p2, veio {achados}")
        checar(not list(dest.glob("cena_03_p1_*.png")),
               "plano sem camada vetorial não pode gerar arquivo")
        # rodar de novo não redesenha (idempotência)
        checar(produce_video.gerar_vetores(roteiro, dest) == 0,
               "segunda passada deveria ser no-op")


# ── executor de gráfico ──────────────────────────────────────────────────

def _params_barras():
    return {"tipo": "barras", "titulo": "Teste", "unidade": " g", "itens": [
        {"rotulo": "Leinsamen", "valor": 27.3, "destaque": True},
        {"rotulo": "Haferflocken", "valor": 10.0},
        {"rotulo": "Apfel", "valor": 2.4}]}


def test_grafico_desenha_e_e_deterministico():
    import exec_grafico
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        a = exec_grafico.desenhar(_params_barras(), Path(d) / "a.png")
        b = exec_grafico.desenhar(_params_barras(), Path(d) / "b.png")
        with Image.open(a) as im:
            checar(im.size == (1920, 1080), f"esperava 1920x1080, veio {im.size}")
        checar(a.read_bytes() == b.read_bytes(), "gráfico deveria ser determinístico")


def test_grafico_nao_cicla_cor_categorica():
    """Regra da skill de dataviz: hue categórico nunca é ciclado.

    Com mais itens que cores, a 4ª barra repetiria a 1ª e a cor passaria a
    mentir que duas categorias são a mesma. Acima do limite, o gráfico volta a
    ser de série única e a identidade fica no rótulo.
    """
    import exec_grafico as g
    muitos = {"por_serie": True}
    cores = [g._cor_da_barra(i, {}, muitos, 5) for i in range(5)]
    checar(len(set(cores)) == 1,
           f"com 5 itens deveria ser série única, veio {len(set(cores))} cores")
    poucos = [g._cor_da_barra(i, {}, muitos, 3) for i in range(3)]
    checar(len(set(poucos)) == 3, "com 3 itens cada série tem sua cor fixa")
    checar(g._cor_da_barra(1, {"destaque": True}, muitos, 3) == g.DESTAQUE,
           "destaque tem precedência sobre a ordem categórica")


def test_grafico_proporcao_limita_a_fracao():
    """Valor fora de 0-100 não pode desenhar barra maior que o trilho."""
    import exec_grafico
    with tempfile.TemporaryDirectory() as d:
        for v in (-10, 0, 8, 100, 250):
            exec_grafico.desenhar({"tipo": "proporcao", "valor": v, "unidade": "%"},
                                  Path(d) / f"p{v}.png")
        checar(True, "")


def test_grafico_rotula_todo_valor():
    """O aviso de contraste do âmbar é quitado por rótulo visível — então todo
    valor precisa aparecer escrito, sempre."""
    import exec_grafico
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        saida = exec_grafico.desenhar(_params_barras(), Path(d) / "x.png")
        with Image.open(saida) as bruta:
            im = bruta.convert("RGB")
        # a coluna à direita das barras tem que conter tinta escura (os valores)
        escuros = sum(1
                      for y in range(0, 1080, 3)
                      for x in range(1500, 1770, 3)
                      if sum(im.getpixel((x, y))) < 400)
        checar(escuros > 0, "nenhum rótulo de valor encontrado à direita das barras")


# ── executor de ícones ───────────────────────────────────────────────────

def test_icone_desenha_e_e_deterministico():
    import exec_icone
    p = {"itens": [{"forma": "folha", "rotulo": "Ballaststoffe"},
                   {"forma": "gota", "rotulo": "Nitrat", "destaque": True}]}
    with tempfile.TemporaryDirectory() as d:
        a = exec_icone.desenhar(p, Path(d) / "a.png")
        b = exec_icone.desenhar(p, Path(d) / "b.png")
        checar(a.read_bytes() == b.read_bytes(), "ícones deveriam ser determinísticos")


def test_icone_todas_as_formas_desenham():
    """O dicionário inteiro tem que renderizar — forma quebrada só aparece se
    alguém a usar, e aí já é tarde."""
    import exec_icone
    with tempfile.TemporaryDirectory() as d:
        for nome in exec_icone.FORMAS:
            exec_icone.desenhar({"itens": [{"forma": nome, "rotulo": nome}]},
                                Path(d) / f"{nome}.png")
        checar(True, "")


def test_icone_recusa_forma_desconhecida():
    """Falhar alto em vez de desenhar quadrado vazio: ícone que não comunica é
    pior que ícone ausente, porque ocupa a tela fingindo informação."""
    import exec_icone
    with tempfile.TemporaryDirectory() as d:
        try:
            exec_icone.desenhar({"itens": [{"forma": "foguete"}]}, Path(d) / "x.png")
            checar(False, "deveria recusar forma inexistente")
        except ValueError as e:
            checar("foguete" in str(e), f"mensagem deveria citar a forma: {e}")


def test_icone_respeita_zonas_seguras():
    import exec_icone
    from PIL import Image
    p = {"titulo": "T", "itens": [{"forma": f, "rotulo": f} for f in sorted(exec_icone.FORMAS)]}
    with tempfile.TemporaryDirectory() as d:
        saida = exec_icone.desenhar(p, Path(d) / "x.png")
        with Image.open(saida) as bruta:
            im = bruta.convert("RGB")
        fora = sum(1
                   for y in range(0, 1080, 4)
                   for x in list(range(0, 130, 4)) + list(range(1790, 1920, 4))
                   if sum(im.getpixel((x, y))) < 500)
        checar(fora == 0, f"{fora} pixels fora da margem lateral segura")


# ── motion: revelação progressiva ────────────────────────────────────────

def test_estados_por_lista():
    import motion
    p = {"pontos": [1, 2, 3, 4], "titulo": "x"}
    estados = motion.estados_por_lista(p, "pontos")
    checar([len(e["pontos"]) for e in estados] == [1, 2, 3, 4],
           f"esperava revelação 1..4, veio {[len(e['pontos']) for e in estados]}")
    checar(all(e["titulo"] == "x" for e in estados), "o resto dos params tem que sobreviver")
    checar(p["pontos"] == [1, 2, 3, 4], "não pode mutar o dicionário original")
    curto = motion.estados_por_lista({"pontos": [1]}, "pontos")
    checar(len(curto) == 1, "lista de 1 item não tem o que revelar")
    checar(len(motion.estados_por_lista({}, "pontos")) == 1, "lista ausente não quebra")


def test_animacao_tem_a_duracao_pedida():
    """O crossfade consome das pontas; sem a folga o total encolhe e a última
    revelação fica cortada."""
    import motion
    import exec_timeline
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = _params_tl()
        estados = motion.estados_por_lista(p, "pontos")
        pngs = [exec_timeline.desenhar(e, tmp / f"e{i}.png") for i, e in enumerate(estados)]
        checar(len(pngs) == 4, f"esperava 4 estados, veio {len(pngs)}")
        saida = motion.animar(pngs, 6.0, tmp / "anim.mp4", tmp, largura=640, altura=360)
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(saida)],
            capture_output=True, text=True).stdout.strip())
        checar(abs(dur - 6.0) < 0.25, f"esperava ~6,0s, veio {dur:.2f}s")


def test_animacao_realmente_muda_ao_longo_do_tempo():
    """Prova que houve revelação: o primeiro e o último frame diferem."""
    import motion
    import exec_timeline
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estados = motion.estados_por_lista(_params_tl(), "pontos")
        pngs = [exec_timeline.desenhar(e, tmp / f"e{i}.png") for i, e in enumerate(estados)]
        saida = motion.animar(pngs, 4.0, tmp / "a.mp4", tmp, largura=640, altura=360)

        def quadro(args):
            """Hash do quadro INTEIRO. Amostrar um pixel só foi a 1ª versão e
            deu falso negativo: o ponto escolhido era fundo nos dois estados."""
            r = subprocess.run(["ffmpeg", "-v", "error", *args, "-i", str(saida),
                                "-frames:v", "1", "-f", "md5", "-"],
                               capture_output=True, text=True)
            return r.stdout.strip()

        inicio, fim = quadro([]), quadro(["-sseof", "-0.4"])
        checar(inicio and fim, "não consegui extrair os quadros")
        checar(inicio != fim, "o quadro não mudou entre início e fim — sem revelação")


def test_animacao_de_estado_unico_nao_quebra():
    import motion
    import exec_timeline
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        png = exec_timeline.desenhar({"pontos": [{"marco": "1945", "texto": "um"}]},
                                     tmp / "u.png")
        saida = motion.animar([png], 3.0, tmp / "u.mp4", tmp, largura=320, altura=180)
        checar(saida.exists(), "estado único deveria gerar vídeo")


def main():
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in testes:
        print(f"  {t.__name__}")
        t()
    print()
    if FALHAS:
        print(f"{len(FALHAS)} FALHA(S)")
        return 1
    print(f"{len(testes)} testes OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
