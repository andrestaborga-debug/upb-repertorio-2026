"""Streamlit admin para UPB Repertorio.

Subí los 3 xlsx actualizados → regenera HTML → publica en Netlify.
Sin terminal, sin git.
"""
import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path

import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import _build_data
import _build_site

st.set_page_config(
    page_title="UPB · Actualizar repertorio",
    page_icon="♪",
    layout="centered",
)

DEFAULT_SITE_ID = "7bc3d77f-aa78-4041-9efe-f52c0072b8d1"

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
}

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
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- AUTH ----------
if not st.session_state.get("authed"):
    st.title("♪ UPB · Actualizar repertorio")
    st.markdown("Ingresá la contraseña para subir los Excel actualizados.")
    with st.form("login"):
        pwd = st.text_input("Contraseña", type="password", key="pwd_input")
        if st.form_submit_button("Entrar", type="primary"):
            if PASSWORD and pwd == PASSWORD:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    st.stop()

# ---------- MAIN UI ----------
st.title("♪ UPB · Actualizar repertorio")
st.markdown(
    "Subí los **3 archivos Excel** actualizados y dale a **Publicar cambios**. "
    "El sitio se regenera y se publica en "
    "[upb-repertorio-2026.netlify.app](https://upb-repertorio-2026.netlify.app) "
    "en menos de 30 segundos."
)

with st.form("upload"):
    st.subheader("1 · Subir los 3 Excel")
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
    st.subheader("2 · Publicar")
    submit = st.form_submit_button("Publicar cambios", type="primary", use_container_width=True)

if submit:
    missing = [EXPECTED_FILES[k] for k, v in files.items() if v is None]
    if missing:
        st.error("Faltan archivos:\n" + "\n".join(f"- {m}" for m in missing))
        st.stop()
    if not NETLIFY_TOKEN:
        st.error("No hay token de Netlify configurado. Avisale al admin.")
        st.stop()

    with st.status("Procesando…", expanded=True) as status:
        with tempfile.TemporaryDirectory() as tmp:
            st.write("📥 Guardando archivos…")
            for key, file in files.items():
                target = os.path.join(tmp, EXPECTED_FILES[key])
                with open(target, "wb") as f:
                    f.write(file.getvalue())

            st.write("📊 Procesando Excel…")
            try:
                data = _build_data.build(tmp, write_json=True, verbose=False)
            except Exception as e:
                status.update(label="Error procesando Excel", state="error")
                st.exception(e)
                st.stop()
            st.write(
                f"   → {len(data['musicians_raw'])} músicos · "
                f"{len(data['songs']['banda'])} banda · "
                f"{len(data['songs']['acusticas'])} acústicas · "
                f"{len(data['songs']['unirock'])} unirock"
            )

            st.write("🎨 Generando HTML…")
            index_path = os.path.join(tmp, "index.html")
            try:
                _build_site.build(tmp, out_paths=[index_path], verbose=False)
            except Exception as e:
                status.update(label="Error generando HTML", state="error")
                st.exception(e)
                st.stop()

            # Netlify digest-based deploy: registramos los SHA1 de cada archivo,
            # el servidor nos dice cuáles faltan, los subimos uno por uno con su
            # Content-Type correcto (inferido por extensión).
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
                st.stop()
            if not resp.ok:
                status.update(label="Netlify rechazó el deploy", state="error")
                st.error(f"HTTP {resp.status_code}: {resp.text[:500]}")
                st.stop()
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
                    st.stop()

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
                    st.stop()
                time.sleep(1)

            status.update(label="✅ ¡Publicado!", state="complete")

    st.success("Sitio actualizado correctamente.")
    live = deploy.get("ssl_url") or deploy.get("url")
    permanent = deploy.get("deploy_ssl_url")
    st.markdown(f"🌐 **Live**: [{live}]({live})")
    if permanent:
        st.markdown(f"🔗 **Deploy permanente**: [{permanent}]({permanent})")
    st.balloons()
