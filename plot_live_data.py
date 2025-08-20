import datetime
import matplotlib.pyplot as plt

from utils import *


def main():
    try:
        csv_url, server_root = get_latest_csv_url()
    except Exception as e:
        print(f"❌ Erreur lors de la détection automatique de l'URL : {e}")
        server_root = "http://172.20.202.182:8080"
        print("🔍 Impossible de détecter automatiquement l'URL du fichier.")
        print("📥 Veuillez sélectionner manuellement un fichier à partir du serveur.")
        csv_url = prompt_for_manual_url(server_root)
        if not csv_url:
            print("❌ Fin du programme. Aucun fichier valide sélectionné.")
            return

    try:
        df, source = fetch_csv(csv_url)
        df.columns = df.columns.str.strip()

        # Convertir 'Timestamp' en datetime
        file_start_time = extract_datetime_from_filename(csv_url)
        df["Time"] = [
            file_start_time + datetime.timedelta(hours=1) + datetime.timedelta(seconds=ts)
            for ts in round(df["Timestamp"])
        ]  # +1 heure à cause de l'heure du Raspberry Pi

        # Moyennes
        df['Chamber_T_avg'] = df[['Chamber_top_T', 'Chamber_bottom_T']].mean(axis=1)
        df['Chamber_RH_avg'] = df[['Chamber_top_RH', 'Chamber_bottom_RH']].mean(axis=1)

        df = df.set_index(df['Time'])

        # --- Graphe 1 : Températures et puissance de chauffe ---
        fig1, (ax1_temp, ax1_power) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))

        ax1_temp.plot(df['Time'], df['Target_T'], label='Cible')
        ax1_temp.plot(df['Time'], df['Sheath_T'], label='Gaine')
        ax1_temp.plot(df['Time'], df['Chamber_T_avg'], label='Pièce')
        ax1_temp.plot(df['Time'], df['Mobile_T'], label='Larves')
        ax1_temp.set_ylabel("Température (°C)")
        ax1_temp.set_title("Températures et puissance de chauffe dans le temps")
        ax1_temp.legend()

        ax1_power.plot(df['Time'], df['Heater_Power'], label='Puissance chauffage', color='tab:red')
        ax1_power.set_ylabel("Puissance (%)")
        ax1_power.set_xlabel("Temps")
        ax1_power.legend()

        fig1.autofmt_xdate()

        # --- Graphe 2 : Humidité et puissance de l’humidificateur ---
        fig2, (ax2_rh, ax2_power) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))

        ax2_rh.plot(df['Time'], df['Target_RH'], label='Cible')
        ax2_rh.plot(df['Time'], df['Sheath_RH'], label='Gaine')
        ax2_rh.plot(df['Time'], df['Chamber_RH_avg'], label='Pièce')
        ax2_rh.plot(df['Time'], df['Mobile_RH'], label='Larves')
        ax2_rh.set_ylabel("Humidité (%)")
        ax2_rh.set_title("Humidité et puissance de l’humidificateur dans le temps")
        ax2_rh.legend()

        ax2_power.plot(df['Time'], df['Humidifier_Power'], label='Puissance humidificateur', color='tab:blue')
        ax2_power.set_ylabel("Puissance (Volt)")
        ax2_power.set_xlabel("Temps")
        ax2_power.legend()

        fig2.autofmt_xdate()

        # --- Graphe 3 : Stratégie de recirculation ---
        fig3, ax3 = plt.subplots()
        ax3.plot(df['Time'], df['Total_CFM'], label='Total CFM')
        ax3.plot(df['Time'], df['Recycling_Ratio'], label='Recirculation', linestyle='-')
        ax3.plot(df['Time'], df['Intake_Temp'], label='Température Entrée', linestyle='-.')
        ax3.plot(df['Time'], df['Intake_Hum'], label='Humidité Entrée', linestyle='-.')

        ax3.set_ylabel("Ratios / Température / Humidité")
        ax3.set_xlabel("Temps")
        ax3.set_title("Stratégie de recirculation dans le temps")
        ax3.legend()

        fig3.autofmt_xdate()

        # --- Graphe 4 : Ammoniac et Poids ---
        fig4, ax4 = plt.subplots()

        # Ammoniac avec lissage sur 1h
        if 'Ammonia' in df.columns:
            ammonia_smoothed = df['Ammonia'].rolling("1h", center=True).mean()
            ax4.plot(df['Time'], ammonia_smoothed, label="Ammoniac (moy. 1h)", color='tab:purple')
            ax4.set_ylabel("Ammoniac (ppm)")
            ax4.set_xlabel("Temps")
            ax4.set_title("Évolution de l'ammoniac et du poids")
        else:
            print("ℹ️ Colonne 'Ammonia' absente du fichier.")

        # Axe secondaire pour le poids
        if 'Weight' in df.columns:
            ax4b = ax4.twinx()
            poids = df['Weight'].rolling("2h", center=True).mean()
            ax4b.plot(df['Time'], poids , label="Poids", color='tab:gray', linestyle='--')
            ax4b.set_ylabel("Poids (kg)")
        else:
            print("ℹ️ Colonne 'Weight' absente du fichier.")

        # Fusion des légendes
        lines1, labels1 = ax4.get_legend_handles_labels()
        lines2, labels2 = (ax4b.get_legend_handles_labels() if 'Weight' in df.columns else ([], []))
        ax4.legend(lines1 + lines2, labels1 + labels2, loc='best')

        fig4.autofmt_xdate()

        # Afficher tous les graphiques
        plt.show()

    except Exception as e:
        print(f"❌ Une erreur s’est produite : {e}")

if __name__ == "__main__":
    main()
