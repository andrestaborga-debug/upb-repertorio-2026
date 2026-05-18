"""Extrae datos de los 3 Excel UPB y genera upb_data.json para el sitio."""
import zipfile, os, re, sys, io, json
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
DEFAULT_BASE = r"C:\Users\andre\OneDrive\Escritorio\CLAUDE\LUIGI"

def col_to_idx(c):
    n = 0
    for ch in c:
        n = n*26 + (ord(ch)-ord("A")+1)
    return n-1

def serial_to_date(n):
    try:
        return datetime(1899,12,30) + timedelta(days=int(float(n)))
    except Exception:
        return None

def read_xlsx(path):
    with zipfile.ZipFile(path) as z:
        ss = []
        if "xl/sharedStrings.xml" in z.namelist():
            tree = ET.parse(z.open("xl/sharedStrings.xml"))
            for si in tree.getroot().findall("x:si", NS):
                txt = "".join(t.text or "" for t in si.iter("{%s}t" % NS["x"]))
                ss.append(txt)
        wbtree = ET.parse(z.open("xl/workbook.xml"))
        sheets = []
        for s in wbtree.getroot().find("x:sheets", NS).findall("x:sheet", NS):
            sheets.append((s.attrib["name"], s.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]))
        rels = ET.parse(z.open("xl/_rels/workbook.xml.rels"))
        rmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels.getroot()}
        result = []
        for name, rid in sheets:
            target = rmap[rid]
            if not target.startswith("xl/"):
                target = "xl/" + target
            stree = ET.parse(z.open(target))
            rows = {}
            for row in stree.getroot().iter("{%s}row" % NS["x"]):
                rdata = {}
                for c in row.findall("x:c", NS):
                    ref = c.attrib.get("r","")
                    ci = col_to_idx(re.match(r"[A-Z]+", ref).group(0))
                    t = c.attrib.get("t")
                    v = c.find("x:v", NS)
                    if v is None:
                        is_node = c.find("x:is", NS)
                        val = "".join(tn.text or "" for tn in is_node.iter("{%s}t" % NS["x"])) if is_node is not None else ""
                    elif t == "s":
                        val = ss[int(v.text)]
                    else:
                        val = v.text
                    rdata[ci] = val
                if rdata:
                    rows[int(row.attrib["r"])] = rdata
            result.append((name, rows))
        return result

def cell(row, idx, default=""):
    v = row.get(idx, default)
    return v if v is not None else default

def clean(s):
    return (s or "").strip()

# ---------- NORMALIZACIÓN DE NOMBRES ----------
NAME_FIXES = {
    "Fenanda H": "Fernanda H",
    "Benardo": "Bernardo",
    "Jeffry": "Jeffrey",
    "Ale  Y": "Ale Y",
    "Ale Y": "Ale Y",
    "Natalia C": "Natalia C",
}

# nickname -> nombre completo (derivado del Excel Lista)
NICK_TO_FULL = {
    "Andy": "Andy Velarde",
    "Anibal": "Anibal Mariaca",
    "Tomy": "Tomás Villanueva",
    "Natalia": "Natalia Maldonado",
    "Natalia C": "Natalia Castro",
    "Karina": "Karina Morales",
    "Vale": "Valentina Camacho",
    "Sebastián": "Sebastián Dávalos",
    "Ale": "Alejandro Burgoa",
    "Fernanda H": "Fernanda Humerez",
    "Ale Y": "Alejandro Yáñez",
    "Mariana": "Mariana Villarroel",
    "Belen": "Belén Arce",
    "Belén": "Belén Arce",
    "Lucas": "Lucas Vargas",
    "Jessica": "Jessica Bolívar",
    "Aleshka": "Aleshka Garvizu",
    "Caleb": "Caleb Astulla",
    "Bernardo": "Bernardo Del Aguila",
    "Camila Ramos": "Camila Ramos",
    "Jennifer": "Jennifer Gutiérrez",
    "Erik": "Erik Rendón",
    "Mateo": "Mateo Moya",
    "Fernando": "Fernando Yugar",
    "Adrián": "Adrián Peredo",
    "Jasmine": "Jasmine Juliano",
    "Silvana": "Silvana López",
    "Gary": "Gari Mamani",
    "Fátima": "Fátima Burgoa",
    "Alira": "Alira Miranda",
    "Tiani": "Tiani Magalhaes",
    "Fabiana Rojas": "Fabiana Rojas",
    "Jeffrey": "Jeffrey Pardo",
    "Nico": "Nico Cueto",
    "Secuencias": None,  # ignorar
}

