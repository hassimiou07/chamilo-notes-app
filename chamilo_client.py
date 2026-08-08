"""Logique de connexion CAS + extraction des notes, partagee entre
le script en ligne de commande et l'appli web."""
import requests
from bs4 import BeautifulSoup


def cas_login(session: requests.Session, cfg: dict) -> None:
    params = {"service": cfg["fiche_url"]}
    login_page = session.get(cfg["cas_login_url"], params=params, timeout=20)
    login_page.raise_for_status()

    soup = BeautifulSoup(login_page.text, "html.parser")
    form = soup.find("form")
    if form is None:
        raise RuntimeError("Formulaire de login CAS introuvable.")

    payload = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        payload[name] = inp.get("value", "")

    payload["username"] = cfg["username"]
    payload["password"] = cfg["password"]

    action = form.get("action") or cfg["cas_login_url"]
    post_url = requests.compat.urljoin(login_page.url, action)

    resp = session.post(post_url, data=payload, timeout=20)
    resp.raise_for_status()


def fetch_fiche_html(session: requests.Session, cfg: dict) -> str:
    resp = session.get(cfg["fiche_url"], timeout=20)
    resp.raise_for_status()
    if "Identifiant" in resp.text and "password" in resp.text.lower():
        raise RuntimeError("Echec de l'authentification - verifie username/password.")
    return resp.text


def extract_raw_rows(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        text = " | ".join(cell.get_text(strip=True) for cell in tr.find_all(["td", "th"]))
        text = text.strip()
        if text:
            rows.append(text)
    return rows


def parse_grade_row(row: str):
    cells = [c.strip() for c in row.split(" | ")]
    if len(cells) < 6:
        return None

    # Certaines lignes contiennent une cellule fantome en tete, artefact
    # d'un tableau imbrique dans le HTML : son texte englobe deja celui
    # de la cellule suivante. On la retire pour ne pas decaler les colonnes.
    if len(cells) > 6 and len(cells[0]) > 35 and cells[1] and cells[1] in cells[0]:
        cells = cells[1:]

    matiere, _, epreuve, coef, note, moyenne = cells[:6]

    HEADER_WORDS = {"Intitulé", "Module", "Type(coef)", "Matiere", "Matière"}
    if matiere in HEADER_WORDS or epreuve in HEADER_WORDS:
        return None

    def looks_numeric(v: str) -> bool:
        return bool(v) and v.replace(",", "").replace(".", "").isdigit()

    if not (looks_numeric(coef) and looks_numeric(note)):
        return None

    return {
        "matiere": matiere,
        "epreuve": epreuve,
        "coef": coef,
        "note": note,
        "moyenne": moyenne,
        "raw": row,
    }


def get_all_grades(cfg: dict) -> list[dict]:
    """Se connecte a Chamilo et renvoie la liste structuree des notes."""
    session = requests.Session()
    cas_login(session, cfg)
    html = fetch_fiche_html(session, cfg)
    raw_rows = extract_raw_rows(html)

    grades = []
    for row in raw_rows:
        grade = parse_grade_row(row)
        if grade:
            grades.append(grade)
    return grades
