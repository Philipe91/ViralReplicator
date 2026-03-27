# 🚀 Global Viral Replicator

Sistema focado na identificação de vídeos virais recentes no YouTube (canais dark e explication) e geração de insights estratégicos para replicação em outros mercados (ex: Brasil).

## 🎯 Como Funciona e Por Que Importa
Ele coleta da API do YouTube centenas de vídeos focados nas principais tendências "Gringas". Analisa cada um deles extraindo views por hora, taxa de engajamento, inscritos, etc.
Ele cria um "Viral Score". Toda vez que um canal pequeno acerta em cheio e viraliza nas primeiras 48h, o sistema o detecta. 
Ele detecta o padrão do título e usa scikit-learn para agrupar as temáticas em clusters inteligentes (Ex: Mistério, Documentários).
Em cima disso, há um gerador de ideias focado no Copyswriting que imediatamente sugere versões nativas ao invés de pífias traduções, acelerando a fase 3 (sua primeira réplica).

## 📦 Instalação e Execução

Abra seu terminal na pasta do projeto e:

```bash
# 1. Crie o ambiente virtual (Recomendado)
python -m venv venv
.\venv\Scripts\activate   # No Windows

# 2. Instale as dependências
pip install -r requirements.txt
```

### Chaves de API
Abra o arquivo `config.py` e insira sua `YOUTUBE_API_KEY`. Se desejar ativar a tradução real via Inteligência Artificial, insira uma `OPENAI_API_KEY`.

```bash
# 3. Rode o Bot Orquestrador Principal
python main.py
```

## 🧠 Módulos do Sistema

*   **`main.py`**: Ponto de entrada e automação com `schedule` rodando a cada 30 min.
*   **`collector.py`**: Interage de maneira otimizada com a API v3 para baixar dados brutos e massivos da timeline das palavras-chave gringas (A API Key é obrigatória e pode ser pega gratuitamente no Google Cloud Plataform habilitando a API do Youtube Data V3).
*   **`analyzer.py`**: Motor matemático contendo os cálculos que evidenciam se a resposta do View/Hora é assustadoramente alta para canais minúsculos.
*   **`filters.py`**: Corta todo lixo mantendo as "Agulhas no Palheiro".
*   **`pattern_detector.py`**: Machine Learning embarcado (Clusterização via K-Means e NLP via Regex de Padrões) formatado de forma simples, direta e cruamente eficaz.
*   **`idea_generator.py`**: Fabrica roteiros em potenciais. No momento roda com Regras para prototipagem mas está totalmente preparado para puxar a OpenAI e deixar automatizada a criação inteira de pautas, copy e até prompts Midjourney das Thumbs.
*   **`storage.py`**: Consolida diariamente as centenas de detecção em formato tabelado puro e cru. 
*   **`alerts.py`**: A vigia na Torre. Assim que o bot detecta um viral novo num ciclo e bate os scores... ele avisa você!

---
⚠️ **ALERTA (JOGO REAL):**
Se você só copiar: não escala, pode cair e fica genérico.
Se fizer com este bot: adapta, melhora e acelera — VIRA UMA MÁQUINA!
