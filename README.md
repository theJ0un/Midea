# Surveillance de stock — Midea PortaSplit 3,5 kW / 12000 BTU

Outil personnel qui vérifie périodiquement une liste de sites officiels et
t'envoie **une seule notification email** dès que le PortaSplit repasse en
stock quelque part — sans avoir à créer une alerte manuelle sur chaque site.

## 1. Installation (une seule fois)

```bash
cd portasplit_monitor
python3 -m venv venv
source venv/bin/activate          # sous Windows : venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium       # télécharge le navigateur headless utilisé pour lire les pages
```

## 2. Configuration de l'email

```bash
cp .env.example .env
```

Édite `.env` avec tes identifiants SMTP. Avec Gmail : active la validation
en 2 étapes puis génère un **mot de passe d'application** dédié (ne mets
jamais ton mot de passe principal) :
https://myaccount.google.com/apppasswords

Le script charge `.env` automatiquement si tu lances via le wrapper ci-dessous,
ou exporte les variables toi-même avant de lancer `main.py`.

Sous Linux/Mac, le plus simple est d'ajouter en haut de ton cron :
```
set -a; source /chemin/vers/portasplit_monitor/.env; set +a
```
(voir exemple de crontab plus bas).

## 3. Premier lancement

```bash
python main.py --dry-run
```

Regarde la sortie : ça t'indique le statut détecté (`IN_STOCK`,
`OUT_OF_STOCK`, `UNKNOWN`) pour chaque site. Si un site affiche `UNKNOWN`,
ouvre sa page produit dans ton navigateur, regarde comment est formulée la
rupture ou la disponibilité (ex. "Produit indisponible", "Être alerté"),
et ajoute ce texte exact (en minuscules) dans `sites.json`, dans
`out_of_stock_keywords` ou `in_stock_keywords`.

Une fois les mots-clés corrects, initialise l'état pour ne pas recevoir une
alerte immédiate sur un site déjà en stock au moment du lancement :

```bash
python main.py    # premier vrai lancement, sans --dry-run
```

## 4. Automatisation (cron)

```bash
crontab -e
```

Ajoute (vérification toutes les 20 minutes) :

```
*/20 * * * * cd /chemin/vers/portasplit_monitor && set -a && source .env && set +a && ./venv/bin/python main.py >> cron.log 2>&1
```

Sous Windows, utilise le Planificateur de tâches avec une action
`venv\Scripts\python.exe main.py`, déclenchée toutes les 20 minutes.

**Ne descends pas en dessous de 10-15 minutes entre deux vérifications** :
au-delà, tu risques de te faire bloquer par certains sites (ils surveillent
les visites trop fréquentes depuis une même IP).

## 5. Ajouter / retirer un site

Édite `sites.json`. Chaque entrée a besoin :
- `name` : nom affiché dans les logs/emails
- `url` : URL de la fiche produit exacte
- `out_of_stock_keywords` : liste de textes (en minuscules) qui signalent une rupture
- `in_stock_keywords` : liste de textes qui signalent une disponibilité

Deux entrées (Darty, Boulanger, Cdiscount) pointent pour l'instant vers une
page de recherche/catégorie car je n'ai pas trouvé de fiche produit dédiée
stable au moment de la config — remplace `url` par le lien produit exact dès
que tu le retrouves (le stock change souvent de référence chez ces enseignes).

## 6. Limites à connaître

- La détection repose sur la présence de certains mots dans la page. Les
  sites changent parfois leur mise en page : si tu arrêtes de recevoir des
  logs cohérents pour un site, relance `--dry-run` et ajuste les mots-clés.
- Ce script respecte les pages telles qu'elles sont publiquement affichées
  (pas de contournement de protection anti-bot, pas de CAPTCHA à casser).
  Si un site bloque le script, la solution est d'espacer les vérifications,
  pas de forcer le passage.
- Alternative sans rien installer : le site climradar.fr propose déjà une
  alerte email agrégée sur ~9 enseignes pour ce produit, actualisée toutes
  les 10 minutes — utile en complément ou en secours si tu ne veux pas
  faire tourner ce script en continu.
