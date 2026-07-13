#!/usr/bin/env python3
"""
Surveillance du retour en stock du Midea PortaSplit sur une liste de sites officiels.

Usage:
    python main.py            # vérifie tous les sites et notifie les nouveaux retours en stock
    python main.py --dry-run  # affiche les statuts sans envoyer de notification ni sauvegarder l'état
    python main.py --reset    # remet l'état à zéro (utile après un premier lancement pour ne pas
                               # être submergé si un site est déjà en stock)

Planifie ce script avec cron (Linux/Mac) ou le Planificateur de tâches (Windows). Ne descends pas
sous 10 minutes en local : les sites peuvent bloquer une IP qui les sollicite trop souvent.
"""

import json
import os
import sys
import time
import random
import smtplib
import argparse
from email.mime.text import MIMEText
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SITES_FILE = BASE_DIR / "sites.json"
STATE_FILE = BASE_DIR / "state.json"
LOG_FILE = BASE_DIR / "monitor.log"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

STATUS_IN_STOCK = "IN_STOCK"
STATUS_OUT_OF_STOCK = "OUT_OF_STOCK"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_ERROR = "ERROR"


def log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_site_status(page, site: dict) -> str:
    """Charge la page et retourne IN_STOCK / OUT_OF_STOCK / UNKNOWN."""
    page.goto(site["url"], wait_until="domcontentloaded", timeout=45000)
    # Laisse largement le temps au JS de finir de peupler la page
    # (bouton stock, bandeau rupture, etc. arrivent souvent après le chargement initial)
    page.wait_for_timeout(6000)

    text = page.inner_text("body").lower()

    for kw in site.get("out_of_stock_keywords", []):
        if kw.lower() in text:
            return STATUS_OUT_OF_STOCK

    for kw in site.get("in_stock_keywords", []):
        if kw.lower() in text:
            return STATUS_IN_STOCK

    return STATUS_UNKNOWN

def send_email_notification(subject: str, body: str) -> None:
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    email_from = os.environ.get("EMAIL_FROM", smtp_user)
    email_to = os.environ.get("EMAIL_TO")

    if not all([smtp_host, smtp_user, smtp_password, email_to]):
        log("ATTENTION: variables SMTP manquantes, notification email non envoyée. "
            "Vérifie ton fichier .env (voir README).")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(email_from, [email_to], msg.as_string())
        log(f"Email envoyé à {email_to} : {subject}")
    except Exception as e:
        log(f"ERREUR envoi email : {e}")


def send_ntfy_notification(title: str, body: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log("ATTENTION: NTFY_TOPIC manquant, notification push non envoyée.")
        return
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={
                "Title": title.encode("utf-8"),
                "Priority": "urgent",
                "Tags": "rotating_light",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        log("Notification push envoyée.")
    except Exception as e:
        log(f"ERREUR envoi notification push : {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="N'envoie pas de notification, ne sauvegarde pas l'état")
    parser.add_argument("--reset", action="store_true", help="Réinitialise l'état stocké (state.json)")
    args = parser.parse_args()

    config = load_json(SITES_FILE, {"sites": [], "product_name": "Produit"})
    sites = config.get("sites", [])
    product_name = config.get("product_name", "Produit")

    if args.reset:
        save_json(STATE_FILE, {})
        log("État réinitialisé (state.json vidé).")
        return

    state = load_json(STATE_FILE, {})
    newly_in_stock = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=random.choice(USER_AGENTS), locale="fr-FR")
        page = context.new_page()

        for site in sites:
            name = site["name"]
            try:
                status = check_site_status(page, site)
            except Exception as e:
                status = STATUS_ERROR
                log(f"{name}: erreur de chargement ({e})")
            else:
                log(f"{name}: {status}")

            previous_status = state.get(name, {}).get("status")

            if status == STATUS_IN_STOCK and previous_status != STATUS_IN_STOCK:
                newly_in_stock.append(site)

            if not args.dry_run:
                state[name] = {
                    "status": status,
                    "last_checked": datetime.now(timezone.utc).isoformat(),
                    "url": site["url"],
                }

            # Pause polie entre deux sites pour ne pas les solliciter en rafale
            time.sleep(random.uniform(3, 7))

        browser.close()

    if not args.dry_run:
        save_json(STATE_FILE, state)

    if newly_in_stock:
        lines = [f"{product_name} vient de repasser en stock sur :", ""]
        for site in newly_in_stock:
            lines.append(f"- {site['name']} : {site['url']}")
        body = "\n".join(lines)
        log(body)
        if not args.dry_run:
            send_email_notification(f"🟢 {product_name} en stock !", body)
            send_ntfy_notification(f"🟢 {product_name} en stock !", body)
    else:
        log("Aucun nouveau retour en stock détecté.")


if __name__ == "__main__":
    main()
