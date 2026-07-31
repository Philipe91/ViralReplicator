# 03 — Protocolo de Publicação (handoff Produção → Postagem)

**Este documento é o contrato entre duas sessões do Claude que não se comunicam diretamente.**

- **Claude PRODUÇÃO** (outro chat): pesquisa, roteiro, narração, imagens, edição, thumbnail.
- **Claude POSTAGEM** (esta sessão): lê o que a produção entregou, redige os metadados em alemão e publica no YouTube via navegador.

Não existe canal direto entre sessões do Claude. **O disco é o canal.** Tudo que a produção precisa me dizer, diz por arquivo. Tudo que eu preciso responder, respondo por arquivo.

---

## 1. Canal de destino

| | |
|---|---|
| Nome | **Dein Körper Erklärt** |
| Handle | `@dein.koerper.erklaert` |
| Channel ID | `UCCGUCSdk1p6v7E3UiZ6SbpA` |
| Idioma do vídeo | Alemão (genérico — cobre DE/AT/CH) |
| Categoria padrão | Educação |
| Cadência alvo | 1 vídeo a cada 2 dias (`canais/de_thinkscience.json`) |

Nome, handle, avatar, banner, palavras-chave, idiomas e template de descrição **já estão configurados**. Ver `BRIEFING-CANAL-DE.md` seção 7.

---

## 2. O sinal: `PRONTO.json`

Quando um vídeo estiver **finalizado e renderizado**, a produção cria **um único arquivo**:

```
output/producao/<id>/PRONTO.json
```

A existência desse arquivo é o gatilho. Enquanto ele não existir, eu não toco no vídeo. Assim que ele aparecer, eu acordo e publico.

> ⚠️ Só crie o `PRONTO.json` quando o MP4 final e a thumbnail estiverem gravados no disco. Ele significa "pode publicar", não "estou quase lá".

---

## 3. Schema do `PRONTO.json`

```jsonc
{
  "id": "de_01_arterien",              // igual ao nome da pasta e do scripts/<id>.json
  "video": "final.mp4",                // caminho relativo à pasta do vídeo, ou absoluto
  "thumbnail": "thumb.png",            // idem. 1280x720, <2MB
  "duracao_seg": 512,

  // Capítulos. Deixe [] se não quiser capítulos.
  // O primeiro DEVE ser 00:00 ou o YouTube ignora todos.
  "capitulos": [
    { "t": "00:00", "titulo": "Warum 'Arterien reinigen' nicht existiert" },
    { "t": "01:30", "titulo": "Was das Endothel wirklich macht" }
  ],

  // OBRIGATÓRIO. O disclaimer da descrição promete fontes — sem elas a promessa é falsa.
  // Links reais e verificáveis (PubMed, NIH, Cochrane, Charité, DGE).
  "fontes": [
    "https://pubmed.ncbi.nlm.nih.gov/XXXXXXX/",
    "https://www.ncbi.nlm.nih.gov/pmc/articles/PMCXXXXXXX/"
  ],

  // Opcional — se vazio eu escolho a partir de scripts/<id>.json
  "titulo_escolhido": "",

  // Opcional. Se preenchido eu uso como base; se vazio eu escrevo do zero em alemão.
  "resumo_para_descricao": "",

  // Opcional
  "playlist": "",                      // ex.: "Herz & Kreislauf"
  "publicar_em": "",                   // "" = imediato. Ou "2026-08-02T18:00:00+02:00"
  "visibilidade": "public",            // "public" | "unlisted" | "private"
  "notas_para_postagem": ""            // qualquer coisa que eu deva saber
}
```

### Campos mínimos para eu conseguir publicar
`id`, `video`, `thumbnail`, `fontes`. O resto tem padrão sensato.

---

## 4. O que eu leio sozinho (não repita no PRONTO.json)

De `scripts/<id>.json`, que a produção já gera:

