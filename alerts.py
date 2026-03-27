from config import VIRAL_SCORE_THRESHOLD

def check_alerts(videos):
    """Verifica e dispara alertas de tendências para os vídeos rastreados."""
    novos_alertas = 0
    print("\n--- 🚨 VERIFICANDO ALERTAS DE TRENS 🚨 ---")
    
    for v in videos:
        if v['viral_score'] >= VIRAL_SCORE_THRESHOLD:
            msg = f"""
🔥 NOVA TREND DETECTADA: {v['title']}
Score Viral: {v['viral_score']}
Padrão: {v['title_structure']}
Cluster: {v['cluster']}
Views Totais: {v['views']} | Upado há: {v['hours_since_upload']} horas
Taxa de Engajamento: {v['engagement_rate']}%

💡 EX DE ADAPTAÇÃO: {v.get('generated_ideas', {}).get('pt_br_title', 'S/ Ideias geradas')}
--------------------------------------------------"""
            print(msg)
            novos_alertas += 1
            
    if novos_alertas == 0:
        print("Tranquilo até o momento. Nenhuma trend nova bateu o Threshold nesta rodada.")
    else:
        print(f"!!! {novos_alertas} POTENCIAIS VIRAIS AVISADOS ACIMA !!!")
