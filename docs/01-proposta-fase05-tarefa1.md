# Proposta — Fase 0.5 / Tarefa 1
## Correção do filtro de data do canal (Opção B)

**Branch:** `fix/saneamento-minimo`
**Status:** aguardando decisão em 3 pontos antes da aplicação
**Decisão da abordagem:** ✅ Opção B (remover gate, usar idade como sinal contínuo no scoring)

---

## Confirmações de pré-aplicação

### ✅ 1. `MAX_SUBSCRIBERS = 100000`

[config.py:37](../config.py#L37) — confirmado em `100000`. Esse continua sendo o gate efetivo de "canal pequeno", como o spec descreve. Idade não vai mais cortar — só dar boost a quem é embrionário.

### ✅ 3. Edge case do phantom channel — sem penalidade

Estrutura final do código que será aplicado em [scoring.py](../scoring.py):

```python
# depois de calcular rising_score base
age = video.get('channel_age_days')
if age is not None and age < EMBRYONIC_AGE_DAYS:
    rising_score = min(rising_score + EMBRYONIC_BOOST, 100)
```

Comportamento por cenário:

| Cenário | `channel_age_days` | Caminho | Resultado |
|---|---|---|---|
| Embrionário (30 dias) | `30` | `30 < threshold` → entra | **+boost** |
| Phantom channel (canal de 5 anos voltando) | `1825` | `1825 < threshold` → **FALSE**, pula | **neutro (0)** |
| Data malformada / ausente | `None` | `is not None` → **FALSE**, pula | **neutro (0)** |

Sem `else`, sem `elif`, sem penalidade. ✅

---

## ⚠️ Decisão #2 — calibração das constantes

### Inventário das constantes mágicas existentes em `scoring.py`

Pra fundamentar a calibração, mapeamento completo do que já existe:

#### `rising_channel_score` ([scoring.py:11-16](../scoring.py#L11-L16))
| Constante | Função |
|---|---|
| `* 1000` | Normalização base de `views/h ÷ subs` |
| `* 50` | Multiplicador de magnitude |
| `min(..., 100)` | Cap em 100 |
| `subs > 50000 → * 0.1` | **Penalidade -90%** se canal já é grande |
| `padrao != 'Indefinido' → += 20` | **Boost +20** se título tem padrão reconhecido |

#### `retention_score` ([scoring.py:19-22](../scoring.py#L19-L22))
| Constante | Função |
|---|---|
| `like_ratio * 10` | Magnitude da heurística |
| `dur > 600 AND v_h > 100 → += 20` | **Boost +20** pra long-form com tração |

#### `trend_timing` ([scoring.py:25-31](../scoring.py#L25-L31))
| Threshold | Resultado |
|---|---|
| `hrs <= 24 AND v_h > 50` | INÍCIO |
| `hrs <= 48 AND v_h > 20` | CRESCENDO |
| resto | SATURADO |

#### `production_difficulty` ([scoring.py:34-40](../scoring.py#L34-L40))
| Threshold | Resultado |
|---|---|
| `'AI' in padrao OR dur < 60` | FÁCIL |
| `dur < 600` | MÉDIO |
| resto | DIFÍCIL |

#### `dark_score` ([scoring.py:43-49](../scoring.py#L43-L49))
| Constante | Função |
|---|---|
| Base `50` | Score neutro |
| `-40` | Penalidade keywords vlog/podcast |
| `+30` | Boost keywords dark/explained |
| `+20` | Boost se difficulty == FÁCIL |

#### `copy_score` ([scoring.py:52-66](../scoring.py#L52-L66))
| Constante | Função |
|---|---|
| FÁCIL → `+35` | Boost por difficulty fácil |
| MÉDIO → `+20` | Boost médio |
| `padrao != 'Indefinido' → +30` | Boost padrão de título |
| `retention_score / 100 * 20` | Contribuição capada em 20 |
| `rising_score / 100 * 15` | Contribuição capada em 15 |

**Faixa observada de boosts: +15 a +35. Penalidades chegam em -90% e -40.**

### Opções de boost

| Opção | Valor | Significado | Justificativa |
|---|---|---|---|
| Tímido | `+10` | "Sinal fraco, só desempata" | Abaixo de tudo que já existe — fica invisível em casos com outros boosts somando |
| **Padrão** | `+15` | "Sinal positivo padrão" | Igual ao cap da contribuição de `rising` em `copy_score` — proporcional sem dominar |
| Paridade | `+20` | "Igual a `padrao_de_titulo`" | Equipara idade nova ao reconhecimento de padrão de título — defensável: ambos são sinais estruturais |
| Forte | `+25 a +30` | "Sinal forte, próximo de dominar" | Começa a competir com a penalidade `× 0.1` de canal grande |

**Minha recomendação:** **`+15`**. É o chão da faixa existente e evita inflar artificialmente canais novos por idade só. Se mais tarde a calibração mostrar que canais embrionários estão ranqueando baixo demais, sobe pra `+20`.

### Opções de threshold

Você falou em "3-8 semanas de vida" no prompt da Tarefa 1. Isso é **21 a 56 dias**. Opções:

| Opção | Threshold | Significado | Justificativa |
|---|---|---|---|
| Apertado | `< 56 dias` (8 semanas) | Fiel à definição "3-8 semanas" | Pega exatamente a janela que você descreveu — mais sinal, menos ruído |
| **Médio** | `< 90 dias` (~3 meses) | "Embrionário inclui consolidação inicial" | Sweet spot — pega canais de 8-12 semanas que ainda não saíram do nascimento |
| Largo | `< 120 dias` (~4 meses) | Equivalente ao que o filtro hardcoded permitia em abril/26 | Espelha o status quo atual sem cliff |

**Minha recomendação:** **`< 90 dias`**. Captura sua faixa de 3-8 semanas integralmente (dá até margem de 4 semanas extras) e ainda mantém o conceito de "embrionário". `< 56` é mais estrito mas pode deixar canais legítimos com 9-12 semanas sem boost — esses ainda estão em fase pré-explosão.

---

## ⚠️ Decisão #3 — onde guardar as constantes

| Opção | Como fica | Prós | Contras |
|---|---|---|---|
| **A: Inline em `scoring.py`** | `EMBRYONIC_AGE_DAYS = 90` no topo do módulo, junto da função | Mínimo diff. Mantém consistência com o resto do `scoring.py` (que tem todas as constantes hardcoded inline) | Torna mais 2 constantes invisíveis ao operador. Mantém a dívida técnica de "constantes espalhadas" intacta |
| **B: Extrair pra `config.py`** | Novo bloco `# LAYER 4 — SCORING` em config.py com `EMBRYONIC_AGE_DAYS = 90`, `EMBRYONIC_BOOST = 15`. Importadas por scoring.py | Operador vê e calibra ao lado de `MAX_SUBSCRIBERS`, `MIN_VIEWS`, etc. Coerente com o que já está em config | Sai do escopo "Fase 0.5 = destravar" — começa a refatorar config (que tem outras constantes do scoring inline) |

**Minha recomendação:** **A (inline em `scoring.py`)** **para esta sessão**.

Razão: a Fase 0.5 é "saneamento mínimo, destravar". Extrair só essas 2 constantes pra config enquanto **todas as outras 30+ constantes do scoring continuam inline** cria inconsistência — fica óbvio que essas 2 foram movidas e o resto não. A migração faz mais sentido como **uma tarefa única na Fase 1** que move TODAS as constantes do `scoring.py` pra um bloco `# LAYER 4 — SCORING` em config.py de uma vez. Aí fica coerente.

Se discordar e quiser **B** já agora, sem problema — mas vou recomendar abrir uma issue/anotação pra fazer a migração completa do scoring depois.

---

## Resumo do diff final (caso aceite recomendações padrão)

Com `EMBRYONIC_AGE_DAYS=90`, `EMBRYONIC_BOOST=15`, **inline em scoring.py**:

### Commit 1 — `fix(filters): remove hardcoded date gate in filters.py:102-104`

[filters.py](../filters.py): remove linhas 98-104 (3 linhas de gate + comentário + dead code do `duration_seconds < 180` duplicado).

```diff
-        # Gate 1b: Elimina shorts (<3 min) E canais velhos (antes de 2026)
-        if v.get('duration_seconds', 0) < 180:
-            continue
-
-        c_date = v.get('channel_created_at', '')
-        if c_date and c_date < '2026-01-01':
-            continue
-
         # Gate 1: Excluir gaming / facecam
```

Aproveita pra eliminar o gate duplicado de duração (dívida #3 do diagnóstico, gratuita aqui).

### Commit 2 — `feat(analyzer): compute channel_age_days as continuous signal`

[analyzer.py](../analyzer.py): em `calculate_metrics`, adicionar:

```python
c_date = video.get('channel_created_at', '')
if c_date:
    try:
        created = datetime.strptime(c_date, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        video['channel_age_days'] = (now - created).days
    except ValueError:
        video['channel_age_days'] = None
else:
    video['channel_age_days'] = None
```

(`now` e `timezone` já existem no escopo da função, [analyzer.py:19](../analyzer.py#L19).)

### Commit 3 — `feat(scoring): apply embryonic channel boost in rising_score`

[scoring.py](../scoring.py): no topo do arquivo + dentro de `calculate_copy_score`:

```python
# topo do arquivo (após docstring, antes da função)
EMBRYONIC_AGE_DAYS = 90    # canal "embrionário": criado nos últimos N dias
EMBRYONIC_BOOST = 15        # boost adicionado ao rising_score se embrionário
```

```python
# dentro de calculate_copy_score, após a linha 16 (cap do rising_score):
age = video.get('channel_age_days')
if age is not None and age < EMBRYONIC_AGE_DAYS:
    video['rising_channel_score'] = round(
        min(video['rising_channel_score'] + EMBRYONIC_BOOST, 100), 2
    )
```

### Atualização — [docs/00-diagnostico.md](00-diagnostico.md)

- Marcar item **#2** do Top 10 (filtro de data) como ✅ resolvido
- Marcar bug **#2** da §3.5 como ✅ resolvido
- Marcar bug **#3** (gate duplicado) como ✅ resolvido (caiu junto)

---

## Decisões pendentes — me responde nesse formato

```
2. Boost: 15 / 20 / outro: ___
2. Threshold: 56 / 90 / 120 / outro: ___
3. Onde: A (inline) / B (config.py)
```

Defaults sugeridos: **boost 15, threshold 90, A (inline)**. Se mandar só "go com defaults", aplico exatamente isso.

Após sua resposta, faço os 3 commits, atualizo o diagnóstico, e te mostro o diff final completo **antes** de qualquer push.
