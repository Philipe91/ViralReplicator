def generate_global_insights(video):
    v_h = video.get('views_per_hour', 100)
    rising = video.get('rising_channel_score', 50)
    
    # Base metrics per country (0-100)
    countries_db = [
        {"nome": "EUA", "demanda": 95, "baixa_concorrencia": 10, "idioma": 90, "cpm": 100, "crescimento": 80},
        {"nome": "Reino Unido", "demanda": 85, "baixa_concorrencia": 20, "idioma": 90, "cpm": 90, "crescimento": 75},
        {"nome": "Brasil", "demanda": 92, "baixa_concorrencia": 50, "idioma": 80, "cpm": 40, "crescimento": 85},
        {"nome": "Índia", "demanda": 100, "baixa_concorrencia": 40, "idioma": 70, "cpm": 20, "crescimento": 95},
        {"nome": "Espanha", "demanda": 70, "baixa_concorrencia": 60, "idioma": 85, "cpm": 60, "crescimento": 70},
        {"nome": "México", "demanda": 85, "baixa_concorrencia": 65, "idioma": 85, "cpm": 30, "crescimento": 80},
        {"nome": "Alemanha", "demanda": 75, "baixa_concorrencia": 45, "idioma": 50, "cpm": 85, "crescimento": 60},
        {"nome": "Hungria", "demanda": 40, "baixa_concorrencia": 95, "idioma": 20, "cpm": 45, "crescimento": 50},
        {"nome": "Japão", "demanda": 80, "baixa_concorrencia": 35, "idioma": 10, "cpm": 80, "crescimento": 65},
        {"nome": "Indonésia", "demanda": 90, "baixa_concorrencia": 60, "idioma": 40, "cpm": 25, "crescimento": 85}
    ]
    
    opportunities = []
    
    for c in countries_db:
        # Dinâmica adaptativa
        demanda = min(100, c['demanda'] + (v_h / 50))
        baixa_concorrencia = c['baixa_concorrencia']
        idioma = c['idioma']
        cpm = c['cpm']
        crescimento_tema = min(100, c['crescimento'] + (rising * 0.2))
        
        # O ALGORITMO DE OPORTUNIDADE GLOBAL
        country_score = (demanda * 0.30) + (baixa_concorrencia * 0.30) + (idioma * 0.20) + (cpm * 0.10) + (crescimento_tema * 0.10)
        
        if country_score >= 80: recomendacao = "Premium Scale (Alto CPM / Grande Público)"
        elif country_score >= 65: recomendacao = "Expansão Sólida (Alta Conversão)"
        elif country_score >= 50: recomendacao = "Oceano Azul (Baixa Concorrência / Pioneiro)"
        else: recomendacao = "Nicho Saturado ou Difícil Acesso"
            
        opportunities.append({
            "pais": c['nome'],
            "score": round(min(100, country_score), 2),
            "recomendacao": recomendacao,
            "concorrencia": "Baixa" if baixa_concorrencia >= 70 else ("Média" if baixa_concorrencia >= 40 else "Alta")
        })
        
    opportunities = sorted(opportunities, key=lambda x: x['score'], reverse=True)
    video['global_opportunities'] = opportunities[:4]
    return video
