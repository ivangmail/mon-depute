"""Rattachement des scrutins à leur dossier législatif : corrections et contrôle.

Les données ouvertes de l'Assemblée indiquent pour chaque scrutin le dossier
du texte voté. Elles se trompent parfois : le 19/11/2026, les 18 scrutins sur
la vie chère outre-mer étaient rattachés au dossier « Territoires zéro
chômeur », examiné le même jour. La lettre affichait alors l'intitulé et le
thème d'un autre texte.

- rattachements_scrutins.csv liste les corrections, vérifiées sur la page
  officielle du scrutin et relues par l'éditeur ; appliquer() les reporte dans
  la base après chaque chargement.
- suspects() repère les scrutins récents dont le titre n'a presque aucun mot en
  commun avec le titre de leur dossier. Rien n'est corrigé automatiquement :
  ils sont signalés à l'éditeur dans le point du lundi.
"""

import csv
import datetime
import os
import re
import unicodedata

FICHIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rattachements_scrutins.csv")
DOSSIER = re.compile(r"^DL[A-Z0-9]+$")
JOURS = 14          # scrutins contrôlés : ceux des deux dernières semaines
SEUIL = 0.25        # part des mots du titre du dossier retrouvés dans le titre du scrutin
VERIFIE = "="       # rattachement signalé, vérifié et juste
# Mots trop courants pour distinguer deux textes.
VIDES = set("""pour dans avec sans leur leurs visant vise afin entre sous plus moins cette
ces des les une aux par sur que qui est son ses lecture premiere deuxieme nouvelle texte
commission mixte paritaire ensemble proposition projet relatif relative portant article
amendement amendements apres avant rect motion rejet prealable""".split())


def _mots(texte):
    texte = unicodedata.normalize("NFD", (texte or "").lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return {m for m in re.findall(r"[a-z]{4,}", texte) if m not in VIDES}


def proximite(titre_scrutin, titre_dossier):
    """Part des mots du titre du dossier présents dans le titre du scrutin
    (entre 0 et 1), ou None si l'un des titres n'a aucun mot distinctif."""
    a, b = _mots(titre_scrutin), _mots(titre_dossier)
    if not a or not b:
        return None
    return len(a & b) / len(b)


def lire(chemin=FICHIER):
    """{numéro de scrutin: dossier correct, ou VERIFIE}. Une ligne mal formée est
    refusée, pour qu'une faute de saisie ne rattache rien par erreur."""
    if not os.path.exists(chemin):
        return {}
    resultat = {}
    with open(chemin, encoding="utf-8", newline="") as f:
        lignes = (l for l in f if l.strip() and not l.lstrip().startswith("#"))
        for ligne in csv.DictReader(lignes, delimiter=";"):
            plage = (ligne.get("scrutins") or "").strip()
            dossier = (ligne.get("dossier") or "").strip()
            bornes = plage.split("-")
            if not (1 <= len(bornes) <= 2 and all(b.isdigit() for b in bornes)):
                raise ValueError(f"{chemin} : numéro de scrutin illisible « {plage} »")
            debut, fin = int(bornes[0]), int(bornes[-1])
            if fin < debut or fin - debut > 500:
                raise ValueError(f"{chemin} : plage de scrutins invalide « {plage} »")
            if dossier != VERIFIE and not DOSSIER.match(dossier):
                raise ValueError(f"{chemin} : dossier illisible « {dossier} » pour {plage}")
            for numero in range(debut, fin + 1):
                resultat[numero] = dossier
    return resultat


def appliquer(db, chemin=FICHIER):
    """Reporte les corrections dans la table des scrutins. Renvoie le nombre de
    scrutins modifiés."""
    n = 0
    for numero, dossier in lire(chemin).items():
        if dossier != VERIFIE:
            n += db.execute("UPDATE scrutins SET dossier_uid = ? WHERE numero = ?"
                            " AND coalesce(dossier_uid, '') <> ?",
                            (dossier, numero, dossier)).rowcount
    return n


def suspects(db, aujourdhui=None, jours=JOURS, chemin=FICHIER):
    """Scrutins des « jours » derniers jours dont le rattachement paraît douteux,
    regroupés par séance et dossier : [{date, dossier_uid, titre_dossier, numeros,
    exemple}]. Les scrutins déjà corrigés ou vérifiés sont exclus."""
    aujourdhui = aujourdhui or datetime.date.today().isoformat()
    depuis = (datetime.date.fromisoformat(aujourdhui)
              - datetime.timedelta(days=jours)).isoformat()
    connus = lire(chemin)
    groupes = {}
    for numero, date, titre, dossier, titre_dossier in db.execute("""
            SELECT s.numero, s.date, s.titre, s.dossier_uid, d.titre FROM scrutins s
            JOIN dossiers d ON d.uid = s.dossier_uid
            WHERE s.date >= ? AND s.date <= ? ORDER BY s.numero""", (depuis, aujourdhui)):
        if numero in connus or (titre or "").lower().startswith("la demande de suspension"):
            continue
        p = proximite(titre, titre_dossier)
        if p is not None and p < SEUIL:
            g = groupes.setdefault((date, dossier), {
                "date": date, "dossier_uid": dossier, "titre_dossier": titre_dossier,
                "numeros": [], "exemple": titre})
            g["numeros"].append(numero)
    return list(groupes.values())
