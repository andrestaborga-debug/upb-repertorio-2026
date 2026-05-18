# UPB Repertorio 2026

Sitio del grupo de música UPB · semestre I 2026.

🌐 **Live**: https://upb-repertorio-2026.netlify.app

---

## Estructura

- `UPB Repertorio 2026 DEF.xlsx` — canciones, roles, % de avance
- `UPB Lista 2026.xlsx` — músicos, instrumentos, asistencia
- `Cronograma de ensayos UPB.xlsx` — calendario
- `_build_data.py` — `xlsx → upb_data.json`
- `_build_site.py` — `upb_data.json → _deploy/index.html`
- `_deploy/index.html` — sitio publicable
- `admin/app.py` — Streamlit admin para subir cambios sin terminal

---

## Editar localmente

```powershell
# 1. reemplazar los 3 xlsx con las versiones nuevas
# 2. regenerar
python _build_data.py
python _build_site.py
# 3. publicar
netlify deploy --prod --dir=_deploy --site=7bc3d77f-aa78-4041-9efe-f52c0072b8d1
```

---

## Admin web (sin terminal)

App de Streamlit en `admin/app.py`. La idea: cualquier persona del grupo entra a
una URL, mete contraseña, sube los 3 xlsx, y el sitio se actualiza solo.

### Setup local

```powershell
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
# editar .streamlit\secrets.toml con tus valores
streamlit run admin/app.py
```

### Deploy a Streamlit Cloud

1. Push este repo a GitHub (privado, contiene xlsx con datos del grupo).
2. https://share.streamlit.io → New app → conectar el repo.
3. Main file path: `admin/app.py`.
4. Settings → Secrets → pegar contenido de `secrets.toml` (sin el ejemplo).
5. Deploy.

### Secrets necesarios

| key | qué es |
|-----|--------|
| `password` | contraseña que se le pasa a quien va a usar el admin |
| `netlify_token` | Personal Access Token de Netlify ([generar acá](https://app.netlify.com/user/applications#personal-access-tokens)) |
| `netlify_site_id` | (opcional) ID del proyecto Netlify, default = el de UPB |
