---
name: publicar
description: Publica no YouTube um vídeo já finalizado pela produção do canal alemão "Dein Körper Erklärt". Use quando o usuário disser /publicar, "publica o vídeo", "sobe o vídeo X", "o vídeo está pronto", ou quando um arquivo PRONTO.json aparecer em output/producao/. Lê o roteiro e o PRONTO.json, escreve título/descrição/tags em alemão e faz o upload pelo navegador.
---

# Publicar vídeo — canal Dein Körper Erklärt

## Antes de qualquer coisa

Leia `docs/03-protocolo-publicacao.md`. Ele é o contrato e pode ter mudado desde a última publicação.

## Canal

| | |
|---|---|
| Handle | `@dein.koerper.erklaert` |
| Channel ID | `UCCGUCSdk1p6v7E3UiZ6SbpA` |
| Studio | `https://studio.youtube.com/channel/UCCGUCSdk1p6v7E3UiZ6SbpA` |

## Passo a passo

### 1. Descobrir o que publicar

Se o usuário passou um id (`/publicar de_01_arterien`), use-o. Senão, procure pastas com sinal pendente:

```
output/producao/*/PRONTO.json   →  sem PUBLICADO.json ao lado = pendente
```

Se houver mais de um pendente, publique o de menor número e avise que os outros estão na fila.
Se não houver nenhum, diga isso e pare — não invente conteúdo nem publique rascunho.

### 2. Ler as duas fontes

- `output/producao/<id>/PRONTO.json` → caminhos, fontes, capítulos, agendamento
- `scripts/<id>.json` → `titulo`, `titulo_variacoes`, `cenas[].narracao`, `nota_metodo`

### 3. Validar antes de subir

Pare e pergunte ao usuário se qualquer uma falhar:

- MP4 e thumbnail existem no caminho indicado?
- `fontes` tem pelo menos um link? (a descrição promete fontes — sem elas a promessa é falsa)
- Primeiro capítulo é `00:00`? (senão o YouTube ignora todos)
- Thumbnail < 2MB?

### 4. Escrever os metadados — em alemão

**Título:** use `titulo` do roteiro, salvo se `titulo_escolhido` estiver preenchido. Guarde `titulo_variacoes` para teste A/B depois.

**Descrição**, nesta ordem:

```
[2-3 linhas de gancho, escritas a partir da narração real das primeiras cenas]

⏱️ Kapitel:
00:00 ...

📚 Quellen und Studien:
[um link por linha]

Wichtiger Hinweis: Die Inhalte dieses Videos dienen ausschließlich der
allgemeinen Information und Bildung. Sie ersetzen keine ärztliche Diagnose,
Beratung oder Behandlung und stellen keine Heilaussage dar. Bei
gesundheitlichen Beschwerden wende dich bitte an eine Ärztin oder einen Arzt.

#Gesundheit #Biologie #[específicas do tema]
```

**Tags:** alemão, derivadas do tema + as palavras-chave do canal (`Intervallfasten`, `Stoffwechsel`, `Herzgesundheit`, etc.).

### 5. Regras de conteúdo — não negociáveis

- Sem promessa de cura. `Was passiert, wenn…` e nunca `So heilst du…`. A Alemanha tem HWG e a moderação alemã é mais dura.
- Hedge: `Studien deuten darauf hin`, nunca `Fakt ist`.
- **A descrição nunca afirma mais que o roteiro.** Cheque `nota_metodo` — se ele marcou algo como preliminar, a descrição não vende como resolvido.
- Nada de `Dr.`/credencial médica em primeira pessoa.

### 6. Upload pelo navegador

Ferramentas `mcp__claude-in-chrome__*`. Chame `list_connected_browsers` e **pergunte ao usuário qual navegador** (obrigatório) antes de agir.

No Studio → Criar → Enviar vídeos:
1. Anexe o MP4 via `file_upload` no file input (não clique no botão — abre diálogo nativo invisível)
2. Título e descrição
3. Thumbnail via `file_upload`
4. Playlist, se houver
5. **"Não, não é conteúdo para crianças"**
6. Mais opções → idioma **Alemão**, categoria **Educação**
7. Visibilidade conforme `visibilidade` / `publicar_em`

**Confirme com o usuário antes de clicar em Publicar.** Publicação é irreversível e pública — mostre título e descrição finais e espere o "ok".

### 7. Fechar o ciclo

Escreva `output/producao/<id>/PUBLICADO.json`:

```json
{
  "id": "...",
  "url": "https://youtu.be/...",
  "video_id": "...",
  "titulo_usado": "...",
  "descricao_usada": "...",
  "publicado_em": "...",
  "visibilidade": "public"
}
```

Atualize a tabela de estado na seção 8 de `docs/03-protocolo-publicacao.md`.

## Erros comuns já vistos neste projeto

- **Coordenadas de clique erram** quando a página rola. Prefira `find` + `ref`, e `form_input` em vez de digitar. Um `ctrl+a` fora do campo seleciona a página inteira.
- **Campos que parecem input podem ser `div` contenteditable** (a descrição do canal é). `form_input` falha neles — clique no ref, `ctrl+a`, `Delete`, depois digite.
- **Sempre revalide o que salvou.** O handle do canal falhou silenciosamente na primeira tentativa e só apareceu ao abrir a página pública.
- **Downloads do Chrome não caem em `~/Downloads`** nesta máquina. Se precisar de um arquivo do navegador, peça ao usuário para baixar.
- **`file_upload` só aceita caminhos que a sessão pode ler.** Copie para o scratchpad ou para dentro do projeto antes.
