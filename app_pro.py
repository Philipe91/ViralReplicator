import streamlit as st
import sqlite3
import pandas as pd
import json
import os
import re
from pathlib import Path
from main import run_pipeline
from filters import classify_niche
from collector import get_recent_videos
from analyzer import analyze_videos
from filters import filter_viral_candidates, classify_niche
from pattern_detector import extract_patterns
from idea_generator import apply_idea_generation
from scoring import calculate_copy_score
from copy_engine import generate_playbook
from global_opportunity_engine import generate_global_insights
from storage import save_to_csv

st.set_page_config(page_title="Viral Replicator Pro", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

SAVED_FILE = "saved_channels.json"

def get_saved():
    if not os.path.exists(SAVED_FILE): return []
    try:
        with open(SAVED_FILE, 'r') as f: return json.load(f)
    except: return []

def toggle_save(vid_id):
    saved = get_saved()
    if vid_id in saved: saved.remove(vid_id)
    else: saved.append(vid_id)
    with open(SAVED_FILE, 'w') as f: json.dump(saved, f)

GAMING_KW = re.compile(
    r'\b(game|games|gaming|gameplay|gamer|minecraft|roblox|fortnite|gta|pubg|'
    r'cod|free fire|valorant|pokemon|walkthrough|playthrough|speedrun|'
    r'lets play|esport|twitch|streamer|pvp|xbox|playstation|nintendo|vlog|shorts)\b',
    re.IGNORECASE
)

def carregar_dados():
    try:
        conn = sqlite3.connect("viral_replicator_v3.db")
        df = pd.read_sql_query("SELECT * FROM videos ORDER BY detected_at DESC", conn)
        conn.close()
        mask = (
            df['title'].apply(lambda t: not bool(GAMING_KW.search(str(t)))) &
            df['channel_title'].apply(lambda c: not bool(GAMING_KW.search(str(c))))
        )
        df = df[mask].copy()
        if 'niche' not in df.columns:
            df['niche'] = df['title'].apply(lambda t: classify_niche({'title': t, 'channel_title': ''}))
        return df
    except:
        return pd.DataFrame()

def calc_channel_score(r):
    return (r['rising_channel_score']*0.3) + (r['retention_score']*0.25) + (r['copy_score']*0.2) + 15 + (r['dark_score']*0.1)

def fmt_num(n):
    try:
        n = float(n)
        if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
        if n >= 1_000: return f"{n/1_000:.1f}K"
        return str(int(n))
    except: return "0"

# ── Inject CSS from external file (avoids Streamlit markdown parser bug) ──────
css_path = Path(__file__).parent / "style.css"
with open(css_path) as f:
    css_content = f.read()

# Inject Google Fonts + FontAwesome separately, CSS via st.html equivalent
st.markdown(
    f'<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">'
    f'<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">',
    unsafe_allow_html=True
)
st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

# ── PLAYBOOK DIALOG ───────────────────────────────────────────────────────────
@st.dialog("PLAYBOOK", width="large")
def render_playbook(row):
    st.markdown(f"<h2 style='font-size:1.2rem;font-weight:700;margin-bottom:4px;color:#fafafa;font-family:Inter,sans-serif;'>{row.get('pt_br_title', '')}</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='font-size:0.78rem;color:#71717a;margin-bottom:20px;font-family:Inter,sans-serif;'>{row.get('channel_title', '')}</p>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        vid_id = str(row['id'])
        st.markdown(
            f'<img src="https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg" '
            f'onerror="this.src=\'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg\'" '
            f'style="width:100%;border-radius:8px;border:1px solid #1c1c1f;">',
            unsafe_allow_html=True
        )
    with c2:
        pb = {}
        try: pb = json.loads(row.get('playbook_json', '{}'))
        except: pass
        for section, key in [("ESTRUTURA", "estrutura"), ("NARRAÇÃO", "narracao"), ("FERRAMENTAS", "ferramentas")]:
            st.markdown(f"<div style='font-size:0.62rem;font-weight:700;color:#52525b;text-transform:uppercase;letter-spacing:1px;margin:14px 0 6px;font-family:Inter,sans-serif;'>{section}</div>", unsafe_allow_html=True)
            val = pb.get(key, {})
            if isinstance(val, dict):
                for k, v in val.items():
                    st.markdown(f"<p style='font-size:0.82rem;color:#d4d4d8;margin-bottom:3px;font-family:Inter,sans-serif;'><strong style='color:#fafafa;'>{k}:</strong> {v}</p>", unsafe_allow_html=True)
            elif isinstance(val, list):
                for item in val:
                    st.markdown(f"<p style='font-size:0.82rem;color:#d4d4d8;margin-bottom:2px;font-family:Inter,sans-serif;'>&bull; {item}</p>", unsafe_allow_html=True)
            else:
                st.markdown(f"<p style='font-size:0.82rem;color:#d4d4d8;font-family:Inter,sans-serif;'>{val}</p>", unsafe_allow_html=True)
    st.markdown("<hr style='border-color:#1c1c1f;margin:20px 0;'>", unsafe_allow_html=True)
    try:
        ops = json.loads(row.get('global_opportunities_json', '[]'))
        st.markdown("<div style='font-size:0.62rem;font-weight:700;color:#52525b;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;font-family:Inter,sans-serif;'>MERCADOS GLOBAIS</div>", unsafe_allow_html=True)
        for o in ops:
            rec = str(o.get('recomendacao','')).replace('🔥','').replace('🚀','').replace('💎','').strip()
            st.markdown(f"<p style='font-size:0.82rem;color:#d4d4d8;margin-bottom:6px;font-family:Inter,sans-serif;'><strong style='color:#fafafa;'>{o['pais']}</strong> &mdash; {rec}</p>", unsafe_allow_html=True)
    except: pass
    cb1, cb2 = st.columns(2)
    with cb1: st.link_button("Assistir Original", f"https://youtube.com/watch?v={row['id']}", use_container_width=True)
    with cb2: st.button("Habilitar Extração IA", type="primary", use_container_width=True)

def get_window_and_btn_html(score, trend_timing, opps_json):
    # Parse window days
    days = 15
    try:
        ops = json.loads(opps_json)
        if ops and 'janela' in ops[0]: days = int(ops[0]['janela'])
    except:
        if trend_timing == 'INÍCIO': days = 8
        elif trend_timing == 'CRESCENDO': days = 18
        else: days = 30
        
    bg_cls = "b-red" if days < 10 else "b-yellow" if days <= 21 else "b-green"
    badge_html = f"<div class='badge-window {bg_cls}'>Janela: {days}d</div>"
    
    # Decision button (Block 5)
    btn_html = ""
    if score > 80 and days < 15:
        btn_html = f"<button class='btn-main btn-attack' title='Score alto + janela fechando. Prioridade máxima.'>⚡ ATACAR AGORA</button>"
    elif score >= 60 or days >= 15:
        btn_html = f"<button class='btn-main btn-observe' title='Crescimento bom mas janela confortável.'>👁 OBSERVAR</button>"
    else:
        btn_html = f"<button class='btn-main btn-saturate'>⏸ SATURANDO</button>"
        
    return badge_html, btn_html, days

def get_country_badge(opps_json, days):
    pais = "🇺🇸 EUA"
    cpm = "$6"
    try:
        ops = json.loads(opps_json)
        if ops:
            p = ops[0].get('pais', 'Geral')
            if 'México' in p: pais = "🇲🇽 México"
            elif 'Brasil' in p: pais = "🇧🇷 Brasil"
            elif 'Japão' in p: pais = "🇯🇵 Japão"
            elif 'Alemanha' in p: pais = "🇩🇪 Alemanha"
            else: pais = f"🏳️ {p}"
            cpm = ops[0].get('CPM', '$4')
    except: pass
    return f"<div class='vrp-country-badge'>{pais} &middot; CPM {cpm} &middot; Janela {days}d</div>"

# ── CARD RENDERER ─────────────────────────────────────────────────────────────
def render_card(row, col, saved_list):
    vid_id = str(row['id'])
    pt_title = str(row.get('pt_br_title') or row.get('title', ''))
    pt_title = pt_title.replace("A Verdade sobre: ", "").replace("A Verdade sobre:", "").strip()
    
    v_h = float(row.get('views_per_hour', 0))
    rising = float(row.get('rising_channel_score', 0))
    copy = float(row.get('copy_score', 0))
    ret = float(row.get('retention_score', 0))
    is_saved = vid_id in saved_list
    
    views_s = fmt_num(row.get('views', 0))
    subs_s = fmt_num(row.get('subscribers', 0))
    channel = str(row.get('channel_title', ''))
    hours = int(float(row.get('hours_since_upload', 0)))
    
    # Calculate base score (avg of all or main logic)
    score_consolidado = int((rising * 0.45) + (ret * 0.30) + (copy * 0.25))
    score_color = "txt-green" if score_consolidado >= 80 else "txt-yellow" if score_consolidado >= 60 else "txt-red"
    
    timing = row.get('trend_timing', 'SATURADO')
    b_timing = "<div class='badge-status green'>INÍCIO</div>" if timing == 'INÍCIO' else \
               "<div class='badge-status yellow'>CRESCENDO</div>" if timing == 'CRESCENDO' else \
               "<div class='badge-status orange'>PICO</div>"
               
    w_badge_html, btn_html, w_days = get_window_and_btn_html(score_consolidado, timing, row.get('global_opportunities_json', '[]'))
    c_badge_html = get_country_badge(row.get('global_opportunities_json', '[]'), w_days)
    
    html = (
        f"<div class='vrp-card'>"
        f"<div class='vrp-card-thumb'>"
        f"<img src='https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg' onerror=\"this.src='https://img.youtube.com/vi/{vid_id}/hqdefault.jpg'\" loading='lazy'>"
        f"{b_timing}<div class='badge-speed'>{v_h:.0f}/h</div>{w_badge_html}"
        f"</div>"
        f"<div class='vrp-card-body'>"
        f"<div class='vrp-card-title'>{pt_title}</div>"
        f"<div class='vrp-card-channel'>{channel} &middot; {subs_s} subs</div>"
        f"<div class='vrp-score-block'>"
        f"<div class='vrp-score-mega {score_color}'>Score {score_consolidado}</div>"
        f"<div class='vrp-bars'>"
        f"<div class='vrp-bar-row'><span class='vrp-bar-label'>Replicação</span><div class='vrp-bar-track'><div class='vrp-bar-fill fill-rep' style='width:{min(100,copy):.0f}%'></div></div><span class='vrp-bar-val'>{copy:.0f}</span></div>"
        f"<div class='vrp-bar-row'><span class='vrp-bar-label'>Crescimento</span><div class='vrp-bar-track'><div class='vrp-bar-fill fill-cre' style='width:{min(100,rising):.0f}%'></div></div><span class='vrp-bar-val'>{rising:.0f}</span></div>"
        f"<div class='vrp-bar-row'><span class='vrp-bar-label'>Retenção</span><div class='vrp-bar-track'><div class='vrp-bar-fill fill-ret' style='width:{min(100,ret):.0f}%'></div></div><span class='vrp-bar-val'>{ret:.0f} <span>· m: 45</span></span></div>"
        f"</div>"
        f"</div>"
        f"{c_badge_html}"
        f"{btn_html}"
        f"</div></div>"
    )

    with col:
        st.markdown(html, unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Playbook", key=f"pb_{vid_id}", use_container_width=True): render_playbook(row)
        with c2:
            lbl = "Remover" if is_saved else "Salvar"
            if st.button(lbl, key=f"sv_{vid_id}", use_container_width=True):
                # Placeholder dropdown logic would go here if Streamlit allowed inline hover dropdowns.
                toggle_save(vid_id)
                st.rerun()

# ─── LOAD DATA ────────────────────────────────────────────────────────────────
df = carregar_dados()
saved_videos = get_saved()

# ─── TOPBAR ───────────────────────────────────────────────────────────────────
st.markdown(
    "<div class='vrp-topbar'>"
    "<div class='vrp-logo'>"
    "<div class='vrp-logo-icon'>VR</div>"
    "<span class='vrp-logo-text'>Viral<em>Replicator</em> Pro</span>"
    "</div>"
    "<div class='vrp-status'><div class='vrp-dot'></div>Sistema Online</div>"
    "</div>",
    unsafe_allow_html=True
)

# ─── NAVIGATION ROW ───────────────────────────────────────────────────────────
c_nav, c_search, c_btn, c_toggle = st.columns([6, 2, 1, 1.2])

with c_nav:
    st.markdown("<div style='padding:14px 40px 0;'>", unsafe_allow_html=True)
    nav_view = st.radio(
        "nav",
        ["Radar", "Oportunidades", "Expansão", "Tendências", "Cold Case", "Histórias IA", "Salvos"],
        horizontal=True, label_visibility="collapsed"
    )
    st.markdown("</div>", unsafe_allow_html=True)

with c_search:
    st.markdown("<div style='padding:12px 0 0;'>", unsafe_allow_html=True)
    search_query = st.text_input("search", placeholder="Buscar...", label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

with c_btn:
    st.markdown("<div style='padding:12px 20px 0 0;'>", unsafe_allow_html=True)
    scan_clicked = st.button("Varredura Agora", type="primary", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# Run pipeline SYNCHRONOUSLY with live progress so user can see what's happening
if scan_clicked:
    with st.status("Varrendo YouTube...", expanded=True) as status:
        try:
            st.write("Coletando vídeos da API do YouTube...")
            raw = get_recent_videos()
            st.write(f"{len(raw)} vídeos encontrados. Analisando métricas...")
            analyzed = analyze_videos(raw)
            st.write("Aplicando filtros (removendo gaming, shorts, facecam)...")
            candidates = filter_viral_candidates(analyzed)
            for v in candidates:
                v['niche'] = classify_niche(v)
            st.write(f"{len(candidates)} candidatos após filtros. Calculando scores...")
            patterned = extract_patterns(candidates)
            scored = [calculate_copy_score(v) for v in patterned]
            global_v = [generate_global_insights(v) for v in scored]
            with_ideas = apply_idea_generation(global_v)
            final = [generate_playbook(v) for v in with_ideas]
            save_to_csv(final)
            status.update(label=f"✅ Concluído! {len(final)} vídeos processados e salvos.", state="complete")
            st.rerun()
        except Exception as e:
            status.update(label=f"❌ Erro: {e}", state="error")
            st.error(str(e))

with c_toggle:
    st.markdown("<div style='padding:16px 40px 0 0;'>", unsafe_allow_html=True)
    modo_cacador = st.toggle("Strict", value=False)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='vrp-divider'></div>", unsafe_allow_html=True)

# ─── DATA PREP ────────────────────────────────────────────────────────────────
if df.empty:
    st.markdown(
        "<div style='text-align:center;padding:100px 40px;'>"
        "<h2 style='font-size:1.3rem;font-weight:600;color:#fafafa;margin-bottom:8px;font-family:Inter,sans-serif;'>Banco de dados vazio</h2>"
        "<p style='color:#52525b;font-size:0.88rem;font-family:Inter,sans-serif;'>Clique em Varredura Agora para buscar novos vídeos no YouTube.</p>"
        "</div>",
        unsafe_allow_html=True
    )
    st.stop()

df['channel_calculated_score'] = df.apply(calc_channel_score, axis=1)

# Base sem filtro de dark_score (usa todos os dados disponíveis)
df_base = df.copy()

# Busca só se aplicada nas abas gerais (NÃO em Cold Case, Histórias IA e Salvos)
if search_query and len(search_query.strip()) >= 2 and nav_view not in ["Cold Case", "Histórias IA", "Salvos"]:
    q = search_query.lower().strip()
    df_base = df_base[
        df_base['title'].str.lower().str.contains(q, na=False) |
        df_base['channel_title'].str.lower().str.contains(q, na=False)
    ]

if modo_cacador and nav_view not in ["Cold Case", "Histórias IA", "Salvos"]:
    df_strict = df_base[
        (df_base['trend_timing'] == 'INÍCIO') &
        (df_base['subscribers'] <= 50000)
    ]
    if len(df_strict) > 0:
        df_base = df_strict

# ─── RENDER VIEWS ─────────────────────────────────────────────────────────────
def render_grid(df_sorted, saved_list):
    if df_sorted.empty:
        st.info("Nenhum resultado encontrado. Tente desativar o Strict Mode ou atualize a base.")
        return
    st.markdown("<div class='vrp-grid-wrap'>", unsafe_allow_html=True)
    cols = st.columns(4)
    for idx, row in df_sorted.iterrows():
        render_card(row, cols[idx % 4], saved_list)
    st.markdown("</div>", unsafe_allow_html=True)

def section_header(title, count=None):
    meta = f"{count} canais" if count is not None else ""
    st.markdown(
        f"<div class='vrp-section-header'>"
        f"<h2 class='vrp-section-h2'>{title}</h2>"
        f"<span class='vrp-section-meta'>{meta}</span>"
        f"</div>",
        unsafe_allow_html=True
    )

if nav_view == "Radar":
    df_view = df_base.sort_values(by=['hours_since_upload', 'rising_channel_score'], ascending=[True, False])

    if not df_view.empty:
        top = df_view.iloc[0]
        top_id = str(top['id'])
        top_title = str(top.get('pt_br_title') or top.get('title', ''))
        top_title = top_title.replace("A Verdade sobre: ", "").replace("A Verdade sobre:", "").strip()
        copy = float(top.get('copy_score', 0))
        rising = float(top.get('rising_channel_score', 0))
        ret = float(top.get('retention_score', 0))
        score_consolidado = int((rising * 0.45) + (ret * 0.30) + (copy * 0.25))
        score_color = "txt-green" if score_consolidado >= 80 else "txt-yellow" if score_consolidado >= 60 else "txt-red"
        w_badge_html, _, w_days = get_window_and_btn_html(score_consolidado, top.get('trend_timing', 'SATURADO'), top.get('global_opportunities_json', '[]'))
        c_badge_html = get_country_badge(top.get('global_opportunities_json', '[]'), w_days)
        
        st.markdown(
            f"<div class='vrp-featured-wrap'>"
            f"<div class='vrp-rank-badge'><i class='fa-solid fa-crown'></i> MELHOR OPORTUNIDADE AGORA</div>"
            f"<div class='vrp-featured'>"
            f"<div class='vrp-feat-left'>"
            f"<img class='vrp-feat-img' src='https://img.youtube.com/vi/{top_id}/maxresdefault.jpg' "
            f"onerror=\"this.src='https://img.youtube.com/vi/{top_id}/hqdefault.jpg'\">"
            f"</div>"
            f"<div class='vrp-feat-right'>"
            f"<div class='vrp-rank-badge'><i class='fa-solid fa-bolt'></i> PRIORIDADE #1</div>"
            f"<div class='vrp-feat-title'>{top_title}</div>"
            f"<div class='vrp-feat-channel'>{top['channel_title']} &middot; {fmt_num(top['subscribers'])} inscritos</div>"
            f"<div class='vrp-feat-metrics'>"
            f"<div class='vrp-metric'><div class='vrp-feat-metric-val'>{fmt_num(top['views'])}</div><div class='vrp-feat-metric-lbl'>Visualizações</div></div>"
            f"<div class='vrp-metric'><div class='vrp-feat-metric-val'>{top['views_per_hour']:.0f}</div><div class='vrp-feat-metric-lbl'>Views/hora</div></div>"
            f"<div class='vrp-metric'><div class='vrp-feat-metric-val'>{int(top['hours_since_upload'])}h</div><div class='vrp-feat-metric-lbl'>Desde upload</div></div>"
            f"</div>"
            f"<div style='display:flex; gap: 32px; align-items:center;'>"
            f"<div class='vrp-score-block' style='flex-direction:row; padding: 16px; min-width:300px; gap:20px;'>"
            f"<div class='vrp-score-mega {score_color}'>Score {score_consolidado}</div>"
            f"<div class='vrp-bars' style='flex:1;'>"
            f"<div class='vrp-bar-row'><span class='vrp-bar-label'>Replicação</span><div class='vrp-bar-track'><div class='vrp-bar-fill fill-rep' style='width:{min(100,int(copy)):.0f}%'></div></div><span class='vrp-bar-val'>{copy:.0f}</span></div>"
            f"<div class='vrp-bar-row'><span class='vrp-bar-label'>Crescimento</span><div class='vrp-bar-track'><div class='vrp-bar-fill fill-cre' style='width:{min(100,int(rising)):.0f}%'></div></div><span class='vrp-bar-val'>{rising:.0f}</span></div>"
            f"<div class='vrp-bar-row'><span class='vrp-bar-label'>Retenção</span><div class='vrp-bar-track'><div class='vrp-bar-fill fill-ret' style='width:{min(100,int(ret)):.0f}%'></div></div><span class='vrp-bar-val'>{ret:.0f}</span></div>"
            f"</div></div>"
            f"<div>{c_badge_html}</div>"
            f"</div>"
            f"<button class='btn-main btn-attack btn-feat-attack'>⚡ ATACAR AGORA</button>"
            f"</div></div></div>",
            unsafe_allow_html=True
        )
        col_feat, _ = st.columns([1, 8])
        with col_feat:
            st.markdown("<div style='padding:12px 40px 0;'>", unsafe_allow_html=True)
            if st.button("Ver Playbook Completo", type="primary", key=f"feat_{top_id}"):
                render_playbook(top)
            st.markdown("</div>", unsafe_allow_html=True)

        df_rest = df_view.iloc[1:]
    else:
        df_rest = df_view

    section_header("Radar Timeline", len(df_view))
    render_grid(df_rest, saved_videos)

elif nav_view == "Oportunidades":
    df_view = df_base.sort_values(by=['copy_score', 'retention_score'], ascending=[False, False])
    section_header("Oportunidades Validadas", len(df_view))
    render_grid(df_view, saved_videos)

elif nav_view == "Expansão":
    df_view = df_base.sort_values(by='channel_calculated_score', ascending=False)
    section_header("Expansão Global Dinâmica", len(df_view))
    render_grid(df_view, saved_videos)

elif nav_view == "Tendências":
    df_view = df_base.sort_values(by='rising_channel_score', ascending=False)
    section_header("Tendências e Analytics", len(df_view))
    render_grid(df_view, saved_videos)

elif nav_view == "Cold Case":
    # Busca ampla por keywords no título — não depende da coluna niche
    COLD_KEYWORDS = r'cold case|unsolved|murder|missing person|true crime|serial killer|fbi|homicide|detective|interrogation|bodycam|fugitive|crime scene|suspect|victim|disappeared|killer|cold-case|investigation'
    df_all = df.copy()  # usa TODO o banco sem filtros de dark_score ou timing
    
    # Filtro por keyword OU niche
    mask_niche = df_all.get('niche', pd.Series(dtype=str)).str.lower() == 'coldcase'
    mask_title = df_all['title'].str.contains(COLD_KEYWORDS, case=False, na=False)
    df_cold = df_all[mask_niche | mask_title].sort_values(by='views_per_hour', ascending=False)
    
    # Aplicar busca do campo search se tiver texto
    if search_query and len(search_query.strip()) >= 2:
        q = search_query.lower().strip()
        df_cold = df_cold[
            df_cold['title'].str.lower().str.contains(q, na=False) |
            df_cold['channel_title'].str.lower().str.contains(q, na=False)
        ]
    
    section_header("Cold Case / True Crime", len(df_cold))
    if df_cold.empty:
        # Debug: mostrar total no banco
        total_db = len(df)
        st.info(f"Nenhum vídeo de Cold Case detectado. Total no banco: {total_db} vídeos. Clique em 'Varredura Agora' para buscar novos.")
    else:
        render_grid(df_cold, saved_videos)

elif nav_view == "Histórias IA":
    AI_KEYWORDS = r'ai|midjourney|leonardo|generated|told by ai|elevenlabs|chatgpt|artificial intelligence'
    STORY_KEYWORDS = r'story|tale|legend|history|lore|creepy pasta|myth'
    
    df_all = df.copy()
    
    # 1. Títulos explicitamente marcados como IA
    mask_ai_title = df_all['title'].str.contains(AI_KEYWORDS, case=False, na=False)
    # 2. OU têm dificuldade "FÁCIL" (nossa engine já marca IA como fácil) + palavra de história
    mask_easy_story = (df_all.get('production_difficulty', pd.Series(dtype=str)) == 'FÁCIL') & df_all['title'].str.contains(STORY_KEYWORDS, case=False, na=False)
    
    df_ai = df_all[mask_ai_title | mask_easy_story].sort_values(by='rising_channel_score', ascending=False)
    
    if search_query and len(search_query.strip()) >= 2:
        q = search_query.lower().strip()
        df_ai = df_ai[
            df_ai['title'].str.lower().str.contains(q, na=False) |
            df_ai['channel_title'].str.lower().str.contains(q, na=False)
        ]
        
    section_header("Contos & Histórias Geradas por IA", len(df_ai))
    if df_ai.empty:
        st.info("Nenhum canal de 'Histórias IA' detectado no momento. Clique em 'Varredura Agora' para rastrear tendências automatizadas (as tags já foram atualizadas internamente).")
    else:
        render_grid(df_ai, saved_videos)

elif nav_view == "Salvos":
    df_saved = df[df['id'].isin(saved_videos)].copy()
    if not df_saved.empty:
        df_saved['channel_calculated_score'] = df_saved.apply(calc_channel_score, axis=1)
        df_saved = df_saved.sort_values(by='channel_calculated_score', ascending=False)
    section_header("Canais Salvos", len(df_saved))
    render_grid(df_saved, saved_videos)

st.markdown("<div style='height:60px;'></div>", unsafe_allow_html=True)
