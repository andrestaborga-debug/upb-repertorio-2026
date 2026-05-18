"""Construye index.html desde upb_data.json. Importable o ejecutable."""
import json, os, sys, io
from datetime import datetime

DEFAULT_BASE = r"C:\Users\andre\OneDrive\Escritorio\CLAUDE\LUIGI"
DEFAULT_OUT = r"C:\Users\andre\OneDrive\Escritorio\UPB_Repertorio_2026.html"

# --- normalización: nombre completo por apodo ---
def find_full(nick, musicians):
    """Match a nickname to the most likely full name from the Lista."""
    if not nick:
        return None
    nick_l = nick.lower().strip()
    # exact match by first name token
    for m in musicians:
        tokens = m["full_name"].lower().split()
        if tokens and tokens[0] == nick_l:
            return m["full_name"]
    # specific overrides
    overrides = {
        "tomy": "Tomás Villanueva",
        "vale": "Valentina Camacho",
        "ale": "Alejandro Burgoa",
        "ale y": "Alejandro Fabián Yañez Parra",
        "fernanda h": "Fernanda Humerez",
        "natalia": "Natalia Maldonado",
        "natalia c": "Natalia Castro",
        "belen": "Belen Arce",
        "belén": "Belen Arce",
        "gary": "Gari Mijael Mamani Condori",
        "fátima": "Fátima Burgoa",
        "andy": "Andy David Velarde Torrico",
        "anibal": "Anibal Mariaca Saavedra",
        "karina": "Karina Morales",
        "sebastián": "Sebastián Dávalos Rosas",
        "aleshka": "Aleshka Garvizu",
        "caleb": "Caleb Astulla Ubizaga",
        "bernardo": "Bernardo Del Aguila",
        "jennifer": "Jennifer Gutierrez Encinas",
        "erik": "Erik Alejandro Rendón Jimenez",
        "mateo": "Mateo Moya Cespedes",
        "fernando": "Fernando Rodrigo Yugar Villafan",
        "adrián": "Adrián Peredo Gutierrez",
        "jasmine": "Jasmine Juliano Fernandez",
        "silvana": "Silvana López Gomóz",
        "lucas": "Lucas Vargas",
        "jessica": "Jessica Bolivar",
        "alira": "Alira Macel Miranda Garcia",
        "tiani": "Tiani Magalhaes",
        "fabiana rojas": "Fabiana Rojas Lizarraga",
        "jeffrey": "Jeffrey David Pardo Paredes",
        "jeffry": "Jeffrey David Pardo Paredes",
        "nico": "Nico Cueto",
        "camila ramos": "Camila Ramos Rodriguez",
        "mariana": "Mariana Villarroel Deheza",
    }
    return overrides.get(nick_l)

# Tokens que aparecen en la columna de músico pero NO son personas
# (categorías de instrumento ejecutadas por backing/secuenciador)
NON_HUMAN_TOKENS = {"secuencias"}

# Construir el roster: por cada músico, sus asignaciones agrupadas por rol
def build_roster(musicians, songs_all):
    # primer paso: assignments por nick -> traducir a full_name
    by_full = {m["full_name"]: {
        "full": m["full_name"],
        "instruments_domain": m["instruments_domain"],
        "attended": m["rehearsals_attended"],
        "total": m["rehearsals_total"],
        "songs_by_role": {},  # role -> list of {cancion, interprete, pct, section}
        "all_pcts": [],
        "count": 0,
    } for m in musicians}
    # Procesar canciones desde la lista normalizada (sin duplicar UniRock)
    for s in songs_all:
        for r in s["roles"]:
            nick = r.get("musician_display")
            if not nick:
                continue
            if nick.strip().lower() in NON_HUMAN_TOKENS:
                continue
            full = r.get("musician_full") or nick
            rec = by_full.get(full)
            if rec is None:
                by_full[full] = {
                    "full": full,
                    "instruments_domain": [],
                    "attended": 0,
                    "total": 0,
                    "songs_by_role": {},
                    "all_pcts": [],
                    "count": 0,
                }
                rec = by_full[full]
            rec["songs_by_role"].setdefault(r["role"], []).append({
                "cancion": s["cancion"],
                "interprete": s["interprete"],
                "pct": r["pct"],
                "section": s["section"],
                "in_unirock": s.get("in_unirock", False),
            })
            rec["count"] += 1
            if r["pct"] is not None:
                rec["all_pcts"].append(r["pct"])
    # convertir a lista, calcular avg, ordenar por count desc luego avg desc
    out = []
    for full, rec in by_full.items():
        avg = round(sum(rec["all_pcts"]) / len(rec["all_pcts"])) if rec["all_pcts"] else None
        rec["avg_pct"] = avg
        out.append(rec)
    out.sort(key=lambda x: (-x["count"], -(x["avg_pct"] or 0), x["full"]))
    return out

