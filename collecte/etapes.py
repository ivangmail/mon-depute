"""Où en est un texte : une phrase tirée des étapes publiées par l'Assemblée.

Seules les étapes datées sont utilisées : décisions de l'Assemblée et du Sénat,
commission mixte paritaire, Conseil constitutionnel, promulgation, retrait,
dépôt et début d'examen en séance. La phrase décrit la dernière étape connue,
sans en tirer de conséquence juridique.
"""

import datetime
import re

from .portrait import jour

# Types d'actes conservés au chargement des dossiers.
TYPES = ("Decision_Type", "Promulgation_Type", "ConclusionEtapeCC_Type", "RetraitInitiative_Type",
         "DepotInitiative_Type", "DepotInitiativeNavette_Type", "DiscussionSeancePublique_Type")

ARTICLE_45 = re.compile(r",? dans les conditions prévues à l'article 45, alinéa 3, de la Constitution")
# Texte « considéré comme adopté » (ou rejeté, si une motion de censure est votée) après
# l'engagement de la responsabilité du Gouvernement : il n'y a pas de vote sur le texte.
ARTICLE_49_3 = re.compile(r"\s*par l'Assemblée nationale en application de l'article 49, "
                          r"alinéa 3,? de la Constitution", re.IGNORECASE)
MASCULIN = (("adoptée", "adopté"), ("modifiée", "modifié"), ("rejetée", "rejeté"),
            ("considérée", "considéré"), ("définitive", "définitif"))


def _chambre(prefixe):
    return "l'Assemblée nationale" if prefixe.startswith("AN") else "le Sénat"


def _vers(prefixe):
    return "à l'Assemblée nationale" if prefixe.startswith("AN") else "au Sénat"


def _lecture(prefixe):
    suite = prefixe[2:]
    if suite == "1":
        return "en 1re lecture"
    if suite.isdigit():
        return f"en {suite}e lecture"
    return {"NLEC": "en nouvelle lecture", "LDEF": "en lecture définitive",
            "LUNI": "en lecture unique"}.get(suite, "")


def _statut(etape):
    texte = ARTICLE_49_3.sub("", ARTICLE_45.sub("", (etape.get("statut") or "").strip())).lower()
    for feminin, masculin in MASCULIN:
        texte = re.sub(rf"\b{feminin}\b", masculin, texte)
    return texte


def _adopte(etape):
    return _statut(etape).startswith(("adopté", "considéré comme adopté"))


def _decision(etape):
    """Phrase décrivant une décision d'une assemblée ou de la commission mixte paritaire."""
    code, date = etape["code"], jour(etape["date"])
    if code == "CMP-DEC":
        accord = "Accord" if _statut(etape).startswith("accord") else "Désaccord"
        return f"{accord} en commission mixte paritaire le {date}"
    statut = _statut(etape)
    if code.startswith("CMP-DEBATS-"):
        prefixe, lecture = code.split("-")[2], "sur le texte de la commission mixte paritaire"
    else:
        prefixe = code.split("-")[0]
        lecture = _lecture(prefixe)
    if statut.startswith(("considéré comme adopté", "considéré comme rejeté")):
        sens = "adopté" if "adopté" in statut else "rejeté"
        return (f"Texte considéré comme {sens} par {_chambre(prefixe)} le {date}"
                + (f", {lecture}" if lecture else "") + ", sans vote sur le texte, le Gouvernement"
                " ayant engagé sa responsabilité (article 49, alinéa 3, de la Constitution)")
    if statut.startswith("considéré comme définitif"):
        # Résolution européenne (article 151-7 du Règlement de l'Assemblée).
        return f"Texte considéré comme définitif par {_chambre(prefixe)} le {date}"
    if statut.split(" ")[0] in ("adopté", "modifié", "rejeté"):
        return f"Texte {statut} par {_chambre(prefixe)} le {date}" + (f", {lecture}" if lecture
                                                                     else "")
    return f"{_chambre(prefixe)[0].upper()}{_chambre(prefixe)[1:]} le {date}" \
        + (f" ({lecture})" if lecture else "") + f" : {statut}"


