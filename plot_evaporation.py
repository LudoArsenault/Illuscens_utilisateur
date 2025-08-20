"""
Résumé
------
Produit une figure Plotly interactive montrant :
- la *masse perdue* (kg) au cours du temps,
- le *taux d’évaporation* (kg/h) lissé,
- la température et l’humidité de la chambre vs. cibles.

Utilisation
----------
1) Lancer le script puis saisir :
   - le chemin complet du CSV de données,
   - le dossier où sauvegarder la figure HTML.
2) La figure s’affiche et est enregistrée sous `Évaporation.html`.

Entrées attendues
-----------------
- CSV contenant (si possible) `Absolute_Time`; sinon le temps est reconstruit à partir du nom
  de fichier + `Timestamp` (secondes), avec un décalage de +1 h (horloge Pi).
- Colonnes utilisées : `Weight`, `Chamber_top_T`, `Chamber_top_RH`, `Target_T`, `Target_RH`, etc.

Traitements clés
----------------
- Nettoyage des outliers de `Weight` (IQR).
- Resampling horaire et lissages (fenêtres basées sur le temps).
- Calcul de `Lost_Weight`, `Smoothed_Loss`, `Smoothed_Rate` et affichage de la moyenne du taux.

Sorties
-------
- Figure interactive (affichée) et sauvegardée en HTML dans le dossier choisi.
"""

from datetime import timedelta
import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from utils import *



# --- Demande à l'utilisateur ---
chemin_fichier = input("Entrez le chemin complet du fichier CSV de données : ").strip().strip('"').strip("'")
while not os.path.isfile(chemin_fichier):
    print("❌ Fichier introuvable. Veuillez réessayer.")
    chemin_fichier = input("Entrez le chemin complet du fichier CSV de données : ").strip().strip('"').strip("'")

dossier_figures = input("Entrez le chemin du dossier où sauvegarder la figure : ").strip().strip('"').strip("'")
while not os.path.isdir(dossier_figures):
    print("❌ Dossier introuvable. Veuillez réessayer.")
    dossier_figures = input("Entrez le chemin du dossier où sauvegarder la figure : ").strip().strip('"').strip("'")

# --- Chargement des données ---
df = pd.read_csv(chemin_fichier)
df.columns = df.columns.str.strip()

# --- Traitement du temps ---
if 'Absolute_Time' in df.columns:
    df['Absolute_Time'] = pd.to_datetime(df['Absolute_Time'])
else:
    filename = os.path.basename(chemin_fichier)
    file_start_time = extract_datetime_from_filename(filename)
    if file_start_time is None:
        file_start_time = timedelta(seconds=0)

    df["Absolute_Time"] = [ file_start_time + timedelta(hours=1) + timedelta(seconds=ts) for ts in round(df["Timestamp"]) ]

start_time = df['Absolute_Time'].min()
df['Elapsed_Hours'] = (df['Absolute_Time'] - start_time).dt.total_seconds() / 3600
df['Day'] = df['Elapsed_Hours'].floordiv(24).astype(int)

# --- Calcul des moyennes ---
df['Chamber_T_avg'] = df[['Chamber_top_T', 'Chamber_bottom_T']].mean(axis=1)
df['Chamber_RH_avg'] = df[['Chamber_top_RH', 'Chamber_bottom_RH']].mean(axis=1)

# --- Nettoyage poids ---
q1 = df["Weight"].quantile(0.25)
q3 = df["Weight"].quantile(0.75)
iqr = q3 - q1
df["Weight"] = df["Weight"].where(df["Weight"].between(q1 - 1.5 * iqr, q3 + 1.5 * iqr))

# --- Interpolation temporelle pour combler les pannes ---
# On passe sur une grille temporelle régulière (≈ pas natif), puis :
# - Interpolation linéaire dans le temps pour les colonnes numériques (dont Weight)
# - Forward-fill pour les consignes / états discrets
# - On mémorise les intervalles de panne pour les afficher en fond

# 1) Index temps + ordre
df = df.sort_values('Absolute_Time').copy()
df = df.set_index(pd.to_datetime(df['Absolute_Time']), drop=False)

# 2) Détection du pas natif et des pannes (avant réindexation)
dt = df.index.to_series().diff().dt.total_seconds().dropna()
pas = int(np.nanmedian(dt)) if len(dt) else 20
if pas < 1 or pas > 3600:
    pas = 20
gap_thresh = 3 * pas  # panne si trou > 3×pas

gap_intervals = []
idx = df.index
for i in range(1, len(idx)):
    delta = (idx[i] - idx[i-1]).total_seconds()
    if delta > gap_thresh:
        gap_intervals.append((idx[i-1], idx[i]))

# 3) Réindexation sur grille régulière
full_index = pd.date_range(df.index.min(), df.index.max(), freq=f"{pas}s")
df_full = df.reindex(full_index)

# 4) Stratégies par type de variable
# Colonnes à "tenir" par palier (consignes/états) -> ffill
cols_ffill_candidates = [
    'Phase', 'Target_T', 'Target_RH', 'Target_airflow',
    'Target_Ratio', 'Expected_Ratio',
    'Intake_Flap', 'Recycling_Flap'
]
cols_ffill = [c for c in cols_ffill_candidates if c in df_full.columns]