# --- songs unificadas para la sección Repertorio ---
# UniRock es un setlist que reutiliza canciones de la Banda (con % posiblemente actualizado).
# Por lo tanto, no añadimos UniRock como canciones separadas: lo usamos como flag sobre las
# canciones de Banda, y si hay un % de UniRock más reciente, lo aplicamos.
def normalize_songs(raw, musicians):
    # construir índice de unirock por (interprete, cancion)
    unirock_index = {}
    for s in raw["songs"]["unirock"]:
        key = ((s.get("interprete") or "").strip().lower(), (s.get("cancion") or "").strip().lower())
        unirock_index[key] = s

    out = []
    for section_key, label in [("banda", "Banda"), ("acusticas", "Acústicas")]:
        for s in raw["songs"][section_key]:
            key = ((s.get("interprete") or "").strip().lower(), (s.get("cancion") or "").strip().lower())
            in_unirock = section_key == "banda" and key in unirock_index
            # si la canción está en UniRock, preferir su data (más reciente)
            source = unirock_index[key] if in_unirock else s
            roles_clean = []
            for r in source["roles"]:
                if r["musician"]:
                    full = find_full(r["musician"], musicians) or r["musician"]
                else:
                    full = None
                roles_clean.append({
                    "role": r["role"],
                    "musician_display": r["musician"],
                    "musician_full": full,
                    "pct": r["pct"],
                })
            out.append({
                "section": section_key,
                "section_label": label,
                "in_unirock": in_unirock,
                "interprete": s["interprete"],
                "cancion": s["cancion"],
                "global_pct": source["global_pct"],
                "roles": roles_clean,
            })
    return out

def build_eventos(raw, musicians):
    """Eventos = setlists para presentaciones. Por ahora: UniRock."""
    songs = []
    for s in raw["songs"]["unirock"]:
        roles_clean = []
        for r in s["roles"]:
            if r["musician"]:
                full = find_full(r["musician"], musicians) or r["musician"]
            else:
                full = None
            roles_clean.append({
                "role": r["role"],
                "musician_display": r["musician"],
                "musician_full": full,
                "pct": r["pct"],
            })
        songs.append({
            "interprete": s["interprete"],
            "cancion": s["cancion"],
            "global_pct": s["global_pct"],
            "roles": roles_clean,
        })
    pcts = [s["global_pct"] for s in songs if s["global_pct"] is not None]
    avg = round(sum(pcts) / len(pcts)) if pcts else None
    return [{"name": "UniRock", "songs": songs, "avg_pct": avg}]

def compute_payload(raw):
    musicians = raw["musicians_raw"]
    songs_all = normalize_songs(raw, musicians)
    eventos = build_eventos(raw, musicians)
    roster = build_roster(musicians, songs_all)
    all_pcts = [s["global_pct"] for s in songs_all if s["global_pct"] is not None]
    avg_global = round(sum(all_pcts) / len(all_pcts)) if all_pcts else 0
    active_musicians = sum(1 for m in roster if m["count"] > 0)
    total_songs = len(raw["songs"]["banda"]) + len(raw["songs"]["acusticas"])
    return {
        "kpis": {
            "musicians_active": active_musicians,
            "musicians_total": len(roster),
            "songs_total": total_songs,
            "songs_banda": len(raw["songs"]["banda"]),
            "songs_acusticas": len(raw["songs"]["acusticas"]),
            "avg_global": avg_global,
        },
        "songs": songs_all,
        "eventos": eventos,
        "roster": roster,
    }

# --- HTML ---
HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UPB Repertorio 2026 — Grupo de Música</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=IBM+Plex+Mono:wght@300;400;500&family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0a0a0f;--bg2:#111118;--bg3:#1a1a24;
  --amber:#e8a849;--gold:#d4a03c;
  --cream:#f0e6d0;--cream2:#c8b99a;--dim:#6b6580;
  --purple:#9b7ecf;--rose:#c7727e;--teal:#5ea8a0;
  --blue:#6b8fc7;--green:#7db87a;--red:#d46a6a;
  --card:#14141e;--border:#2a2a3a;
  --ok:#7db87a;--warn:#e8a849;--low:#d46a6a;
}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--cream);font-family:'Cormorant Garamond',Georgia,serif;font-size:18px;line-height:1.6;overflow-x:hidden}
body::after{content:'';position:fixed;inset:0;pointer-events:none;z-index:9999;opacity:.035;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}

