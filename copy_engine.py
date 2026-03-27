def generate_playbook(video):
    playbook = {}
    
    playbook['estrutura'] = {
        'Hook (Início)': 'Apresentar a premissa chocante nos primeiros 3 segundos.',
        'Desenvolvimento': 'Explicar de forma contínua escondendo duas informações chaves.',
        'Final': 'Não concluir 100% da ideia, forçar comentários e perguntas do público.'
    }
    
    diff = video.get('production_difficulty', '')
    if diff == 'FÁCIL':
        tom = 'Ritmo rápido, hiper interativo, som de transição alto.'
    else:
        tom = 'Cinematográfico, pausas profundas, voz grave e pausada.'
        
    playbook['narracao'] = tom
    
    playbook['ferramentas'] = [
        'Voz IA: ElevenLabs',
        'Imagens IA: Midjourney',
        'Vídeo IA: Runway Gen-2',
        'Roteiro: ChatGPT'
    ]
        
    video['playbook'] = playbook
    return video
