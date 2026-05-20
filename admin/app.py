"""Streamlit admin para UPB Repertorio.

Dos modos después de login (tabs):
- 📊 Ver datos: dashboard del maestro con repertorio, músicos, eventos y asistencia.
- 🔄 Actualizar: subida de los 4 xlsx → regenera HTML → publica en Netlify.
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import _build_data
import _build_site

st.set_page_config(
    page_title="UPB · Repertorio (admin)",
    page_icon="♪",
    layout="wide",
)

DEFAULT_SITE_ID = "7bc3d77f-aa78-4041-9efe-f52c0072b8d1"
LIVE_URL = "https://upb-repertorio-2026.netlify.app"

def _secret(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

SITE_ID = _secret("netlify_site_id", DEFAULT_SITE_ID)
PASSWORD = _secret("password", "")
NETLIFY_TOKEN = _secret("netlify_token", "")

EXPECTED_FILES = {
    "repertorio": "UPB Repertorio 2026 DEF.xlsx",
    "lista": "UPB Lista 2026.xlsx",
    "cronograma": "Cronograma de ensayos UPB.xlsx",
    "eventos": "Eventos.xlsx",  # opcional
}
REQUIRED_KEYS = ["repertorio", "lista", "cronograma"]

st.markdown(
    """
    <style>
    .stApp { background:#0a0a0f; }
    h1, h2, h3 { font-family: 'Playfair Display', Georgia, serif !important; color:#f0e6d0; }
    .stTextInput input, .stTextArea textarea { background:#14141e; color:#f0e6d0; }
    section[data-testid="stFileUploader"] { background:#14141e; border:1px solid #2a2a3a; border-radius:6px; padding:.5rem; }
    .stButton>button[kind="primary"],
    .stFormSubmitButton>button[kind="primaryFormSubmit"],
    button[kind="primary"], button[kind="primaryFormSubmit"] {
        background:#d4a03c !important;
        color:#0a0a0f !important;
        border:none !important;
        font-weight:600 !important;
    }
    .stButton>button[kind="primary"]:hover,
    button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {
        background:#e8a849 !important;
        color:#0a0a0f !important;
    }
    [data-testid="stMetricValue"] { color:#d4a03c; font-family:'Playfair Display', Georgia, serif; }
    .stTabs [data-baseweb="tab-list"] { gap: 1.5rem; }
    .stTabs [data-baseweb="tab"] { color:#c8b99a; font-size:1.05rem; }
    .stTabs [aria-selected="true"] { color:#d4a03c !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- AUTH ----------
if not st.session_state.get("authed"):
    st.title("♪ UPB · Repertorio (admin)")
    st.markdown("Ingresá la contraseña para continuar.")
    with st.form("login"):
        pwd = st.text_input("Contraseña", type="password", key="pwd_input")
        if st.form_submit_button("Entrar", type="primary"):
            if PASSWORD and pwd == PASSWORD:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    st.stop()

# ---------- HELPERS ----------
@st.cache_data(ttl=60)
def fetch_live_data():
    """Trae el HTML público y extrae el JSON embebido (const DATA = ...)."""
    try:
        resp = requests.get(LIVE_URL + "/", timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return None, str(e)
    m = re.search(r"const DATA = (\{.+?\});", resp.text, re.DOTALL)
    if not m:
        return None, "No se pudo extraer el payload del HTML público."
    try:
        return json.loads(m.group(1)), None
    except Exception as e:
        return None, f"JSON inválido: {e}"

def pct_color(p):
    if p is None: return "#6b6580"
    if p >= 70: return "#7db87a"
    if p >= 40: return "#e8a849"
    return "#d46a6a"

# ---------- RENDER: DASHBOARD ----------
def render_dashboard(data):
    kpis = data.get("kpis", {})
    cols = st.columns(4)
    cols[0].metric("Músicos activos", kpis.get("musicians_active", "—"))
    cols[1].metric("Canciones", kpis.get("songs_total", "—"))
    cols[2].metric("Avance medio", f"{kpis.get('avg_global', 0)}%")
    eventos = data.get("eventos", []) or []
    cols[3].metric("Eventos", len(eventos))

    st.markdown(f"🌐 Vista pública: [{LIVE_URL}]({LIVE_URL}) · "
                f"última carga hace {int((time.time() - st.session_state.get('fetched_at', time.time())))}s")
    st.divider()

    sub_eventos, sub_rep, sub_mus, sub_cal = st.tabs(
        ["🎤 Eventos", "🎵 Repertorio", "👥 Músicos", "📅 Calendario"]
    )

    # ===== EVENTOS =====
    with sub_eventos:
        if not eventos:
            st.info("No hay eventos cargados todavía. Subí `Eventos.xlsx` en la pestaña Actualizar.")
        for ev in eventos:
            avg = ev.get("avg_pct")
            header_lbl = f"**{ev['name']}** · {len(ev['songs'])} canciones"
            if avg is not None:
                header_lbl += f" · promedio {avg}%"
            with st.expander(header_lbl, expanded=True):
                # tabla resumen de la setlist
                table_rows = []
                for i, s in enumerate(ev["songs"]):
                    table_rows.append({
                        "#": i + 1,
                        "Canción": s.get("cancion"),
                        "Intérprete": s.get("interprete"),
                        "Duración": s.get("duration") or "—",
                        "Inst": s.get("inst") or "—",
                        "Avance %": s.get("global_pct"),
                    })
                st.dataframe(
                    pd.DataFrame(table_rows), use_container_width=True, hide_index=True,
                    column_config={
                        "Avance %": st.column_config.ProgressColumn(
                            "Avance %", min_value=0, max_value=100, format="%d%%",
                        ),
                    },
                )
                # detalle por canción: roles del repertorio si hay match
                songs_with_roles = [s for s in ev["songs"] if s.get("roles")]
                if songs_with_roles:
                    st.caption("👇 Detalle de roles por canción (vienen del Repertorio cuando hay match)")
                    for s in songs_with_roles:
                        pct = s.get("global_pct")
                        pct_lbl = f"{pct}%" if pct is not None else "—"
                        color = pct_color(pct)
                        st.markdown(
                            f"<div style='display:flex;justify-content:space-between;align-items:baseline;"
                            f"padding:.4rem .7rem;border-left:3px solid {color};background:#14141e;"
                            f"margin-top:.8rem;border-radius:0 4px 4px 0'>"
                            f"<div><strong style='color:#f0e6d0'>{s['cancion']}</strong>"
                            f" <span style='color:#6b6580;font-size:.85rem'>· {s['interprete']}</span></div>"
                            f"<div style='color:{color};font-weight:600;font-family:monospace'>{pct_lbl}</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        roles_df = pd.DataFrame([
                            {
                                "Rol": r.get("role"),
                                "Músico": r.get("musician_full") or r.get("musician_display") or "—",
                                "%": r.get("pct"),
                            }
                            for r in s.get("roles", [])
                        ])
                        st.dataframe(
                            roles_df, use_container_width=True, hide_index=True,
                            column_config={
                                "%": st.column_config.ProgressColumn(
                                    "%", min_value=0, max_value=100, format="%d%%",
                                ),
                            },
                        )

    # ===== REPERTORIO =====
    with sub_rep:
        songs = data.get("songs", []) or []
        if not songs:
            st.info("Sin canciones cargadas.")
        else:
            rows = []
            for s in songs:
                roles_filled = sum(1 for r in s.get("roles", []) if r.get("musician_display"))
                rows.append({
                    "Canción": s.get("cancion"),
                    "Intérprete": s.get("interprete"),
                    "Sección": s.get("section_label", s.get("section", "")).capitalize(),
                    "Avance %": s.get("global_pct"),
                    "Roles asignados": roles_filled,
                    "Roles totales": len(s.get("roles", [])),
                })
            df = pd.DataFrame(rows)
            st.caption(f"{len(df)} canciones · ordenable por columna")
            st.dataframe(
                df, use_container_width=True, hide_index=True,
                column_config={
                    "Avance %": st.column_config.ProgressColumn(
                        "Avance %", min_value=0, max_value=100, format="%d%%",
                    ),
                },
            )

    # ===== MÚSICOS (con drill-down) =====
    with sub_mus:
        roster = data.get("roster", []) or []
        active = [m for m in roster if m.get("count", 0) > 0]
        if not active:
            st.info("Sin músicos activos.")
        else:
            rows = []
            for m in active:
                attended = m.get("attended", 0)
                total = m.get("total", 0)
                pct = round(attended / total * 100) if total else 0
                instruments = ", ".join(m.get("instruments_domain", []) or [])
                rows.append({
                    "Músico": m.get("full"),
                    "Instrumentos": instruments,
                    "Asignaciones": m.get("count", 0),
                    "% canciones": m.get("avg_pct"),
                    "Asistencia": f"{attended}/{total}",
                    "% asistencia": pct,
                })
            df = pd.DataFrame(rows)
            st.caption(f"{len(df)} músicos activos · **click en una fila** para ver las canciones del músico")
            event = st.dataframe(
                df, use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row",
                column_config={
                    "% canciones": st.column_config.ProgressColumn(
                        "% canciones", min_value=0, max_value=100, format="%d%%",
                    ),
                    "% asistencia": st.column_config.ProgressColumn(
                        "% asistencia", min_value=0, max_value=100, format="%d%%",
                    ),
                },
                key="musicians_df",
            )
            if event.selection.rows:
                idx = event.selection.rows[0]
                m = active[idx]
                st.divider()
                st.subheader(f"📌 {m['full']}")
                meta_cols = st.columns(4)
                meta_cols[0].metric("Asignaciones", m.get("count", 0))
                meta_cols[1].metric("% promedio", f"{m.get('avg_pct', 0) or 0}%")
                meta_cols[2].metric("Asistencia", f"{m.get('attended', 0)}/{m.get('total', 0)}")
                meta_cols[3].metric("Instrumentos", len(m.get("instruments_domain", []) or []))
                songs_by_role = m.get("songs_by_role", {})
                if not songs_by_role:
                    st.info("Sin canciones asignadas.")
                else:
                    for role, role_songs in songs_by_role.items():
                        st.markdown(f"##### {role} · {len(role_songs)} canción(es)")
                        role_df = pd.DataFrame([
                            {
                                "Canción": s.get("cancion"),
                                "Intérprete": s.get("interprete"),
                                "Sección": (s.get("section") or "").capitalize(),
                                "% avance": s.get("pct"),
                            } for s in role_songs
                        ])
                        st.dataframe(
                            role_df, use_container_width=True, hide_index=True,
                            column_config={
                                "% avance": st.column_config.ProgressColumn(
                                    "% avance", min_value=0, max_value=100, format="%d%%",
                                ),
                            },
                        )

    # ===== CALENDARIO =====
    with sub_cal:
        calendar = data.get("calendar", []) or []
        if not calendar:
            st.info("Sin entradas en el calendario.")
        else:
            cal_rows = [
                {
                    "Fecha": e.get("date"),
                    "Día": e.get("day"),
                    "Evento": e.get("event") or "—",
                    "Detalle / Lugar": e.get("extra") or "",
                }
                for e in calendar
            ]
            st.caption(f"{len(cal_rows)} entradas (todo el cronograma: ensayos, conciertos, presentaciones)")
            st.dataframe(pd.DataFrame(cal_rows), use_container_width=True, hide_index=True)

# ---------- RENDER: UPLOAD ----------
def render_upload():
    st.markdown(
        "Subí los Excel actualizados y dale a **Publicar cambios**. "
        f"El sitio se regenera y se publica en [{LIVE_URL.replace('https://','')}]({LIVE_URL}) "
        "en menos de 30 segundos."
    )

    with st.form("upload"):
        st.subheader("1 · Subir los Excel")
        st.markdown("**Obligatorios:**")
        files = {
            "repertorio": st.file_uploader(
                "Repertorio · `UPB Repertorio 2026 DEF.xlsx`",
                type=["xlsx"], key="rep",
            ),
            "lista": st.file_uploader(
                "Lista de músicos · `UPB Lista 2026.xlsx`",
                type=["xlsx"], key="lst",
            ),
            "cronograma": st.file_uploader(
                "Cronograma de ensayos · `Cronograma de ensayos UPB.xlsx`",
                type=["xlsx"], key="cron",
            ),
        }
        st.markdown("**Opcional** (si no lo subís, no se muestran eventos):")
        files["eventos"] = st.file_uploader(
            "Eventos · `Eventos.xlsx` (cada hoja = un evento)",
            type=["xlsx"], key="ev",
        )
        st.subheader("2 · Publicar")
        submit = st.form_submit_button("Publicar cambios", type="primary", use_container_width=True)

    if not submit:
        return

    missing = [EXPECTED_FILES[k] for k in REQUIRED_KEYS if files.get(k) is None]
    if missing:
        st.error("Faltan archivos obligatorios:\n" + "\n".join(f"- {m}" for m in missing))
        return
    if not NETLIFY_TOKEN:
        st.error("No hay token de Netlify configurado. Avisale al admin.")
        return

    with st.status("Procesando…", expanded=True) as status:
        with tempfile.TemporaryDirectory() as tmp:
            st.write("📥 Guardando archivos…")
            for key, file in files.items():
                if file is None:
                    continue
                target = os.path.join(tmp, EXPECTED_FILES[key])
                with open(target, "wb") as f:
                    f.write(file.getvalue())

            st.write("📊 Procesando Excel…")
            try:
                data = _build_data.build(tmp, write_json=True, verbose=False)
            except Exception as e:
                status.update(label="Error procesando Excel", state="error")
                st.exception(e)
                return
            events_count = len(data.get("events", []))
            events_summary = ", ".join(f"{e['name']}×{len(e['songs'])}" for e in data.get("events", []))
            st.write(
                f"   → {len(data['musicians_raw'])} músicos · "
                f"{len(data['songs']['banda'])} banda · "
                f"{len(data['songs']['acusticas'])} acústicas · "
                f"{events_count} evento(s) ({events_summary or 'ninguno'})"
            )

            st.write("🎨 Generando HTML…")
            index_path = os.path.join(tmp, "index.html")
            try:
                _build_site.build(tmp, out_paths=[index_path], verbose=False)
            except Exception as e:
                status.update(label="Error generando HTML", state="error")
                st.exception(e)
                return

            with open(index_path, "rb") as f:
                index_bytes = f.read()
            files_map = {"/index.html": hashlib.sha1(index_bytes).hexdigest()}

            st.write("🚀 Registrando deploy en Netlify…")
            headers = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
            try:
                resp = requests.post(
                    f"https://api.netlify.com/api/v1/sites/{SITE_ID}/deploys",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"files": files_map, "async": False},
                    timeout=60,
                )
            except Exception as e:
                status.update(label="Error de red con Netlify", state="error")
                st.exception(e)
                return
            if not resp.ok:
                status.update(label="Netlify rechazó el deploy", state="error")
                st.error(f"HTTP {resp.status_code}: {resp.text[:500]}")
                return
            deploy = resp.json()
            deploy_id = deploy["id"]
            required = set(deploy.get("required") or [])

            st.write(f"📤 Subiendo {len(required)} archivo(s)…")
            for path, sha in files_map.items():
                if sha not in required:
                    continue
                content = index_bytes if path == "/index.html" else b""
                up = requests.put(
                    f"https://api.netlify.com/api/v1/deploys/{deploy_id}/files{path}",
                    headers={**headers, "Content-Type": "application/octet-stream"},
                    data=content,
                    timeout=120,
                )
                if not up.ok:
                    status.update(label="Error subiendo archivo", state="error")
                    st.error(f"HTTP {up.status_code}: {up.text[:500]}")
                    return

            st.write("⏳ Esperando que Netlify procese…")
            for _ in range(30):
                state_resp = requests.get(
                    f"https://api.netlify.com/api/v1/sites/{SITE_ID}/deploys/{deploy_id}",
                    headers=headers, timeout=30,
                )
                deploy = state_resp.json()
                if deploy.get("state") == "ready":
                    break
                if deploy.get("state") == "error":
                    status.update(label="Netlify falló al procesar", state="error")
                    st.error(deploy.get("error_message") or "error desconocido")
                    return
                time.sleep(1)

            status.update(label="✅ ¡Publicado!", state="complete")

    # invalidate cache so the view tab fetches the new data on next render
    fetch_live_data.clear()

    st.success("Sitio actualizado correctamente.")
    live = deploy.get("ssl_url") or deploy.get("url")
    permanent = deploy.get("deploy_ssl_url")
    st.markdown(f"🌐 **Live**: [{live}]({live})")
    if permanent:
        st.markdown(f"🔗 **Deploy permanente**: [{permanent}]({permanent})")
    st.balloons()

# ---------- MAIN ----------
st.title("♪ UPB · Repertorio (admin)")

tab_view, tab_update = st.tabs(["📊 Ver datos", "🔄 Actualizar"])

with tab_view:
    with st.spinner("Cargando datos del sitio público…"):
        data, err = fetch_live_data()
    st.session_state["fetched_at"] = time.time()
    if err:
        st.error(f"No se pudo cargar los datos live: {err}")
    elif data:
        render_dashboard(data)

with tab_update:
    render_upload()
