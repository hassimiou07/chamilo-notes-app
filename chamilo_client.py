"""Logique de connexion CAS + extraction des notes, partagee entre
le script en ligne de commande et l'appli web.

Note sur le HTML de la fiche etudiant : les <td> ne sont pas fermes.
Le parseur les imbrique donc les uns dans les autres au lieu de les
mettre cote a cote, ce qui faisait fusionner les colonnes (une "note"
a 71710 au lieu des coefficients 7, 17 et 10). flatten_cells remet la
ligne a plat, et own_text ne lit que le texte propre d'une cellule.
"""
import re

import requests
from bs4 import BeautifulSoup

EPREUVE_A_VENIR = "epreuve a venir"
NB_UE = 6


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
    if resp.status_code in (401, 403):
        raise RuntimeError(
            "Le CAS a refuse les identifiants (mot de passe UGA change ou expire ?). "
            "Mets a jour username/password dans la configuration."
        )
    resp.raise_for_status()


def fetch_fiche_html(session: requests.Session, cfg: dict) -> str:
    resp = session.get(cfg["fiche_url"], timeout=20)
    resp.raise_for_status()
    if "Identifiant" in resp.text and "password" in resp.text.lower():
        raise RuntimeError("Echec de l'authentification - verifie username/password.")
    return resp.text


# ---------------------------------------------------------------- cellules


def own_text(cell) -> str:
    """Texte d'une cellule, sans celui des cellules qu'elle contient par
    accident (consequence des <td> non fermes dans la fiche)."""
    morceaux = []
    for chaine in cell.strings:
        parent = chaine.parent
        imbriquee = False
        while parent is not None and parent is not cell:
            if parent.name in ("td", "th"):
                imbriquee = True
                break
            parent = parent.parent
        if not imbriquee:
            texte = chaine.strip()
            if texte:
                morceaux.append(texte)
    return " ".join(morceaux).replace("\xa0", " ").strip()


def flatten_cells(noeud) -> list:
    """Toutes les cellules d'une ligne, dans l'ordre d'affichage, meme
    quand le HTML les a imbriquees les unes dans les autres."""
    cellules = []
    for cell in noeud.find_all(["td", "th"], recursive=False):
        cellules.append(cell)
        cellules.extend(flatten_cells(cell))
    return cellules


def own_find(cell, nom: str):
    """Premier <nom> appartenant a cette cellule et pas a une cellule
    imbriquee derriere elle."""
    for trouve in cell.find_all(nom):
        parent = trouve.parent
        imbrique = False
        while parent is not None and parent is not cell:
            if parent.name in ("td", "th"):
                imbrique = True
                break
            parent = parent.parent
        if not imbrique:
            return trouve
    return None


def row_texts(tr) -> list[str]:
    return [own_text(c) for c in flatten_cells(tr)]


def extract_raw_rows(html: str) -> list[str]:
    """Conserve pour compatibilite : une ligne = ses cellules jointes."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        texte = " | ".join(row_texts(tr)).strip()
        if texte.strip(" |"):
            rows.append(texte)
    return rows


# ---------------------------------------------------------------- en-tete

ENTETE_RE = re.compile(r"BUT\s*(\d)A\s*S(\d)\s*([0-9]+[.,][0-9]+)?")
BLOC_RE = re.compile(r"^([RS])(\d+)\s*\((\d+)\)$")
MODULE_RE = re.compile(r"^((?:R|SAE|P)\d+\.\d+(?:\([0-9A-Z]+\))?)")


def parse_entete(soup) -> dict:
    """Annee, semestre et moyenne generale depuis la premiere ligne
    ('BARRY Mamadou / BUT 2A S3 12,18')."""
    premiere = soup.find("tr")
    texte = " ".join(row_texts(premiere)) if premiere else ""
    m = ENTETE_RE.search(texte)
    if not m:
        return {"annee": None, "semestre": None, "moyenne_generale": None}
    return {
        "annee": int(m.group(1)),
        "semestre": int(m.group(2)),
        "moyenne_generale": m.group(3),
    }


def looks_numeric(valeur: str) -> bool:
    return bool(valeur) and valeur.replace(",", "").replace(".", "").isdigit()


# ---------------------------------------------------------------- modules


def parse_modules(soup) -> list[dict]:
    """Une entree par module (R3.01, SAE3.01(1B)...) avec ses epreuves
    et son poids dans chacune des 6 UE."""
    table = soup.find("table")
    if table is None:
        return []

    modules = []
    bloc_courant = None

    for tr in table.find_all("tr"):
        cellules = flatten_cells(tr)
        if len(cellules) < 6:
            continue

        textes = [own_text(c) for c in cellules]

        # Certaines lignes ouvrent un bloc ("R3 (360)", "S3 (240)") : cette
        # cellule a un rowspan et n'apparait que sur la premiere ligne.
        bloc = BLOC_RE.match(textes[0])
        if bloc:
            bloc_courant = {"type": bloc.group(1), "coef_total": int(bloc.group(3))}
            cellules = cellules[1:]
            textes = textes[1:]

        if len(cellules) < 6:
            continue

        cell_module = cellules[0]
        libelle = textes[0]
        if not MODULE_RE.match(libelle.replace(" ", "")):
            continue

        balise_code = own_find(cell_module, "b")
        balise_nom = own_find(cell_module, "i")
        lien = own_find(cell_module, "a")

        code = own_text(balise_code) if balise_code else libelle.split()[0]
        nom = own_text(balise_nom) if balise_nom else ""
        if not nom:
            nom = libelle[len(code):].strip()

        absences = textes[1]
        epreuves = parse_epreuves(cellules[2], textes[2], textes[3], textes[4])
        moyenne = textes[5]

        coefs_ue = {}
        for i in range(NB_UE):
            index = 6 + i
            valeur = textes[index].strip() if index < len(textes) else ""
            if looks_numeric(valeur):
                coefs_ue[i + 1] = int(float(valeur.replace(",", ".")))

        modules.append(
            {
                "code": code,
                "nom": nom,
                "bloc": bloc_courant["type"] if bloc_courant else None,
                "url": lien.get("href") if lien else None,
                "absences": absences,
                "epreuves": epreuves,
                "moyenne": moyenne,
                "coefs_ue": coefs_ue,
                "note_attendue": all(e["note"] == "" for e in epreuves),
            }
        )

    return modules


def parse_epreuves(cell_intitule, intitule: str, coef: str, note: str) -> list[dict]:
    """Les epreuves d'un module. Tant qu'aucune note n'est tombee, la
    fiche affiche 'epreuve·s a venir' a la place du tableau."""
    if "venir" in intitule.lower():
        return []

    # Plusieurs epreuves sont empilees dans la meme cellule, separees par
    # des <br>. On aligne intitules / coefs / notes ligne a ligne.
    intitules = [t for t in lignes_de(cell_intitule) if t] or [intitule]
    coefs = coef.split()
    notes = note.split()

    epreuves = []
    for i, titre in enumerate(intitules):
        epreuves.append(
            {
                "intitule": titre,
                "coef": coefs[i] if i < len(coefs) else "",
                "note": notes[i] if i < len(notes) else "",
            }
        )
    return epreuves


def lignes_de(cell) -> list[str]:
    """Decoupe le texte propre d'une cellule sur ses <br>."""
    lignes = []
    courante = []
    for enfant in cell.children:
        nom = getattr(enfant, "name", None)
        if nom in ("td", "th"):
            break
        if nom == "br":
            lignes.append(" ".join(courante).strip())
            courante = []
            continue
        texte = enfant.get_text(" ", strip=True) if hasattr(enfant, "get_text") else str(enfant).strip()
        if texte:
            courante.append(texte)
    if courante:
        lignes.append(" ".join(courante).strip())
    return [l for l in lignes if l]


