"""
Résumé
------
Application Dash pour *surveiller en direct* la température et l’humidité de la chambre à partir
des CSV servis par le Raspberry Pi (plusieurs IP possibles). Le script détecte automatiquement
le dernier fichier, récupère périodiquement les données et trace deux graphiques (Température & Humidité).

Utilisation
----------
1) Installer les dépendances (voir README).
2) Lancer :

   python monitor_data_live.py

3) Le navigateur s’ouvre sur http://127.0.0.1:8050/.
4) Optionnel : saisir un nom de fichier précis dans l’UI ou laisser la détection automatique.

Fonctionnalités
---------------
- Détection du fichier le plus récent (par timestamp dans le nom ou fallback lexicographique).
- Essai de téléchargement sur plusieurs IP (timeouts courts).
- Mise en cache locale du CSV (`./cached_data`).
- Fenêtre d’affichage glissante (par défaut 48 h) et *downsampling* paramétrable.
- Graphiques interactifs (Plotly) avec conservation du zoom entre rafraîchissements.

Entrées
-------
- CSV avec colonnes candidates pour le temps : `Timestamp`/`Time`/`Timestamps`.
- Colonnes tracées si présentes : Température (`Target_T`, `Sheath_T`, `Chamber_top_T`) et
  Humidité (`Target_RH`, `Sheath_RH`, `Chamber_top_RH`).

Sorties
-------
- Tableau de bord web local avec 2 graphes.
- Cache du dernier fichier sous `./cached_data/<nom>.csv`.

Notes
-----
- La colonne `Timestamp` (secondes écoulées) est convertie en datetimes réels à partir de l’heure
  de départ déduite du nom de fichier.
- Variables clés : `PLOT_WINDOW`, `RESAMPLE_RULE`, `REFRESH_MS`.
"""

# monitor_data_live.py
import os
import time
import io
import re
import webbrowser
from urllib.parse import urljoin
from datetime import datetime

import pandas as pd
import requests
from dash import Dash, dcc, html, Output, Input, State, no_update
import plotly.graph_objs as go

# ------------------ CONFIG ------------------
SERVER_ROOT_URLS = [
    "http://172.20.202.52:8080",
    "http://172.20.206.103:8080",
    "http://172.20.202.182:8080",
]

LOCAL_CACHE_FOLDER = "./cached_data"
os.makedirs(LOCAL_CACHE_FOLDER, exist_ok=True)

TEMP_COLS = ["Target_T", "Sheath_T", "Chamber_top_T"]
HUMI_COLS = ["Target_RH", "Sheath_RH", "Chamber_top_RH"]
TIMESTAMP_CANDIDATES = ["Timestamp", "Time", "Timestamps"]

REFRESH_MS = 120_000      # 2 minutes
CONNECT_TIMEOUT = 1.5
READ_TIMEOUT = 6.0

# Plot window / downsampling
PLOT_WINDOW = "48H"
RESAMPLE_RULE = "2min"

# ------------------ FILENAME / START-TIME HELPERS ------------------
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

# Fast directory listing (single GET + regex)
CSV_HREF_RE = re.compile(r'href="([^"]+\.csv)"', re.IGNORECASE)

