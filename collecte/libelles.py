"""Intitulés en langage courant des textes, relus par l'éditeur du site.

Le titre officiel d'un texte est souvent long ou technique (« Projet de loi de
finances de fin de gestion pour 2026 »). libelles_textes.csv propose pour
certains textes une reformulation, qui ne doit rien ajouter au titre officiel.
Seuls les libellés marqués « validé » sont affichés : une proposition n'est
jamais publiée sans relecture. Sans libellé validé, le titre officiel s'affiche.
"""

import csv
import os

FICHIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libelles_textes.csv")
STATUTS = ("proposé", "validé")
LONGUEUR_MAX = 120


def lire(chemin=FICHIER):
    """Toutes les lignes du fichier : {dossier: (statut, libellé)}.

    Une ligne qui commence par # est un commentaire. Un statut inconnu, un
    libellé vide ou trop long sont refusés, pour qu'une faute de saisie ne
    publie rien par erreur."""
    if not os.path.exists(chemin):
        return {}
    resultat = {}
    with open(chemin, encoding="utf-8", newline="") as f:
        lignes = (l for l in f if l.strip() and not l.lstrip().startswith("#"))
        for ligne in csv.DictReader(lignes, delimiter=";"):
            dossier = (ligne.get("dossier") or "").strip()
            statut = (ligne.get("statut") or "").strip()
            libelle = " ".join((ligne.get("libelle") or "").split())
            if statut not in STATUTS:
                raise ValueError(f"{chemin} : statut inconnu « {statut} » pour {dossier}")
            if not libelle or len(libelle) > LONGUEUR_MAX:
                raise ValueError(f"{chemin} : libellé vide ou de plus de {LONGUEUR_MAX} "
                                 f"caractères pour {dossier}")
            resultat[dossier] = (statut, libelle)
    return resultat


_VALIDES = None


def valides(chemin=None):
    """{dossier: libellé} des seuls libellés validés."""
    global _VALIDES
    if chemin is not None:
        return {d: l for d, (s, l) in lire(chemin).items() if s == "validé"}
    if _VALIDES is None:
        _VALIDES = {d: l for d, (s, l) in lire().items() if s == "validé"}
    return _VALIDES


def pour_dossiers(uids, chemin=None):
    """{dossier: libellé validé} pour les dossiers demandés qui en ont un."""
    table = valides(chemin)
    return {u: table[u] for u in set(uids) if u and u in table}