# ---------------------------------------------------------------- UE


def parse_ue_averages(soup_or_rows, semestre: int = 2) -> list[dict]:
    """Moyennes des 6 UE, sur la ligne qui commence par 'Intitule'.
    Accepte soit la soupe, soit l'ancienne liste de lignes texte."""
    if isinstance(soup_or_rows, list):
        lignes = soup_or_rows
    else:
        lignes = [" | ".join(row_texts(tr)) for tr in soup_or_rows.find_all("tr")]

    for ligne in lignes:
        cellules = [c.strip() for c in ligne.split(" | ")]
        if len(cellules) >= 9 and cellules[0].startswith("Intitul"):
            valeurs = cellules[3:9]
            if all(looks_numeric(v) for v in valeurs):
                return [
                    {"nom": f"UE{semestre}.{i + 1}", "moyenne": valeurs[i]}
                    for i in range(NB_UE)
                ]
    return []


# ---------------------------------------------------------------- API


def parse_fiche(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    entete = parse_entete(soup)
    modules = parse_modules(soup)
    semestre = entete["semestre"] or detect_semestre_depuis_modules(modules) or 2

    for module in modules:
        module["ue"] = {
            f"UE{semestre}.{num}": coef for num, coef in module["coefs_ue"].items()
        }

    return {
        "annee": entete["annee"],
        "semestre": semestre,
        "moyenne_generale": entete["moyenne_generale"],
        "modules": modules,
        "ue_averages": parse_ue_averages(soup, semestre),
        "grades": grades_depuis_modules(modules),
    }


def detect_semestre_depuis_modules(modules: list[dict]):
    for module in modules:
        m = re.match(r"^(?:R|SAE|P)(\d)", module["code"])
        if m:
            return int(m.group(1))
    return None


def grades_depuis_modules(modules: list[dict]) -> list[dict]:
    """Aplatit en la liste de notes reellement tombees, format historique
    attendu par l'appli web et les notifications."""
    grades = []
    for module in modules:
        for epreuve in module["epreuves"]:
            if not epreuve["note"]:
                continue
            grades.append(
                {
                    "matiere": f"{module['code']} {module['nom']}".strip(),
                    "epreuve": epreuve["intitule"],
                    "coef": epreuve["coef"],
                    "note": epreuve["note"],
                    "moyenne": module["moyenne"],
                    "raw": f"{module['code']}|{epreuve['intitule']}|{epreuve['coef']}|{epreuve['note']}",
                }
            )
    return grades


def detect_semestre(grades: list[dict]) -> int:
    """Conserve pour compatibilite avec check_notes.py."""
    for grade in grades:
        m = re.match(r"^(?:R|SAE|P)(\d)", grade.get("matiere", ""))
        if m:
            return int(m.group(1))
    return 2


def get_fiche_full(cfg: dict) -> dict:
    session = requests.Session()
    cas_login(session, cfg)
    return parse_fiche(fetch_fiche_html(session, cfg))


def get_fiche_data(cfg: dict) -> tuple[list[dict], list[dict]]:
    """(notes, moyennes des 6 UE) - signature historique."""
    fiche = get_fiche_full(cfg)
    return fiche["grades"], fiche["ue_averages"]


def get_all_grades(cfg: dict) -> list[dict]:
    return get_fiche_full(cfg)["grades"]
