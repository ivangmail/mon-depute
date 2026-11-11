"""Catalogue des jeux de données de l'open data de l'Assemblée nationale.

Toutes les adresses ont été relevées sur https://data.assemblee-nationale.fr
(rubriques de la législature en cours). Pour changer de législature, il suffit
en principe de modifier LEGISLATURE ; à vérifier le moment venu, car
l'arborescence a déjà changé d'une législature à l'autre.
"""

LEGISLATURE = "17"
BASE = f"https://data.assemblee-nationale.fr/static/openData/repository/{LEGISLATURE}"

HISTORIQUE = "amo30.json.zip"

# nom du jeu -> liste de (nom de fichier local, adresse)
JEUX = {
    "acteurs": [
        # Tous les organes, y compris les circonscriptions et les commissions.
        ("amo10.json.zip", f"{BASE}/amo/deputes_actifs_mandats_actifs_organes/"
                           "AMO10_deputes_actifs_mandats_actifs_organes.json.zip"),
        # Tous les députés de la législature (y compris ceux qui ont quitté
        # l'Assemblée), les sénateurs et les ministres : nécessaire pour
        # rattacher les votes et les prises de parole passés.
        ("amo20.json.zip", f"{BASE}/amo/deputes_senateurs_ministres_legislature/"
                           "AMO20_dep_sen_min_tous_mandats_et_organes.json.zip"),
        # Historique complet : sert uniquement à retrouver les mandats de
        # député des législatures précédentes.
        (HISTORIQUE, f"{BASE}/amo/tous_acteurs_mandats_organes_xi_legislature/"
                     "AMO30_tous_acteurs_tous_mandats_tous_organes_historique.json.zip"),
    ],
    "scrutins": [
        ("scrutins.json.zip", f"{BASE}/loi/scrutins/Scrutins.json.zip"),
    ],
    "reunions": [
        ("agenda.json.zip", f"{BASE}/vp/reunions/Agenda.json.zip"),
    ],
    "questions": [
        ("questions_ecrites.json.zip",
         f"{BASE}/questions/questions_ecrites/Questions_ecrites.json.zip"),
        ("questions_gouvernement.json.zip",
         f"{BASE}/questions/questions_gouvernement/Questions_gouvernement.json.zip"),
        ("questions_orales.json.zip",
         f"{BASE}/questions/questions_orales_sans_debat/Questions_orales_sans_debat.json.zip"),
    ],
    "dossiers": [
        ("dossiers.json.zip",
         f"{BASE}/loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip"),
    ],
    "debats": [
        ("debats.xml.zip", f"{BASE}/vp/syceronbrut/syseron.xml.zip"),
    ],
    "amendements": [
        ("amendements.json.zip",
         f"{BASE}/loi/amendements_div_legis/Amendements.json.zip"),
    ],
}

# Ordre de chargement : les acteurs d'abord, les autres jeux s'y rattachent.
ORDRE = ["acteurs", "scrutins", "reunions", "questions", "dossiers", "debats",
         "amendements"]
