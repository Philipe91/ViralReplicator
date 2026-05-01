from collector import get_recent_videos
from analyzer import analyze_videos
from filters import filter_viral_candidates, classify_niche
from pattern_detector import extract_patterns
from idea_generator import apply_idea_generation
from scoring import calculate_copy_score
from copy_engine import generate_playbook
from global_opportunity_engine import generate_global_insights
from storage import save_to_csv, clear_old_videos, save_channel_snapshots
from alerts import check_alerts

def run_pipeline():
    """
    Pipeline de Inteligência Competitiva — 4 Camadas:
      1. COLETA      → get_recent_videos()
      2. ANÁLISE     → analyze_videos()
      3. FILTRO/NICHO→ filter_viral_candidates() + classify_niche()
      4. SCORING/UI  → scoring, playbook, storage
    """
    try:
        print("[PIPELINE] Iniciando varredura...")

        # ── Camada 1: Coleta ──────────────────────────────────────
        raw_videos = get_recent_videos()
        if not raw_videos:
            print("[PIPELINE] Nenhum vídeo coletado. Encerrando.")
            return

        # Persiste snapshot de cada canal coletado (data moat — base do velocity score).
        # Independe do filtro: salva TODOS os canais, mesmo os que serão descartados.
        save_channel_snapshots(raw_videos)

        # ── Camada 2: Análise de metadados ───────────────────────
        analyzed_videos = analyze_videos(raw_videos)

        # ── Camada 3: Filtro RÍGIDO (gaming OUT, dark IN) ─────────
        viral_candidates = filter_viral_candidates(analyzed_videos)
        if not viral_candidates:
            print("[PIPELINE] Zero candidatos após filtros. Pipeline encerrado.")
            return

        # Classificar nicho de cada vídeo sobrevivente
        for v in viral_candidates:
            v['niche'] = classify_niche(v)

        # ── Camada 4: Scoring, Insights e Armazenamento ───────────
        patterned   = extract_patterns(viral_candidates)
        scored      = [calculate_copy_score(v) for v in patterned]
        global_v    = [generate_global_insights(v) for v in scored]
        with_ideas  = apply_idea_generation(global_v)
        final       = [generate_playbook(v) for v in with_ideas]

        save_to_csv(final)
        check_alerts(final)

        print(f"[PIPELINE] Concluido. {len(final)} videos processados e salvos.")

    except Exception as e:
        print(f"[PIPELINE][ERRO] {e}")

if __name__ == "__main__":
    import schedule, time
    run_pipeline()
    schedule.every(30).minutes.do(run_pipeline)
    while True:
        schedule.run_pending()
        time.sleep(1)
