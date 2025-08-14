import pandas as pd
import matplotlib.pyplot as plt
import re
import datetime
from utils import *



def main():
    try:
        csv_url, server_root = get_latest_csv_url()
    except Exception as e:
        print(f"❌ Error during initial URL detection: {e}")
        server_root = "http://172.20.202.182:8080"
        csv_url = prompt_for_manual_url(server_root)
        if not csv_url:
            print("❌ Exiting. No valid file selected.")
            return

    try:
        df, source = fetch_csv(csv_url)
        df.columns = df.columns.str.strip()

        # Convert 'Timestamp' to datetime

        file_start_time = extract_datetime_from_filename(csv_url)
        df["Time"] = [
            file_start_time +datetime.timedelta(hours=1) + datetime.timedelta(seconds=ts) for ts in round(df["Timestamp"])    # +1 heure à cause de l'heure de du raspberry pi
        ]
        # df['Time'] = pd.to_datetime(df['Time_HMS'], format='%H:%M:%S')
        # df['Time'] = pd.to_datetime(df['Time'], unit='m')

        # Compute averages
        df['Chamber_T_avg'] = df[['Chamber_top_T', 'Chamber_bottom_T']].mean(axis=1)
        df['Chamber_RH_avg'] = df[['Chamber_top_RH', 'Chamber_bottom_RH']].mean(axis=1)

        df = df.set_index(df['Time'])


        # --- Plot 1: Temperature and Heater Power (Two stacked subplots) ---
        fig1, (ax1_temp, ax1_power) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))

        ax1_temp.plot(df['Time'], df['Target_T'], label='Target_T')
        ax1_temp.plot(df['Time'], df['Sheath_T'], label='Sheath_T')
        ax1_temp.plot(df['Time'], df['Chamber_T_avg'], label='Chamber_T_avg')
        ax1_temp.plot(df['Time'], df['Mobile_T'], label='Capteur mobile')
        ax1_temp.set_ylabel("Temperature (°C)")
        ax1_temp.set_title("Temperature and Heater Power Over Time")
        ax1_temp.legend()

        ax1_power.plot(df['Time'], df['Heater_Power'], label='Heater Power', color='tab:red')
        ax1_power.set_ylabel("Heater Power (%)")
        ax1_power.set_xlabel("Time")
        ax1_power.legend()

        fig1.autofmt_xdate()

        # --- Plot 2: Humidity and Humidifier Power (Two stacked subplots) ---
        fig2, (ax2_rh, ax2_power) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))

        ax2_rh.plot(df['Time'], df['Target_RH'], label='Target_RH')
        ax2_rh.plot(df['Time'], df['Sheath_RH'], label='Sheath_RH')
        ax2_rh.plot(df['Time'], df['Chamber_RH_avg'], label='Chamber RH Avg')
        ax2_rh.plot(df['Time'], df['Mobile_RH'], label='Capteur mobile')
        ax2_rh.set_ylabel("Humidity (%)")
        ax2_rh.set_title("Humidity and Humidifier Power Over Time")
        ax2_rh.legend()

        ax2_power.plot(df['Time'], df['Humidifier_Power'], label='Humidifier Power', color='tab:blue')
        ax2_power.set_ylabel("Power (Volt)")
        ax2_power.set_xlabel("Time")
        ax2_power.legend()

        fig2.autofmt_xdate()

        # --- Plot 3: Recycling Strategy Overview ---
        fig3, ax3 = plt.subplots()
        ax3.plot(df['Time'], df['Total_CFM'], label='Total_CFM')
        ax3.plot(df['Time'], df['Target_Ratio'], label='Target_Ratio', linestyle='--')
        ax3.plot(df['Time'], df['Recycling_Ratio'], label='Recycling_Ratio', linestyle='-')
        ax3.plot(df['Time'], df['Intake_Temp'], label='Intake_Temp', linestyle='-.')
        ax3.plot(df['Time'], df['Intake_Hum'], label='Intake_RH', linestyle='-.')
        # ax3.plot(df['Time'], df['Weight'], label='Weight')
        ax3.set_ylabel("Ratios / Temperature / RH")
        ax3.set_xlabel("Time")
        ax3.set_title("Recycling Strategy Over Time")
        ax3.legend()

        # --- Secondary axis (right) ---
        ax3b = ax3.twinx()
        ax3b.plot(df['Time'], df['Ammonia'].rolling("1h", center=True).mean(), label='Ammonia')
        ax3b.set_ylabel("Ammonia", labelpad=15)  # 15–20 is a good starting range

        # --- Combine legends from both axes ---
        lines1, labels1 = ax3.get_legend_handles_labels()
        lines2, labels2 = ax3b.get_legend_handles_labels()
        ax3.legend(lines1 + lines2, labels1 + labels2, loc='best')
        fig3.subplots_adjust(right=0.85)  # frees up space for the right y-axis label

        fig3.autofmt_xdate()

        # Show all plots
        plt.show()

    except Exception as e:
        print(f"❌ {e}")



if __name__ == "__main__":
    main()

