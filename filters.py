"""
LAYER 2 — FILTRO / CLASSIFICAÇÃO
Responsável por exclusão de conteúdo indesejado ANTES de qualquer scoring.
Regra absoluta: gaming OUT, podcast com rosto OUT, conteúdo dark IN.
"""
import re
from config import MIN_VIEWS, MAX_HOURS_OLD, MAX_SUBSCRIBERS

# ─────────────────────────────────────────────
#  BLOCO DE EXCLUSÃO TOTAL — GAMING & GAMEPLAY
# ─────────────────────────────────────────────
GAMING_KEYWORDS = {
    # Títulos de jogos
    "minecraft", "gta", "roblox", "fortnite", "fifa",
    "call of duty", "cod", "free fire", "pubg", "valorant",
    "league of legends", "apex legends", "overwatch", "elden ring",
    "zelda", "pokemon", "pokemon", "mario", "halo", "warzone",
    # Termos de gameplay
    "gameplay", "game", "gaming", "walkthrough", "playthrough",
    "speedrun", "let's play", "lets play", "letsplay",
    "mods", "modpack", "texture pack", "shader",
    "pvp", "pve", "raid", "dungeon", "quest",
    # Canais de streaming / esports
    "twitch", "stream", "streamer", "esport", "esports",
    "tournament", "competitive", "ranked",
    # Termos gerais que indicam jogo
    "video game", "videogame", "pc game", "console",
    "playstation", "xbox", "nintendo", "steam",
    "fps game", "rpg game", "mmorpg",
}

# Palavras de canal que denunciam canal de gaming
GAMING_CHANNEL_KEYWORDS = {
    "gaming", "gamer", "plays", "game", "games",
    "minecraft", "roblox", "fortnite", "pubg",
    "clips", "highlights", "esports",
}

# ─────────────────────────────────────────────
#  BLOCO DE EXCLUSÃO — CONTEÚDO COM ROSTO/VLOG
# ─────────────────────────────────────────────
FACECAM_KEYWORDS = {
    "vlog", "my life", "my day", "daily routine",
    "q&a", "qa", "irl", "face reveal",
    "podcast", "interview", "sit down", "talking with",
    "reaction", "reacting", "watching",
}

def _contains_any(text: str, keyword_set: set) -> bool:
    """Verifica se o texto contém qualquer keyword do conjunto (case-insensitive)."""
    t = text.lower()
    for kw in keyword_set:
        if re.search(r'\b' + re.escape(kw) + r'\b', t):
            return True
    return False

def exclude_gaming(video: dict) -> bool:
    """
    Retorna True se o vídeo DEVE SER EXCLUÍDO (é gaming ou com rosto).
    Regra de segurança: em caso de dúvida, exclui.
    """
    title   = str(video.get('title', ''))
    channel = str(video.get('channel_title', ''))
    desc    = str(video.get('description', ''))[:300]   # primeiros 300 chars

    # 1. Checar título + descrição contra gaming
    if _contains_any(title + " " + desc, GAMING_KEYWORDS):
        return True

    # 2  Checar nome do canal contra gaming
    if _contains_any(channel, GAMING_CHANNEL_KEYWORDS):
        return True

    # 3. Checar facecam / podcast no título
    if _contains_any(title, FACECAM_KEYWORDS):
        return True

    return False

# ─────────────────────────────────────────────
#  FILTRO PRINCIPAL DO PIPELINE
# ─────────────────────────────────────────────
def filter_viral_candidates(videos: list) -> list:
    """
    LAYER 2: Aplica filtros em cascata antes do scoring.
    Ordem: Gaming OUT → Face OUT → Métricas OK
    """
    filtered = []

    for v in videos:
        # Gate 0: Excluir Shorts (< 62 segundos)
        if v.get('is_short', False):
            continue
        # Gate 0b: Excluir vídeos sem duração mínima razoável (< 3 min = provavelmente ruído)
        if v.get('duration_seconds', 0) < 180:
            continue

        # Gate 1: Excluir gaming / facecam
        if exclude_gaming(v):
            continue

        # Gate 2: Métricas mínimas
        if v['views'] < MIN_VIEWS:
            continue
        if v['hours_since_upload'] > MAX_HOURS_OLD:
            continue
        if v['subscribers'] > MAX_SUBSCRIBERS:
            continue

        filtered.append(v)

    print(f"[FILTRO] {len(filtered)} / {len(videos)} videos passaram (gaming/facecam removidos).")
    return filtered


# ─────────────────────────────────────────────
#  CLASSIFICAÇÃO DE NICHO
# ─────────────────────────────────────────────
COLDCASE_KEYWORDS = {
    "cold case", "unsolved", "murder", "missing person",
    "true crime", "killer", "serial killer", "fbi",
    "homicide", "detective", "investigation", "bodycam",
    "interrogation", "fugitive", "wanted", "disappeared",
    "crime scene", "evidence", "suspect", "victim",
}

DARK_STORY_KEYWORDS = {
    "dark history", "dark secret", "dark psychology",
    "scary story", "horror story", "creepy", "paranormal",
    "conspiracy", "hidden truth", "exposed", "shocking",
    "mystery", "reddit story", "disturbing", "untold story",
}

def classify_niche(video: dict) -> str:
    """Classifica o vídeo num nicho para roteamento correto nas abas."""
    title = str(video.get('title', '')).lower()

    if _contains_any(title, COLDCASE_KEYWORDS):
        return 'coldcase'
    if _contains_any(title, DARK_STORY_KEYWORDS):
        return 'dark_story'

    return 'general_dark'