def _definitif(decisions):
    """Date de l'adoption définitive par le Parlement, ou None."""
    dates = []
    for e in decisions:
        code, statut = e["code"], _statut(e)
        if not _adopte(e):
            continue
        prefixe = code.split("-")[0]
        if prefixe in ("ANLDEF", "SNLDEF"):
            dates.append(e["date"])
        elif "sans modification" in statut and prefixe[2:].isdigit():
            dates.append(e["date"])  # vote conforme : les deux assemblées ont adopté le même texte
    cmp = {e["code"]: e["date"] for e in decisions
           if e["code"] in ("CMP-DEBATS-AN-DEC", "CMP-DEBATS-SN-DEC") and _adopte(e)}
    if len(cmp) == 2:
        dates.append(max(cmp.values()))
    return max(dates) if dates else None


def _rang(etape):
    """Ordre chronologique. Le même jour, l'accord en commission mixte paritaire
    précède les votes des assemblées sur son texte, quel que soit l'ordre du dossier."""
    return etape["date"], etape["code"] != "CMP-DEC", etape.get("ordre", 0)


def decrire(etapes):
    """Phrase décrivant l'état d'un texte, ou "" si rien n'est connu.

    etapes : dictionnaires (code, date AAAA-MM-JJ, statut, code_loi), dans
    l'ordre du dossier. Les étapes sans date sont ignorées.
    """
    datees = sorted((e for e in etapes if e.get("date")), key=_rang)
    if not datees:
        return ""

    def dernier(condition):
        trouves = [e for e in datees if condition(e)]
        return trouves[-1] if trouves else None

    promulgation = dernier(lambda e: e["code"] == "PROM-PUB")
    conseil = dernier(lambda e: e["code"] == "CC-CONCLUSION")
    if promulgation:
        texte = f"Loi promulguée le {jour(promulgation['date'])}"
        if promulgation.get("code_loi"):
            texte += f" (loi n° {promulgation['code_loi']})"
        if conseil and conseil["date"] <= promulgation["date"] and conseil.get("statut"):
            texte += f", après une décision du Conseil constitutionnel : {conseil['statut'].lower()}"
        return texte
    retrait = dernier(lambda e: e["code"].endswith("-RTRINI"))
    if retrait and retrait is datees[-1]:
        return f"Texte retiré par son auteur le {jour(retrait['date'])}"
    if conseil:
        return (f"Décision du Conseil constitutionnel le {jour(conseil['date'])} : "
                f"{(conseil.get('statut') or '').lower()} ; loi pas encore promulguée")
    decisions = [e for e in datees if e["code"].endswith("-DEC") and e.get("statut")]
    definitif = _definitif(decisions)
    if definitif:
        return (f"Texte adopté définitivement par le Parlement le {jour(definitif)}, "
                "pas encore promulgué")
    if decisions:
        derniere = decisions[-1]
        texte = _decision(derniere)
        apres = [e for e in datees if _rang(e) > _rang(derniere)]
        depots = [e for e in apres if e["code"].endswith("-DEPOT")]
        seances = [e for e in apres if e["code"].endswith("-DEBATS-SEANCE")]
        if seances:
            prefixe = seances[0]["code"].split("-")[0]
            texte += f" ; examen en séance {_vers(prefixe)} depuis le {jour(seances[0]['date'])}"
        elif depots:
            prefixe = depots[-1]["code"].split("-")[0]
            if prefixe != "CMP":
                texte += f", puis transmis {_vers(prefixe)} le {jour(depots[-1]['date'])}"
        return texte
    seances = [e for e in datees if e["code"].endswith("-DEBATS-SEANCE")]
    if seances:
        prefixe = seances[-1]["code"].split("-")[0]
        premiere = [e for e in seances if e["code"].split("-")[0] == prefixe][0]
        return (f"Examen en séance commencé {_vers(prefixe)} le {jour(premiere['date'])}, "
                "sans vote sur l'ensemble du texte à ce jour")
    depot = datees[-1]
    return f"Texte déposé {_vers(depot['code'].split('-')[0])} le {jour(depot['date'])}"


PARCOURS_MAX = 8  # étapes affichées au plus ; au-delà, les plus récentes


def _assemblee(prefixe):
    return "Assemblée" if prefixe.startswith("AN") else "Sénat"