def normalize_name(raw):
    s = clean(raw)
    if not s or s.upper() == "NO":
        return None
    s = NAME_FIXES.get(s, s)
    return s

# ---------- 1. CRONOGRAMA: extraer ensayos ----------
def extract_rehearsals(base_dir):
    path = os.path.join(base_dir, "Cronograma de ensayos UPB.xlsx")
    sheets = read_xlsx(path)
    _, rows = sheets[0]
    # estructura: bloques de 4 filas (mes-label, día semana, fecha, evento)
    # las fechas (R3,R7,R11,R15,R19) y eventos (R4,R8,R12,R16,R20) intercalados
    date_event_pairs = [(3,4),(7,8),(11,12),(15,16),(17,17),(19,20),(21,21)]
    rehearsals = []
    for date_row, event_row in date_event_pairs:
        dr = rows.get(date_row, {})
        er = rows.get(event_row, {})
        for ci, val in dr.items():
            dt = serial_to_date(val)
            if dt is None:
                continue
            event = clean(er.get(ci, ""))
            if event.lower() == "ensayo" or event.lower() == "ensayo sala":
                rehearsals.append({"date": dt.strftime("%Y-%m-%d"), "label": event})
    rehearsals.sort(key=lambda x: x["date"])
    return rehearsals

# ---------- 2. LISTA: instrumentos y asistencia por músico ----------
def extract_musicians(base_dir):
    path = os.path.join(base_dir, "UPB Lista 2026.xlsx")
    sheets = read_xlsx(path)
    _, rows = sheets[0]
    # encabezado en R1 (días) y R2 (etiquetas + fechas)
    header2 = rows.get(2, {})
    # columnas de fecha = donde header2 tiene un serial numérico
    date_cols = []
    for ci, val in header2.items():
        dt = serial_to_date(val)
        if dt and ci > 10:
            date_cols.append((ci, dt))
    musicians = []
    for rnum in sorted(rows.keys()):
        if rnum < 3:
            continue
        r = rows[rnum]
        full = clean(cell(r, 4))
        if not full:
            continue
        # instrumentos: columnas 5-9
        instruments = [clean(cell(r, c)) for c in range(5, 10)]
        instruments = [i for i in instruments if i]
        # repertorio personal: columnas 10-12
        repertoire = [clean(cell(r, c)) for c in range(10, 13)]
        repertoire = [i for i in repertoire if i]
        # asistencia
        attended = 0
        for ci, _ in date_cols:
            v = cell(r, ci)
            if str(v).strip() == "1":
                attended += 1
        total = len(date_cols)
        musicians.append({
            "full_name": full,
            "instruments_domain": instruments,
            "personal_repertoire": repertoire,
            "rehearsals_attended": attended,
            "rehearsals_total": total,
        })
    return musicians

# ---------- 3. REPERTORIO: canciones con % y roles ----------
ROLE_LAYOUT = [
    # (col_pct, col_name, role_label)
    (4, 5, "Voces"),
    (6, 7, "Voces 2"),
    (8, 9, "Guitarra 1"),
    (10, 11, "Guitarra 2"),
    (12, 13, "Guitarra 3"),
    (14, 15, "Bajo"),
    (16, 17, "Teclado"),
    (18, 19, "Armónica"),
    (20, 21, "Violín"),
    (22, 23, "Batería"),
]

