import os
import re
from urllib.parse import urljoin
import pandas as pd
import requests
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime


# --- Extract timestamp from filename ---
def extract_datetime_from_filename(filename):
    match = re.search(r"(\d{4})-(\d+)-(\d+)_([0-9]+)h([0-9]+)m([0-9]+)s", filename)
    if match:
        y, m, d, h, mi, s = map(int, match.groups())
        return pd.Timestamp(year=y, month=m, day=d, hour=h, minute=mi, second=s)
    return None


SERVER_ROOT_URLS = [
    "http://172.20.202.52:8080",
    "http://172.20.206.103:8080",
    "http://172.20.202.182:8080"

]

LOCAL_CACHE_FOLDER = "./cached_data"

def get_latest_csv_url():
    for server_root in SERVER_ROOT_URLS:
        try:
            response = requests.get(server_root, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            csv_links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].endswith('.csv')]
            if not csv_links:
                continue

            latest_file = None
            latest_time = None

            for href in csv_links:
                file_url = urljoin(server_root, href)
                head = requests.head(file_url, timeout=5)
                last_modified = head.headers.get("Last-Modified")

                if last_modified:
                    mod_time = parsedate_to_datetime(last_modified)
                    if latest_time is None or mod_time > latest_time:
                        latest_time = mod_time
                        latest_file = file_url

            if latest_file:
                return latest_file, server_root

        except Exception as e:
            print(f"⚠️  Failed with {server_root}: {e}")

    raise RuntimeError("❌ All server root URLs failed.")


def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')


def fetch_csv(csv_url):
    local_cache_file = os.path.join(LOCAL_CACHE_FOLDER, os.path.basename(csv_url))
    try:
        response = requests.get(csv_url, timeout=5)
        response.raise_for_status()

        with open(local_cache_file, 'wb') as f:
            f.write(response.content)

        df = pd.read_csv(csv_url)
        return df, "🌐 Live (HTTP)"
    except Exception:
        try:
            df = pd.read_csv(local_cache_file)
            return df, "💾 Fallback (Cached)"
        except Exception as cache_error:
            raise RuntimeError(f"❌ Failed to fetch from server and cache. {cache_error}")

def prompt_for_manual_url(server_root):
    filename = input("🔎 Enter the CSV filename to look for (e.g., test_2025-7-22_15h26m30s.csv): ").strip()
    if not filename.endswith(".csv"):
        print("❌ Invalid filename. Must end with '.csv'.")
        return None
    return urljoin(server_root, filename)

def annotate_code_updates(fig, time_series, threshold_seconds=120, label="Code update (reboot)"):
    time_deltas = time_series.diff().dt.total_seconds()

    for i, delta in enumerate(time_deltas):
        if pd.notna(delta) and delta > threshold_seconds:
            reboot_time = time_series.iloc[i]

            # --- Vertical line across all subplots ---
            fig.add_vline(
                x=reboot_time,
                line=dict(color="red", dash="dot", width=1),
                layer="below",  # or "above"
            )

            # --- Single annotation outside the plotting area ---
            fig.add_annotation(
                x=reboot_time,
                y=1.02,  # slightly above top of plot
                xref="x",
                yref="paper",
                text=label,
                showarrow=False,
                bgcolor="lightyellow",
                font=dict(size=10),
                bordercolor="black",
                borderwidth=1,
                yanchor="bottom"
            )
