"""Stockage persistant via Upstash Redis (REST API), avec repli sur
des fichiers JSON locaux si les identifiants Upstash ne sont pas configures
(pratique pour les tests en local)."""
import json
import os
from pathlib import Path

import requests

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

BASE_DIR = Path(__file__).parent


def _headers():
    return {"Authorization": f"Bearer {UPSTASH_TOKEN}"}


def load_json(key: str, default):
    if UPSTASH_URL and UPSTASH_TOKEN:
        resp = requests.get(f"{UPSTASH_URL}/get/{key}", headers=_headers(), timeout=10)
        resp.raise_for_status()
        result = resp.json().get("result")
        if result is None:
            return default
        return json.loads(result)
    else:
        path = BASE_DIR / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return default


def save_json(key: str, data) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    if UPSTASH_URL and UPSTASH_TOKEN:
        resp = requests.post(
            f"{UPSTASH_URL}/set/{key}",
            headers=_headers(),
            data=payload.encode("utf-8"),
            timeout=10,
        )
        resp.raise_for_status()
    else:
        path = BASE_DIR / f"{key}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
