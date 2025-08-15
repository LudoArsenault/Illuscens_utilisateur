# monitor_simple.py
import re
import time
import io
import webbrowser
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
import requests
from dash import Dash, dcc, html, Output, Input, State, no_update
import plotly.graph_objs as go

# ------------------ CONFIG (simple & rapide) ------------------
SERVER_ROOT_URLS = [
    "http://172.20.202.52:8080",
    "http://172.20.206.103:8080",
    "http://172.20.202.182:8080",
]

# Colonnes à tracer
TEMP_COLS = ["Target_T", "Sheath_T", "Chamber_top_T", "Mobile_T"]
HUMI_COLS = ["Target_RH", "Sheath_RH", "Chamber_top_RH", "Mobile_RH"]

# Rafraîchissement du graphique
REFRESH_MS = 60_000  # 1 min
CONNECT_TIMEOUT = 1.5
READ_TIMEOUT = 6.0

# Fenêtre d’affichage (mettre None pour tout afficher)
PLOT_WINDOW = "48h"   # ex: "24H", "48H" ou None

# ------------------ Détection du dernier fichier (par nom) ------------------
# Ex: 2025-8-5_11h41m45s
FILENAME_TS_PATTERNS = [
    r'(\d{4})-(\d{1,2})-(\d{1,2})_([0-9]{1,2})h([0-9]{1,2})m([0-9]{1,2})s'
]

def ts_from_name(name: str):
    for pat in FILENAME_TS_PATTERNS:
        m = re.search(pat, name)
        if m:
            y, mo, d, h, mi, s = (int(x) for x in m.groups())
            return datetime(y, mo, d, h, mi, s)
    return None

CSV_HREF_RE = re.compile(r'href="([^"]+\.csv)"', re.IGNORECASE)

