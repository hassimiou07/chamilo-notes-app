"""Collecteur de mails a lancer depuis le reseau de la maison.

Le serveur IMAP de l'universite coupe les connexions venant d'un
hebergeur, donc l'app deployee ne peut pas lire la messagerie. Ce script
fait le travail depuis ta machine, ou l'IMAP repond, et depose le
resultat dans le meme stockage Upstash que l'app lit deja. L'app affiche
alors les mails sans jamais toucher a l'IMAP.

A lancer en tache planifiee (voir run_collect_mail.bat).

Usage :
    python collect_mail.py              # collecte et envoie les notifications
    python collect_mail.py --no-push    # collecte sans notifier
    python collect_mail.py --local      # ecrit dans les fichiers locaux
                                        # (test, sans toucher a Upstash)
"""
import argparse
import sys

import storage
from app import MAIL_STATE_KEY, load_config, send_push_to_all
from mail_client import get_recent_messages
from storage import load_json, save_json


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
        "Sans eux, les mails seraient ecrits dans des fichiers locaux et l'app\n"
        "deployee ne les verrait jamais. Reprends les deux valeurs depuis la\n"
        "configuration de ton hebergeur, puis relance :\n"
        "    set UPSTASH_REDIS_REST_URL=...\n"
        "    set UPSTASH_REDIS_REST_TOKEN=...\n"
        "Ou lance avec --local pour un simple test hors ligne."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-push", action="store_true", help="ne pas envoyer de notification"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="ecrire dans les fichiers locaux au lieu d'Upstash (test)",
    )
    args = parser.parse_args()

    destination = verifier_destination(args.local)
    cfg = load_config()

    try:
        messages = get_recent_messages(cfg)
    except Exception as exc:
        print(f"Collecte impossible : {exc}", file=sys.stderr)
        return 1

    anciens = load_json(MAIL_STATE_KEY, [])
    ids_connus = {m["id"] for m in anciens}
    nouveaux = [m for m in messages if m["id"] not in ids_connus]

    save_json(MAIL_STATE_KEY, messages)
    print(f"{len(messages)} message(s) deposes dans {destination}, {len(nouveaux)} nouveau(x).")

    # Au tout premier passage, tout est "nouveau" : on n'envoie rien pour
    # ne pas noyer le telephone sous trente notifications.
    premier_passage = not anciens
    if premier_passage:
        print("Premier passage : aucune notification envoyee.")
        return 0

    if args.no_push or not nouveaux:
        return 0

    for message in nouveaux:
        send_push_to_all(
            f"Nouveau mail : {message['subject']}",
            f"De : {message['from']}\n{message['body'][:300]}",
            notif_type="mail",
        )
    print(f"{len(nouveaux)} notification(s) envoyee(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
