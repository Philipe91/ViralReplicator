def calculate_copy_score(video):
    v_h = video.get('views_per_hour', 0.1)
    subs = max(video.get('subscribers', 1), 1)
    likes = video.get('likes', 0)
    views = max(video.get('views', 1), 1)
    dur = video.get('duration_seconds', 0)
    hrs = video.get('hours_since_upload', 0.1)
    padrao = video.get('title_structure', 'Indefinido')
    title_lower = str(video.get('title', '')).lower()
    
    # 1. VELOCIDADE DE CRESCIMENTO (RISING_CHANNEL_SCORE)
    base_rising = (v_h / subs) * 1000
    rising_score = min(base_rising * 50, 100)
    if subs > 50000: rising_score *= 0.1
    if padrao != 'Indefinido': rising_score += 20
    video['rising_channel_score'] = round(min(rising_score, 100), 2)
    
    # 2. RETENÇÃO ESTIMADA
    like_ratio = (likes / views) * 100 
    retencao_estimada = like_ratio * 10 
    if dur > 600 and v_h > 100: retencao_estimada += 20
    video['retention_score'] = round(min(retencao_estimada, 100), 2)
    
    # 3. DETECÇÃO DE FASE
    if hrs <= 24 and v_h > 50:
        fase = 'INÍCIO'
    elif hrs <= 48 and v_h > 20:
        fase = 'CRESCENDO'
    else:
        fase = 'SATURADO'
    video['trend_timing'] = fase
    
    # 4. DIFICULDADE DE PRODUÇÃO
    if 'AI' in padrao or dur < 60:
        diff = 'FÁCIL'
    elif dur < 600:
        diff = 'MÉDIO'
    else:
        diff = 'DIFÍCIL'
    video['production_difficulty'] = diff
    
    # 5. SCORE DARK (Canais sem rosto)
    dark_score = 50
    if any(x in title_lower for x in ['podcast', 'interview', 'vlog', 'irl', 'me', 'i am', 'my life', 'episode', 'ep ']):
        dark_score -= 40
    if any(x in title_lower for x in ['explained', 'mystery', 'truth', 'dark', 'history', 'story', 'ai', 'robot', 'top', 'list']):
        dark_score += 30
    if diff == 'FÁCIL': dark_score += 20
    video['dark_score'] = min(max(dark_score, 0), 100)
    
    # 6. FACILIDADE DE REPLICAÇÃO (COPY_SCORE)
    cs = 0
    if diff == 'FÁCIL': cs += 35
    elif diff == 'MÉDIO': cs += 20
    
    if padrao != 'Indefinido': cs += 30
    cs += min(video['retention_score'] / 100 * 20, 20)
    cs += min(video['rising_channel_score'] / 100 * 15, 15)
    
    copy_score = round(min(cs, 100), 2)
    video['copy_score'] = copy_score
    
    if copy_score >= 85: video['copy_classification'] = 'PERFEITO PARA COPIAR'
    elif copy_score >= 60: video['copy_classification'] = 'MUITO BOM'
    elif copy_score >= 40: video['copy_classification'] = 'MÉDIO'
    else: video['copy_classification'] = 'DESCARTAR'
    
    return video
