"""Collecteur d'offres JobTeaser a lancer depuis ta machine.

JobTeaser exige d'etre connecte (compte JobTeaser, pas forcement le
meme mot de passe que le CAS UGA) et bloque en plus toute requete qui
n'est pas un vrai navigateur ("Security checkup"). La solution : te
connecter une fois dans un navigateur pilote par ce script (--login),
la session est alors sauvegardee localement, et les passages suivants
la reutilisent en arriere-plan (headless), sans redemander de mot de
passe. Meme principe que collect_mail.py a l'epoque pour les mails :
le resultat est depose dans le meme stockage Upstash que l'app lit.

Installation (une fois) :
    pip install -r requirements-local.txt
    playwright install chromium

Usage :
    python collect_jobteaser.py --login      # a faire une fois (et a
                                              # refaire si la session expire)
    python collect_jobteaser.py              # collecte et notifie
    python collect_jobteaser.py --no-push    # collecte sans notifier
    python collect_jobteaser.py --local      # fichiers locaux (test)
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

import storage
from app import JOBTEASER_OFFERS_KEY, load_config, send_push_to_all
from jobteaser_client import page_url, parse_offers
from storage import load_json, save_json

MAX_PAGES = 2
SESSION_PATH = Path(__file__).parent / "jobteaser_session.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def login_interactif(url: str) -> None:
    """Ouvre un vrai navigateur (visible) pour que l'utilisateur se
    connecte a la main, puis sauvegarde la session (cookies) pour les
    prochains passages en headless."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(user_agent=USER_AGENT, locale="fr-FR")
        page = context.new_page()
        page.goto(url, timeout=30000)
        print(
            "Connecte-toi a JobTeaser dans la fenetre qui vient de s'ouvrir.\n"
            "Une fois que tu vois la liste des offres (pas la page de connexion),\n"
            "reviens ici et appuie sur Entree."
        )
        input()
        context.storage_state(path=str(SESSION_PATH))
        browser.close()
    print(f"Session sauvegardee dans {SESSION_PATH}.")


def fetch_html(playwright, url: str) -> str:
    browser = playwright.chromium.launch(
        headless=True, args=["--disable-blink-features=AutomationControlled"]
    )
    try:
        context_kwargs = {"user_agent": USER_AGENT, "locale": "fr-FR"}
        if SESSION_PATH.exists():
            context_kwargs["storage_state"] = str(SESSION_PATH)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )
        page.goto(url, wait_until="networkidle", timeout=30000)
        return page.content()
    finally:
        browser.close()


def collect_offers(cfg: dict, max_pages: int = MAX_PAGES) -> list[dict]:
    if not SESSION_PATH.exists():
        raise RuntimeError(
            "Pas de session JobTeaser enregistree. Lance d'abord : "
            "python collect_jobteaser.py --login"
        )
    base_url = cfg["jobteaser_url"]
    offres = []
    vus = set()
    with sync_playwright() as playwright:
        for n in range(1, max_pages + 1):
            html = fetch_html(playwright, page_url(base_url, n))
            for offre in parse_offers(html, base_url):
                if offre["id"] in vus:
                    continue
                vus.add(offre["id"])
                offres.append(offre)
    return offres


def verifier_destination(autoriser_local: bool) -> str:
    """Sans identifiants Upstash, storage ecrit dans des fichiers locaux :
    le script tournerait sans rien envoyer a l'app deployee. On refuse
    plutot que de laisser croire que la collecte a servi a quelque chose."""
    if storage.UPSTASH_URL and storage.UPSTASH_TOKEN:
        return "Upstash"
    if autoriser_local:
        return "fichiers locaux"
    raise SystemExit(
        "UPSTASH_REDIS_REST_URL et UPSTASH_REDIS_REST_TOKEN ne sont pas definis.\n"
        "Sans eux, les offres seraient ecrites dans des fichiers locaux et l'app\n"
        "deployee ne les verrait jamais. Reprends les deux valeurs depuis la\n"
        "configuration de ton hebergeur, puis relance :\n"
        "    set UPSTASH_REDIS_REST_URL=...\n"
        "    set UPSTASH_REDIS_REST_TOKEN=...\n"
        "Ou lance avec --local pour un simple test hors ligne."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--login", action="store_true", help="connexion manuelle a refaire une fois"
    )
    parser.add_argument(
        "--no-push", action="store_true", help="ne pas envoyer de notification"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="ecrire dans les fichiers locaux au lieu d'Upstash (test)",
    )
    args = parser.parse_args()

    cfg = load_config()

    if args.login:
        login_interactif(page_url(cfg["jobteaser_url"], 1))
        return 0

    destination = verifier_destination(args.local)

    try:
        offres = collect_offers(cfg)
    except Exception as exc:
        print(f"Collecte impossible : {exc}", file=sys.stderr)
        return 1

    anciennes = load_json(JOBTEASER_OFFERS_KEY, [])
    ids_connus = {o["id"] for o in anciennes}
    nouvelles = [o for o in offres if o["id"] not in ids_connus]

    save_json(JOBTEASER_OFFERS_KEY, offres)
    print(f"{len(offres)} offre(s) deposee(s) dans {destination}, {len(nouvelles)} nouvelle(s).")

    # Au tout premier passage, tout est "nouveau" : on n'envoie rien pour
    # ne pas noyer le telephone de notifications.
    premier_passage = not anciennes
    if premier_passage:
        print("Premier passage : aucune notification envoyee.")
        return 0

    if args.no_push or not nouvelles:
        return 0

    for offre in nouvelles:
        details = " - ".join(p for p in (offre.get("entreprise"), offre.get("lieu")) if p)
        send_push_to_all(
            f"Nouvelle offre de stage : {offre['titre']}",
            "JobTeaser" + (f" ({details})" if details else ""),
            notif_type="offre",
        )
    print(f"{len(nouvelles)} notification(s) envoyee(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
