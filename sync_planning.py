"""Compile le planning de la semaine vers la page servie par l'appli.

La source de verite est planning/semaine-type.html, versionnee dans le
depot. Ce script l'emballe dans un document complet (doctype, charset,
viewport) et ecrit static/planning.html, que l'onglet Planning affiche
dans une iframe.

L'artefact publie sur claude.ai n'est pas recuperable en HTTP simple :
l'URL renvoie une coquille d'application et le contenu est charge en
JavaScript derriere l'authentification. On importe donc une nouvelle
version depuis un fichier (ou une URL qui sert vraiment du HTML).

Usage :
    python sync_planning.py                  # recompile depuis la source
    python sync_planning.py chemin.html      # importe puis recompile
    python sync_planning.py https://...      # idem depuis une URL
    python sync_planning.py --check          # dit si la page est a jour
"""
import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
SOURCE = BASE_DIR / "planning" / "semaine-type.html"
CIBLE = BASE_DIR / "static" / "planning.html"

ENTETE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<!-- Genere par sync_planning.py - ne pas editer a la main.
     La source est planning/semaine-type.html. -->
</head>
<body>
"""
PIED = "\n</body>\n</html>\n"


def est_document_complet(html: str) -> bool:
    debut = html.lstrip()[:200].lower()
    return debut.startswith("<!doctype") or debut.startswith("<html")


# Signatures de la coquille d'application claude.ai. Sans ce garde-fou,
# importer l'URL de l'artefact remplace le planning par une page vide.
MARQUEURS_COQUILLE = (
    "data-frame-uuid",
    "frame-shell",
    'content="Claude Artifact"',
    "assets-proxy.anthropic.com",
)

# Ce qu'un vrai planning contient forcement (classes de la feuille de style).
MARQUEURS_PLANNING = ("day-name", "day-head", "class=\"week\"")


def verifier_planning(html: str, origine: str) -> None:
    """Refuse d'importer autre chose qu'un planning, pour ne pas ecraser
    la source avec une page d'application ou un fichier quelconque."""
    coquille = [m for m in MARQUEURS_COQUILLE if m in html]
    if coquille:
        raise SystemExit(
            f"{origine} renvoie la coquille d'application claude.ai, pas le planning\n"
            f"(marqueur trouve : {coquille[0]}).\n"
            "Le contenu d'un artefact est charge en JavaScript derriere ton compte :\n"
            "enregistre la page depuis le navigateur, puis passe le fichier au script."
        )
    if not any(m in html for m in MARQUEURS_PLANNING):
        raise SystemExit(
            f"{origine} ne ressemble pas au planning : aucun des reperes attendus\n"
            f"({', '.join(MARQUEURS_PLANNING)}) n'y figure. Import annule."
        )


def lire_source(origine: str) -> str:
    """Lit le HTML depuis un fichier local ou une URL, et verifie que
    c'est bien un planning avant de le rendre."""
    if origine.startswith(("http://", "https://")):
        import requests

        reponse = requests.get(origine, timeout=30)
        reponse.raise_for_status()
        html = reponse.text
    else:
        chemin = Path(origine).expanduser()
        if not chemin.is_file():
            raise SystemExit(f"Fichier introuvable : {chemin}")
        html = chemin.read_text(encoding="utf-8")

    verifier_planning(html, origine)
    return html


def construire(fragment: str) -> str:
    """Un document complet reste tel quel ; un fragment est emballe."""
    if est_document_complet(fragment):
        return fragment if fragment.endswith("\n") else fragment + "\n"
    return ENTETE + fragment.strip() + PIED


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "origine",
        nargs="?",
        help="fichier ou URL a importer comme nouvelle source (optionnel)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verifie que static/planning.html est a jour, sans rien ecrire",
    )
    args = parser.parse_args()

    if args.origine:
        nouveau = lire_source(args.origine)
        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        ancien = SOURCE.read_text(encoding="utf-8") if SOURCE.exists() else ""
        if nouveau == ancien:
            print(f"Source inchangee ({SOURCE.name}).")
        else:
            if ancien:
                sauvegarde = SOURCE.with_name(SOURCE.name + ".bak")
                sauvegarde.write_text(ancien, encoding="utf-8")
                print(f"Version precedente conservee dans {sauvegarde.name}")
            SOURCE.write_text(nouveau, encoding="utf-8")
            print(f"Source mise a jour depuis {args.origine} -> {SOURCE.name}")

    if not SOURCE.exists():
        raise SystemExit(
            f"Source absente : {SOURCE}\n"
            "Passe un fichier au script pour la creer :\n"
            "    python sync_planning.py mon-planning.html"
        )

    attendu = construire(SOURCE.read_text(encoding="utf-8"))
    actuel = CIBLE.read_text(encoding="utf-8") if CIBLE.exists() else None

    if args.check:
        if actuel == attendu:
            print(f"{CIBLE.relative_to(BASE_DIR)} est a jour.")
            return 0
        print(f"{CIBLE.relative_to(BASE_DIR)} est perime - lance sync_planning.py.")
        return 1

    if actuel == attendu:
        print(f"{CIBLE.relative_to(BASE_DIR)} etait deja a jour ({len(attendu)} octets).")
        return 0

    CIBLE.parent.mkdir(parents=True, exist_ok=True)
    CIBLE.write_text(attendu, encoding="utf-8")
    print(f"{CIBLE.relative_to(BASE_DIR)} regenere ({len(attendu)} octets).")
    print("Pense a commiter et pousser pour que le telephone le recupere.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
