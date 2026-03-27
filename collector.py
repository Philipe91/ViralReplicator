import requests
import random
from datetime import datetime, timezone, timedelta
from config import YOUTUBE_API_KEY, SEARCH_QUERIES, MAX_RESULTS_PER_QUERY

BASE_URL = "https://www.googleapis.com/youtube/v3"

def get_recent_videos():
    """Busca vídeos recentes baseados nas palavras-chave no YouTube de forma aleatória/dinâmica"""
    if YOUTUBE_API_KEY == "SUA_CHAVE_YOUTUBE_AQUI" or not YOUTUBE_API_KEY:
        print("⚠️ AVISO: Configure sua YOUTUBE_API_KEY no arquivo config.py!")
        return []
        
    videos = []
    video_ids = []
    
    # Misturar as queries para nunca fazer exata mesma busca na mesma ordem
    random.shuffle(SEARCH_QUERIES)
    
    # Pegar 6 queries aleatórias (economiza cota e gera variação)
    active_queries = SEARCH_QUERIES[:6]
    
    videos = []
    video_ids = []
    # 1. Buscar os IDs dos vídeos (Query)
    for query in active_queries:
        # Voltei o tempo ranzoado (12h a 72h atrás). Isso garante que você não pegue "lixo postado há 2 minutos sem views"
        # mas também garante que NENHUM clique seja no mesmo ponto do tempo, sempre trazendo canais diferentes!
        random_hours = random.randint(12, 72)
        published_after = (datetime.now(timezone.utc) - timedelta(hours=random_hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        print(f"🔎 Buscando na API por tags: '{query}' ({random_hours}h atrás)...")
        params = {
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'videoDuration': 'medium',   # medium = 4-20 min | long = +20 min | exclui Shorts
            'publishedAfter': published_after,
            'maxResults': MAX_RESULTS_PER_QUERY,
            'relevanceLanguage': 'en',
            'order': 'viewCount',        # Prioriza APENAS os vídeos com mais visualizações nesse pedaço de tempo sorteado
            'key': YOUTUBE_API_KEY
        }
        
        try:
            response = requests.get(f"{BASE_URL}/search", params=params, timeout=10)
            if response.status_code == 200:
                items = response.json().get('items', [])
                for item in items:
                    video_ids.append(item['id']['videoId'])
            else:
                print(f"❌ Erro na API do YouTube (Busca): {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Erro ao conectar com API de Busca: {e}")

    video_ids = list(set(video_ids))
    print(f"📊 Foram encontrados {len(video_ids)} vídeos únicos nesta rodada aleatória.")

    if not video_ids:
        return []

    # 2. Obter estatísticas dos vídeos em lotes de 50
    for i in range(0, len(video_ids), 50):
        batch_ids = video_ids[i:i+50]
        params = {
            'part': 'snippet,statistics,contentDetails',
            'id': ','.join(batch_ids),
            'key': YOUTUBE_API_KEY
        }
        
        try:
            response = requests.get(f"{BASE_URL}/videos", params=params, timeout=10)
            if response.status_code == 200:
                items = response.json().get('items', [])
                for item in items:
                    snippet = item['snippet']
                    stats = item.get('statistics', {})
                    content_details = item.get('contentDetails', {})
                    
                    video_data = {
                        'id': item['id'],
                        'title': snippet.get('title', ''),
                        'description': snippet.get('description', ''),
                        'published_at': snippet.get('publishedAt', ''),
                        'channel_id': snippet.get('channelId', ''),
                        'channel_title': snippet.get('channelTitle', ''),
                        'views': int(stats.get('viewCount', 0)),
                        'likes': int(stats.get('likeCount', 0)),
                        'comments': int(stats.get('commentCount', 0)),
                        'duration': content_details.get('duration', 'PT0S')
                    }
                    videos.append(video_data)
        except Exception as e:
            print(f"Erro ao conectar com API de Detalhes: {e}")

    # 3. Obter dados dos canais para saber número de inscritos
    channel_ids = list(set([v['channel_id'] for v in videos]))
    channels_data = {}
    
    for i in range(0, len(channel_ids), 50):
        batch_ids = channel_ids[i:i+50]
        params = {
            'part': 'statistics,snippet',
            'id': ','.join(batch_ids),
            'key': YOUTUBE_API_KEY
        }
        try:
            response = requests.get(f"{BASE_URL}/channels", params=params, timeout=10)
            if response.status_code == 200:
                items = response.json().get('items', [])
                for item in items:
                    channels_data[item['id']] = {
                        'subscribers': int(item['statistics'].get('subscriberCount', 0)),
                        'channel_created_at': item.get('snippet', {}).get('publishedAt', '')
                    }
        except Exception as e:
            print(f"Erro ao conectar com API de Canais: {e}")
                
    # Atrelar quantidade de inscritos ao vídeo correspondente
    for v in videos:
            c_data = channels_data.get(v['channel_id'], {'subscribers': 0, 'channel_created_at': ''})
            if isinstance(c_data, dict):
                v['subscribers'] = c_data.get('subscribers', 0)
                v['channel_created_at'] = c_data.get('channel_created_at', '')
            else:
                v['subscribers'] = c_data
                v['channel_created_at'] = ''

    return videos