def parcours(etapes):
    """Étapes déjà franchies et datées, dans l'ordre : [{libelle, date, sens}].

    sens vaut « adopté », « rejeté » ou « neutre » (dépôt, décision du Conseil
    constitutionnel, retrait). Aucune étape future n'est déduite. Au-delà de
    PARCOURS_MAX étapes, seules les plus récentes sont gardées."""
    datees = sorted((e for e in etapes if e.get("date")), key=_rang)
    sortie, depose = [], False
    for e in datees:
        code, statut = e["code"], _statut(e)
        prefixe = code.split("-")[0]
        if code.endswith("-DEPOT") and not depose and prefixe != "CMP":
            depose = True
            sortie.append({"libelle": f"Dépôt, {_assemblee(prefixe)}", "date": e["date"],
                           "sens": "neutre"})
        elif code == "CMP-DEC":
            accord = statut.startswith("accord")
            sortie.append({"libelle": "Commission mixte paritaire" + ("" if accord else
                                                                     ", désaccord"),
                           "date": e["date"], "sens": "adopté" if accord else "rejeté"})
        elif code.endswith("-DEC") and e.get("statut"):
            if code.startswith("CMP-DEBATS-"):
                libelle = f"{_assemblee(code.split('-')[2])}, texte de la CMP"
            else:
                lecture = {"en 1re lecture": "1re lecture"}.get(_lecture(prefixe),
                                                                 _lecture(prefixe)[3:])
                libelle = _assemblee(prefixe) + (f", {lecture}" if lecture else "")
            if statut.startswith("considéré comme"):
                libelle += ", sans vote (49.3)" if "49" in (e.get("statut") or "") else ""
            sens = ("rejeté" if "rejeté" in statut.split(",")[0]
                    else "adopté" if statut.startswith(("adopté", "modifié", "considéré"))
                    else "neutre")
            sortie.append({"libelle": libelle, "date": e["date"], "sens": sens})
        elif code == "CC-CONCLUSION":
            sortie.append({"libelle": "Conseil constitutionnel", "date": e["date"],
                           "sens": "neutre"})
        elif code == "PROM-PUB":
            sortie.append({"libelle": "Promulgation", "date": e["date"], "sens": "adopté"})
        elif code.endswith("-RTRINI"):
            sortie.append({"libelle": "Retrait", "date": e["date"], "sens": "neutre"})
    return sortie[-PARCOURS_MAX:]


def _charger(db, uids, aujourdhui=None):
    """{dossier: [étapes]} pour les dossiers demandés, sans les étapes datées après
    aujourdhui (AAAA-MM-JJ, par défaut la date du jour) : le dossier publié par
    l'Assemblée contient aussi les séances prévues, qui ne sont pas des étapes
    franchies."""
    aujourdhui = aujourdhui or datetime.date.today().isoformat()
    if not any(r[0] == "etapes" for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")):
        return {}
    uids = sorted({u for u in uids if u})
    par_dossier = {}
    for i in range(0, len(uids), 500):
        morceau = uids[i:i + 500]
        for uid, ordre, code, date, statut, code_loi in db.execute(
                "SELECT dossier_uid, ordre, code, date, statut, code_loi FROM etapes"
                f" WHERE dossier_uid IN ({','.join('?' * len(morceau))}) ORDER BY dossier_uid,"
                " ordre", morceau).fetchall():
            if date and date > aujourdhui:
                continue
            par_dossier.setdefault(uid, []).append(
                {"ordre": ordre, "code": code, "date": date, "statut": statut,
                 "code_loi": code_loi})
    return par_dossier


def parcours_pour_dossiers(db, uids, aujourdhui=None):
    """{dossier: parcours} pour les dossiers demandés qui ont au moins une étape datée."""
    return {uid: p for uid, etapes in _charger(db, uids, aujourdhui).items()
            if (p := parcours(etapes))}


def pour_dossiers(db, uids, aujourdhui=None):
    """{dossier: phrase} pour les dossiers demandés qui ont au moins une étape datée,
    en ne tenant compte que des étapes datées au plus tard aujourdhui."""
    resultat = {}
    for uid, etapes in _charger(db, uids, aujourdhui).items():
        texte = decrire(etapes)
        if texte:
            resultat[uid] = texte
    return resultat
