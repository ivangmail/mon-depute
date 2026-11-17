"""Thème d'un texte, déduit de la commission de l'Assemblée saisie au fond.

Chaque texte est examiné par une commission avant d'arriver en séance. Les huit
commissions permanentes couvrent chacune un domaine : leur nom sert de thème,
sans aucune lecture du contenu. Un domaine en réunit souvent plusieurs (la
commission des lois traite d'institutions, de justice et de sécurité), d'où des
libellés composés. Seule exception : les textes de la commission des affaires
économiques sont répartis entre trois thèmes d'après des mots de leur titre,
publiés ci-dessous (MOTS_CLES). Les textes confiés à une commission spéciale, et
les erreurs manifestes, sont classés à la main dans themes_corrections.csv.
"""

import csv
import os
import re

# Début du libellé officiel de la commission -> thème affiché. Le libellé est
# plus stable d'une législature à l'autre que l'identifiant de la commission.
COMMISSIONS = (
    ("Commission des finances", "Budget et fiscalité"),
    ("Commission des affaires économiques", "Économie, énergie et consommation"),
    ("Commission des affaires sociales", "Santé, travail et solidarités"),
    ("Commission des affaires culturelles", "Éducation, culture et médias"),
    ("Commission du développement durable", "Environnement et transports"),
    ("Commission des lois", "Institutions, justice et sécurité"),
    ("Commission des affaires étrangères", "Affaires étrangères"),
    ("Commission de la défense", "Défense"),
)

# Pour une commission trop large, thèmes plus précis attribués d'après le titre du
# texte. Un mot terminé par « … » vaut pour tous les mots qui commencent ainsi.
# Un titre qui contient un mot exclu, ou les mots de deux thèmes, garde le thème
# de la commission.
MOTS_CLES = {
    "Commission des affaires économiques": (
        ("Logement et urbanisme",
         ("logement…", "locataire…", "locati…", "loyer…", "habitat…", "copropriété…", "HLM",
          "bailleur…", "urbanisme", "renouvellement urbain…", "rénovation urbaine",
          "insalubr…", "habitation…", "immobili…", "sans-abri", "occupation… illicite…",
          "sans droit ni titre", "expulsion…", "primo-accédant…", "meublé…",
          "rénovation énergétique", "bâti", "bâtiment…", "cabanisation", "résidence… services",
          "viager"),
         ("commerciaux", "commerciale…", "professionnel…", "fibre optique",
          "immobilière économique")),
        ("Agriculture et alimentation",
         ("agricult…", "agricole…", "agroalimentaire…", "élevage…", "éleveur…", "paysan…",
          "pêche", "pêcheur…", "halieutique…", "viticole…", "viticult…", "vin", "vins",
          "laitier…", "laitière…", "semence…", "pesticide…", "phytopharmaceutique…",
          "phytosanitaire…", "acétamipride", "néonicotinoïde…", "forêt…", "forestier…",
          "forestière…", "abeille…", "apicult…", "cadmium", "chasse", "animal", "animaux",
          "animale…", "bovin…", "pastoralisme", "noisette…", "alimentaire…", "alimentation",
          "abattu…", "abattoir…", "hexane", "fermier…", "végétarien…", "végétalien…"),
         ("titre… restaurant", "titres-restaurant", "ticket… restaurant",
          "raisons médicales")),
    ),
}
THEMES = tuple(theme for _, theme in COMMISSIONS) + tuple(
    theme for regles in MOTS_CLES.values() for theme, _, _ in regles)


def _motif(mots):
    morceaux = (re.escape(m).replace("…", r"\w*") for m in mots)
    return re.compile(r"\b(?:" + "|".join(morceaux) + r")\b", re.IGNORECASE)


_REGLES = {commission: [(theme, _motif(mots), _motif(exclus)) for theme, mots, exclus in regles]
           for commission, regles in MOTS_CLES.items()}
CORRECTIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes_corrections.csv")


def theme_de_commission(libelle, titre=None):
    """Thème d'un texte d'après le libellé de sa commission (et, pour une
    commission listée dans MOTS_CLES, d'après son titre), ou None."""
    for debut, theme in COMMISSIONS:
        if (libelle or "").startswith(debut):
            trouves = [t for t, mots, exclus in _REGLES.get(debut, ())
                       if titre and mots.search(titre) and not exclus.search(titre)]
            return trouves[0] if len(trouves) == 1 else theme
    return None


def lire_corrections(chemin=CORRECTIONS):
    """{dossier: thème} lu dans le fichier des corrections manuelles.

    Une ligne qui commence par # est un commentaire. Un thème inconnu est
    refusé, pour qu'une faute de frappe ne crée pas un thème de plus.
    """
    if not os.path.exists(chemin):
        return {}
    resultat = {}
    with open(chemin, encoding="utf-8", newline="") as f:
        lignes = (l for l in f if l.strip() and not l.lstrip().startswith("#"))
        for numero, ligne in enumerate(csv.DictReader(lignes, delimiter=";"), start=2):
            dossier, theme = (ligne.get("dossier") or "").strip(), (ligne.get("theme") or "").strip()
            if theme not in THEMES:
                raise ValueError(f"{chemin} : thème inconnu « {theme} » pour {dossier}")
            resultat[dossier] = theme
    return resultat


_CORRECTIONS = None


def disponible(db):
    """Vrai si la base connaît la commission saisie au fond. Une base créée avant
    cet ajout ne l'a qu'après le prochain chargement des dossiers."""
    return any(c[1] == "commission_fond" for c in db.execute("PRAGMA table_info(dossiers)"))


def pour_dossiers(db, uids, corrections=None):
    """{dossier: thème} pour les dossiers demandés qui en ont un."""
    global _CORRECTIONS
    if corrections is None:
        if _CORRECTIONS is None:
            _CORRECTIONS = lire_corrections()
        corrections = _CORRECTIONS
    uids = sorted({u for u in uids if u})
    resultat = {}
    if not disponible(db):
        return resultat
    for debut in range(0, len(uids), 500):
        morceau = uids[debut:debut + 500]
        for uid, libelle, titre in db.execute(
                "SELECT d.uid, o.libelle, d.titre FROM dossiers d"
                " LEFT JOIN organes o ON o.uid = d.commission_fond"
                f" WHERE d.uid IN ({','.join('?' * len(morceau))})", morceau).fetchall():
            theme = corrections.get(uid) or theme_de_commission(libelle, titre)
            if theme:
                resultat[uid] = theme
    for uid in uids:  # une correction vaut aussi pour un dossier absent de la base
        if uid not in resultat and uid in corrections:
            resultat[uid] = corrections[uid]
    return resultat
