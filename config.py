import os

# Configurações de API
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "AIzaSyA6OJDvvDaH-MbjkTBkJeUJWzLGQ4OAioA")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "SUA_CHAVE_OPENAI_AQUI")

# ────────────────────────────────────────────────
#  LAYER 1 — COLETA
#  Pool de palavras-chave estritamente dark / sem-rosto (Serão sorteadas aleatoriamente a cada busca)
# ────────────────────────────────────────────────
SEARCH_QUERIES = [
    # True Crime / Cold Case
    "cold case unsolved", "true crime documentary", "unsolved murder mystery", 
    "missing person story", "cold case solved", "fbi interrogation breakdown",
    "serial killer documentary", "detective bodycam footage", "crime scene investigation",
    
    # Dark curiosidades / mistério
    "dark history explained", "dark secrets revealed", "scary story narrated",
    "mysterious disappearance", "reddit dark stories", "creepy historical facts",
    "disturbing truths", "unexplained phenomena", "bizarre historical events",
    
    # Documentário IA / Ciência / Psicologia
    "ai documentary explained", "dark psychology explained", "conspiracy revealed",
    "financial crimes explained", "matrix simulation theory", "cult manipulation",
    "internet rabbit hole", "deep web mystery", "scam breakdown",
    
    # Histórias contadas por IA (Dark / Fantasia / Mistério)
    "ai generated scary story", "ai visual story midjourney", "ai history told",
    "creepy pasta ai generated", "ai narrator story", "forgotten legend ai",
    "ai animated dark story", "urban legend ai"
]

#  Parâmetros de Coleta
MAX_RESULTS_PER_QUERY = 25     # Reduzido → mais qualidade por cota da API
MAX_HOURS_OLD         = 168    # Aumentado para 1 semana para não bloquear o tempo real
MIN_VIEWS             = 1000   # Ignorar lixo — queremos Pelo menos 1k views
MAX_SUBSCRIBERS       = 100000 # Canal pequeno (< 100k subs)

#  Threshold de Viral Score
VIRAL_SCORE_THRESHOLD = 5.0

#  Saída legado
OUTPUT_FILE = "virais_detectados.csv"
