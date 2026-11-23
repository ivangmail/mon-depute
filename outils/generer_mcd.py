"""Dessine le modèle conceptuel des données (MCD, notation Merise) en SVG.

    python3 outils/generer_mcd.py        écrit docs/mcd-*.svg

Le modèle décrit les deux bases (assemblee.sqlite, abonnes.sqlite) au niveau
conceptuel : entités, associations, cardinalités. Il est découpé en vues, une
par domaine ; ACTEUR, ORGANE et DOSSIER reviennent dans plusieurs vues. À
mettre à jour à la main quand le schéma (collecte/base.py, lettre/abonnes.py)
change.
"""

import math
import os
from html import escape

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICE = "Helvetica, Arial, sans-serif"
ENCRE, DOUX, FOND_ENTITE, FOND_ASSO = "#1c1f26", "#5b6270", "#ffffff", "#eef3f8"
CALCULE, SEPAREE = "#8a8f98", "#9a6a00"

# Entités : nom -> (identifiant(s), attributs, genre). Le genre « calculé » est
# recalculé chaque jour, « séparé » vit dans la base des abonnés, « référence »
# rappelle une entité détaillée dans une autre vue.
ENTITES = {
    "ACTEUR": (["uid"], ["civilité", "prénom", "nom", "date de naissance", "lieu de naissance",
                         "profession", "lien HATVP"], ""),
    "ORGANE": (["uid"], ["type (groupe, commission…)", "libellé", "libellé abrégé",
                         "législature", "date de début", "date de fin", "couleur"], ""),
    "MANDAT": (["uid"], ["type d'organe", "législature", "qualité", "date de début",
                         "date de fin"], ""),
    "CONTACT": (["uid"], ["type", "valeur"], ""),
    "DÉPUTÉ": ([], ["en exercice", "date de début", "date de fin", "cause du mandat",
                    "place dans l'hémicycle"], ""),
    "CIRCONSCRIPTION": (["n° de département", "n° de circonscription"],
                        ["département", "région", "contour (fichier)"], ""),
    "ABONNÉ": (["id"], ["e-mail", "fréquence", "statut", "créé le", "confirmé le",
                        "dernier envoi", "dernier courriel le"], "séparé"),
    "SCRUTIN": (["uid"], ["numéro", "date", "type de vote", "sort", "titre", "demandeur",
                          "votants", "exprimés", "pour", "contre", "abstentions"], ""),
    "DOSSIER": (["uid"], ["type", "législature", "titre", "procédure"], ""),
    "ÉTAPE": (["ordre"], ["code", "date", "statut", "n° de loi"], ""),
    "DOCUMENT": (["uid"], ["type", "dénomination", "législature", "titre",
                           "date de dépôt"], ""),
    "AMENDEMENT": (["uid"], ["numéro", "type d'auteur", "date de dépôt", "état", "sort",
                             "article", "dispositif", "exposé"], ""),
    "RÉUNION": (["uid"], ["type (séance, commission…)", "début", "fin", "état", "objet"], ""),
    "POINT D'ORDRE DU JOUR": (["uid"], ["ordre", "état", "type", "objet"], ""),
    "COMPTE RENDU": (["uid"], ["date", "session", "n° de séance", "état"], ""),
    "INTERVENTION": (["ordre"], ["orateur", "qualité", "rôle", "code grammaire", "sujet",
                                 "nombre de mots", "texte"], ""),
    "QUESTION": (["uid"], ["type (écrite, au Gouvernement, orale)", "numéro", "ministère",
                           "rubrique", "analyse", "date de la question", "date de la réponse",
                           "statut", "texte", "réponse"], ""),
    "INDICATEURS": ([], ["scrutins éligibles, exprimés", "scrutins solennels éligibles, exprimés",
                         "votes pour, contre, abstention", "votes comparables, conformes",
                         "présences, absences en commission", "questions par type",
                         "interventions longues, courtes", "amendements déposés, adoptés, cosignés",
                         "propositions de loi"], "calculé"),
    "RÉFÉRENCE": (["indicateur"], ["médiane", "effectif"], "calculé"),
    "IMPORT": (["fichier"], ["jeu", "url", "etag", "date de mise à jour", "téléchargé le",
                             "chargé le"], "calculé"),
    # Même entité que DOSSIER (vue 2), vue par ses attributs dérivés.
    "DOSSIER#calcul": (["uid"], ["titre", "thème (déduit de la commission saisie au fond)",
                                 "thème corrigé (fichier)",
                                 "intitulé en langage courant (fichier, validé)"], "calculé"),
}


