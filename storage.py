import sqlite3
import json
from datetime import datetime, timedelta

DB_NAME = "viral_replicator_v3.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            title TEXT,
            published_at TEXT,
            channel_id TEXT,
            channel_title TEXT,
            views INTEGER,
            likes INTEGER,
            comments INTEGER,
            subscribers INTEGER,
            hours_since_upload REAL,
            views_per_hour REAL,
            engagement_rate REAL,
            viral_score REAL,
            duration_seconds INTEGER,
            cluster TEXT,
            title_structure TEXT,
            pt_br_title TEXT,
            copy_score REAL,
            copy_classification TEXT,
            production_difficulty TEXT,
            trend_timing TEXT,
            playbook_json TEXT,
            detected_at TEXT,
            rising_channel_score REAL,
            retention_score REAL,
            global_opportunities_json TEXT,
            dark_score REAL,
            niche TEXT,
            channel_created_at TEXT
        )
    ''')
    # Migração segura: garantir coluna niche e channel_created_at em bancos antigos
    try:
        c.execute("ALTER TABLE videos ADD COLUMN niche TEXT DEFAULT 'general_dark'")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE videos ADD COLUMN channel_created_at TEXT DEFAULT ''")
    except Exception:
        pass
    conn.commit()
    conn.close()

def clear_old_videos(hours: int = 48):
    """Remove vídeos detectados há mais de N horas para manter o banco fresco."""
    try:
        init_db()
        conn = sqlite3.connect(DB_NAME)
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("DELETE FROM videos WHERE detected_at < ?", (cutoff,))
        deleted = conn.total_changes
        conn.commit()
        conn.close()
        print(f"[DB] {deleted} vídeos antigos removidos (>{hours}h).")
    except Exception as e:
        print(f"[DB] Erro ao limpar: {e}")

def save_to_db(videos):
    if not videos: return
    init_db()
    conn = sqlite3.connect(DB_NAME)
    
    for v in videos:
        pt_br_title = v.get('generated_ideas', {}).get('pt_br_title', '')
        playbook = json.dumps(v.get('playbook', {}), ensure_ascii=False)
        gl_opps = json.dumps(v.get('global_opportunities', []), ensure_ascii=False)
        detected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        tuple_data = (
            v.get('id', ''), str(v.get('title', '')), v.get('published_at', ''),
            v.get('channel_id', ''), v.get('channel_title', ''),
            v.get('views', 0), v.get('likes', 0), v.get('comments', 0), v.get('subscribers', 0),
            v.get('hours_since_upload', 0), v.get('views_per_hour', 0), v.get('engagement_rate', 0),
            v.get('viral_score', 0), v.get('duration_seconds', 0), v.get('cluster', ''), v.get('title_structure', ''),
            pt_br_title, v.get('copy_score', 0), v.get('copy_classification', ''), v.get('production_difficulty', ''),
            v.get('trend_timing', ''), playbook, detected_at,
            v.get('rising_channel_score', 0),
            v.get('retention_score', 0),
            json.dumps(v.get('global_opportunities', {}), ensure_ascii=False), # Changed from gl_opps and default from [] to {}
            v.get('dark_score', 0),
            v.get('niche', 'general_dark'),
            v.get('channel_created_at', '') # Added channel_created_at
        )
        conn.execute(
            'INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', # Added one '?' for channel_created_at
            tuple_data
        )
    conn.commit()
    conn.close()

def save_to_csv(videos):
    save_to_db(videos)
