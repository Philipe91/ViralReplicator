"""
Channel velocity — calcula taxa de crescimento de subs/views por dia
a partir do histórico salvo em channel_history.

Phantom-channel-friendly: canal sem histórico (1 só snapshot ou nenhum)
recebe velocity = None — sinal neutro, não penaliza.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

from storage import DB_NAME

WINDOW_DAYS = 7  # janela quente, sem ruído de snapshots muito antigos


def _parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def compute_velocity(channel_id, conn, window_days=WINDOW_DAYS):
    """Retorna (sub_per_day, view_per_day) — float ou None se sinal insuficiente.

    Política:
      - <2 snapshots na janela → (None, None)   (sem dado, sinal neutro)
      - elapsed entre primeiro e último ≈ 0 → (None, None)  (mesma rodada)
      - caso contrário → delta absoluto / dias decorridos
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rows = conn.execute(
        "SELECT subscribers, view_count, seen_at FROM channel_history "
        "WHERE channel_id = ? AND seen_at >= ? "
        "ORDER BY seen_at ASC",
        (channel_id, cutoff),
    ).fetchall()
    if len(rows) < 2:
        return None, None

    first_subs, first_views, first_at = rows[0]
    last_subs, last_views, last_at = rows[-1]
    elapsed_days = (_parse_iso(last_at) - _parse_iso(first_at)).total_seconds() / 86400.0
    if elapsed_days <= 0:
        return None, None

    sub_v = (last_subs - first_subs) / elapsed_days
    view_v = (last_views - first_views) / elapsed_days
    return round(sub_v, 1), round(view_v, 1)


def enrich_videos_with_velocity(videos):
    """Popula v['subscriber_velocity_7d'] e v['view_velocity_7d'] em cada video.

    Cache em memória por channel_id — vários vídeos da mesma rodada podem ser
    do mesmo canal, então 1 query SQL serve N vídeos.
    """
    if not videos:
        return videos
    conn = sqlite3.connect(DB_NAME)
    cache = {}
    try:
        for v in videos:
            cid = v.get("channel_id")
            if not cid:
                v["subscriber_velocity_7d"] = None
                v["view_velocity_7d"] = None
                continue
            if cid not in cache:
                cache[cid] = compute_velocity(cid, conn)
            sub_v, view_v = cache[cid]
            v["subscriber_velocity_7d"] = sub_v
            v["view_velocity_7d"] = view_v
    finally:
        conn.close()
    return videos
