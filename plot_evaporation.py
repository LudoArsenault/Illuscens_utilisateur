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

# --- Resampling et calculs ---
df_weight = df.set_index(pd.to_datetime(df["Absolute_Time"]))
df_down = df_weight.select_dtypes(include='number').resample("1h").mean().dropna()

initial_weight = df_down["Weight"].iloc[0]
df_down["Lost_Weight"] = initial_weight - df_down["Weight"]
df_down["Smoothed_Loss"] = df_down["Lost_Weight"].rolling("12h", center=True).mean()

df_down["Rate_kg_h"] = df_down["Smoothed_Loss"].diff() / df_down.index.to_series().diff().dt.total_seconds() * 3600
df_down["Smoothed_Rate"] = df_down["Rate_kg_h"].rolling("12h", center=True).mean()

df_down["Chamber_top_T"] = df_down["Chamber_top_T"].rolling("6h", center=True).mean()
df_down["Chamber_top_RH"] = df_down["Chamber_top_RH"].rolling("6h", center=True).mean()

# --- Création de la figure ---
fig_weight = go.Figure()

if "Smoothed_Rate" in df_down.columns and df_down["Smoothed_Rate"].notna().any():
    avg_rate = df_down["Smoothed_Rate"].mean()
    fig_weight.add_annotation(
        xref="paper", yref="paper",
        x=0.99, y=0.99,
        text=f"Moyenne: {avg_rate:.2f} kg/h",
        showarrow=False,
        font=dict(size=12, color="black"),
        bgcolor="lightyellow",
        bordercolor="black", borderwidth=1
    )

fig_weight.add_trace(go.Scattergl(x=df_down.index, y=df_down["Smoothed_Loss"],
    mode="lines+markers", name="Masse perdue (kg)",
    line=dict(shape='hv', color='black')))

fig_weight.add_trace(go.Scattergl(x=df_down.index, y=df_down["Smoothed_Rate"],
    mode="lines", name="Taux d'évaporation (kg/h)", yaxis="y2", line=dict(color="black")))

fig_weight.add_trace(go.Scattergl(x=df_down.index, y=df_down["Chamber_top_T"],
    mode="lines", name=f"Température (°C)", line=dict(dash="dash", color="orange")))

fig_weight.add_trace(go.Scattergl(x=df_down.index, y=df_down["Target_T"],
    mode="lines", name=f"Température cible (°C)", line=dict(color="orange")))

fig_weight.add_trace(go.Scattergl(x=df_down.index, y=df_down["Target_RH"],
    mode="lines", name=f"Humidité cible (%)", line=dict(color="purple")))

fig_weight.add_trace(go.Scattergl(x=df_down.index, y=df_down["Chamber_top_RH"],
    mode="lines", name=f"Humidité réelle (%)", line=dict(dash="dot", color="purple")))

fig_weight.update_layout(
    title="Évaporation au cours du cycle",
    xaxis=dict(title="Temps"),
    yaxis=dict(title="Masse perdue (kg)"),
    yaxis2=dict(title="Taux d'évaporation (kg/h)", overlaying="y", side="right"),
    height=None,
    width=None,
    legend=dict(x=150, y=0.99)
)

# --- Affichage et sauvegarde ---
fig_weight.show(config={"responsive": True})

# Sauvegarde
fig_path = os.path.join(dossier_figures, "Évaporation.html")
fig_weight.write_html(fig_path)
print(f"✅ Figure sauvegardée : {fig_path}")
