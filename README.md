# Illuscens — Scripts d’analyse et de suivi

Ce dépôt regroupe des scripts pour **récupérer**, **fusionner** et **visualiser** les données
du banc de test (Raspberry Pi + CSV). Chaque script possède un en‑tête
de documentation détaillant son usage.


## Sommaire rapide

- **`monitor_data_live.py`** — Tableau de bord *live* (Dash/Plotly) qui détecte le dernier CSV
  disponible sur plusieurs IP, rafraîchit périodiquement et affiche Température & Humidité.  
- **`plot_Température_Humidité.py`** — Figure Plotly d’**aperçu global** du test (3 sous‑graphes :
  Température/Heater, Humidité/Humidifier, Recirculation/Intake/Ammoniac).  
- **`plot_evaporation.py`** — Analyse de l’**évaporation** : masse perdue (kg), taux d’évaporation (kg/h),
  température/humidité vs cibles, avec export HTML.  
- **`plot_live_data.py`** — Visualisations **Matplotlib** en local (température, humidité, recirculation)
  à partir du dernier CSV détecté (ou saisi).  
- **`merge_test_files.py`** — **Fusion** de plusieurs CSV d’un même test en un seul fichier chronologique.  
- **`open_http_in_browser.py`** — Ouvre dans le navigateur la **première IP** de serveur HTTP qui répond.  
- **`utils.py`** — Fonctions utilitaires (détection du dernier fichier, cache, parsing d’horodatage, etc.).


## Installation rapide

```bash
# Python >= 3.10 recommandé
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -U pip
pip install pandas requests beautifulsoup4 plotly dash matplotlib
```

> Remarque : Matplotlib est surtout utilisé par `plot_live_data.py`. Dash/Plotly sont requis
> pour l’app *live* et les figures interactives.

## Utilisation express

- **Live dashboard** : `python monitor_data_live.py` → navigateur sur `http://127.0.0.1:8050/`
- **Aperçu global** : `python plot_Température_Humidité.py` (puis indiquer fichier + dossier de sortie)
- **Évaporation** : `python plot_evaporation.py` (fichier CSV + dossier de sortie demandés)
- **Plots Matplotlib locaux** : `python plot_live_data.py`
- **Fusion CSV** : `python merge_test_files.py` (saisir dossier + préfixe)
- **Ouvrir serveur HTTP** : `python open_http_in_browser.py`

## Format de temps & conventions

- Les CSV contiennent souvent `Timestamp` = secondes écoulées depuis le début de test.
- L’heure de départ est extraite du **nom de fichier** (`YYYY-M-D_HhMmSs`). Certains scripts ajoutent
  un **décalage de +1 h** pour compenser l’horloge du Pi.
- Les figures Plotly sont sauvegardées en **HTML** pour un partage facile.

## Arborescence (principale)

```
/cached_data            # cache local pour les CSV récupérés
monitor_data_live.py
plot_Température_Humidité.py
plot_evaporation.py
plot_live_data.py
merge_test_files.py
open_http_in_browser.py
utils.py
```

## Astuces

- Si une IP change, `monitor_data_live.py` et `open_http_in_browser.py` testent **plusieurs IP**.
- Ajustez `PLOT_WINDOW`, `RESAMPLE_RULE` (live) ou `OVERVIEW_*` (aperçu global) selon vos besoins.
- Les *markers* de redémarrage sont ajoutés via `utils.annotate_code_updates` dès qu’un saut de temps > 120 s est détecté.