def list_csvs_fast(root: str, limit: int = 400):
    try:
        r = requests.get(root, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r.raise_for_status()
        hrefs = CSV_HREF_RE.findall(r.text)
        names = [h.split("/")[-1] for h in hrefs]
        if len(names) > limit:
            names = names[-limit:]  # keep tail; most HTTP indexes are sorted
        return names
    except Exception:
        return []

def filename_exists_on_any_server(filename: str) -> bool:
    for root in SERVER_ROOT_URLS:
        try:
            url = urljoin(root, filename)
            h = requests.head(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            if 200 <= h.status_code < 400:
                return True
        except Exception:
            continue
    return False

def get_latest_csv_filename_fast():
    """Auto-pick newest by timestamp parsed from filename. Fall back to lexicographic."""
    best_name, best_dt, lex_fallback = None, None, None
    for root in SERVER_ROOT_URLS:
        names = list_csvs_fast(root)
        if not names:
            continue

        # keep lexicographic fallback
        local_lex = max(names)
        if (lex_fallback is None) or (local_lex > lex_fallback):
            lex_fallback = local_lex

        for n in names:
            dt = ts_from_name(n)
            if dt is None:
                continue
            if (best_dt is None) or (dt > best_dt):
                best_dt, best_name = dt, n

        # stop early once we found a timestamped best on this root
        if best_name is not None:
            break

    if best_name:
        return best_name
    if lex_fallback:
        return lex_fallback
    raise RuntimeError("No CSV files found on any server.")

# ------------------ FETCH (every refresh; tries all IPs) ------------------
def fetch_csv_first_alive(filename):
    """
    Try GET on each IP (tight timeouts). On success, return (bytes, content_length, root_url).
    If all fail, return (None, None, last_err).
    """
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

# ------------------ TIME PARSING ------------------
def coerce_timestamp(df: pd.DataFrame, test_start_str=None) -> pd.DataFrame:
    """
    Convert 'Timestamp' (elapsed seconds since start) into actual datetimes using test_start_str.
    """
    if "Timestamp" not in df.columns or not test_start_str:
        return df
    try:
        test_start_dt = datetime.fromisoformat(test_start_str)
    except Exception:
        return df

    df = df.copy()
    secs = pd.to_numeric(df["Timestamp"], errors="coerce")
    df["Timestamp"] = test_start_dt + pd.to_timedelta(secs, unit="s")
    return df

def preprocess(df: pd.DataFrame, test_start_str=None) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()

    # Convert Timestamp from elapsed seconds → real datetimes
    df = coerce_timestamp(df, test_start_str=test_start_str)

    # Keep only columns we plot
    keep = ["Timestamp"] + [c for c in (TEMP_COLS + HUMI_COLS) if c in df.columns]
    df = df[keep]

    # Window & optional downsample
    ts_col = "Timestamp"
    if ts_col in df.columns and pd.api.types.is_datetime64_any_dtype(df[ts_col]):
        if PLOT_WINDOW:
            cutoff = df[ts_col].max() - pd.Timedelta(PLOT_WINDOW)
            df = df[df[ts_col] >= cutoff]
        if RESAMPLE_RULE:
            df = (
                df.set_index(ts_col)
                  .resample(RESAMPLE_RULE)
                  .mean(numeric_only=True)
                  .reset_index()
            )
    return df

# ------------------ FIGURES ------------------
def build_figs(df, ts_col="Timestamp"):
    Trace = go.Scattergl  # WebGL for speed
    temp_fig, humi_fig = go.Figure(), go.Figure()

    if ts_col in df.columns:
        for c in TEMP_COLS:
            if c in df.columns:
                temp_fig.add_trace(Trace(x=df[ts_col], y=df[c], mode="lines", name=c.replace("_", " ")))
        for c in HUMI_COLS:
            if c in df.columns:
                humi_fig.add_trace(Trace(x=df[ts_col], y=df[c], mode="lines", name=c.replace("_", " ")))

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
            uirevision="stay",  # keep zoom on refresh
        )
    return temp_fig, humi_fig

# ------------------ DASH APP ------------------
app = Dash(__name__)
app.title = "Climate Monitor"
app.config.suppress_callback_exceptions = True

app.layout = html.Div(
    style={"fontFamily": "system-ui, Arial, sans-serif", "padding": "14px", "maxWidth": "1400px", "margin": "0 auto"},
    children=[
        # Stores
        dcc.Store(id="filename-store"),     # chosen CSV filename
        dcc.Store(id="starttime-store"),    # ISO start datetime parsed from filename
        dcc.Store(id="data-store"),         # parsed DataFrame JSON
        dcc.Store(id="meta-store"),         # last content_length + origin

        # URL (optional: allow ?file=NAME.csv later if you want)
        dcc.Location(id="url"),

        # Filename chooser UI
        html.Div(
            style={"display": "flex", "gap": "8px", "alignItems": "center", "margin": "8px 0 12px"},
            children=[
                html.Label("Fichier CSV (optionnel) :"),
                dcc.Input(
                    id="filename-input",
                    type="text",
                    placeholder="Laisser vide pour détecter automatiquement le plus récent…",
                    debounce=True,
                    style={"width": "420px"},
                ),
                html.Button("Utiliser ce fichier", id="filename-submit"),
            ],
        ),

        html.H2("Illuscens — Température et humidité (48 dernières heures)", style={"marginBottom": "6px"}),
        html.Div(
            id="status-bar",
            style={
                "padding": "10px 12px",
                "background": "#f4f6f8",
                "border": "1px solid #e1e5ea",
                "borderRadius": "10px",
                "marginBottom": "12px",
                "fontSize": "14px",
            },
        ),
        dcc.Graph(id="temp-graph", config={"displaylogo": False}),
        dcc.Graph(id="humi-graph", config={"displaylogo": False}),
        dcc.Interval(id="refresh", interval=REFRESH_MS, n_intervals=0),
    ],
)

# ---- Choose filename from UI (or auto) ----
@app.callback(
    Output("filename-store", "data"),
    Output("starttime-store", "data"),
    Output("status-bar", "children"),
    Input("filename-submit", "n_clicks"),     # button
    Input("filename-input", "n_submit"),      # press Enter
    Input("refresh", "n_intervals"),          # first tick (auto-pick if empty)
    State("filename-input", "value"),
    State("filename-store", "data"),
    prevent_initial_call=False,
)
def choose_filename(n_clicks, n_submit, n_intervals, typed_value, stored_filename):
    ctx = Dash.callback_context if hasattr(Dash, "callback_context") else None
    trig = ctx.triggered[0]["prop_id"] if ctx and ctx.triggered else ""

    # If already chosen and this trigger is only the recurring interval, do nothing
    if stored_filename and trig.endswith("n_intervals"):
        return no_update, no_update, no_update

    # 1) User typed something: validate it exists
    if typed_value and typed_value.strip():
        chosen = os.path.basename(typed_value.strip())
        if filename_exists_on_any_server(chosen):
            start_dt = ts_from_name(chosen)
            ok = f"✅ Fichier choisi: {chosen}"
            if start_dt is None:
                ok += " • ⚠️ Impossible d’extraire l’heure de départ du nom; utilisation du temps écoulé brut."
            return chosen, (start_dt.isoformat() if start_dt else None), ok
        # Fall back to auto
        warn = f"⚠️ '{chosen}' introuvable. Détection automatique…"
    else:
        warn = ""

    # 2) Auto-detect latest by filename timestamp
    try:
        chosen = get_latest_csv_filename_fast()
        start_dt = ts_from_name(chosen)
        status = ("🔎 " + warn + " " if warn else "🔎 ") + f"Fichier détecté: {chosen}"
        return chosen, (start_dt.isoformat() if start_dt else None), status
    except Exception as e:
        return no_update, no_update, f"❌ Aucun CSV trouvé: {e}"

# ---- Update plots every refresh ----
@app.callback(
    Output("temp-graph", "figure"),
    Output("humi-graph", "figure"),
    Output("status-bar", "children"),
    Output("data-store", "data"),
    Output("meta-store", "data"),
    Input("refresh", "n_intervals"),
    State("filename-store", "data"),
    State("starttime-store", "data"),
    State("data-store", "data"),
    State("meta-store", "data"),
    prevent_initial_call=False,
)
def update_plots(n_intervals, filename, starttime_str, data_json, meta_json):
    if not filename:
        return go.Figure(), go.Figure(), "⏳ Recherche du fichier…", data_json, meta_json

    # Try all servers for the file
    content, content_length, origin = fetch_csv_first_alive(filename)
    if content is None:
        if data_json:
            df = pd.read_json(io.StringIO(data_json), orient="split")
            tfig, hfig = build_figs(df)
            return tfig, hfig, "💾 Données en cache (aucun serveur accessible)", data_json, meta_json
        return go.Figure(), go.Figure(), "❌ Aucun serveur accessible et aucun cache", None, meta_json

    new_meta = {"content_length": int(content_length), "origin": str(origin)}
    if meta_json == new_meta and data_json:
        df = pd.read_json(io.StringIO(data_json), orient="split")
        tfig, hfig = build_figs(df)
        status = f"⏩ Inchangé — cache réutilisé • {origin} • {time.strftime('%H:%M:%S')} • {filename}"
        return tfig, hfig, status, data_json, new_meta

    # Save file, read only needed columns
    cache_path = os.path.join(LOCAL_CACHE_FOLDER, filename)
    with open(cache_path, "wb") as f:
        f.write(content)

    wanted = set(TIMESTAMP_CANDIDATES) | set(TEMP_COLS) | set(HUMI_COLS)
    df = pd.read_csv(cache_path, usecols=lambda c: c.strip() in wanted)

    # Convert elapsed seconds → real datetimes using start time from filename
    df = preprocess(df, test_start_str=starttime_str)

    data_json_new = df.to_json(orient="split", date_format="iso")
    tfig, hfig = build_figs(df)
    status = f"🌐 Live {origin} — rafraîchi {time.strftime('%H:%M:%S')} • {filename}"
    return tfig, hfig, status, data_json_new, new_meta

if __name__ == "__main__":
    # Open browser automatically
    webbrowser.open_new("http://127.0.0.1:8050/")
    app.run(debug=False)
