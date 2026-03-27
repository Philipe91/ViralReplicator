import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

def detect_pattern_in_title(title):
    title_lower = title.lower()
    
    structures = {
        "This man/person...": r"\b(this man|this woman|this person|he|she)\b",
        "Nobody knows / Dark truth": r"\b(nobody knows|no one knows|the secret|hidden truth|dark truth)\b",
        "Top 10 / Listas": r"\b(top \d+|list of|best \d+)\b",
        "AI / Futurismo": r"\b(ai|chatgpt|artificial intelligence|robot)\b",
        "Mistério / True Crime": r"\b(murder|killed|missing|mystery|solved|found|caught)\b",
        "Explanations / Como/Por que": r"\b(explained|how to|why|what happens|the reason)\b"
    }
    
    for structure_name, pattern in structures.items():
        if re.search(pattern, title_lower):
            return structure_name
            
    return "Estrutura Genérica / Indefinida"

def extract_content_type(duration_seconds):
    if duration_seconds < 60:
        return "Shorts/Tiktok (< 1 min)"
    elif duration_seconds < 600:
        return "Medium Form (1-10 min)"
    else:
        return "Long Form / Storytelling (> 10 min)"

def cluster_videos(videos):
    """Agrupa vídeos usando KMeans no TF-IDF dos títulos."""
    if not videos:
        return []
        
    titles = [v['title'] for v in videos]
    
    # Executa K-Means apenas se número de amostragem for suficiente para clusterizar
    if len(titles) < 3:
        for v in videos:
            v['cluster'] = "Único / Sem agrupamento suficiente"
            v['title_structure'] = detect_pattern_in_title(v['title'])
            v['content_type'] = extract_content_type(v['duration_seconds'])
        return videos

    vectorizer = TfidfVectorizer(stop_words='english')
    X = vectorizer.fit_transform(titles)
    
    n_clusters = min(len(titles), 3)
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    klabels = kmeans.fit_predict(X)
    
    # Categorias base para os clusters (em produção, os labels podem 
    # vir de forma dinâmica baseada nas palavras dominantes do cluster)
    cluster_names = {
        0: "Focus: Mistérios Subterrâneos",
        1: "Focus: Curiosidades / Listas",
        2: "Focus: True Crime / Explicativos"
    }

    for i, v in enumerate(videos):
        cluster_id = klabels[i]
        v['cluster'] = cluster_names.get(cluster_id, f"Cluster Diferenciado {cluster_id}")
        v['title_structure'] = detect_pattern_in_title(v['title'])
        v['content_type'] = extract_content_type(v['duration_seconds'])
        
    return videos

def extract_patterns(videos):
    print("🪄 Detectando padrões visuais, tipos de conteúdo e clusterizando...")
    videos = cluster_videos(videos)
    
    if videos:
        avg_dur = sum([v['duration_seconds'] for v in videos]) / len(videos)
        print(f"📈 Duração média do padrão viral entre os selecionados: {avg_dur/60:.2f} minutos")
        
    return videos
