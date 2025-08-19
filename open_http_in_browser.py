"""
Résumé
------
Teste une liste d’adresses IP d’un serveur HTTP (Raspberry Pi) et ouvre la première
qui répond dans le navigateur, à la racine (listing des fichiers).

Utilisation
----------
python open_http_in_browser.py

Personnalisation
----------------
- Modifier la liste `IP_ADDRESSES` si de nouvelles adresses sont possibles.
- Adapter le chemin ouvert (`f"{ip}/"`) si nécessaire (ex.: sous-dossier).

Sorties
-------
- Ouvre le navigateur sur la première IP atteignable.
- Affiche en console le résultat de chaque tentative.
"""

import requests
import webbrowser

# List of possible server IPs
IP_ADDRESSES = [
    "http://raspberrypi.local:8080",
    "http://172.20.202.52:8080",
    "http://172.20.206.103:8080",
    "http://172.20.202.182:8080"
]


# Function to check the server and open the link in the browser
def open_browser_with_file_list():
    for ip in IP_ADDRESSES:
        try:
            # Attempt to fetch the directory listing from the server
            response = requests.get(f"{ip}/")  # Modify to the correct path if necessary
            response.raise_for_status()  # Check if the request was successful

            # If the server is reachable, open the URL in the browser
            print(f"Successfully reached the server at {ip}. Opening in browser...")
            webbrowser.open(f"{ip}/")  # Open the server's directory listing in the default browser
            break  # Exit the loop once a working IP is found
        except requests.RequestException as e:
            print(f"Failed to reach {ip}: {e}")


# Run the function to try opening the directory listing
open_browser_with_file_list()
