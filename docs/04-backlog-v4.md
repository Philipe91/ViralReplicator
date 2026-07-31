# Backlog V4 — ideias que NÃO entram agora

A arquitetura V3 está **congelada** (aprovada em 31/07/2026). Toda melhoria de
estrutura que aparecer durante a implementação da V3 é anotada aqui e não
interrompe o desenvolvimento.

Regra: este arquivo recebe **ideia com justificativa**, não tarefa. Se o item já
tem execução decidida e cabe na V3, ele vai para o plano da V3, não para cá.

---

## Adiado de propósito na V3

### Semantic Analyzer como módulo próprio
Reservado no schema, não construído. Hoje teria um único consumidor (o
VisualBrain), e camada com um consumidor só é a primeira metade do consumidor.
Passa a se pagar quando o segundo chegar — e ele está mapeado: o `/publicar`
precisa de descrição, capítulos e tags, que saem bem de semântica estruturada.

**Régua para quando for construído — o teste do podcast:** um campo pertence à
semântica se seria escrito igual caso a saída fosse um podcast, sem vídeo.
`ano: 1945` passa. `necessita_cronologia` reprova — isso é VisualBrain.

### Grafo de dependências de verdade
A V3 usa `camadas[]` ordenadas + `deriva_de`, porque as dependências reais têm
profundidade máxima 2. Se um dia surgir dependência que a lista não expresse,
uma lista é um DAG degenerado válido — cresce sem reescrita.

### Rosto consistente com IP-Adapter ou LoRA
Hoje a coerência de elenco depende de `expandir_elenco()` repetir a mesma
descrição. Funciona melhor que o esperado, mas não garante o mesmo rosto.
Custo: modelo novo + VRAM concorrendo com o SDXL na 3060.

---

## Surgido durante a implementação da V3

### Timeline com revelação progressiva
A timeline é estática: os marcos aparecem todos de uma vez e o movimento vem da
câmera. Revelar marco a marco, acompanhando a narração que os cita, é
visivelmente melhor — e é motion graphics, que é a etapa 7. Par natural quando
ela chegar. O mesmo vale para gráfico (barra que cresce) e para o diagrama
(rótulo que entra quando a fala o nomeia).

### Direção precisa consultar a capacidade do executor
`composicao.Executor` já declara `aceita_camera`, e nada lê esse campo ainda.
`direcao.py` escolhe a câmera sem saber a fonte do plano — então um `handheld`
pode cair num diagrama vetorial, onde tremor lê como defeito de render e não
como câmera. Também é o `push_in` forte que empurra o texto do diagrama para
perto da legenda (mitigado por margem no desenho, não resolvido na origem).

Encaixe natural: `direcao.dirigir()` recebe a composição já adaptada e filtra o
vocabulário por `aceita_camera` / `fonte`. É acoplamento legítimo e previsto na
revisão de arquitetura — só não cabia na etapa 3, que era "somente o executor
de diagrama".

### Piso de grave 5,5 dB acima da referência
Medido em 31/07, janelas de 1s abaixo de 70Hz:

| | mediana | máximo | excursão |
|---|---|---|---|
| canal de referência | −27,6 dBFS | −16,2 | **11,4 dB** |
| nosso | −22,1 dBFS | −17,4 | **4,7 dB** |

O **pico** do nosso impacto está certo (1,2 dB da referência). O que difere é o
PISO: o sub deles é mais limpo, então o impacto salta 11 dB e o nosso salta 5.

Investigado e **descartado**: não é a música. Testar `highpass=f=90` na trilha
não mudou a mediana em nada (−22,1 com e sem). A fonte é a VOZ vazando pelo
highpass de 85Hz, que sendo de 2ª ordem atenua pouco a 70Hz. Resolver exigiria
mexer no processamento da narração — fora do escopo do sound design e com risco
de afetar a inteligibilidade, que é o ativo mais importante do canal.

## Dívida técnica conhecida

### Cadeia de encodes (2 a 3 passes)
Medido em 31/07: `ken_burns` crf 18 → concat (cópia) → xfade entre atos crf 19 →
acabamento crf 19. **Deve ser resolvido dentro da V3**, pelo compositor com
intermediários sem perda. Fica registrado aqui caso não seja.

### Duas gerações de schema de roteiro
53 planos usam `planos[]`, 18 usam `imagem` no nível da cena. Ambos suportados
pelo adaptador. Não há urgência em migrar; há urgência em nunca quebrar os dois.

### `montagem_legada.py` congelado
Preservado por compatibilidade (`--montagem simples`). Se um dia ninguém usar
por meses, é candidato a remoção — decisão do dono, não minha.

---

## Escopo que se revelou maior do que parece

### Executor de mapa
Mapa de verdade é **dado geográfico**, não desenho: pede GeoJSON, projeção e
simplificação de fronteira. Não é "mais um executor vetorial". Provavelmente
merece ser o último da fila, ou usar imagem estática pré-renderizada por região.

### Teto de novidade visual
Nenhuma câmera conserta um plano de 8,7s que mostra a mesma imagem recortada
duas vezes. O teto da direção é o **número de imagens por minuto**, e isso é
GPU. Parallax alivia (faz o recorte parecer outro ângulo) mas não elimina.

### Parallax: oclusão não é preenchida
`parallax.py` usa mapeamento INVERSO, que não deixa buraco mas estica os pixels
nas bordas de profundidade. A amplitude foi limitada a 2,2% da largura para o
estiramento ficar abaixo do limiar de percepção. Amplitude maior exigiria
inpaint das áreas reveladas — trocaria "câmera de verdade" por "borracha
derretendo" sem isso.

### Custo do parallax: ~11s por plano
Medido: ~3,8s de profundidade (uma vez, cacheada ao lado da imagem) + ~7s de
render por plano de 5s a 1080p. Num vídeo de 8 min com 83 planos, aplicar em
todos custaria ~15 min. É caro o bastante para ser decisão do diretor por plano,
e não padrão — está desligado por omissão.
