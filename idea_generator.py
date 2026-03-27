import json
from config import OPENAI_API_KEY

def generate_ideas_for_video(video):
    """
    Gera ideias convertidas/adaptadas para o mercado alvo (ex: Brasil).
    Deixa estrutura pronta para usar OpenAI, com fallback para heurística simples.
    """
    title = video['title']
    
    # -------------------------------------------------------------
    # PREPARAÇÃO PARA ESCALA (INTEGRAÇÃO REAL COM OPENAI)
    # -------------------------------------------------------------
    if OPENAI_API_KEY and OPENAI_API_KEY != "SUA_CHAVE_OPENAI_AQUI":
        try:
            import openai
            openai.api_key = OPENAI_API_KEY
            
            prompt = f"""
            Você é um roteirista de YouTube especializado em canais Dark no Brasil que traduzem tendências gringas.
            Analise o seguinte título de vídeo gringo que acabou de viralizar: "{title}".
            
            Me devolva APENAS um JSON válido contendo a estrutura abaixo e NADA MAIS:
            {{
                "pt_br_title": "Um título forte em português BR, adaptando a ideia sem traduzir ao pé da letra.",
                "title_variations": ["Opcao 1", "Opcao 2", "Opcao 3", "Opcao 4", "Opcao 5"],
                "sugestoes": {{
                    "hook": "Sua sugestão de 2-5 segundos de hook inicial visual ou narrativo.",
                    "narrativa": "Estilo de narrativa a ser adotada ao longo do vídeo.",
                    "thumbnail": "Descritivo visual de uma thumbnail CTR altíssimo."
                }}
            }}
            """
            # Se for integrado, execute e retorne. Exemplo:
            # response = openai.chat.completions.create(
            #     model="gpt-3.5-turbo",
            #     messages=[{"role": "user", "content": prompt}],
            #     temperature=0.7
            # )
        except Exception as e:
            print(f"Erro ao conectar na OpenAI: {e}")

    # -------------------------------------------------------------
    # FALLBACK / SIMULAÇÃO RULE-BASED PARA FASE 1 (MVP)
    # -------------------------------------------------------------
    
    v_adaptada = f"A Verdade sobre: {title[:15]}..."
    
    ideias = {
        'pt_br_title': v_adaptada,
        'title_variations': [
            f"Por que {title[:15]} mudou tudo...",
            f"O Segredo sobre {title[:10]}",
            f"Eles esconderam isso: {title[:12]}",
            f"O pior erro de {title[:15]}",
            f"Descubra o mistério de {title[:10]}"
        ],
        'sugestoes': {
            'hook': "Comece com uma afirmação controversa e uma tela preta rápida por 1s.",
            'narrative': "Suspense progressivo. Crie loops abertos a cada 2 minutos.",
            'thumbnail': "Fundo escuro. Rosto focado borrado com olhos ocultos e Seta vermelha minimalista."
        }
    }
    
    video['generated_ideas'] = ideias
    return video

def apply_idea_generation(videos):
    print("💡 Gerando ideias e adaptações para o mercado.")
    for v in videos:
        generate_ideas_for_video(v)
    return videos
