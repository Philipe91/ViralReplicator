import re
from datetime import datetime, timezone

def isodate_to_datetime(iso_str):
    if not iso_str:
        return datetime.now(timezone.utc)
    return datetime.strptime(iso_str, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)

def parse_duration(duration_str):
    """Converte padrão de duração ISO 8601 (PT10M30S) para segundos (simples)."""
    match = re.match(r'^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', duration_str)
    if not match:
        return 0
    h, m, s = match.groups()
    return int(h or 0) * 3600 + int(m or 0) * 60 + int(s or 0)

def calculate_metrics(video):
    pub_date = isodate_to_datetime(video['published_at'])
    now = datetime.now(timezone.utc)
    
    hours_since_upload = (now - pub_date).total_seconds() / 3600.0
    hours_since_upload = max(hours_since_upload, 0.1) # Evita divisao por zero
    
    views = video.get('views', 0)
    likes = video.get('likes', 0)
    comments = video.get('comments', 0)
    subscribers = video.get('subscribers', 0)
    
    views_per_hour = views / hours_since_upload
    engagement_rate = ((likes + comments) / views) if views > 0 else 0
    
    # viral_score = (views_por_hora * taxa_engajamento) / (inscritos + 1)
    # Quanto menor o canal e maiores views rápidas e engajamento, maior a pontuação.
    viral_score = (views_per_hour * engagement_rate) / (subscribers + 1) * 1000
    
    video['hours_since_upload'] = round(hours_since_upload, 1)
    video['views_per_hour'] = round(views_per_hour, 1)
    video['engagement_rate'] = round(engagement_rate * 100, 2)
    video['viral_score'] = round(viral_score, 2)
    dur = parse_duration(video['duration'])
    video['duration_seconds'] = dur
    # Flag Shorts: qualquer vídeo menor que 62 segundos é Short
    video['is_short'] = dur < 62

    # Idade do canal em dias — sinal contínuo (sem gate), usado pelo scoring.
    # Phantom channels (canais antigos) caem como sinal neutro; embrionários ganham boost.
    c_date = video.get('channel_created_at', '')
    if c_date:
        try:
            created = datetime.strptime(c_date, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
            video['channel_age_days'] = (now - created).days
        except ValueError:
            video['channel_age_days'] = None
    else:
        video['channel_age_days'] = None

    return video

def analyze_videos(videos):
    print(f"🧠 Calculando métricas de viralização (Viral Score) para {len(videos)} vídeos...")
    analyzed = []
    for v in videos:
        analyzed.append(calculate_metrics(v))
    return analyzed