| Campo | Uso |
|---|---|
| `titulo` | título principal |
| `titulo_variacoes` | pool de variações para teste A/B de título |
| `cenas[].narracao` | escrevo a descrição a partir do conteúdo real, não de um resumo genérico |
| `nota_metodo` | me diz o que foi ajustado por evidência — evita eu prometer na descrição algo que o roteiro deliberadamente não afirma |
| `idioma`, `voz` | conferência |

**Por isso não preciso que a produção escreva a descrição.** Eu leio o roteiro e escrevo.

---

## 5. O que eu faço quando o sinal chega

1. Leio `PRONTO.json` + `scripts/<id>.json`
2. Confiro que o MP4 e a thumb existem e batem com o schema
3. Escolho o título (o principal, salvo instrução em contrário) e guardo as variações para teste A/B
4. **Escrevo a descrição em alemão**, com esta estrutura:
   - 2–3 linhas de gancho, derivadas da narração real
   - Capítulos com timestamps
   - `📚 Quellen und Studien:` com os links de `fontes`
   - Disclaimer HWG/YMYL fixo (já está no template de upload do canal)
   - Hashtags
5. Escrevo as tags (alemão, derivadas do assunto + palavras-chave do canal)
6. Faço upload pelo YouTube Studio no navegador: vídeo, título, descrição, thumbnail, capítulos, playlist, `Não, não é conteúdo para crianças`, idioma alemão, categoria Educação
7. Publico (ou agendo, se `publicar_em` estiver preenchido)
8. **Escrevo `PUBLICADO.json`** na mesma pasta, com URL, video ID, título usado, descrição usada e horário — para a produção saber que fechou e para termos histórico

---

## 6. Regras de conteúdo que eu aplico na descrição

Herdadas de `canais/de_thinkscience.json` → `riscos.regulatorio` e do `BRIEFING-CANAL-DE.md` seção 9:

- **Sem promessa de cura.** `"Was mit deinen Arterien passiert, wenn…"` e nunca `"So heilst du deine Arterien"`. O HWG alemão é rígido e a moderação alemã do YouTube é mais dura que a americana.
- **Linguagem com hedge:** `Studien deuten darauf hin`, `Hinweise sprechen dafür` — nunca `Fakt ist`.
- **A descrição nunca afirma mais que o roteiro.** Se `nota_metodo` diz que K2 é preliminar, a descrição não vende K2 como resolvido.
- **Sem `Dr.`/`Arzt`** em primeira pessoa. O canal não tem credencial médica.
- **Impressum:** ainda pendente (falta endereço). Quando existir, entra no fim da descrição do canal.

---

## 7. Atalhos de ativação

| Como | O quê |
|---|---|
| **Automático** | Monitor observando `output/producao/*/PRONTO.json`. Quando um aparece, eu sou notificado e começo a publicação. |
| **Manual** | O dono digita `/publicar` (ou `/publicar de_01_arterien`) nesta sessão. |
| **Se a sessão caiu** | Basta dizer "publica o vídeo X" — eu releio este protocolo e a pasta. O estado está todo no disco, nada depende da minha memória. |

---

## 8. Estado atual

| Vídeo | Pasta | Roteiro | Áudio | PRONTO.json | Publicado |
|---|---|---|---|---|---|
| 01 — Arterien | `output/producao/de_01_arterien/` | ✅ `scripts/de_01_arterien.json` | ✅ 14 cenas | ⬜ | ⬜ |
| 02 — Augenfarbe | — | ✅ `scripts/de_01_augenfarbe.json` | ⬜ | ⬜ | ⬜ |

---

## 9. Recado direto para o Claude da produção

Seu trabalho está limpo e o `scripts/<id>.json` já cobre quase tudo que preciso — título, variações e a narração completa. **Não escreva descrição nem tags; isso é meu.** Só me faltam quatro coisas que você tem e eu não:

1. onde está o **MP4 final**
2. onde está a **thumbnail**
3. os **links das fontes** que embasaram o roteiro
4. os **capítulos** com timestamps reais do corte final

Coloque isso no `PRONTO.json` e eu assumo daí. Se mudar a convenção de pastas ou o schema do roteiro, edite este arquivo — eu leio ele antes de cada publicação.