def parse_song_row(r):
    interprete = clean(cell(r, 1))
    cancion = clean(cell(r, 2))
    if not interprete and not cancion:
        return None
    if interprete.upper() in ("BANDA", "ACÚSTICAS") and not cancion:
        return None
    roles = []
    for pct_col, name_col, label in ROLE_LAYOUT:
        name_raw = clean(cell(r, name_col))
        pct_raw = clean(cell(r, pct_col))
        if not name_raw and not pct_raw:
            continue
        name = normalize_name(name_raw)
        if name is None and pct_raw == "":
            continue
        # interpretar pct
        pct = None
        if pct_raw and pct_raw.upper() != "NO":
            try:
                pct = int(round(float(pct_raw)))
            except Exception:
                pct = None
        roles.append({"role": label, "musician": name, "pct": pct, "raw": name_raw})
    # % global = última columna 25 (col idx 24 final). El layout pone % global en col 24 (después del nombre de Batería)... revisemos: row idx 24 columnas... el dump muestra " | 32" al final => col idx 24 (la 25ª)
    global_pct_raw = clean(cell(r, 24))
    global_pct = None
    if global_pct_raw and global_pct_raw.upper() != "NO":
        try:
            global_pct = int(round(float(global_pct_raw)))
        except Exception:
            global_pct = None
    return {"interprete": interprete, "cancion": cancion, "roles": roles, "global_pct": global_pct}

def extract_songs(base_dir):
    path = os.path.join(base_dir, "UPB Repertorio 2026 DEF.xlsx")
    sheets = read_xlsx(path)
    repertorio = dict(sheets)["Repertorio"]
    unirock = dict(sheets)["Unirock"]
    # secciones en Repertorio: rows 5-32 = BANDA, rows 33-46 = ACÚSTICAS
    banda = []
    acusticas = []
    section = None
    for rnum in sorted(repertorio.keys()):
        r = repertorio[rnum]
        label = clean(cell(r, 1))
        if label == "BANDA":
            section = "banda"
            continue
        if label == "ACÚSTICAS":
            section = "acusticas"
            continue
        # skip headers
        if cell(r, 0) == "#" or clean(cell(r, 0)).lower() == "#":
            continue
        song = parse_song_row(r)
        if song and song["cancion"]:
            (banda if section == "banda" else acusticas).append(song)
    # Unirock setlist
    unirock_songs = []
    for rnum in sorted(unirock.keys()):
        r = unirock[rnum]
        if rnum < 3:
            continue
        if rnum > 9:  # filas 11+ son minicalendario
            break
        song = parse_song_row(r)
        if song and song["cancion"]:
            unirock_songs.append(song)
    return {"banda": banda, "acusticas": acusticas, "unirock": unirock_songs}

# ---------- 4. PIPELINE ----------
def all_song_assignments(songs):
    out = {}  # display_name -> list of (section, song, role, pct)
    for section, slist in [("banda", songs["banda"]), ("acústicas", songs["acusticas"])]:
        for s in slist:
            for r in s["roles"]:
                if r["musician"]:
                    out.setdefault(r["musician"], []).append({
                        "section": section,
                        "cancion": s["cancion"],
                        "interprete": s["interprete"],
                        "role": r["role"],
                        "pct": r["pct"],
                    })
    return out

def build(base_dir, write_json=True, verbose=False):
    rehearsals = extract_rehearsals(base_dir)
    musicians = extract_musicians(base_dir)
    songs = extract_songs(base_dir)
    assignments = all_song_assignments(songs)
    data = {
        "rehearsals": rehearsals,
        "musicians_raw": musicians,
        "songs": songs,
        "assignments": assignments,
        "nick_to_full": NICK_TO_FULL,
    }
    if write_json:
        out_path = os.path.join(base_dir, "upb_data.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"Wrote {out_path}")
            print(f"Rehearsals: {len(rehearsals)} | Musicians: {len(musicians)}")
            print(f"Songs banda: {len(songs['banda'])} | acústicas: {len(songs['acusticas'])} | unirock: {len(songs['unirock'])}")
            print(f"Assignments: {len(assignments)}")
    return data

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    build(DEFAULT_BASE, verbose=True)
