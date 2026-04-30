# Diagnóstico — Viral Replicator Pro

**Data:** 2026-04-29
**Repo:** [github.com/Philipe91/ViralReplicator](https://github.com/Philipe91/ViralReplicator)
**Commit analisado:** `ccd6fed` (HEAD de `main`)
**Modo:** somente leitura — nenhum arquivo do projeto foi alterado nesta sessão (este documento é o único arquivo novo).

> ⚠️ **Bug crítico de segurança encontrado durante a leitura, anotado mas NÃO corrigido:** ver seção [§3.5](#35-bugs-encontrados-no-caminho-só-anotados).

---

## 1. Mapa do projeto

### 1.1 Árvore (3 níveis, sem `venv/` e `__pycache__/`)

```
ViralReplicator/
├── .gitignore
├── .streamlit/
│   └── config.toml                  # tema dark Streamlit (#eab308 primary)
├── README.md
├── core_intelligence_prompt.md      # spec do sistema (4 camadas, scoring, modo strict)
├── requirements.txt                 # 5 deps — INCOMPLETO (faltam streamlit, flask)
│
├── main.py                          # entry CLI: pipeline + agendador 30min
├── app.py                           # entry Flask  (ÓRFÃO — ver §2.3)
├── app_pro.py                       # entry Streamlit (UI viva, 488 linhas)
│
├── collector.py                     # camada 1 — YouTube Data API v3
├── analyzer.py                      # camada 2 — métricas (views/h, eng, viral_score)
├── filters.py                       # camada 3 — exclusão gaming/face + classify_niche
├── pattern_detector.py              # camada 3 — regex + KMeans/TF-IDF
├── scoring.py                       # camada 4 — 6 sub-scores
├── global_opportunity_engine.py     # camada 4 — IO por país (10 países hardcoded)
├── idea_generator.py                # camada 4 — OpenAI (chamada COMENTADA) + fallback
├── copy_engine.py                   # camada 4 — playbook 100% estático
├── alerts.py                        # camada 4 — print() no console
├── storage.py                       # SQLite v3 (save_to_csv é alias de save_to_db)
├── config.py                        # API keys + 36 queries + thresholds
│
├── style.css                        # 12 KB — design system inline da UI
├── templates/index.html             # template do app.py (Flask)
├── static/css/style.css             # 5 KB — outro CSS (do Flask)
│
├── saved_channels.json              # IDs de vídeos salvos pelo usuário
├── viral_replicator.db              # SQLite v1 (legado, 114 KB)
├── viral_replicator_v2.db           # SQLite v2 (legado, 176 KB)
├── viral_replicator_v3.db           # SQLite v3 (em uso, 159 KB)
└── virais_detectados.csv            # CSV legado (135 KB) — não é gerado pela pipeline atual
```

### 1.2 Stack identificada

| Camada | Tech |
|---|---|
| Linguagem | Python 3.x (sem versão fixada) |
| Orquestração | `schedule` (loop 30 min) |
| HTTP | `requests` (sem retry/backoff) |
| Coleta | YouTube Data API v3 (search + videos + channels) |
| ML | `scikit-learn` (TfidfVectorizer + KMeans) |
| Dados | `pandas` |
| LLM | `openai` (declarado mas chamada comentada em `idea_generator.py:35-39`) |
| Persistência | `sqlite3` (stdlib) + JSON + CSV legado |
| UI principal | `streamlit` (não declarada em `requirements.txt`) |
| UI legada | `flask` + `flask-cors` (não declaradas em `requirements.txt`) |
| Front-end | HTML inline em strings Python + Inter (Google Fonts) + FontAwesome 6.5 (CDN) |

### 1.3 Pontos de entrada

| Arquivo | Tipo | O que faz |
|---|---|---|
| [main.py](../main.py) | CLI | `run_pipeline()` síncrono → loop `schedule` a cada 30 min |
| [app_pro.py](../app_pro.py) | Streamlit | Dashboard "Viral Replicator Pro" — abre [viral_replicator_v3.db](../viral_replicator_v3.db), 7 abas, botão "Varredura Agora" replica a pipeline |
| [app.py](../app.py) | Flask | Servidor REST `/api/data` + `/api/run` — lê [virais_detectados.csv](../virais_detectados.csv) (que ninguém escreve hoje) |

---

## 2. Camadas funcionais

### 2.1 Descoberta — [collector.py](../collector.py)

**Único coletor:** YouTube Data API v3 via `requests`.

- 36 queries em [config.py:11-31](../config.py#L11-L31), divididas em 4 blocos: True Crime, Dark Curiosidades, Documentário IA/Ciência, Histórias IA Dark.
- A cada rodada faz `random.shuffle` e usa **6 queries**.
- Para cada query: `publishedAfter` é **aleatorizado entre 12h-72h atrás** ([collector.py:29](../collector.py#L29)) — escolha intencional pra forçar variação.
- 3 chamadas API por query: `/search` (IDs), `/videos` (estatísticas em batches de 50), `/channels` (subs em batches de 50).
- `videoDuration: medium` (4-20 min) — exclui Shorts no nível da API.
- **Não tem:** retry, backoff, cache de quota, paginação (só primeira página), tratamento de erro `403 quotaExceeded`.

**Não existe coleta por:** RSS, scraping (yt-dlp/ytsr), comments, trending por país, search por canal "phantom".

### 2.2 Scoring — fragmentado em 4 arquivos

#### [analyzer.py](../analyzer.py) — métricas brutas
- `hours_since_upload`, `views_per_hour`, `engagement_rate`, `is_short` (<62s).
- `viral_score = (views_per_hour × engagement_rate) / (subscribers + 1) × 1000` — fórmula heurística simples; **só usada por [alerts.py](../alerts.py)**, não pela UI.

#### [scoring.py](../scoring.py) — 6 sub-scores que a UI consome
| Score | Como é calculado |
|---|---|
| `rising_channel_score` | `(views/h ÷ subs) × 50000`, capado em 100; penaliza canais > 50k subs (×0.1); +20 se padrão de título reconhecido |
| `retention_score` | `(likes/views × 100) × 10`, capado em 100; +20 se vídeo > 10 min e views/h > 100 |
| `trend_timing` | `INÍCIO` (≤24h, v/h>50) / `CRESCENDO` (≤48h, v/h>20) / `SATURADO` (resto) |
| `production_difficulty` | `FÁCIL` (AI/<60s) / `MÉDIO` (<10min) / `DIFÍCIL` |
| `dark_score` | base 50, ±40 por keywords (vlog/podcast pra baixo, dark/explained pra cima), +20 se difficulty FÁCIL |
| `copy_score` | combinação ponderada dos anteriores |

A fórmula final do "Score" exibido nos cards (ex: [app_pro.py:183](../app_pro.py#L183)) é **calculada na UI** e diferente da fórmula no spec ([core_intelligence_prompt.md:41](../core_intelligence_prompt.md#L41)):
- **Spec:** `Score = Rising × 0.45 + Retenção × 0.30 + Copy × 0.25`
- **UI:** mesma fórmula, mas sem qualquer penalização ou bonificação contextual; e `calc_channel_score` ([app_pro.py:60](../app_pro.py#L60)) introduz um `+ 15` mágico sem comentário.

#### [pattern_detector.py](../pattern_detector.py)
- Regex de 6 estruturas de título (`This man...`, `Top 10`, `AI/Futurismo`, `Mistério/True Crime`, etc).
- KMeans com **n_clusters fixo em 3** e **nomes hardcoded** em [pattern_detector.py:55-58](../pattern_detector.py#L55-L58) — clusters não refletem semântica real, só posição numérica.

#### [global_opportunity_engine.py](../global_opportunity_engine.py)
- 10 países com 5 dimensões hardcoded: demanda, baixa_concorrência, idioma, cpm, crescimento.
- `country_score = demanda×0.30 + concorrência×0.30 + idioma×0.20 + cpm×0.10 + crescimento×0.10`.
- Top 4 vão pro DB.
- **Não calcula a "janela em dias"** que a UI promete — a UI faz fallback hardcoded em [app_pro.py:131-133](../app_pro.py#L131-L133) (8/18/30 dias por `trend_timing`).

### 2.3 Dashboard — Streamlit, com Flask órfão

**[app_pro.py](../app_pro.py)** (488 linhas) é a UI viva:
- Topbar custom + nav radio horizontal de 7 abas: Radar / Oportunidades / Expansão / Tendências / Cold Case / Histórias IA / Salvos.
- Toggle "Strict" (filtra `INÍCIO` + ≤50k subs).
- Busca local por título/canal.
- "Varredura Agora" executa a pipeline **síncrona** (com `st.status` mostrando progresso) — replica `main.run_pipeline` no botão.
- Card customizado em HTML inline ([app_pro.py:194-214](../app_pro.py#L194-L214)) com:
  - Thumb + 4 badges sobrepostos (timing, speed, window, country).
  - Score grande + 3 mini-barras (Replicação/Crescimento/Retenção).
  - Botão de decisão dinâmico: **ATACAR AGORA** / **OBSERVAR** / **SATURANDO**.
- Dialog de "Playbook" via `@st.dialog` com estrutura/narração/ferramentas + lista de mercados globais.
- Featured card no topo do Radar ("MELHOR OPORTUNIDADE AGORA").
- Visual: dark, Inter, FontAwesome 6.5, paleta verde/amarelo/vermelho/azul. CSS de 12 KB injetado por `st.markdown(..., unsafe_allow_html=True)`.

**[app.py](../app.py)** (Flask) + **[templates/index.html](../templates/index.html)** + **[static/css/style.css](../static/css/style.css)**: UI antiga, já abandonada — lê [virais_detectados.csv](../virais_detectados.csv) que **a pipeline atual não escreve mais** (só salva no DB; `save_to_csv` em [storage.py:102-103](../storage.py#L102-L103) é alias pra `save_to_db`).

### 2.4 Persistência — SQLite com 3 versões coexistindo

- Arquivo ativo: [viral_replicator_v3.db](../viral_replicator_v3.db) (consumido por [storage.py:5](../storage.py#L5) e [app_pro.py:45](../app_pro.py#L45)).
- Tabela única `videos` (29 colunas), PK = `id` (vídeo do YouTube).
- Estratégia de upsert: `INSERT OR REPLACE`.
- Migrações inline com `try/except Exception: pass` em [storage.py:44-51](../storage.py#L44-L51) — adiciona colunas `niche` e `channel_created_at` em bancos antigos.
- TTL de 48h via `clear_old_videos` ([storage.py:55](../storage.py#L55)) — **definido mas nunca chamado** pela pipeline.
- Bancos legados [viral_replicator.db](../viral_replicator.db) e [viral_replicator_v2.db](../viral_replicator_v2.db) seguem versionados sem propósito.
- Estado de UI: [saved_channels.json](../saved_channels.json) (lista de vídeo-IDs salvos pelo usuário).

### 2.5 Configuração

- Tudo em [config.py](../config.py).
- API keys leem `os.getenv` com **fallback hardcoded** — e a chave default do YouTube **é uma chave real** (ver §3.5 #1).
- Sem `.env`, sem `python-dotenv`, sem `pydantic-settings`.
- Thresholds (`MAX_RESULTS_PER_QUERY`, `MIN_VIEWS`, `MAX_HOURS_OLD`, `MAX_SUBSCRIBERS`, `VIRAL_SCORE_THRESHOLD`) são constantes globais — não há perfis por nicho/idioma.
- 36 queries de busca codificadas no mesmo arquivo, sem segmentação por idioma/região.

---

## 3. Análise de qualidade

### 3.1 Testes
**Cobertura: 0%.** Não existe pasta `tests/`, `pytest`/`unittest` não estão em [requirements.txt](../requirements.txt), nenhum arquivo `test_*.py` ou `*_test.py` no repo. Nenhum CI configurado (`.github/workflows/` ausente).

### 3.2 Logging
**Logging estruturado: ausente.** Tudo é `print()` com emojis (🔎, 📊, 🧠, 💡, 🚨, ❌). Pontos mais frágeis:
- [main.py:54](../main.py#L54) — exceção genérica engole stack trace inteiro: `except Exception as e: print(f"[PIPELINE][ERRO] {e}")`.
- [collector.py:53,93,116](../collector.py#L53) — três `except Exception` separados por chamada API, sem rate-limit awareness.
- [storage.py:67](../storage.py#L67) — falha de DB engolida em `print`.
- [app_pro.py:56](../app_pro.py#L56) — `except: return pd.DataFrame()` mascara qualquer erro de leitura do DB.

### 3.3 Type hints e docstrings
- Type hints **em ~5%** do código: aparecem só em [filters.py:49,57,83,142](../filters.py#L49) (`_contains_any`, `exclude_gaming`, `filter_viral_candidates`, `classify_niche`).
- Docstrings esparsos: presentes em [main.run_pipeline](../main.py#L13), [collector.get_recent_videos](../collector.py#L9), [filters.exclude_gaming](../filters.py#L57). Ausentes em todo o `scoring.py`, `analyzer.py`, `pattern_detector.py`, `global_opportunity_engine.py`, `copy_engine.py`.
- Constantes mágicas espalhadas (`50000`, `0.1`, `+15`, `+20`, `+30`) sem comentário do porquê.

### 3.4 Tratamento de erros — pontos frágeis ranqueados

1. **`carregar_dados` em [app_pro.py:43-57](../app_pro.py#L43-L57)** — `try/except: return pd.DataFrame()` esconde tudo. Se o DB ficar corrompido, o usuário vê "Banco vazio".
2. **`init_db` migrations em [storage.py:44-51](../storage.py#L44-L51)** — `except Exception: pass` aceita qualquer erro de `ALTER TABLE` silenciosamente.
3. **`get_saved` / `toggle_save` em [app_pro.py:24-34](../app_pro.py#L24-L34)** — `except: return []` mascara JSON corrompido.
4. **`generate_ideas_for_video` em [idea_generator.py:14-41](../idea_generator.py#L14-L41)** — chamada OpenAI **comentada**, sempre cai no fallback heurístico (linhas 35-39 não fazem nada).
5. **`isodate_to_datetime` em [analyzer.py:4-7](../analyzer.py#L4-L7)** — quebra se a API retornar timezone com fração de segundo (`.000Z`); sem `try`, propaga.
6. **`run_pipeline` em [main.py:54-55](../main.py#L54-L55)** — captura `Exception` genérica no nível do orquestrador inteiro: uma falha em qualquer camada esconde de qual.

### 3.5 Bugs encontrados no caminho (só anotados)

> Estes bugs foram identificados durante o mapeamento. Conforme combinado, **NÃO foram corrigidos** nesta sessão.

#### #1 — 🚨 **CRÍTICO** — API key real do Google **commitada no GitHub público**
- Local: [config.py:4](../config.py#L4)
- A chave `AIzaSyA6OJDvvDaH-MbjkTBkJeUJWzLGQ4OAioA` está como valor default de `os.getenv` e foi pushed para `main` em `ccd6fed`.
- **Risco:** qualquer pessoa pode usar a quota do Google Cloud do Philipe; revoga-se cota da YouTube Data API rapidinho. Bots scrapeiam GitHub atrás disso.
- **Ação P0 (fora desta sessão):** revogar a chave imediatamente no Google Cloud Console; gerar nova; mover pra `.env` ignorado pelo git; remover do histórico do git (`git filter-repo` ou BFG).

#### #2 — Filtro de data invertido elimina canais legítimos ✅ RESOLVIDO (Fase 0.5)
- Local: [filters.py:103](../filters.py#L103) → `if c_date and c_date < '2026-01-01': continue`
- O comentário acima ([filters.py:99](../filters.py#L99)) dizia "elimina shorts E canais velhos (antes de 2026)". Hoje é **2026-04-29** — a regra excluía qualquer canal criado antes de janeiro/2026. Isso descartava praticamente todos os canais do YouTube com ≥1 ano de idade.
- **Resolução:** gate removido em `4fe1a306`; idade do canal virou sinal contínuo no scoring (`EMBRYONIC_BOOST=15` se `channel_age_days < 90`, senão neutro). Phantom channels da §5.2 agora destravados. Ver [docs/01-proposta-fase05-tarefa1.md](01-proposta-fase05-tarefa1.md) pro racional.

#### #3 — Gate duplicado em `filter_viral_candidates` ✅ RESOLVIDO (Fase 0.5)
- Local: [filters.py:95-96](../filters.py#L95-L96) e [filters.py:99-100](../filters.py#L99-L100) — mesmo `if duration_seconds < 180: continue` repetido.
- **Resolução:** dead code eliminado junto do bug #2 em `4fe1a306`.

#### #4 — Chamada OpenAI comentada
- Local: [idea_generator.py:35-39](../idea_generator.py#L35-L39) — código `openai.chat.completions.create(...)` está dentro de comentário. O `try` só monta o `prompt` e nunca executa nada.
- **Efeito:** mesmo com `OPENAI_API_KEY` configurada, todas as ideias caem no fallback rule-based.

#### #5 — `app.py` (Flask) é UI órfã
- Local: [app.py:11](../app.py#L11) → lê [virais_detectados.csv](../virais_detectados.csv); mas [storage.py:102-103](../storage.py#L102-L103) → `save_to_csv` na verdade salva no DB, nunca toca o CSV.
- O CSV existente (135 KB) é fóssil de uma versão anterior. Flask app está rodando vazio.

#### #6 — Pipeline duplicada na UI
- Local: [app_pro.py:269-285](../app_pro.py#L269-L285) — copia-cola de [main.run_pipeline](../main.py#L20-L52). Qualquer mudança na pipeline precisa ser feita em 2 lugares.

#### #7 — `clear_old_videos` definido mas nunca chamado
- Local: [storage.py:55](../storage.py#L55). DB cresce sem TTL aplicado — versão atual já tem 159 KB sem nenhuma limpeza.

#### #8 — `generate_global_insights` não preenche `janela`
- A UI lê `o['janela']` em [app_pro.py:131](../app_pro.py#L131) com `try/except` que sempre cai no fallback de 8/18/30 dias hardcoded. O motor global retorna só `pais`, `score`, `recomendacao`, `concorrencia` ([global_opportunity_engine.py:37-42](../global_opportunity_engine.py#L37-L42)) — nunca `janela` nem `CPM`. Logo, **as duas informações principais de "janela de oportunidade" são chumbadas**, não calculadas.

#### #9 — `requirements.txt` incompleto
- [requirements.txt](../requirements.txt) lista 5 deps. Faltam **streamlit, flask, flask-cors, python-dotenv** (e `google-api-python-client` se decidirem migrar do `requests` cru). Quem clonar o repo não consegue rodar a UI.

#### #10 — `.gitignore` tem `*.db` mas 3 .db estão versionados
- [.gitignore:4](../.gitignore#L4) tem `*.db`, mas [viral_replicator.db](../viral_replicator.db), [viral_replicator_v2.db](../viral_replicator_v2.db), [viral_replicator_v3.db](../viral_replicator_v3.db) estão no histórico (provavelmente commitados antes do gitignore). Podem conter dados pessoais/de teste do Philipe (canais, scores, decisões salvas).

### 3.6 Acoplamento entre módulos

**Acoplamento médio-alto, com pontos de atenção:**

```
main.run_pipeline ──┬─→ collector ──┐
                    ├─→ analyzer ───┤   (recebem/devolvem List[dict] mutável)
                    ├─→ filters ────┤
                    ├─→ pattern_detector
                    ├─→ scoring
                    ├─→ global_opportunity_engine
                    ├─→ idea_generator
                    ├─→ copy_engine
                    ├─→ storage     ──→ sqlite v3
                    └─→ alerts

app_pro ──┬─→ storage (lê v3 direto via sqlite3, sem passar por storage.py)
          ├─→ todos os módulos da pipeline (duplica run_pipeline no botão)
          └─→ saved_channels.json (lê/escreve direto, sem abstração)
```

- **Acoplamento estrutural baixo:** módulos são funções puras que recebem/devolvem `dict` ou `list[dict]`. Não há classes, não há herança. Isso é bom — qualquer módulo pode ser substituído sem refactor cascata.
- **Acoplamento de dados alto:** todos os módulos compartilham o mesmo `dict` mutável de vídeo, com nomes de chave implícitos (`'rising_channel_score'`, `'pt_br_title'`, `'global_opportunities_json'`, etc). **Não há contrato/schema** — quebrar uma chave silenciosamente quebra a UI sem erro de runtime.
- **Acoplamento de UI alta:** [app_pro.py](../app_pro.py) lê o DB diretamente com SQL cru ([app_pro.py:45](../app_pro.py#L45)) — bypassa a camada `storage.py`. Migrar schema do DB exige editar UI também.
- **Pontos de duplicação:**
  - Filtro de gaming existe em [filters.py:12-30](../filters.py#L12-L30) **e** em [app_pro.py:36-41](../app_pro.py#L36-L41) (regex menor mas duplicada).
  - Pipeline existe em [main.py:20-52](../main.py#L20-L52) **e** em [app_pro.py:269-285](../app_pro.py#L269-L285).
  - Cálculo de score consolidado existe em [app_pro.py:183](../app_pro.py#L183) **e** em [app_pro.py:362](../app_pro.py#L362) (mesmo código copiado).

---

## 4. Top 10 — Dívida Técnica (impacto × esforço)

Ordenados por **impacto/esforço** (alto valor por baixo custo no topo).

| # | Item | Impacto | Esforço | Onde |
|---|------|--------|--------|------|
| 1 | **API key vazada no repo público** | 🔴 Crítico (segurança + custo) | Baixo (15 min: revogar, regenerar, `.env`) | [config.py:4](../config.py#L4) |
| 2 | ~~**Bug do filtro `c_date < '2026-01-01'`** descartando canais legítimos~~ ✅ RESOLVIDO em `4fe1a306` (Fase 0.5) | — | — | [filters.py](../filters.py) |
| 3 | **Pipeline duplicada** entre `main.py` e `app_pro.py` | 🟠 Alto (todo refactor precisa ser feito 2× e divergência já existe) | Baixo (extrair `pipeline.py`) | [app_pro.py:269-285](../app_pro.py#L269-L285) |
| 4 | **Janela de oportunidade chumbada na UI** (8/18/30) — feature principal do produto não é calculada | 🟠 Alto (é o "Pro" do Pro) | Médio (precisa modelo de saturação por nicho/país) | [global_opportunity_engine.py](../global_opportunity_engine.py) ↔ [app_pro.py:124-147](../app_pro.py#L124-L147) |
| 5 | **OpenAI desligada por código comentado** | 🟠 Médio (idéias são genéricas) | Baixo (descomentar + ajustar SDK 1.x) | [idea_generator.py:35-39](../idea_generator.py#L35-L39) |
| 6 | **`requirements.txt` incompleto** — repo não roda em clone novo | 🟠 Médio (DX) | Baixo (`pip freeze` filtrado) | [requirements.txt](../requirements.txt) |
| 7 | **`app.py` Flask órfão + CSS/template legados** | 🟡 Médio (confusão de entrada) | Baixo (remover `app.py`, `templates/`, `static/`) | [app.py](../app.py) |
| 8 | **3 .db versionados + `.gitignore` ignorado** | 🟡 Médio (segurança + repo size) | Baixo (`git rm --cached *.db` + history rewrite) | repo todo |
| 9 | **0% de testes + zero CI** — toda mudança é roleta russa | 🟠 Alto (a longo prazo) | Alto (montar do zero) | — |
| 10 | **`print()` em todo lado + `try/except` engolindo erros** | 🟡 Médio (impossível debugar produção) | Médio (logger + sentry/loguru + tipar exceções) | sistema todo |

> **Dívidas correlatas que merecem nota mas saem do top 10:** clusters K-Means com nomes hardcoded ([pattern_detector.py:55](../pattern_detector.py#L55)); `playbook` 100% estático ([copy_engine.py](../copy_engine.py)); 10 países hardcoded em código em vez de data file; ausência de retry/backoff na API do YouTube; magic number `+15` em [app_pro.py:60](../app_pro.py#L60); `clear_old_videos` definido e nunca chamado.

---

## 5. Oportunidades de evolução

### 5.1 Pipeline NotebookLM (roteiro PT-BR pronto pra produção)

**Objetivo:** transformar um vídeo viral selecionado em roteiro PT-BR + gancho + thumbnail prompt prontos pra produzir.

**Onde plugar:**
- Criar módulo novo: `script_pipeline.py` (ou pasta `scripts/`).
- Plugar **depois** de `apply_idea_generation` e **antes** de `generate_playbook` em [main.py:46-47](../main.py#L46-L47), recebendo o vídeo já com `generated_ideas` e produzindo um campo `notebooklm_script`.
- Acionar **on-demand** no botão "Habilitar Extração IA" do dialog ([app_pro.py:122](../app_pro.py#L122)) — hoje é só placeholder. Roteiro completo é caro, faz sentido só pros canais que o usuário decidiu atacar.

**Código a tocar:**
- [main.py](../main.py) — adicionar 1 etapa (`scripted = [generate_script(v) for v in with_ideas]`).
- [storage.py](../storage.py) — nova coluna `notebooklm_script TEXT` + migração via `ALTER TABLE` no padrão atual.
- [app_pro.py](../app_pro.py) — wire do botão "Extração IA" + nova seção no dialog Playbook.
- [config.py](../config.py) — `NOTEBOOKLM_API_KEY` ou similar; ou roteamento via OpenAI/Anthropic SDK.

**Código a NÃO tocar:**
- [collector.py](../collector.py), [analyzer.py](../analyzer.py), [scoring.py](../scoring.py), [filters.py](../filters.py), [pattern_detector.py](../pattern_detector.py), [global_opportunity_engine.py](../global_opportunity_engine.py) — coleta+análise são totalmente upstream e não dependem de roteiro.
- [copy_engine.py](../copy_engine.py) — playbook é separado de roteiro.

**Risco: BAIXO.**
- Módulo novo, isolado, gatilho on-demand.
- Único ponto de schema-change é storage; segue o padrão de migração já existente.
- Custo de LLM controlado por ser on-demand.

---

### 5.2 Coletores novos (comments mining, trending multi-país, phantom channels)

**Objetivo:** ampliar a descoberta. Hoje é **1 coletor** baseado em search EN-only.

**Onde plugar:**
- Promover `collector.py` pra package `collectors/`:
  ```
  collectors/
  ├── __init__.py             # export get_all() que orquestra os ativos
  ├── youtube_search.py       # = collector.py atual (renomeado)
  ├── youtube_trending.py     # /videos?chart=mostPopular&regionCode=XX
  ├── youtube_comments.py     # /commentThreads pra extrair tópicos
  ├── phantom_channels.py     # search por canais novos sem vídeos populares
  └── optional/
      ├── reddit.py           # módulo opcional, importado dinamicamente
      └── tiktok.py           # idem
  ```
- Em [main.py:24](../main.py#L24): `raw_videos = get_all()` em vez de `get_recent_videos()`. Cada coletor produz a mesma estrutura `dict` que o pipeline já consome (deduplicado por `id`).
- Em [config.py](../config.py): segmentar queries por idioma/região (`SEARCH_QUERIES_EN`, `SEARCH_QUERIES_ES`, `SEARCH_QUERIES_DE`); flags `ENABLE_TRENDING`, `ENABLE_COMMENTS`, `ENABLE_REDDIT`.

**Código a tocar:**
- [collector.py](../collector.py) → renomear/mover.
- [main.py:24](../main.py#L24) → trocar import e chamada.
- [app_pro.py:271](../app_pro.py#L271) → idem (botão "Varredura Agora" — daí a importância de extrair `pipeline.py` antes — ver dívida #3).
- [config.py](../config.py) → adicionar listas multi-idioma + feature flags.
- [storage.py](../storage.py) → coluna nova `source` (qual coletor produziu) — facilita debug e ablation.

**Código a NÃO tocar:**
- [analyzer.py](../analyzer.py), [scoring.py](../scoring.py), [filters.py](../filters.py), [pattern_detector.py](../pattern_detector.py), [global_opportunity_engine.py](../global_opportunity_engine.py), [idea_generator.py](../idea_generator.py), [copy_engine.py](../copy_engine.py) — todos consomem `dict`s; são source-agnósticos.
- UI — só ganha mais cards.

**Risco: MÉDIO.**
- **Cota da YouTube API explode rápido** com comments mining (`commentThreads` custa mais quotas; um vídeo viral pode ter 10k comentários → várias páginas).
- **Dedup é necessário** entre os coletores (mesmo vídeo pode aparecer em search + trending) — ainda mais quando entra Reddit/TikTok que não têm o mesmo `id`.
- **Risco de quebrar a normalização do dict de vídeo:** se trending retornar campos faltando, scoring engasga (sem schema enforced). Recomenda-se adotar `dataclass` ou `TypedDict` antes de escalar.
- **Reddit/TikTok não têm `subscribers` nem `views_per_hour`** no mesmo sentido — vão precisar de adaptadores de score, ou flag `external_source: True` que muda fórmula.

---

### 5.3 Refactor de UI com `ui-ux-pro-max`

**Objetivo:** tirar a UI atual do estado "HTML em string Python + CSS de 12KB num arquivo" e construir um design system real.

**Onde plugar:**
- [app_pro.py](../app_pro.py) — único arquivo de UI viva (488 linhas).
- [style.css](../style.css) (12 KB) — substituir.
- **Considerar quebrar em multi-page Streamlit:** criar `pages/01_Radar.py`, `pages/02_Oportunidades.py`, etc — hoje as 7 abas são ramos `if/elif` num único script de 200+ linhas de render.

**Código a tocar:**
- [app_pro.py](../app_pro.py) — divisão em componentes (`components/card.py`, `components/topbar.py`, `components/featured.py`).
- [style.css](../style.css) — substituir por design system tokenizado (cores, espaçamento, tipografia, badges, shadows como variáveis CSS).
- [.streamlit/config.toml](../.streamlit/config.toml) — atualizar tema base pra ficar consistente com o design system.
- **Remover** [app.py](../app.py), [templates/](../templates/), [static/](../static/) — Flask órfão, já morto (dívida #7).

**Código a NÃO tocar:**
- **Toda a pipeline** — [collector.py](../collector.py), [analyzer.py](../analyzer.py), [filters.py](../filters.py), [pattern_detector.py](../pattern_detector.py), [scoring.py](../scoring.py), [global_opportunity_engine.py](../global_opportunity_engine.py), [idea_generator.py](../idea_generator.py), [copy_engine.py](../copy_engine.py).
- [storage.py](../storage.py) — UI lê o DB; refactor de UI não exige nem mexe em schema.
- [main.py](../main.py) — orquestrador segue rodando paralelo.

**Risco: BAIXO no back-end. MÉDIO na UI.**
- Pipeline e storage não são afetados (zero risco de quebrar coleta/scoring).
- Risco médio na UI por ser **um monolito de 488 linhas com HTML inline e 7 abas** — refactor extenso, fácil de quebrar paridade visual no caminho.
- **Pré-requisito recomendado** antes do refactor de UI: extrair `pipeline.py` (dívida #3) — senão a UI vai continuar duplicando código de back-end.

---

## 6. Resumo executivo

**Estado atual:**
- Pipeline funcional 4-camadas + UI Streamlit decente em produção.
- ~2k linhas de Python espalhadas em arquivos planos, sem testes, sem CI.
- **1 bug crítico de segurança** (API key exposta) e **1 bug funcional grave** (filtro de data invertido cortando descobertas).
- Recursos "premium" do produto (janela de oportunidade, ideias com IA, playbook adaptativo) são parcialmente chumbados/desligados — o produto entrega menos do que a UI promete.

**Pré-requisitos antes de qualquer evolução planejada:**
1. **P0 — fora do escopo desta sessão:** revogar API key vazada e fazer history rewrite.
2. Ideal antes de evolução §5.1 e §5.2: extrair `pipeline.py` (dívida #3) e completar `requirements.txt` (#6).
3. Ideal antes de §5.3: remover `app.py`/Flask (#7) — sumir com a UI morta antes de refatorar a viva.

**Prontas pra avançar com baixo risco:**
- §5.1 (NotebookLM) — módulo novo isolado, gatilho on-demand.
- §5.3 (refactor UI) — back-end intocado.

**Risco médio, requer planejamento:**
- §5.2 (coletores novos) — cota da API, dedup, normalização de schema.

---

## 🔬 Calibrações pendentes

> Constantes que foram introduzidas com valores iniciais e precisam ser revisitadas com dados reais. Esta seção é viva — acumular novas calibrações aqui conforme forem aparecendo.

| Constante | Valor inicial | Quando revisitar | Como ajustar |
|---|---|---|---|
| [`EMBRYONIC_BOOST`](../scoring.py) | `15` | 2 semanas após `4fe1a306` em produção | Se canais embrionários estão ranqueando baixo demais → subir pra `20`. Se começaram a inflar resultados sem explosão real → baixar pra `10`. |
| [`EMBRYONIC_AGE_DAYS`](../scoring.py) | `90` | 2 semanas após `4fe1a306` em produção | Se ruído alto entre 60-90 dias (canais que ganharam boost mas eram só "estabelecidos sem tração") → apertar pra `60`. Se canais legítimos de 12-16 semanas estão sem boost e bombando → afrouxar pra `120`. |

**Sinais a observar (sem instrumentação ainda — análise visual da UI):**
- % de cards com badge de "INÍCIO" que vêm de canais com <90 dias.
- Taxa de canais embrionários no topo do "Radar" — se for 100% deles, boost está dominando demais.
- Aparição de "phantom channels" (canais antigos com tração) no Radar — se aparecer zero, ajuste do scoring pode estar enviesando.

---

*Aguardando seus comentários antes de avançar pra fase seguinte.*
