"""Parsing des offres JobTeaser depuis du HTML deja recupere.

JobTeaser protege cette page avec un controle anti-bot ("Security
checkup") qui bloque toute requete HTTP simple, meme avec des en-tetes
de navigateur. Seul un vrai navigateur (voir collect_jobteaser.py, lance
depuis la machine de l'utilisateur) passe ce controle. Ce module se
limite donc au parsing du HTML une fois obtenu par ce moyen.
"""
import requests
from bs4 import BeautifulSoup


def page_url(base_url: str, page: int) -> str:
    return base_url if page == 1 else f"{base_url}&page={page}"


def parse_offers(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    offres = []
    vus = set()
    for a in soup.select('a[href*="/job-offers/"]'):
        href = a.get("href", "")
        if not href or href in vus:
            continue
        titre = a.get_text(strip=True)
        if not titre:
            continue
        vus.add(href)

        card = a
        for _ in range(8):
            if card is None or card.name == "li":
                break
            card = card.parent

        entreprise = lieu = contrat = ""
        if card is not None:
            company = card.select_one('[data-testid="jobad-card-company-name"]')
            location = card.select_one('[data-testid="jobad-card-location"]')
            contract = card.select_one('[data-testid="jobad-card-contract"]')
            entreprise = company.get_text(strip=True) if company else ""
            lieu = location.get_text(strip=True) if location else ""
            contrat = contract.get_text(strip=True) if contract else ""

        offres.append(
            {
                "id": href,
                "titre": titre,
                "entreprise": entreprise,
                "lieu": lieu,
                "contrat": contrat,
                "url": requests.compat.urljoin(base_url, href),
                "source": "JobTeaser",
            }
        )
    return offres