def reference(nom):
    """Rappel d'une entité détaillée ailleurs : identifiant et titre seulement."""
    return nom + "#ref"


# Vues : titre, taille, positions des entités (centre), associations.
# Association : (nom, attributs, centre, [(entité, cardinalité, décalage en x)]).
VUES = [
    ("1-acteurs", "Vue 1 : acteurs, organes, circonscriptions et abonnés", (1720, 1000), {
        "ABONNÉ": (190, 150), "CIRCONSCRIPTION": (640, 150), "DÉPUTÉ": (640, 480),
        "ACTEUR": (640, 830), "CONTACT": (190, 830), "MANDAT": (1100, 830),
        "ORGANE": (1500, 480),
    }, [
        ("suit", [], (415, 150), [("ABONNÉ", "1,1", 0), ("CIRCONSCRIPTION", "0,n", 0)]),
        ("est élu dans", [], (640, 315), [("DÉPUTÉ", "1,1", 0), ("CIRCONSCRIPTION", "0,n", 0)]),
        ("est", [], (640, 655), [("ACTEUR", "0,1", 0), ("DÉPUTÉ", "(1,1)", 0)]),
        ("est joignable par", [], (415, 830), [("ACTEUR", "0,n", 0), ("CONTACT", "1,1", 0)]),
        ("détient", [], (870, 830), [("ACTEUR", "0,n", 0), ("MANDAT", "1,1", 0)]),
        ("s'exerce dans", [], (1300, 655), [("MANDAT", "1,1", 0), ("ORGANE", "0,n", 0)]),
        ("siège au groupe", [], (1070, 480), [("DÉPUTÉ", "0,1", 0), ("ORGANE", "0,n", 0)]),
        ("dépend de", [], (1500, 190), [("ORGANE", "0,1", -70), ("ORGANE", "0,n", 70)]),
    ]),
    ("2-votes-textes", "Vue 2 : votes, textes et amendements", (1800, 1560), {
        "SCRUTIN": (250, 230), "DOSSIER": (900, 200), "ÉTAPE": (1520, 200),
        "ACTEUR": (250, 820), "ORGANE": (900, 820), "DOCUMENT": (1520, 820),
        "AMENDEMENT": (900, 1360),
    }, [
        ("porte sur", [], (580, 200), [("SCRUTIN", "0,1", 0), ("DOSSIER", "0,n", 0)]),
        ("jalonne", [], (1210, 200), [("ÉTAPE", "(1,1)", 0), ("DOSSIER", "0,n", 0)]),
        ("est examiné au fond par", [], (900, 500), [("DOSSIER", "0,1", 0), ("ORGANE", "0,n", 0)]),
        ("est rattaché à", [], (1210, 500), [("DOCUMENT", "0,1", 0), ("DOSSIER", "0,n", 0)]),
        ("VOTE", ["position", "par délégation"], (420, 560),
         [("SCRUTIN", "1,n", 0), ("ACTEUR", "0,n", 0), ("ORGANE", "0,n", -90)]),
        ("LIGNE DU GROUPE", ["position", "nette (> 60 %)"], (660, 420),
         [("SCRUTIN", "0,n", 0), ("ORGANE", "0,n", 90)]),
        ("signe", ["rôle"], (1210, 1080), [("ACTEUR", "0,n", 0), ("DOCUMENT", "0,n", 0)]),
        ("dépose", [], (540, 1160), [("ACTEUR", "0,n", 40), ("AMENDEMENT", "0,1", 0)]),
        ("cosigne", [], (250, 1330), [("ACTEUR", "0,n", -40), ("AMENDEMENT", "0,n", 0)]),
        ("modifie", [], (1340, 1360), [("AMENDEMENT", "1,1", 0), ("DOCUMENT", "0,n", 0)]),
        ("est examiné par", [], (860, 1090), [("AMENDEMENT", "0,1", 0), ("ORGANE", "0,n", 0)]),
    ]),
    ("3-reunions", "Vue 3 : réunions, séances, interventions et questions", (1780, 1440), {
        "QUESTION": (250, 230), "ACTEUR": (250, 710), "INTERVENTION": (250, 1180),
        reference("SCRUTIN"): (880, 180), "RÉUNION": (880, 710), "COMPTE RENDU": (880, 1180),
        "ORGANE": (1500, 370), "POINT D'ORDRE DU JOUR": (1500, 870),
        reference("DOSSIER"): (1500, 1250),
    }, [
        ("pose", [], (250, 470), [("QUESTION", "1,1", 0), ("ACTEUR", "0,n", 0)]),
        ("PRÉSENCE", ["présent, absent, excusé"], (565, 710),
         [("ACTEUR", "0,n", 0), ("RÉUNION", "0,n", 0)]),
        ("prononce", [], (250, 950), [("INTERVENTION", "0,1", 0), ("ACTEUR", "0,n", 0)]),
        ("contient", [], (565, 1180), [("INTERVENTION", "(1,1)", 0), ("COMPTE RENDU", "0,n", 0)]),
        ("rend compte de", [], (880, 950), [("COMPTE RENDU", "0,1", 0), ("RÉUNION", "0,1", 0)]),
        ("est tenu en séance", [], (880, 400), [(reference("SCRUTIN"), "0,1", 0),
                                                ("RÉUNION", "0,n", 0)]),
        ("est organisée par", [], (1200, 540), [("RÉUNION", "0,1", 0), ("ORGANE", "0,n", 0)]),
        ("est inscrit à", [], (1200, 790), [("POINT D'ORDRE DU JOUR", "1,1", 0),
                                            ("RÉUNION", "0,n", 0)]),
        ("concerne", [], (1500, 1080), [("POINT D'ORDRE DU JOUR", "0,1", 0),
                                        (reference("DOSSIER"), "0,n", 0)]),
    ]),
    ("4-calculs", "Vue 4 : données calculées chaque jour et compléments", (1700, 1180), {
        "ACTEUR": (230, 230), "INDICATEURS": (860, 230), "ORGANE": (230, 700),
        "RÉFÉRENCE": (860, 560), "IMPORT": (1440, 230), "DOSSIER#calcul": (900, 920),
    }, [
        ("mesure", [], (540, 230), [("ACTEUR", "0,1", 0), ("INDICATEURS", "(1,1)", 0)]),
        ("est le repère de", ["« tous » si aucun groupe"], (540, 560),
         [("RÉFÉRENCE", "0,1", 0), ("ORGANE", "0,n", 0)]),
        ("est examiné au fond par", [], (540, 920), [("DOSSIER#calcul", "0,1", 0),
                                                     ("ORGANE", "0,n", 0)]),
    ]),
]

