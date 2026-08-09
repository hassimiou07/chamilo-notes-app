"""Recuperation des emails via IMAP (webmail Partage/Renater - UGA)."""
import email
import email.message
import imaplib
from email.header import decode_header
from email.utils import parsedate_to_datetime


def _decode(value: str) -> str:
    if not value:
        return ""
    # Deplie les en-tetes coupes sur plusieurs lignes (RFC 2822) avant
    # de decoder les mots encodes (=?charset?Q/B?...?=), sinon la regex
    # de decode_header ne les reconnait pas.
    unfolded = value.replace("\r\n", "").replace("\n", "")
    parts = decode_header(unfolded)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _get_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        text_plain = None
        text_html = None
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            if ctype == "text/plain" and text_plain is None:
                text_plain = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                text_plain = text_plain.decode(charset, errors="replace")
            elif ctype == "text/html" and text_html is None:
                text_html = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                text_html = text_html.decode(charset, errors="replace")
        if text_plain:
            return text_plain.strip()
        if text_html:
            import re
            return re.sub("<[^<]+?>", " ", text_html).strip()
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload is None:
            return ""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()


def get_recent_messages(cfg: dict, limit: int = 30) -> list[dict]:
    conn = imaplib.IMAP4_SSL(cfg["imap_host"], cfg.get("imap_port", 993))
    try:
        conn.login(cfg["email_username"], cfg["email_password"])
        conn.select("INBOX")

        status, data = conn.search(None, "ALL")
        if status != "OK":
            return []

        ids = data[0].split()
        ids = ids[-limit:] if len(ids) > limit else ids
        ids.reverse()

        messages = []
        for msg_id in ids:
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            date_str = msg.get("Date", "")
            try:
                date_iso = parsedate_to_datetime(date_str).isoformat()
            except Exception:
                date_iso = date_str

            message_id = msg.get("Message-ID", str(msg_id))
            body = _get_body(msg)

            messages.append({
                "id": message_id,
                "from": _decode(msg.get("From", "")),
                "subject": _decode(msg.get("Subject", "(sans objet)")),
                "date": date_iso,
                "body": body[:20000],
            })

        return messages
    finally:
        try:
            conn.logout()
        except Exception:
            pass
