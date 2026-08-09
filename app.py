import json
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from pywebpush import webpush, WebPushException

from chamilo_client import get_fiche_data
from mail_client import get_recent_messages

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "grades_state.json"
UE_STATE_PATH = BASE_DIR / "ue_state.json"
MAIL_STATE_PATH = BASE_DIR / "mail_state.json"
MAIL_READ_PATH = BASE_DIR / "mail_read.json"
SUBS_PATH = BASE_DIR / "subscriptions.json"

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:example@example.com")
CHECK_SECRET = os.environ.get("CHECK_SECRET", "")

app = Flask(__name__, static_folder="static", static_url_path="")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "username": os.environ["CHAMILO_USERNAME"],
        "password": os.environ["CHAMILO_PASSWORD"],
        "fiche_url": os.environ.get(
            "CHAMILO_FICHE_URL",
            "https://iut2-dg-scolarite.univ-grenoble-alpes.fr/app/ficheEtudiant.php",
        ),
        "cas_login_url": os.environ.get(
            "CHAMILO_CAS_URL", "https://authentification.univ-grenoble-alpes.fr/login"
        ),
        "email_username": os.environ.get("EMAIL_USERNAME", ""),
        "email_password": os.environ.get("EMAIL_PASSWORD", ""),
        "imap_host": os.environ.get("IMAP_HOST", "imap.partage.renater.fr"),
        "imap_port": int(os.environ.get("IMAP_PORT", "993")),
    }


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/vapid-public-key")
def vapid_public_key():
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})


@app.get("/api/grades")
def api_grades():
    grades = load_json(STATE_PATH, [])
    return jsonify({"grades": grades})


@app.get("/api/ue-averages")
def api_ue_averages():
    ue_averages = load_json(UE_STATE_PATH, [])
    return jsonify({"ue_averages": ue_averages})


@app.get("/api/messages")
def api_messages():
    messages = load_json(MAIL_STATE_PATH, [])
    read_ids = set(load_json(MAIL_READ_PATH, []))
    for m in messages:
        m["unread"] = m["id"] not in read_ids
    return jsonify({"messages": messages})


@app.post("/api/messages/read")
def api_mark_read():
    body = request.get_json(force=True)
    msg_id = body.get("id")
    if not msg_id:
        return jsonify({"error": "id manquant"}), 400
    read_ids = set(load_json(MAIL_READ_PATH, []))
    read_ids.add(msg_id)
    save_json(MAIL_READ_PATH, sorted(read_ids))
    return jsonify({"ok": True})


@app.post("/api/subscribe")
def api_subscribe():
    subscription = request.get_json(force=True)
    subs = load_json(SUBS_PATH, [])
    if subscription not in subs:
        subs.append(subscription)
        save_json(SUBS_PATH, subs)
    return jsonify({"ok": True})


def send_push_to_all(title: str, body: str, notif_type: str = "general") -> None:
    icon = "icons/icon-mail.png" if notif_type == "mail" else "icons/icon-note.png"
    subs = load_json(SUBS_PATH, [])
    still_valid = []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps({"title": title, "body": body, "type": notif_type, "icon": icon}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL},
            )
            still_valid.append(sub)
        except WebPushException as exc:
            print("Push echoue pour un abonnement (probablement expire) :", exc)
    save_json(SUBS_PATH, still_valid)


@app.post("/api/test-push")
def api_test_push():
    if CHECK_SECRET and request.headers.get("X-Check-Secret") != CHECK_SECRET:
        return jsonify({"error": "unauthorized"}), 401
    send_push_to_all("Nouvelle note : R2.99Test", "Epreuve : Test - Note : 18,00/20", notif_type="note")
    send_push_to_all("Nouveau mail : Test messagerie", "De : Test <test@example.com>\nCeci est un test.", notif_type="mail")
    subs_count = len(load_json(SUBS_PATH, []))
    return jsonify({"sent_to": subs_count})


@app.post("/api/check")
def api_check():
    """A appeler periodiquement (cron externe) pour verifier les notes
    et notifier les abonnes en cas de changement."""
    if CHECK_SECRET and request.headers.get("X-Check-Secret") != CHECK_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    cfg = load_config()
    current_grades, ue_averages = get_fiche_data(cfg)
    previous_grades = load_json(STATE_PATH, [])

    previous_raw = {g["raw"] for g in previous_grades}
    new_grades = [g for g in current_grades if g["raw"] not in previous_raw]

    save_json(STATE_PATH, current_grades)
    save_json(UE_STATE_PATH, ue_averages)

    is_first_run = len(previous_grades) == 0
    if not is_first_run:
        for grade in new_grades:
            title = f"Nouvelle note : {grade['matiere']}"
            body = (
                f"{grade['epreuve']} - Note : {grade['note']}/20 (coef {grade['coef']})\n"
                f"Ta moyenne dans cette ressource : {grade['moyenne']}"
            )
            send_push_to_all(title, body, notif_type="note")

    current_messages = get_recent_messages(cfg)
    previous_messages = load_json(MAIL_STATE_PATH, [])
    previous_ids = {m["id"] for m in previous_messages}
    new_messages = [m for m in current_messages if m["id"] not in previous_ids]

    save_json(MAIL_STATE_PATH, current_messages)

    mail_is_first_run = len(previous_messages) == 0
    if not mail_is_first_run:
        for msg in new_messages:
            title = f"Nouveau mail : {msg['subject']}"
            body = f"De : {msg['from']}\n{msg['body'][:300]}"
            send_push_to_all(title, body, notif_type="mail")

    return jsonify({
        "new_grades": len(new_grades),
        "first_run": is_first_run,
        "new_messages": len(new_messages),
        "mail_first_run": mail_is_first_run,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