/* HERO */
.hero{min-height:100vh;min-height:100svh;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:2rem 1.25rem;position:relative;background:radial-gradient(ellipse at 50% 80%,#1a1428 0%,var(--bg) 70%)}
.hero::before{content:'';position:absolute;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 49px,rgba(232,168,73,.04) 50px);pointer-events:none}
.hero-badge{font-family:'IBM Plex Mono',monospace;font-size:.7rem;letter-spacing:.35em;text-transform:uppercase;color:var(--amber);border:1px solid rgba(232,168,73,.3);padding:.5em 1.5em;border-radius:2px;margin-bottom:2rem;animation:fadeDown .8s ease-out both}
.hero h1{font-family:'Playfair Display',serif;font-size:clamp(2.4rem,9vw,7rem);font-weight:900;line-height:.95;color:var(--cream);margin-bottom:1rem;animation:fadeDown 1s ease-out .2s both;word-break:break-word}
.hero h1 em{font-style:italic;color:var(--amber)}
.hero-sub{font-size:clamp(1rem,2.5vw,1.4rem);color:var(--cream2);max-width:600px;font-style:italic;margin-bottom:2.5rem;animation:fadeDown 1s ease-out .4s both}
.hero-stats{display:flex;gap:2.5rem;flex-wrap:wrap;justify-content:center;animation:fadeDown 1s ease-out .6s both}
.hero-stat{text-align:center}
.hero-stat .num{font-family:'Playfair Display',serif;font-size:clamp(2.4rem,9vw,3.5rem);font-weight:900;color:var(--amber);display:block;line-height:1}
.hero-stat .lbl{font-family:'IBM Plex Mono',monospace;font-size:.65rem;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);margin-top:.3rem}
.next-rehearsal{margin-top:2.5rem;font-family:'IBM Plex Mono',monospace;font-size:.7rem;letter-spacing:.15em;color:var(--cream2);padding:.6em 1.4em;border:1px solid rgba(232,168,73,.2);border-radius:3px;animation:fadeDown 1s ease-out .8s both}
.next-rehearsal strong{color:var(--amber);font-weight:500}
.scroll-hint{position:absolute;bottom:2rem;font-family:'IBM Plex Mono',monospace;font-size:.65rem;letter-spacing:.2em;color:var(--dim);text-transform:uppercase;animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:.3;transform:translateY(0)}50%{opacity:.8;transform:translateY(5px)}}
@keyframes fadeDown{from{opacity:0;transform:translateY(-20px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeIn{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:translateY(0)}}

/* NAV */
.nav{position:sticky;top:0;z-index:100;background:rgba(10,10,15,.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:.8rem 1.25rem;display:flex;align-items:center;justify-content:space-between;font-family:'IBM Plex Mono',monospace;font-size:.7rem}
.nav-brand{color:var(--amber);font-weight:500;letter-spacing:.15em;text-transform:uppercase}
.nav-links{display:flex;gap:1.5rem}
.nav-links a{color:var(--dim);text-decoration:none;letter-spacing:.1em;text-transform:uppercase;transition:color .3s}
.nav-links a:hover{color:var(--amber)}

/* SECTIONS */
section{padding:4rem 1.25rem;max-width:1100px;margin:0 auto}
.section-title{font-family:'Playfair Display',serif;font-size:clamp(2rem,5vw,3.5rem);font-weight:900;margin-bottom:.5rem;color:var(--cream)}
.section-sub{font-family:'IBM Plex Mono',monospace;font-size:.7rem;letter-spacing:.25em;text-transform:uppercase;color:var(--amber);margin-bottom:2.5rem}

/* FILTER BAR */
.filter-bar{display:flex;gap:.8rem;flex-wrap:wrap;margin-bottom:2rem}
.filter-btn{font-family:'IBM Plex Mono',monospace;font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;padding:.7em 1.1em;min-height:38px;border:1px solid var(--border);background:transparent;color:var(--dim);border-radius:3px;cursor:pointer;transition:all .3s;-webkit-tap-highlight-color:transparent}
.filter-btn:hover,.filter-btn.active{border-color:var(--amber);color:var(--amber);background:rgba(232,168,73,.08)}
.sort-bar{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin-bottom:1.5rem;font-family:'IBM Plex Mono',monospace;font-size:.65rem;letter-spacing:.1em;color:var(--dim);text-transform:uppercase}
.sort-bar .sort-label{margin-right:.3rem}

/* SONG CARDS (Repertorio) */
.song-card{background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:1rem;overflow:hidden;transition:border-color .3s;opacity:0;animation:fadeIn .5s ease-out forwards}
.song-card:hover{border-color:rgba(232,168,73,.3)}
.song-head{display:flex;align-items:center;gap:1rem;padding:1.1rem 1.4rem;cursor:pointer;user-select:none;position:relative;-webkit-tap-highlight-color:rgba(232,168,73,.1);min-height:64px}
.song-info{flex:1;min-width:0}
.song-title{font-family:'Playfair Display',serif;font-size:1.2rem;font-weight:700;color:var(--cream);line-height:1.2;word-break:break-word}
.song-artist{font-family:'IBM Plex Mono',monospace;font-size:.65rem;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-top:.25rem}
.song-pct{font-family:'IBM Plex Mono',monospace;font-size:.95rem;font-weight:500;padding:.25em .65em;border-radius:3px;flex-shrink:0;min-width:3.2em;text-align:center}
.pct-ok{background:rgba(125,184,122,.15);color:var(--ok)}
.pct-warn{background:rgba(232,168,73,.15);color:var(--warn)}
.pct-low{background:rgba(212,106,106,.15);color:var(--low)}
.pct-na{background:rgba(107,101,128,.15);color:var(--dim)}
.song-section-badge{font-family:'IBM Plex Mono',monospace;font-size:.55rem;letter-spacing:.15em;text-transform:uppercase;color:var(--purple);border:1px solid rgba(155,126,207,.3);padding:.15em .55em;border-radius:2px;flex-shrink:0}
.badge-banda{color:var(--amber);border-color:rgba(232,168,73,.3)}
.badge-acusticas{color:var(--teal);border-color:rgba(94,168,160,.3)}
.badge-unirock{color:var(--rose);border-color:rgba(199,114,126,.3)}
.song-toggle{font-family:'IBM Plex Mono',monospace;font-size:1.2rem;color:var(--dim);transition:transform .3s;flex-shrink:0}
.song-toggle.open{transform:rotate(45deg)}
.song-progress{position:absolute;bottom:0;left:0;height:2px;transition:width 1s cubic-bezier(.22,1,.36,1)}
.song-body{max-height:0;overflow:hidden;transition:max-height .5s cubic-bezier(.22,1,.36,1);background:rgba(10,10,15,.4)}
.song-body.open{max-height:1000px}
.song-body-inner{padding:.5rem 1.4rem 1.3rem}
.role-row{display:grid;grid-template-columns:auto 1fr auto;gap:.7rem;align-items:center;padding:.5rem 0;border-bottom:1px solid rgba(42,42,58,.5)}
.role-row:last-child{border-bottom:none}
.role-label{font-family:'IBM Plex Mono',monospace;font-size:.65rem;letter-spacing:.1em;text-transform:uppercase;color:var(--purple);display:flex;align-items:center;gap:.4rem;min-width:6.5rem}
.role-label .dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.role-musician{color:var(--cream2);font-size:.95rem}
.role-musician.empty{color:var(--dim);font-style:italic}
.role-pct{font-family:'IBM Plex Mono',monospace;font-size:.75rem;color:var(--dim);min-width:3rem;text-align:right}

/* MUSICIAN CARDS */
.musician-card{background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:1.2rem;overflow:hidden;transition:border-color .3s,transform .3s;opacity:0;animation:fadeIn .6s ease-out forwards}
.musician-card:hover{border-color:rgba(232,168,73,.3)}
.musician-card.inactive{opacity:.5}
.musician-card.inactive:hover{opacity:1}
.mc-head{display:flex;align-items:center;gap:.9rem;padding:1.1rem 1.4rem;cursor:pointer;user-select:none;-webkit-tap-highlight-color:rgba(232,168,73,.1);min-height:62px}
.mc-name{font-family:'Playfair Display',serif;font-size:1.35rem;font-weight:700;color:var(--cream);flex:1;min-width:0;word-break:break-word;line-height:1.15}
.mc-meta{display:flex;gap:.5rem;align-items:center;flex-shrink:0}
.mc-count{font-family:'IBM Plex Mono',monospace;font-size:.75rem;font-weight:500;color:var(--bg);background:var(--amber);padding:.2em .65em;border-radius:3px;min-width:1.8em;text-align:center}
.mc-attendance{font-family:'IBM Plex Mono',monospace;font-size:.65rem;color:var(--dim);letter-spacing:.05em}
.mc-toggle{font-family:'IBM Plex Mono',monospace;font-size:1.15rem;color:var(--dim);transition:transform .3s}
.mc-toggle.open{transform:rotate(45deg)}
.mc-body{max-height:0;overflow:hidden;transition:max-height .5s cubic-bezier(.22,1,.36,1)}
.mc-body.open{max-height:3000px}
.mc-body-inner{padding:0 1.4rem 1.3rem}
.mc-block{margin-bottom:1.1rem}
.mc-block:last-child{margin-bottom:0}
.mc-block-label{font-family:'IBM Plex Mono',monospace;font-size:.6rem;letter-spacing:.2em;text-transform:uppercase;color:var(--amber);margin-bottom:.5rem}
.mc-chips{display:flex;flex-wrap:wrap;gap:.4rem}
.mc-chip{font-family:'IBM Plex Mono',monospace;font-size:.65rem;letter-spacing:.05em;color:var(--cream2);background:rgba(232,168,73,.05);border:1px solid rgba(232,168,73,.15);padding:.3em .7em;border-radius:2px}
.mc-role-block{margin-bottom:.8rem}
.mc-role-label{font-family:'IBM Plex Mono',monospace;font-size:.65rem;letter-spacing:.12em;text-transform:uppercase;color:var(--purple);margin-bottom:.3rem;display:flex;align-items:center;gap:.4rem}
.mc-role-label .dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.mc-song-line{padding:.3rem 0 .3rem .9rem;border-left:1px solid var(--border);font-size:.92rem;color:var(--cream2);margin-left:.2rem;display:flex;justify-content:space-between;gap:.7rem;align-items:baseline}
.mc-song-line .artist{color:var(--dim);font-size:.78rem;font-family:'IBM Plex Mono',monospace}
.mc-song-pct{font-family:'IBM Plex Mono',monospace;font-size:.7rem;flex-shrink:0;color:var(--dim)}
.mc-attendance-bar{display:flex;gap:.7rem;align-items:center;font-family:'IBM Plex Mono',monospace;font-size:.7rem;color:var(--cream2)}
.mc-attendance-bar .bar{flex:1;height:6px;background:var(--bg3);border-radius:3px;overflow:hidden;max-width:200px}
.mc-attendance-bar .bar .fill{height:100%;background:linear-gradient(90deg,var(--gold),var(--amber));border-radius:3px;transition:width 1s ease}

/* INSTRUMENT DOTS */
.dot.voces{background:var(--rose)}
.dot.guitarra{background:var(--amber)}
.dot.bajo{background:var(--teal)}
.dot.teclado{background:var(--blue)}
.dot.bateria{background:var(--red)}
.dot.violin{background:var(--green)}
.dot.armonica{background:var(--purple)}

/* ENSAYOS */
.ensayo-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.8rem}
.ensayo-item{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:.9rem 1rem;transition:all .3s;position:relative}
.ensayo-item.past{opacity:.35}
.ensayo-item.next{border-color:var(--amber);box-shadow:0 0 0 1px rgba(232,168,73,.3);background:linear-gradient(135deg,rgba(232,168,73,.08),var(--card))}
.ensayo-day{font-family:'IBM Plex Mono',monospace;font-size:.6rem;letter-spacing:.2em;text-transform:uppercase;color:var(--dim)}
.ensayo-item.next .ensayo-day{color:var(--amber)}
.ensayo-date{font-family:'Playfair Display',serif;font-size:1.8rem;font-weight:700;color:var(--cream);line-height:1;margin:.3rem 0}
.ensayo-month{font-family:'IBM Plex Mono',monospace;font-size:.65rem;letter-spacing:.15em;text-transform:uppercase;color:var(--cream2)}
.ensayo-label{font-family:'IBM Plex Mono',monospace;font-size:.55rem;letter-spacing:.15em;text-transform:uppercase;color:var(--dim);margin-top:.5rem}
.ensayo-item.next .ensayo-label{color:var(--amber)}
.ensayo-next-badge{position:absolute;top:-7px;right:8px;font-family:'IBM Plex Mono',monospace;font-size:.5rem;letter-spacing:.2em;text-transform:uppercase;background:var(--amber);color:var(--bg);padding:.15em .55em;border-radius:2px;font-weight:500}

/* FOOTER */
.footer{text-align:center;padding:4rem 1.25rem 2rem;font-family:'IBM Plex Mono',monospace;font-size:.65rem;color:var(--dim);letter-spacing:.1em}
.footer .logo{font-family:'Playfair Display',serif;font-size:1.2rem;color:var(--amber);margin-bottom:.5rem}

/* RESPONSIVE */
@media(max-width:700px){
  .hero{padding:1.5rem 1rem}
  .hero-badge{font-size:.65rem;padding:.45em 1.2em;margin-bottom:1.5rem}
  .hero-sub{margin-bottom:2rem;padding:0 .5rem}
  .hero-stats{gap:1.3rem}
  .hero-stat .lbl{font-size:.6rem}
  .next-rehearsal{font-size:.65rem;letter-spacing:.1em}
  .nav{padding:.7rem 1rem;font-size:.65rem}
  .nav-links{display:none}
  section{padding:3rem 1rem}
  .section-sub{margin-bottom:2rem}
  .filter-bar{gap:.5rem;flex-wrap:nowrap;overflow-x:auto;margin:0 -1rem 1.5rem;padding:0 1rem .5rem;scrollbar-width:none;-webkit-overflow-scrolling:touch}
  .filter-bar::-webkit-scrollbar{display:none}
  .filter-btn{flex-shrink:0}
  .sort-bar{font-size:.6rem}
  .song-head{padding:1rem;gap:.7rem;min-height:60px}
  .song-title{font-size:1.05rem}
  .song-artist{font-size:.58rem}
  .song-pct{font-size:.85rem;min-width:2.9em}
  .song-section-badge{font-size:.5rem;display:none}
  .song-body-inner{padding:.4rem 1rem 1rem}
  .role-row{grid-template-columns:auto 1fr auto;gap:.6rem;padding:.45rem 0}
  .role-label{min-width:5rem;font-size:.6rem}
  .role-musician{font-size:.88rem}
  .mc-head{padding:1rem;gap:.7rem}
  .mc-name{font-size:1.15rem}
  .mc-count{font-size:.7rem}
  .mc-attendance{display:none}
  .mc-body-inner{padding:0 1rem 1rem}
  .mc-song-line{font-size:.88rem;padding:.3rem 0 .3rem .7rem}
  .mc-song-line .artist{font-size:.7rem}
  .ensayo-grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:.6rem}
  .ensayo-date{font-size:1.5rem}
  .footer{padding:3rem 1rem 2rem}
}
@media(max-width:380px){
  .hero h1{font-size:2.2rem}
  .hero-stats{gap:.9rem}
  .hero-stat .num{font-size:2.1rem}
  .song-title{font-size:1rem}
  .mc-name{font-size:1.1rem}
  .ensayo-grid{grid-template-columns:repeat(2,1fr)}
}
</style>
</head>
<body>

<div class="hero">
  <div class="hero-badge">Semestre I · 2026</div>
  <h1>Repertorio<br><em>UPB</em></h1>
  <p class="hero-sub">Grupo de música · canciones, músicos y avance del semestre</p>
  <div class="hero-stats">
    <div class="hero-stat"><span class="num" id="kpi-musicians">__M__</span><span class="lbl">Músicos activos</span></div>
    <div class="hero-stat"><span class="num" id="kpi-songs">__S__</span><span class="lbl">Canciones</span></div>
    <div class="hero-stat"><span class="num" id="kpi-avg">__A__%</span><span class="lbl">Avance medio</span></div>
  </div>
  <div class="scroll-hint">↓ scroll ↓</div>
</div>

<nav class="nav">
  <div class="nav-brand">UPB Música</div>
  <div class="nav-links">
    <a href="#repertorio">Repertorio</a>
    <a href="#musicos">Músicos</a>
    <a href="#eventos">Eventos</a>
  </div>
</nav>

<section id="repertorio">
  <div class="section-title">Repertorio</div>
  <div class="section-sub">38 canciones · % de avance por rol</div>
  <div class="filter-bar" id="song-filters">
    <button class="filter-btn" data-filter="banda">Banda</button>
    <button class="filter-btn" data-filter="acusticas">Acústicas</button>
  </div>
  <div class="sort-bar" id="song-sort">
    <span class="sort-label">Avance:</span>
    <button class="filter-btn active" data-sort="pct-desc">Más avanzadas</button>
    <button class="filter-btn" data-sort="pct-asc">Menos avanzadas</button>
  </div>
  <div id="songs-container"></div>
</section>

<section id="musicos">
  <div class="section-title">Músicos</div>
  <div class="section-sub">Asignaciones, instrumentos y asistencia · click para expandir</div>
  <div class="filter-bar" id="musician-filters">
    <button class="filter-btn active" data-filter="all">Todos</button>
    <button class="filter-btn" data-filter="voces">Voces</button>
    <button class="filter-btn" data-filter="guitarra">Guitarras</button>
    <button class="filter-btn" data-filter="bajo">Bajo</button>
    <button class="filter-btn" data-filter="teclado">Teclado</button>
    <button class="filter-btn" data-filter="bateria">Batería</button>
    <button class="filter-btn" data-filter="violin">Violín</button>
  </div>
  <div id="musicians-container"></div>
</section>

<section id="eventos">
  <div class="section-title">Eventos</div>
  <div class="section-sub">Setlists para presentaciones · click para expandir</div>
  <div id="eventos-container"></div>
</section>

<div class="footer">
  <div class="logo">♪ UPB</div>
  Universidad Privada Boliviana · Grupo de Música 2026-I
</div>

<script>
const DATA = __PAYLOAD__;

const ROLE_DOT = {"Voces":"voces","Voces 2":"voces","Guitarra 1":"guitarra","Guitarra 2":"guitarra","Guitarra 3":"guitarra","Bajo":"bajo","Teclado":"teclado","Batería":"bateria","Violín":"violin","Armónica":"armonica"};

function pctClass(p){
  if(p==null) return "pct-na";
  if(p>=70) return "pct-ok";
  if(p>=40) return "pct-warn";
  return "pct-low";
}
function pctColor(p){
  if(p==null) return "#6b6580";
  if(p>=70) return "#7db87a";
  if(p>=40) return "#e8a849";
  return "#d46a6a";
}
function pctLabel(p){ return p==null ? "—" : p + "%"; }

function roleCategory(role){
  const r = role.toLowerCase();
  if(r.includes("voces")||r.includes("voz")) return "voces";
  if(r.includes("guitarra")) return "guitarra";
  if(r==="bajo") return "bajo";
  if(r==="teclado") return "teclado";
  if(r==="batería"||r==="bateria") return "bateria";
  if(r==="violín"||r==="violin") return "violin";
  if(r==="armónica"||r==="armonica") return "armonica";
  return "all";
}

/* ---------- KPIs ---------- */
function renderKpis(){
  document.getElementById("kpi-musicians").textContent = DATA.kpis.musicians_active;
  document.getElementById("kpi-songs").textContent = DATA.kpis.songs_total;
  document.getElementById("kpi-avg").textContent = DATA.kpis.avg_global + "%";
}

/* ---------- SONGS ---------- */
let songFilter = "all";
let songSort = "pct-desc";

function renderSongs(){
  const c = document.getElementById("songs-container");
  c.innerHTML = "";
  let list = DATA.songs.slice();
  if(songFilter !== "all") list = list.filter(s => s.section === songFilter);
  if(songSort === "pct-desc") list.sort((a,b) => (b.global_pct ?? -1) - (a.global_pct ?? -1));
  else if(songSort === "pct-asc") list.sort((a,b) => (a.global_pct ?? 101) - (b.global_pct ?? 101));
  list.forEach((s, i) => {
    const card = document.createElement("div");
    card.className = "song-card";
    card.style.animationDelay = (i * 0.03) + "s";
    const pct = s.global_pct;
    const barW = pct == null ? 0 : pct;
    const barColor = pctColor(pct);
    const sectionClass = "badge-" + s.section;
    const sectionLabel = s.section_label;
    let rolesHtml = "";
    s.roles.forEach(r => {
      const dot = ROLE_DOT[r.role] || "voces";
      const name = r.musician_full || r.musician_display || "<span class='empty'>sin asignar</span>";
      rolesHtml += `<div class="role-row">
        <div class="role-label"><span class="dot ${dot}"></span>${r.role}</div>
        <div class="role-musician ${r.musician_display ? '' : 'empty'}">${name}</div>
        <div class="role-pct">${pctLabel(r.pct)}</div>
      </div>`;
    });
    card.innerHTML = `<div class="song-head" onclick="toggleSong(this)">
      <div class="song-info">
        <div class="song-title">${s.cancion}</div>
        <div class="song-artist">${s.interprete}</div>
      </div>
      <span class="song-section-badge ${sectionClass}">${sectionLabel}</span>
      <div class="song-pct ${pctClass(pct)}">${pctLabel(pct)}</div>
      <div class="song-toggle">+</div>
      <div class="song-progress" style="width:${barW}%;background:${barColor}"></div>
    </div>
    <div class="song-body"><div class="song-body-inner">${rolesHtml}</div></div>`;
    c.appendChild(card);
  });
}

function toggleSong(h){
  const b = h.nextElementSibling;
  const t = h.querySelector(".song-toggle");
  b.classList.toggle("open");
  t.classList.toggle("open");
}

document.querySelectorAll("#song-filters .filter-btn").forEach(b => {
  b.addEventListener("click", () => {
    if(b.classList.contains("active")){
      b.classList.remove("active");
      songFilter = "all";
    } else {
      document.querySelectorAll("#song-filters .filter-btn").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      songFilter = b.dataset.filter;
    }
    renderSongs();
  });
});

document.querySelectorAll("#song-sort .filter-btn").forEach(b => {
  b.addEventListener("click", () => {
    document.querySelectorAll("#song-sort .filter-btn").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    songSort = b.dataset.sort;
    renderSongs();
  });
});

/* ---------- MUSICIANS ---------- */
let musicianFilter = "all";

function renderMusicians(){
  const c = document.getElementById("musicians-container");
  c.innerHTML = "";
  // ordenados: activos primero (count desc), luego inactivos al fondo
  const list = DATA.roster.filter(m => m.count > 0);
  list.forEach((m, i) => {
    if(musicianFilter !== "all" && !Object.keys(m.songs_by_role).some(r => roleCategory(r) === musicianFilter)) return;
    const card = document.createElement("div");
    card.className = "musician-card" + (m.count === 0 ? " inactive" : "");
    card.style.animationDelay = (i * 0.03) + "s";
    const attPct = m.total > 0 ? Math.round((m.attended / m.total) * 100) : 0;
    let body = "";
    if(m.instruments_domain && m.instruments_domain.length){
      body += `<div class="mc-block"><div class="mc-block-label">Instrumentos</div><div class="mc-chips">${m.instruments_domain.map(i => `<span class="mc-chip">${i}</span>`).join("")}</div></div>`;
    }
    if(m.total > 0){
      body += `<div class="mc-block"><div class="mc-block-label">Asistencia a ensayos</div><div class="mc-attendance-bar"><span><strong style="color:var(--cream)">${m.attended}</strong>/${m.total}</span><div class="bar"><div class="fill" style="width:${attPct}%"></div></div><span>${attPct}%</span></div></div>`;
    }
    if(Object.keys(m.songs_by_role).length){
      body += `<div class="mc-block"><div class="mc-block-label">Asignaciones (${m.count})</div>`;
      Object.entries(m.songs_by_role).forEach(([role, songs]) => {
        if(musicianFilter !== "all" && roleCategory(role) !== musicianFilter) return;
        const dot = ROLE_DOT[role] || "voces";
        body += `<div class="mc-role-block"><div class="mc-role-label"><span class="dot ${dot}"></span>${role} (${songs.length})</div>`;
        songs.forEach(s => {
          body += `<div class="mc-song-line"><span>${s.cancion}<span class="artist"> · ${s.interprete}</span></span><span class="mc-song-pct ${pctClass(s.pct)}" style="padding:.05em .35em;border-radius:2px">${pctLabel(s.pct)}</span></div>`;
        });
        body += `</div>`;
      });
      body += `</div>`;
    }
    if(!body){
      body = `<div class="mc-block"><div class="mc-block-label">Sin asignaciones</div><p style="color:var(--dim);font-size:.85rem">Este músico aún no tiene canciones asignadas en el repertorio.</p></div>`;
    }
    card.innerHTML = `<div class="mc-head" onclick="toggleMusician(this)">
      <div class="mc-name">${m.full}</div>
      <div class="mc-meta">
        <span class="mc-attendance">${m.attended}/${m.total}</span>
        <span class="mc-count">${m.count}</span>
      </div>
      <div class="mc-toggle">+</div>
    </div>
    <div class="mc-body"><div class="mc-body-inner">${body}</div></div>`;
    c.appendChild(card);
  });
}

function toggleMusician(h){
  const b = h.nextElementSibling;
  const t = h.querySelector(".mc-toggle");
  b.classList.toggle("open");
  t.classList.toggle("open");
}

document.querySelectorAll("#musician-filters .filter-btn").forEach(b => {
  b.addEventListener("click", () => {
    document.querySelectorAll("#musician-filters .filter-btn").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    musicianFilter = b.dataset.filter;
    renderMusicians();
  });
});

/* ---------- EVENTOS ---------- */
function renderEventos(){
  const c = document.getElementById("eventos-container");
  c.innerHTML = "";
  DATA.eventos.forEach((ev, eIdx) => {
    const header = document.createElement("div");
    header.style.cssText = "font-family:'IBM Plex Mono',monospace;font-size:.75rem;letter-spacing:.2em;text-transform:uppercase;color:var(--amber);margin:" + (eIdx > 0 ? "2.5rem 0 1rem" : "0 0 1.2rem") + ";display:flex;align-items:baseline;gap:.8rem;flex-wrap:wrap";
    const avgLbl = ev.avg_pct == null ? "—" : ev.avg_pct + "%";
    header.innerHTML = `<span style="font-family:'Playfair Display',serif;font-size:1.4rem;font-weight:700;color:var(--cream);letter-spacing:0;text-transform:none">${ev.name}</span><span style="color:var(--dim)">${ev.songs.length} canciones · promedio <span style="color:var(--cream2)">${avgLbl}</span></span>`;
    c.appendChild(header);
    const sorted = ev.songs.slice().sort((a,b) => (b.global_pct ?? -1) - (a.global_pct ?? -1));
    sorted.forEach((s, i) => {
      const card = document.createElement("div");
      card.className = "song-card";
      card.style.animationDelay = (i * 0.03) + "s";
      const pct = s.global_pct;
      const barW = pct == null ? 0 : pct;
      const barColor = pctColor(pct);
      let rolesHtml = "";
      s.roles.forEach(r => {
        const dot = ROLE_DOT[r.role] || "voces";
        const name = r.musician_full || r.musician_display || "<span class='empty'>sin asignar</span>";
        rolesHtml += `<div class="role-row">
          <div class="role-label"><span class="dot ${dot}"></span>${r.role}</div>
          <div class="role-musician ${r.musician_display ? '' : 'empty'}">${name}</div>
          <div class="role-pct">${pctLabel(r.pct)}</div>
        </div>`;
      });
      card.innerHTML = `<div class="song-head" onclick="toggleSong(this)">
        <div class="song-info">
          <div class="song-title">${s.cancion}</div>
          <div class="song-artist">${s.interprete}</div>
        </div>
        <div class="song-pct ${pctClass(pct)}">${pctLabel(pct)}</div>
        <div class="song-toggle">+</div>
        <div class="song-progress" style="width:${barW}%;background:${barColor}"></div>
      </div>
      <div class="song-body"><div class="song-body-inner">${rolesHtml}</div></div>`;
      c.appendChild(card);
    });
  });
}

renderKpis();
renderSongs();
renderMusicians();
renderEventos();
</script>
</body>
</html>
"""

def render_html(payload):
    return HTML.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))

def build(base_dir, out_paths=None, verbose=False):
    """Lee upb_data.json desde base_dir, genera HTML y lo escribe a cada path de out_paths."""
    with open(os.path.join(base_dir, "upb_data.json"), encoding="utf-8") as f:
        raw = json.load(f)
    payload = compute_payload(raw)
    html = render_html(payload)
    if out_paths:
        for p in out_paths:
            os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
            with open(p, "w", encoding="utf-8") as f:
                f.write(html)
            if verbose:
                print(f"Wrote {p}  ({len(html)} bytes)")
    if verbose:
        print(f"KPIs: {payload['kpis']}")
    return html

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    build(
        DEFAULT_BASE,
        out_paths=[DEFAULT_OUT, os.path.join(DEFAULT_BASE, "_deploy", "index.html")],
        verbose=True,
    )