LIGNE, ENTETE, MARGE = 19, 34, 12
LEGENDE = ("Rectangle : entité (identifiant souligné). Ellipse : association, avec ses attributs. "
           "Cardinalités min,max côté entité ; (1,1) : identification relative. "
           "Pointillés : donnée calculée, base séparée ou rappel d'une autre vue.")
NOTES = {"4-calculs": [
    "Également recalculées chaque jour : la ligne de chaque groupe sur chaque scrutin (vue 2), "
    "et la liste des réunions de commission",
    "retenues pour la présence (réunions confirmées, passées, avec au moins un présent).",
]}


def largeur(texte, taille=14):
    return len(texte) * taille * 0.55


def boite(nom):
    """(largeur, hauteur, identifiants, attributs, genre, titre) d'une entité."""
    if nom.endswith("#calcul"):
        ids, attrs, _ = ENTITES[nom]
        return (max([largeur(a) + 2 * MARGE for a in ids + attrs] + [170]),
                ENTETE + LIGNE * len(ids + attrs) + 12, ids, attrs, "dérivé", nom[:-7])
    if nom.endswith("#ref"):
        vrai = nom[:-4]
        ids, _, _ = ENTITES[vrai]
        attrs, genre, titre = ["titre"] if vrai == "DOSSIER" else ["numéro"], "référence", vrai
    else:
        ids, attrs, genre = ENTITES[nom]
        titre = nom
    lignes = ids + attrs
    l = max([largeur(titre, 15) + 2 * MARGE + 10] + [largeur(a) + 2 * MARGE for a in lignes]
            + [170])
    h = ENTETE + LIGNE * len(lignes) + 12
    return l, h, ids, attrs, genre, titre


