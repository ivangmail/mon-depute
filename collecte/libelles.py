"""Intitulés en langage courant des textes, relus par l'éditeur du site.

Le titre officiel d'un texte est souvent long ou technique (« Projet de loi de
finances de fin de gestion pour 2026 »). libelles_textes.csv propose pour
certains textes une reformulation : elle reprend le titre officiel ou, quand il
est vague, dit ce que fait le texte d'après le texte déposé, sans jugement ni
appréciation (règle du 24/11/2026).
Seuls les libellés marqués « validé » sont affichés : une proposition n'est
jamais publiée sans relecture. Sans libellé validé, le titre officiel s'affiche.
Le statut « titre officiel » note qu'un titre est déjà clair : aucun libellé
n'est alors attendu, et le texte n'est plus signalé comme « à libeller ».
"""

import csv
import datetime
import os

FICHIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libelles_textes.csv")
STATUTS = ("proposé", "validé", "titre officiel")
JOURS_VOTES = 14   # textes votés récemment...
JOURS_AGENDA = 7   # ... ou inscrits à l'ordre du jour des jours qui viennent
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
            if statut == "titre officiel":
                libelle = ""
            elif not libelle or len(libelle) > LONGUEUR_MAX:
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


def a_faire(db, aujourdhui=None, chemin=None):
    """Textes qui vont apparaître dans les lettres et attendent une décision :
    votés depuis JOURS_VOTES jours ou inscrits à l'ordre du jour des JOURS_AGENDA
    jours qui viennent. Renvoie (sans_ligne, proposes) : listes de (dossier, titre
    officiel), les uns absents du fichier, les autres proposés mais pas validés.
    Les motions de censure et les déclarations du Gouvernement sont écartées."""
    jour = datetime.date.fromisoformat(aujourdhui or datetime.date.today().isoformat())
    depuis = (jour - datetime.timedelta(days=JOURS_VOTES)).isoformat()
    jusque = (jour + datetime.timedelta(days=JOURS_AGENDA)).isoformat()
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    uids = {r[0] for r in db.execute(
        "SELECT DISTINCT dossier_uid FROM scrutins WHERE dossier_uid != '' AND date >= ?",
        (depuis,))}
    if "points_odj" in tables:
        uids |= {r[0] for r in db.execute(
            "SELECT DISTINCT dossier_uid FROM points_odj WHERE dossier_uid IS NOT NULL"
            " AND etat = 'Confirmé' AND substr(debut, 1, 10) >= ? AND substr(debut, 1, 10) < ?",
            (jour.isoformat(), jusque))}
    connus = lire(chemin or FICHIER)
    sans_ligne, proposes = [], []
    for uid in sorted(uids):
        ligne = db.execute("SELECT titre, procedure FROM dossiers WHERE uid = ?",
                           (uid,)).fetchone()
        if ligne is None or (ligne[1] or "").startswith(("Engagement de la responsabilité",
                                                        "Déclaration")):
            continue
        statut = connus.get(uid, (None, None))[0]
        if statut is None:
            sans_ligne.append((uid, ligne[0]))
        elif statut == "proposé":
            proposes.append((uid, ligne[0]))
    return sans_ligne, proposes


def pour_dossiers(uids, chemin=None):
    """{dossier: libellé validé} pour les dossiers demandés qui en ont un."""
    table = valides(chemin)
    return {u: table[u] for u in set(uids) if u and u in table}
