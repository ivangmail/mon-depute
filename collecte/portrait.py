"""Portrait rédigé d'un député, en phrases, à partir des données.

Aucune appréciation : uniquement des faits tirés de la base. Les tournures
évitent les articles devant les noms de département (« de l'Ain », « du
Nord », « de la Loire »…), impossibles à accorder sans table dédiée.
"""

import datetime
import re

# Certaines professions arrivent précédées de leur code : « (47) - Technicien ».
PREFIXE_CODE = re.compile(r"^\(\d+\)\s*-\s*")


def jour(iso):
    """AAAA-MM-JJ -> JJ/MM/AAAA."""
    if not iso or len(iso) < 10:
        return "—"
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"


def ordinal(n, feminin=False):
    n = int(n)
    if n == 1:
        return "1re" if feminin else "1er"
    return f"{n}e"


def age(naissance, aujourdhui=None):
    if not naissance:
        return None
    a = aujourdhui or datetime.date.today()
    n = datetime.date.fromisoformat(naissance[:10])
    return a.year - n.year - ((a.month, a.day) < (n.month, n.day))


def enumerer(elements):
    elements = [str(e) for e in elements]
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " et " + elements[-1]


def rediger(acteur, depute, commissions, legislatures, aujourdhui=None):
    """Renvoie la liste des phrases du portrait.

    acteur, depute : lignes des tables du même nom.
    commissions : liste de (libellé, qualité) des commissions permanentes en cours.
    legislatures : numéros des législatures où la personne a été députée.
    """
    femme = acteur["civilite"] == "Mme"
    e = "e" if femme else ""
    pronom = "Elle" if femme else "Il"
    nom = f"{acteur['prenom']} {acteur['nom']}"
    en_exercice = bool(depute["en_exercice"])
    phrases = []

    naissance = ""
    if acteur["date_naissance"]:
        naissance = f", né{e} le {jour(acteur['date_naissance'])}"
        if acteur["lieu_naissance"]:
            ville, _, departement = acteur["lieu_naissance"].partition(", ")
            naissance += f" à {ville}" + (f" ({departement})" if departement else "")
        naissance += ","
    circo = ""
    if depute["num_circo"]:
        circo = (f" de la {ordinal(depute['num_circo'], feminin=True)} circonscription"
                 f" ({depute['departement']}, {depute['num_departement']})")
    if en_exercice:
        ans = age(acteur["date_naissance"], aujourdhui)
        phrases.append(f"{nom}{naissance} est député{e}{circo}."
                       + (f" {pronom} a {ans} ans." if ans is not None else ""))
    else:
        phrases.append(f"{nom}{naissance} a été député{e}{circo} pendant la"
                       f" 17e législature.")

    if en_exercice:
        mandat = f"{pronom} siège depuis le {jour(depute['date_debut'])}"
    else:
        mandat = (f"Son mandat a couru du {jour(depute['date_debut'])}"
                  f" au {jour(depute['date_fin'])}")
    cause = depute["cause_mandat"] or ""
    if cause.startswith("élection partielle"):
        mandat += ", à la suite d'une élection partielle"
    elif cause.startswith("reprise de l'exercice"):
        mandat += ", avec une interruption pendant un passage au Gouvernement"
    elif "incompatibilité" in cause:
        mandat += ", en remplacement d'un député démissionnaire pour incompatibilité"
    elif cause.startswith("remplacement"):
        mandat += f", en {cause}"
    phrases.append(mandat + ".")

    # L'historique publié par l'Assemblée ne remonte qu'à 2002 : on ne peut donc
    # jamais affirmer qu'il s'agit d'un premier mandat, seulement citer ceux connus.
    autres = sorted(int(l) for l in legislatures if l and int(l) != 17)
    if autres:
        phrases.append(
            f"Depuis 2002, {pronom.lower()} a aussi été député{e} sous "
            + ("la " if len(autres) == 1 else "les ")
            + enumerer(f"{n}e" for n in autres)
            + (" législature." if len(autres) == 1 else " législatures."))

    if depute["groupe_libelle"]:
        verbe = "siège" if en_exercice else "siégeait en dernier lieu"
        if depute["groupe_sigle"] == "NI":
            phrases.append(f"{pronom} {verbe} parmi les députés non inscrits,"
                           " c'est-à-dire sans groupe politique.")
        else:
            phrases.append(f"{pronom} {verbe} au sein du groupe"
                           f" {depute['groupe_libelle']} ({depute['groupe_sigle']}).")

    if en_exercice and commissions:
        libelles = {}
        for libelle, qualite in commissions:
            libelles.setdefault(libelle, [])
            if qualite and qualite.lower() != "membre":
                libelles[libelle].append(qualite.lower())
        morceaux = []
        for libelle, qualites in libelles.items():
            nom_commission = libelle[0].lower() + libelle[1:]
            morceaux.append(f"la {nom_commission}"
                            + (f" ({enumerer(qualites)})" if qualites else ""))
        phrases.append(f"{pronom} est membre de {enumerer(morceaux)}.")

    profession = PREFIXE_CODE.sub("", acteur["profession"] or "").strip()
    if profession and not profession.lower().startswith("sans profession"):
        phrases.append(f"Profession déclarée : {profession[0].lower() + profession[1:]}.")
    return phrases
