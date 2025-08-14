from datetime import timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils import *

# -------------------- Parameters for the overview figure --------------------
OVERVIEW_RESAMPLE = "30min"   # e.g. "5min", "15min", "30min", "1H"
OVERVIEW_SMOOTH   = "2h"      # time-based rolling window, centered

def make_overview_figure(df, resample_rule=OVERVIEW_RESAMPLE, smooth_window=OVERVIEW_SMOOTH):
    """
    Create an overview figure on the entire test:
    - Downsamples (resamples) uniformly in time
    - Smooths with a centered rolling mean (time-based window)
    - Plots same signals as the day figures
    """
    # Ensure datetime index for time-based ops
    df_idx = df.set_index(pd.to_datetime(df["Absolute_Time"])).sort_index()

    # Columns to include (subset used in day plots)
    cols = [
        "Target_T", "Sheath_T", "Chamber_T_avg", "Heater_Power", "Ammonia",
        "Target_RH", "Sheath_RH", "Chamber_RH_avg", "Humidifier_Power",
        "Total_CFM", "Target_Ratio", "Recycling_Ratio", "Intake_Temp", "Intake_Hum"
    ]
    cols = [c for c in cols if c in df_idx.columns]  # keep only existing

    # Resample with mean for numeric columns
    df_res = df_idx[cols].resample(resample_rule).mean()

    # Smooth (centered) with time-based rolling; keep min_periods=1 so edges don't go NaN
    df_smooth = df_res.rolling(smooth_window, center=True, min_periods=1).mean()

    # Build figure
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        specs=[[{"secondary_y": True}], [{"secondary_y": True}], [{"secondary_y": True}] ],
        subplot_titles=[
            "Température et Heater Power",
            "Humidité et Humidifier Power",
            "Données de recirculation"
        ]
    )

    # --- Subplot 1: Temperature & Heater ---
    if "Target_T" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Target_T"], name='Température cible'), row=1, col=1)
    if "Sheath_T" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Sheath_T"], name='Température gaine'), row=1, col=1)
    if "Chamber_T_avg" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Chamber_T_avg"], name='Température chambre'), row=1, col=1)
    if "Heater_Power" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Heater_Power"], name='Heater Power'), row=1, col=1, secondary_y=True)


    # --- Subplot 2: Humidity & Humidifier ---
    if "Target_RH" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Target_RH"], name='Humidité cible'), row=2, col=1)
    if "Sheath_RH" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Sheath_RH"], name='Humidité gaine'), row=2, col=1)
    if "Chamber_RH_avg" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Chamber_RH_avg"], name='Humidité chambre'), row=2, col=1)
    if "Humidifier_Power" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Humidifier_Power"], name='Humidifier Power'), row=2, col=1, secondary_y=True)

    # --- Subplot 3: Recirculation & Intake ---
    if "Total_CFM" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Total_CFM"], name="Débit d'air"), row=3, col=1)
    if "Target_Ratio" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Target_Ratio"], name='Recirc. cible', line=dict(dash='dash')), row=3, col=1)
    if "Recycling_Ratio" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Recycling_Ratio"], name='Ratio de recirc.'), row=3, col=1)
    if "Intake_Temp" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Intake_Temp"], name='Température (intake)', line=dict(dash='dot')), row=3, col=1)
    if "Intake_Hum" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Intake_Hum"], name='Humidité (intake)', line=dict(dash='dot')), row=3, col=1)
    if "Ammonia" in df_smooth:
        fig.add_trace(go.Scattergl(x=df_smooth.index, y=df_smooth["Ammonia"], name='Ammoniac'), row=3, col=1, secondary_y=True)

    # Axis titles & layout
    fig.update_layout(height=900, title_text="Aperçu global — test complet", showlegend=True)
    fig.update_yaxes(title_text="Température (°C)", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Heater Power (%)", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Humidité relative (%)", row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Humidifier Power (V)", row=2, col=1, secondary_y=True)
    fig.update_xaxes(title_text="Temps", row=3)
    fig.update_yaxes(title_text="Ratios / RH / Temp", row=3)
    fig.update_yaxes(title_text="Ammoniac (ppm)", row=3, col=1, secondary_y=True)



    # Add reboot markers using the original (un-resampled) timestamps
    annotate_code_updates(fig, df["Absolute_Time"], label="Redémarrage")

    return fig

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


fig_overview = make_overview_figure(df, OVERVIEW_RESAMPLE, OVERVIEW_SMOOTH)
fig_overview.show()
fig_overview.write_html(f"{dossier_figures}/Température_Humidité.html")