def bord(centre, taille, vers):
    """Point où le segment centre -> vers sort du rectangle."""
    (cx, cy), (l, h) = centre, taille
    dx, dy = vers[0] - cx, vers[1] - cy
    if dx == 0 and dy == 0:
        return centre
    t = min((l / 2) / abs(dx) if dx else math.inf, (h / 2) / abs(dy) if dy else math.inf)
    return cx + dx * t, cy + dy * t


def svg_vue(cle, titre, taille, positions, associations):
    w, h = taille
    morceaux = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
                f'viewBox="0 0 {w} {h}" font-family="{POLICE}" role="img" '
                f'aria-label="{escape(titre)}">',
                f'<rect width="{w}" height="{h}" fill="#fafaf7"/>',
                f'<text x="24" y="38" font-size="22" font-weight="bold" fill="{ENCRE}">'
                f"{escape(titre)}</text>"]
    boites = {n: boite(n) for n in positions}
    traits, formes, etiquettes = [], [], []

    for nom, attrs, (ax, ay), pattes in associations:
        rx = max(largeur(nom, 15 if attrs else 14) / 2 + (34 if attrs else 24),
                 max([largeur(a, 13) / 2 + 22 for a in attrs] + [0]), 58)
        ry = 22 + 12 * len(attrs)
        for entite, cardinalite, decalage in pattes:
            (ex, ey) = positions[entite]
            l, hh = boites[entite][:2]
            cible = (ex + decalage, ey)
            px, py = bord((ex, ey), (l, hh), (ax, ay)) if not decalage else (
                ex + decalage, ey - hh / 2 if ay < ey else ey + hh / 2)
            traits.append(f'<line x1="{ax:.0f}" y1="{ay:.0f}" x2="{px:.0f}" y2="{py:.0f}" '
                          f'stroke="{ENCRE}" stroke-width="1.4"/>')
            longueur = math.hypot(ax - px, ay - py) or 1
            ux, uy = (ax - px) / longueur, (ay - py) / longueur
            tx, ty = px + ux * 26 - uy * 13, py + uy * 26 + ux * 13
            etiquettes.append(
                f'<text x="{tx:.0f}" y="{ty + 5:.0f}" font-size="14" font-weight="bold" '
                f'text-anchor="middle" fill="{ENCRE}" stroke="#fafaf7" stroke-width="4" '
                f'paint-order="stroke">{escape(cardinalite)}</text>')
            del cible
        formes.append(f'<ellipse cx="{ax}" cy="{ay}" rx="{rx:.0f}" ry="{ry}" fill="{FOND_ASSO}" '
                      f'stroke="{ENCRE}" stroke-width="1.4"/>')
        if attrs:
            haut = ay - 8 * len(attrs)
            formes.append(f'<text x="{ax}" y="{haut - 2}" font-size="14" font-weight="bold" '
                          f'text-anchor="middle" fill="{ENCRE}">{escape(nom)}</text>')
            formes.append(f'<line x1="{ax - rx * 0.7:.0f}" y1="{haut + 6}" '
                          f'x2="{ax + rx * 0.7:.0f}" y2="{haut + 6}" stroke="{DOUX}"/>')
            for i, a in enumerate(attrs):
                formes.append(f'<text x="{ax}" y="{haut + 22 + 16 * i}" font-size="13" '
                              f'text-anchor="middle" fill="{ENCRE}">{escape(a)}</text>')
        else:
            formes.append(f'<text x="{ax}" y="{ay + 5}" font-size="14" text-anchor="middle" '
                          f'fill="{ENCRE}">{escape(nom)}</text>')

    for nom, (cx, cy) in positions.items():
        l, hh, ids, attrs, genre, titre_entite = boites[nom]
        x, y = cx - l / 2, cy - hh / 2
        couleur = {"calculé": CALCULE, "séparé": SEPAREE, "référence": CALCULE,
                   "dérivé": CALCULE}.get(genre, ENCRE)
        pointilles = (' stroke-dasharray="7 4"'
                      if genre in ("calculé", "séparé", "référence", "dérivé") else "")
        formes.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{l:.0f}" height="{hh}" rx="3" '
                      f'fill="{FOND_ENTITE}" stroke="{couleur}" stroke-width="1.8"{pointilles}/>')
        formes.append(f'<line x1="{x:.0f}" y1="{y + ENTETE - 6:.0f}" x2="{x + l:.0f}" '
                      f'y2="{y + ENTETE - 6:.0f}" stroke="{couleur}"/>')
        formes.append(f'<text x="{cx:.0f}" y="{y + 20:.0f}" font-size="15" font-weight="bold" '
                      f'text-anchor="middle" fill="{ENCRE}">{escape(titre_entite)}</text>')
        for i, a in enumerate(ids + attrs):
            souligne = ' text-decoration="underline"' if i < len(ids) else ""
            formes.append(f'<text x="{x + MARGE:.0f}" y="{y + ENTETE + 10 + LIGNE * i:.0f}" '
                          f'font-size="14" fill="{ENCRE}"{souligne}>{escape(a)}</text>')
        if genre == "séparé":
            formes.append(f'<text x="{cx:.0f}" y="{y + hh + 18:.0f}" font-size="12" '
                          f'text-anchor="middle" fill="{SEPAREE}">base séparée abonnes.sqlite'
                          "</text>")
        elif genre == "dérivé":
            formes.append(f'<text x="{cx:.0f}" y="{y + hh + 18:.0f}" font-size="12" '
                          f'text-anchor="middle" fill="{DOUX}">même entité que DOSSIER (vue 2) : '
                          "attributs calculés ou lus dans des fichiers, sans colonne</text>")
        elif nom == "IMPORT":
            formes.append(f'<text x="{cx:.0f}" y="{y + hh + 18:.0f}" font-size="12" '
                          f'text-anchor="middle" fill="{DOUX}">table technique, hors modèle : '
                          "journal des fichiers téléchargés</text>")
        elif genre == "référence":
            formes.append(f'<text x="{x + l + 10:.0f}" y="{cy + 4:.0f}" font-size="12" '
                          f'fill="{DOUX}">détaillé dans la vue 2</text>')
    for i, ligne in enumerate(NOTES.get(cle, [])):
        formes.append(f'<text x="24" y="{h - 70 + 18 * i}" font-size="14" fill="{DOUX}">'
                      f"{escape(ligne)}</text>")
    formes.append(f'<text x="24" y="{h - 16}" font-size="13" fill="{DOUX}">{escape(LEGENDE)}</text>')
    morceaux += traits + formes + etiquettes + ["</svg>"]
    return "\n".join(morceaux)


def main():
    dossier = os.path.join(RACINE, "docs")
    os.makedirs(dossier, exist_ok=True)
    for cle, titre, taille, positions, associations in VUES:
        chemin = os.path.join(dossier, f"mcd-{cle}.svg")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(svg_vue(cle, titre, taille, positions, associations))
        print(chemin)


if __name__ == "__main__":
    main()
