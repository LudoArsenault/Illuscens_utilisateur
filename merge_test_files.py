# Ce script permet d'unifier les fichiers de données d'un test qui a été arrêté et redémarré, tant qu'ils ont le même nom.

import os
import re
import pandas as pd
from datetime import timedelta
from utils import *

# --- CONFIGURATION ---
LOCAL_FOLDER = r"C:\Users\ludovic.arsenault-levesque\OneDrive - Entosystem\Documents\Illuscens\données/cached_data/"
FILENAME_PREFIX = "test_larves_7"
OUTPUT_FILENAME = "merged_test_larves_7.csv"




# --- Main script ---
def main():

    while True:
        path = input("Entrez le chemin d'accès complet du dossier contenants les données : ").strip()

        # Vérifier que le dor existe
        if not os.path.isdir(path):
            print("❌ Le dossier n'existe pas. Veuillez réessayer.")
            continue

        filename_prefix = input("Entrez le nom du test : ").strip()

        all_files = [
            f for f in os.listdir(path)
            if f.startswith(filename_prefix) and f.endswith(".csv")
        ]
        if not all_files:
            print("No matching files found.")
            return
        else:
            break


    # Sort by datetime embedded in filename
    all_files.sort(key=lambda f: extract_datetime_from_filename(f))

    dfs = []
    first_start_time = None

    for filename in all_files:
        filepath = os.path.join(path, filename)
        print(f"Reading: {filename}")
        df = pd.read_csv(filepath)

        # Drop rows with missing Timestamps
        df = df.dropna(subset=["Timestamp"])

        file_start_time = extract_datetime_from_filename(filename)
        if file_start_time is None:
            print(f"Skipping {filename}, couldn't extract datetime.")
            continue

        if first_start_time is None:
            first_start_time = file_start_time

        # Compute absolute time and time since first file
        df["Absolute_Time"] = [
            file_start_time + timedelta(seconds=ts) for ts in round(df["Timestamp"])
        ]
        dfs.append(df)

    # Concatenate all DataFrames
    merged_df = pd.concat(dfs, ignore_index=True)

    # Compute elapsed time since first file
    merged_df["Elapsed"] = merged_df["Absolute_Time"] - first_start_time
    merged_df["Elapsed_str"] = merged_df["Elapsed"].apply(lambda x: str(x).split('.')[0])  # drop microseconds

    # Save to disk
    output_path = os.path.join(path, f"{filename_prefix}_merged.csv")
    merged_df.to_csv(output_path, index=False)
    print(f"Fichier unifié sauvegardé en tant que : {output_path}")

if __name__ == "__main__":
    main()