def list_csvs_fast(root: str, limit: int = 400):
    """1 GET + regex → liste des CSV (basenames). Rapide."""
    try:
        r = requests.get(root, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r.raise_for_status()
        hrefs = CSV_HREF_RE.findall(r.text)
        names = [h.split("/")[-1] for h in hrefs]
        if len(names) > limit:
            names = names[-limit:]
        return names
    except Exception:
        return []

def get_latest_csv_filename_fast():
    """Retourne le nom du CSV le plus récent selon la date dans le nom (fallback lexicographique)."""
    best_name, best_dt, lex_fallback = None, None, None
    for root in SERVER_ROOT_URLS:
        names = list_csvs_fast(root)
        if not names:
            continue

        # fallback lexicographique au cas où
        local_lex = max(names)
        if (lex_fallback is None) or (local_lex > lex_fallback):
            lex_fallback = local_lex

        for n in names:
            dt = ts_from_name(n)
            if dt is None:
                continue
            if (best_dt is None) or (dt > best_dt):
                best_dt, best_name = dt, n

        if best_name is not None:
            break

    if best_name:
        return best_name
    if lex_fallback:
        return lex_fallback
    raise RuntimeError("Aucun fichier CSV trouvé sur les serveurs.")

# ------------------ Récupération du CSV ------------------
def fetch_csv_first_alive(filename):
    """Essaie chaque IP; renvoie (bytes, content_length, root) ou (None, None, err)."""
    last_err = None
    for root in SERVER_ROOT_URLS:
        url = urljoin(root, filename)
        try:
            resp = requests.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            resp.raise_for_status()
            content = resp.content
            clen = resp.headers.get("Content-Length")
            content_length = int(clen) if (clen and str(clen).isdigit()) else len(content)
            return content, content_length, root
        except Exception as e:
            last_err = e
            continue
    return None, None, last_err

# ------------------ Prétraitement minimal ------------------
def coerce_timestamp(df: pd.DataFrame, start_iso: str) -> pd.DataFrame:
    """Timestamp (secondes écoulées) → datetimes réels = start + secondes."""
    if "Timestamp" not in df.columns or not start_iso:
        return df
    try:
        start_dt = datetime.fromisoformat(start_iso)
    except Exception:
        return df
    df = df.copy()
    secs = pd.to_numeric(df["Timestamp"], errors="coerce")
    df["Timestamp"] = start_dt + pd.to_timedelta(secs, unit="s")
    return df

def preprocess(df: pd.DataFrame, start_iso: str) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    # Conversion du temps
    df = coerce_timestamp(df, start_iso)
    # Ne garder que l’essentiel
    keep = ["Timestamp"] + [c for c in (TEMP_COLS + HUMI_COLS) if c in df.columns]
    df = df[keep]

    # Fenêtre d’affichage optionnelle
    if PLOT_WINDOW and "Timestamp" in df.columns and pd.api.types.is_datetime64_any_dtype(df["Timestamp"]):
        cutoff = df["Timestamp"].max() - pd.Timedelta(PLOT_WINDOW)
        df = df[df["Timestamp"] >= cutoff]

    return df

# ------------------ Figures ------------------
def build_figs(df: pd.DataFrame):
    Trace = go.Scattergl  # rapide (WebGL)
    temp_fig, humi_fig = go.Figure(), go.Figure()

    if "Timestamp" in df.columns:
        for c in TEMP_COLS:
            if c in df.columns:
                temp_fig.add_trace(Trace(x=df["Timestamp"], y=df[c], mode="lines", name=c.replace("_", " ")))
        for c in HUMI_COLS:
            if c in df.columns:
                humi_fig.add_trace(Trace(x=df["Timestamp"], y=df[c], mode="lines", name=c.replace("_", " ")))

    for f, ylab, title in [
        (temp_fig, "°C", "Température"),
        (humi_fig, "RH (%)", "Humidité"),
    ]:
        f.update_layout(
            title={"text": title, "x": 0, "xanchor": "left"},
            xaxis_title="Temps",
            yaxis_title=ylab,
            hovermode="x unified",
            legend={"orientation": "v", "x": 1.05, "y": 1},
            margin=dict(l=50, r=20, t=50, b=40),
            uirevision="stay",
        )
    return temp_fig, humi_fig

# ------------------ Dash (minimal) ------------------
app = Dash(__name__)
app.title = "Climate Monitor (simple)"

app.layout = html.Div(
    style={"fontFamily": "system-ui, Arial, sans-serif", "padding": "14px", "maxWidth": "1400px", "margin": "0 auto"},
    children=[
        dcc.Store(id="filename-store"),
        dcc.Store(id="starttime-store"),
        html.H2("Illuscens — Température & Humidité (auto, dernier fichier)"),
        html.Div(id="status-bar", style={
            "padding": "10px 12px", "background": "#f4f6f8", "border": "1px solid #e1e5ea",
            "borderRadius": "10px", "marginBottom": "12px", "fontSize": "14px"
        }),
        dcc.Graph(id="temp-graph", config={"displaylogo": False}),
        dcc.Graph(id="humi-graph", config={"displaylogo": False}),
        dcc.Interval(id="refresh", interval=REFRESH_MS, n_intervals=0),
    ],
)

# 1) Détecter le fichier une seule fois au démarrage
@app.callback(
    Output("filename-store", "data"),
    Output("starttime-store", "data"),
    Input("refresh", "n_intervals"),
    State("filename-store", "data"),
    prevent_initial_call=False,
)
def discover_once(n, stored_filename):
    if stored_filename:
        return no_update, no_update
    try:
        filename = get_latest_csv_filename_fast()
        start_dt = ts_from_name(filename)
        return filename, (start_dt.isoformat() if start_dt else None)
    except Exception:
        return no_update, no_update

# 2) Rafraîchir les graphiques
@app.callback(
    Output("temp-graph", "figure"),
    Output("humi-graph", "figure"),
    Output("status-bar", "children"),
    Input("refresh", "n_intervals"),
    State("filename-store", "data"),
    State("starttime-store", "data"),
    prevent_initial_call=False,
)
def update_plots(n, filename, start_iso):
    if not filename:
        return go.Figure(), go.Figure(), "⏳ Recherche du dernier fichier…"

    # Télécharger depuis la 1re IP disponible
    content, content_length, origin = fetch_csv_first_alive(filename)
    if content is None:
        return go.Figure(), go.Figure(), "❌ Aucun serveur accessible."

    # Lire uniquement les colonnes utiles (plus rapide)
    wanted = {"Timestamp", *TEMP_COLS, *HUMI_COLS}
    df = pd.read_csv(io.BytesIO(content), usecols=lambda c: c.strip() in wanted)
    df = preprocess(df, start_iso)

    tfig, hfig = build_figs(df)
    status = f"🌐 Source: {origin} • Fichier: {filename} • Maj: {time.strftime('%H:%M:%S')}"
    return tfig, hfig, status

if __name__ == "__main__":
    webbrowser.open_new("http://127.0.0.1:8050/")
    app.run(debug=False)