# Colonnes numériques pour interpolation linéaire (capteurs / puissances / débits…)
num_cols = df_full.select_dtypes(include=['number']).columns.tolist()
# S'assurer que Weight est bien traité en numérique
if 'Weight' in df_full.columns and 'Weight' not in num_cols:
    num_cols.append('Weight')

# On évite d’interpoler les colonnes ffill (si elles sont numériques)
num_cols = [c for c in num_cols if c not in cols_ffill]

# Interpolation temporelle sur les colonnes numériques (uniquement au milieu des trous)
df_full[num_cols] = df_full[num_cols].apply(pd.to_numeric, errors='coerce')
df_full[num_cols] = df_full[num_cols].interpolate(method='time', limit_area='inside')

# Forward-fill pour consignes / états
if cols_ffill:
    df_full[cols_ffill] = df_full[cols_ffill].ffill()

# 5) Jeu de données final pour les calculs
df_down = df_full  # on remplace votre df_down par la version comblée


# --- Calculs simples (sans sur-lissage) ---
# Masse perdue = masse initiale - masse instantanée
initial_weight = df_down['Weight'].dropna().iloc[0]
df_down['Lost_Weight'] = initial_weight - df_down['Weight']
df_down['Lost_Weight'] = df_down['Lost_Weight'].rolling(int(3600*12/pas), center=True, min_periods=1).mean()

# Taux instantané (kg/h) à partir de la dérivée de Lost_Weight
dt_s = df_down.index.to_series().diff().dt.total_seconds()
df_down['Rate_kg_h'] = df_down['Lost_Weight'].diff() / dt_s * 3600.0

# (Optionnel) petit lissage local si la quantification 0.5 kg crée trop de pics
df_down['Rate_kg_h'] = df_down['Rate_kg_h'].rolling(int(3600*10/pas), center=True, min_periods=1).mean()


# --- Figure Plotly ---
fig_weight = go.Figure()

# Zones ombrées pour les intervalles interpolés (pannes comblées)
for (x0, x1) in gap_intervals:
    fig_weight.add_vrect(
        x0=x0, x1=x1,
        fillcolor="LightSalmon", opacity=0.15,
        line_width=0, layer="below",
        annotation_text="Interpolé", annotation_position="top left"
    )

# Annotation de la moyenne du taux (sur les valeurs valides)
if 'Rate_kg_h' in df_down.columns and df_down['Rate_kg_h'].notna().any():
    avg_rate = df_down['Rate_kg_h'].mean()
    fig_weight.add_annotation(
        xref="paper", yref="paper", x=0.99, y=0.99,
        text=f"Moyenne: {avg_rate:.2f} kg/h",
        showarrow=False, font=dict(size=12, color="black"),
        bgcolor="lightyellow", bordercolor="black", borderwidth=1
    )

# Traces
fig_weight.add_trace(go.Scattergl(
    x=df_down.index, y=df_down['Lost_Weight'],
    mode="lines", name="Masse perdue (kg)",
    line=dict(shape='hv', color='black')
))

fig_weight.add_trace(go.Scattergl(
    x=df_down.index, y=df_down['Rate_kg_h'],
    mode="lines", name="Taux d'évaporation (kg/h)",
    yaxis="y2", line=dict(color="black")
))

if 'Chamber_top_T' in df_down.columns:
    fig_weight.add_trace(go.Scattergl(
        x=df_down.index, y=df_down['Chamber_top_T'].rolling(int(3600*2/pas), center=True, min_periods=1).mean(),
        mode="lines", name="Température (°C)",
        line=dict(dash="dash", color="orange")
    ))

if 'Target_T' in df_down.columns:
    fig_weight.add_trace(go.Scattergl(
        x=df_down.index, y=df_down['Target_T'],
        mode="lines", name="Température cible (°C)",
        line=dict(color="orange")
    ))

if 'Target_RH' in df_down.columns:
    fig_weight.add_trace(go.Scattergl(
        x=df_down.index, y=df_down['Target_RH'],
        mode="lines", name="Humidité cible (%)",
        line=dict(color="purple")
    ))

if 'Chamber_top_RH' in df_down.columns:
    fig_weight.add_trace(go.Scattergl(
        x=df_down.index, y=df_down['Chamber_top_RH'].rolling(int(3600*2/pas), center=True, min_periods=1).mean(),
        mode="lines", name="Humidité réelle (%)",
        line=dict(dash="dot", color="purple")
    ))

fig_weight.update_layout(
    title="Évaporation au cours du cycle",
    xaxis=dict(title="Temps"),
    yaxis=dict(title="Masse perdue (kg)"),
    yaxis2=dict(title="Taux d'évaporation (kg/h)", overlaying="y", side="right"),
    legend=dict(x=150, y=0.99)
)


# --- Affichage et sauvegarde ---
fig_weight.show(config={"responsive": True})

# Sauvegarde
fig_path = os.path.join(dossier_figures, "Évaporation.html")
fig_weight.write_html(fig_path)
print(f"✅ Figure sauvegardée : {fig_path}")
