"""Chargement des archives de l'Assemblée dans la base.

Chaque archive est un instantané complet : on vide les tables du jeu puis on
recharge tout, dans une seule transaction. Si le chargement échoue, la base
garde les données précédentes.
"""

import html
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile

from .sources import HISTORIQUE, LEGISLATURE

NS = "{http://schemas.assemblee-nationale.fr/referentiel}"
BALISE = re.compile(r"<[^>]+>")
ESPACES = re.compile(r"\s+")
ORGANE_DANS_UID = re.compile(r"(PO\d+)")


# ---------------------------------------------------------------- utilitaires

def val(x):
    """Valeur simple d'un champ. Les champs vides arrivent sous la forme
    {"@xsi:nil": "true"} et les identifiants typés sous {"#text": ...}."""
    if isinstance(x, dict):
        return x.get("#text")
    return x


def liste(x):
    """Le format JSON de l'Assemblée donne un objet seul quand il n'y a
    qu'un élément, et une liste sinon."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def lire(objet, *chemin):
    """Descend dans des dictionnaires imbriqués sans lever d'erreur."""
    for cle in chemin:
        if not isinstance(objet, dict):
            return None
        objet = objet.get(cle)
    return val(objet)


def sous(objet, *chemin):
    """Comme lire(), mais renvoie la structure brute (dict ou liste)."""
    for cle in chemin:
        if not isinstance(objet, dict):
            return None
        objet = objet.get(cle)
    if isinstance(objet, dict) and objet.get("@xsi:nil") == "true":
        return None
    return objet


def date(x):
    """Ne garde que AAAA-MM-JJ d'une date ou d'un horodatage."""
    x = val(x)
    return x[:10] if isinstance(x, str) and len(x) >= 10 else None


def entier(x):
    try:
        return int(val(x))
    except (TypeError, ValueError):
        return None


def texte_brut(x):
    """Retire les balises HTML et décode les entités."""
    x = val(x)
    if not isinstance(x, str):
        return None
    return ESPACES.sub(" ", html.unescape(BALISE.sub(" ", x))).strip() or None


def fichiers_json(chemin_zip, contient=""):
    with zipfile.ZipFile(chemin_zip) as archive:
        for nom in archive.namelist():
            if nom.endswith(".json") and contient in nom:
                yield nom, json.loads(archive.read(nom))


# -------------------------------------------------------------------- acteurs

def _contact(adresse):
    genre = adresse.get("typeLibelle")
    if adresse.get("valElec"):
        return genre, adresse["valElec"]
    morceaux = [adresse.get(c) for c in ("intitule", "numeroRue", "nomRue",
                                         "complementAdresse", "codePostal", "ville")]
    return genre, ESPACES.sub(" ", " ".join(m for m in morceaux if m)).strip()


def charger_acteurs(db, chemins):
    for table in ("organes", "acteurs", "mandats", "contacts", "deputes"):
        db.execute(f"DELETE FROM {table}")
    historiques = [c for c in chemins if os.path.basename(c) == HISTORIQUE]
    for chemin in chemins:
        if chemin in historiques:
            continue
        for _, contenu in fichiers_json(chemin, "/organe/"):
            o = contenu["organe"]
            db.execute(
                "INSERT OR REPLACE INTO organes VALUES (?,?,?,?,?,?,?,?,?)",
                (val(o.get("uid")), o.get("codeType"), o.get("libelle"),
                 o.get("libelleAbrege") or o.get("libelleAbrev"), val(o.get("legislature")),
                 date(lire(o, "viMoDe", "dateDebut")), date(lire(o, "viMoDe", "dateFin")),
                 val(o.get("couleurAssociee")), val(o.get("organeParent"))))
        for _, contenu in fichiers_json(chemin, "/acteur/"):
            a = contenu["acteur"]
            uid = val(a.get("uid"))
            naissance = sous(a, "etatCivil", "infoNaissance") or {}
            lieu = ", ".join(v for v in (val(naissance.get("villeNais")),
                                         val(naissance.get("depNais"))) if v)
            db.execute(
                "INSERT OR REPLACE INTO acteurs VALUES (?,?,?,?,?,?,?,?)",
                (uid, lire(a, "etatCivil", "ident", "civ"),
                 lire(a, "etatCivil", "ident", "prenom"),
                 lire(a, "etatCivil", "ident", "nom"),
                 date(naissance.get("dateNais")), lieu or None,
                 lire(a, "profession", "libelleCourant"), val(a.get("uri_hatvp"))))
            for adresse in liste(sous(a, "adresses", "adresse")):
                genre, valeur = _contact(adresse)
                if valeur:
                    db.execute("INSERT OR REPLACE INTO contacts VALUES (?,?,?,?)",
                               (adresse.get("uid"), uid, genre, valeur))
            for m in liste(sous(a, "mandats", "mandat")):
                db.execute(
                    "INSERT OR REPLACE INTO mandats VALUES (?,?,?,?,?,?,?,?)",
                    (m.get("uid"), uid, _premier_organe(m),
                     m.get("typeOrgane"), val(m.get("legislature")),
                     date(m.get("dateDebut")), date(m.get("dateFin")),
                     lire(m, "infosQualite", "codeQualite")))
                _depute_depuis_mandat(db, uid, m)
    _rattacher_groupes(db)
    for chemin in historiques:
        _mandats_anterieurs(db, chemin)
    return db.execute("SELECT count(*) FROM deputes").fetchone()[0]


def _mandats_anterieurs(db, chemin):
    """Ajoute les mandats de député des législatures précédentes, pour les
    seuls députés de la législature en cours."""
    connus = {l[0] for l in db.execute("SELECT acteur_uid FROM deputes")}
    with zipfile.ZipFile(chemin) as archive:
        for nom in archive.namelist():
            uid = os.path.basename(nom)[:-5]
            if "/acteur/" not in nom or uid not in connus:
                continue
            acteur = json.loads(archive.read(nom))["acteur"]
            for m in liste(sous(acteur, "mandats", "mandat")):
                if m.get("typeOrgane") == "ASSEMBLEE":
                    db.execute(
                        "INSERT OR IGNORE INTO mandats VALUES (?,?,?,?,?,?,?,?)",
                        (m.get("uid"), uid, _premier_organe(m), "ASSEMBLEE",
                         val(m.get("legislature")), date(m.get("dateDebut")),
                         date(m.get("dateFin")), lire(m, "infosQualite", "codeQualite")))


def _premier_organe(mandat):
    """Un mandat ministériel peut citer plusieurs organes : on garde le premier."""
    refs = liste(sous(mandat, "organes", "organeRef"))
    return val(refs[0]) if refs else None


def _depute_depuis_mandat(db, uid, m):
    if m.get("typeOrgane") != "ASSEMBLEE" or val(m.get("legislature")) != LEGISLATURE:
        return
    debut, fin = date(m.get("dateDebut")), date(m.get("dateFin"))
    existant = db.execute("SELECT date_debut, date_fin FROM deputes WHERE acteur_uid = ?",
                          (uid,)).fetchone()
    # Un député peut avoir plusieurs mandats dans la législature, parfois avec
    # la même date de début (retour après un passage au gouvernement). On garde
    # le mandat en cours s'il existe, sinon celui qui s'est terminé le plus tard.
    rang = lambda d, f: (f is None, f or "", d or "")
    if existant and rang(existant["date_debut"], existant["date_fin"]) > rang(debut, fin):
        return
    lieu = sous(m, "election", "lieu") or {}
    db.execute(
        "INSERT OR REPLACE INTO deputes VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
        (uid, 0 if fin else 1, m.get("uid"), debut, fin,
         lire(m, "election", "causeMandat"),
         val(lieu.get("region")), val(lieu.get("departement")),
         val(lieu.get("numDepartement")), val(lieu.get("numCirco")),
         lire(m, "mandature", "placeHemicycle")))


def _rattacher_groupes(db):
    """Groupe politique : le mandat de groupe en cours, sinon le dernier."""
    db.execute("""
        UPDATE deputes SET groupe_uid = (
            SELECT m.organe_uid FROM mandats m
            WHERE m.acteur_uid = deputes.acteur_uid AND m.type_organe = 'GP'
              AND m.legislature = ?
            ORDER BY (m.date_fin IS NULL) DESC, m.date_debut DESC LIMIT 1)""",
               (LEGISLATURE,))
    db.execute("""
        UPDATE deputes SET
            groupe_sigle = (SELECT libelle_abrege FROM organes WHERE uid = groupe_uid),
            groupe_libelle = (SELECT libelle FROM organes WHERE uid = groupe_uid)""")


# ------------------------------------------------------------------- scrutins

POSITIONS = {"pours": "pour", "contres": "contre", "abstentions": "abstention",
             "nonVotants": "non_votant",
             "nonVotantsVolontaires": "non_votant_volontaire"}


def charger_scrutins(db, chemins):
    db.execute("DELETE FROM scrutins")
    db.execute("DELETE FROM votes")
    for chemin in chemins:
        for _, contenu in fichiers_json(chemin):
            s = contenu["scrutin"]
            uid = s["uid"]
            decompte = sous(s, "syntheseVote", "decompte") or {}
            db.execute(
                "INSERT OR REPLACE INTO scrutins VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uid, entier(s.get("numero")), date(s.get("dateScrutin")),
                 lire(s, "typeVote", "libelleTypeVote"), lire(s, "sort", "code"),
                 texte_brut(s.get("titre")), texte_brut(lire(s, "demandeur", "texte")),
                 lire(s, "objet", "dossierLegislatif", "dossierRef"),
                 val(s.get("seanceRef")),
                 entier(lire(s, "syntheseVote", "nombreVotants")),
                 entier(lire(s, "syntheseVote", "suffragesExprimes")),
                 entier(decompte.get("pour")), entier(decompte.get("contre")),
                 entier(decompte.get("abstentions"))))
            groupes = liste(sous(s, "ventilationVotes", "organe", "groupes", "groupe"))
            for groupe in groupes:
                nominatif = sous(groupe, "vote", "decompteNominatif") or {}
                for cle, position in POSITIONS.items():
                    for votant in liste(sous(nominatif, cle, "votant")):
                        db.execute(
                            "INSERT OR REPLACE INTO votes VALUES (?,?,?,?,?)",
                            (uid, votant.get("acteurRef"), groupe.get("organeRef"),
                             position, 1 if votant.get("parDelegation") == "true" else 0))
    return db.execute("SELECT count(*) FROM scrutins").fetchone()[0]


# ------------------------------------------------------------------- réunions

TYPES_REUNION = {"reunionCommission_type": "commission", "seance_type": "seance",
                 "reunionInitParlementaire_type": "initiative_parlementaire"}


def charger_reunions(db, chemins):
    db.execute("DELETE FROM reunions")
    db.execute("DELETE FROM presences")
    for chemin in chemins:
        for _, contenu in fichiers_json(chemin):
            r = contenu["reunion"]
            uid = r["uid"]
            objet = sous(r, "ODJ", "resumeODJ", "item") or sous(r, "ODJ", "convocationODJ", "item")
            if objet is None:
                points = liste(sous(r, "ODJ", "pointsODJ", "pointODJ"))
                objet = [p.get("objet") for p in points if isinstance(p, dict)]
            objet = " ; ".join(str(o) for o in liste(objet) if o) or None
            db.execute(
                "INSERT OR REPLACE INTO reunions VALUES (?,?,?,?,?,?,?,?)",
                (uid, TYPES_REUNION.get(r.get("@xsi:type"), r.get("@xsi:type")),
                 val(r.get("timeStampDebut")), val(r.get("timeStampFin")),
                 val(r.get("organeReuniRef")), lire(r, "cycleDeVie", "etat"),
                 texte_brut(objet), val(r.get("compteRenduRef"))))
            internes = sous(r, "participants", "participantsInternes", "participantInterne")
            for p in liste(internes):
                if p.get("acteurRef") and p.get("presence"):
                    db.execute("INSERT OR REPLACE INTO presences VALUES (?,?,?)",
                               (uid, p["acteurRef"], p["presence"]))
    return db.execute("SELECT count(*) FROM reunions").fetchone()[0]


# ------------------------------------------------------------------ questions

def charger_questions(db, chemins):
    db.execute("DELETE FROM questions")
    for chemin in chemins:
        for _, contenu in fichiers_json(chemin):
            q = contenu["question"]
            textes_q = liste(sous(q, "textesQuestion", "texteQuestion"))
            textes_r = liste(sous(q, "textesReponse", "texteReponse"))
            attributions = liste(sous(q, "minAttribs", "minAttrib"))
            date_q = (lire(textes_q[0], "infoJO", "dateJO") if textes_q
                      else lire(attributions[0], "infoJO", "dateJO") if attributions
                      else None)
            analyses = liste(sous(q, "indexationAN", "analyses", "analyse"))
            db.execute(
                "INSERT OR REPLACE INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (q["uid"], q.get("type"), entier(lire(q, "identifiant", "numero")),
                 lire(q, "auteur", "identite", "acteurRef"),
                 lire(q, "auteur", "groupe", "abrege"), lire(q, "minInt", "developpe"),
                 lire(q, "indexationAN", "rubrique"),
                 " ; ".join(a for a in analyses if isinstance(a, str)) or None,
                 date(date_q),
                 date(lire(textes_r[0], "infoJO", "dateJO")) if textes_r else None,
                 lire(q, "cloture", "libelleCloture"),
                 texte_brut(textes_q[0].get("texte")) if textes_q else None,
                 texte_brut(textes_r[0].get("texte")) if textes_r else None))
    return db.execute("SELECT count(*) FROM questions").fetchone()[0]


# ------------------------------------------------------- dossiers et documents

def charger_dossiers(db, chemins):
    for table in ("dossiers", "documents", "documents_signataires"):
        db.execute(f"DELETE FROM {table}")
    for chemin in chemins:
        for _, contenu in fichiers_json(chemin, "/dossierParlementaire/"):
            d = contenu["dossierParlementaire"]
            db.execute(
                "INSERT OR REPLACE INTO dossiers VALUES (?,?,?,?,?,?)",
                (d["uid"], d.get("@xsi:type"), val(d.get("legislature")),
                 lire(d, "titreDossier", "titre"), lire(d, "titreDossier", "titreChemin"),
                 lire(d, "procedureParlementaire", "libelle")))
        for _, contenu in fichiers_json(chemin, "/document/"):
            d = contenu["document"]
            uid = d["uid"]
            db.execute(
                "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?)",
                (uid, lire(d, "classification", "type", "code"),
                 val(d.get("denominationStructurelle")), val(d.get("legislature")),
                 lire(d, "titres", "titrePrincipal"),
                 date(lire(d, "cycleDeVie", "chrono", "dateDepot")),
                 val(d.get("dossierRef"))))
            for auteur in liste(sous(d, "auteurs", "auteur")):
                ref = lire(auteur, "acteur", "acteurRef")
                if ref:
                    db.execute(
                        "INSERT OR REPLACE INTO documents_signataires VALUES (?,?,?)",
                        (uid, ref, lire(auteur, "acteur", "qualite") or "auteur"))
            for cosignataire in liste(sous(d, "coSignataires", "coSignataire")):
                ref = lire(cosignataire, "acteur", "acteurRef")
                if ref and not val(cosignataire.get("dateRetraitCosignature")):
                    db.execute(
                        "INSERT OR REPLACE INTO documents_signataires VALUES (?,?,?)",
                        (uid, ref, "cosignataire"))
    return db.execute("SELECT count(*) FROM documents").fetchone()[0]


# --------------------------------------------------------------------- débats

def _texte_xml(element):
    if element is None:
        return ""
    return ESPACES.sub(" ", "".join(element.itertext())).strip()


def _date_seance(brut):
    """« 20261109160000000 » -> « 2026-11-09 »."""
    if not brut or len(brut) < 8 or not brut[:8].isdigit():
        return None
    return f"{brut[:4]}-{brut[4:6]}-{brut[6:8]}"


def _parcourir(element, etat, sortie):
    """Parcourt le compte rendu dans l'ordre et note, pour chaque prise de
    parole, le dernier titre de niveau 1 rencontré. Ce titre est un élément
    voisin des prises de parole, pas leur parent : on le mémorise au passage."""
    for enfant in element:
        nom = enfant.tag.replace(NS, "")
        if nom == "point":
            titre = _texte_xml(enfant.find(NS + "texte"))
            if enfant.get("nivpoint") == "1" and titre:
                etat["sujet"] = titre
            _parcourir(enfant, etat, sortie)
        elif nom == "paragraphe":
            sortie.append((enfant, etat["sujet"]))
        elif nom not in ("orateurs", "texte"):
            _parcourir(enfant, etat, sortie)


def _acteur_reel(identifiant):
    """Les orateurs sans fiche (« Un député du groupe… », personnes
    auditionnées) portent un identifiant factice : PA0 ou PA-123456."""
    if not identifiant or identifiant == "PA0" or identifiant.startswith("PA-"):
        return None
    return identifiant


def charger_debats(db, chemins):
    db.execute("DELETE FROM comptes_rendus")
    db.execute("DELETE FROM interventions")
    for chemin in chemins:
        with zipfile.ZipFile(chemin) as archive:
            for nom in archive.namelist():
                if not nom.endswith(".xml"):
                    continue
                racine = ET.fromstring(archive.read(nom))
                uid = _texte_xml(racine.find(NS + "uid"))
                meta = racine.find(NS + "metadonnees")
                trouver = lambda cle: _texte_xml(meta.find(NS + cle)) if meta is not None else ""
                db.execute(
                    "INSERT OR REPLACE INTO comptes_rendus VALUES (?,?,?,?,?,?)",
                    (uid, _texte_xml(racine.find(NS + "seanceRef")) or None,
                     _date_seance(trouver("dateSeance")), trouver("session") or None,
                     trouver("numSeance") or None, trouver("etat") or None))
                contenu = racine.find(NS + "contenu")
                if contenu is None:
                    continue
                paragraphes = []
                _parcourir(contenu, {"sujet": None}, paragraphes)
                for p, sujet in paragraphes:
                    texte = _texte_xml(p.find(NS + "texte"))
                    orateur = p.find(f"{NS}orateurs/{NS}orateur")
                    if not texte or orateur is None:
                        continue
                    acteur = _acteur_reel(p.get("id_acteur"))
                    db.execute(
                        "INSERT INTO interventions (compte_rendu_uid, ordre, acteur_uid,"
                        " orateur, qualite, role, code_grammaire, sujet, nb_mots, texte)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (uid, entier(p.get("ordre_absolu_seance")), acteur,
                         _texte_xml(orateur.find(NS + "nom")) or None,
                         _texte_xml(orateur.find(NS + "qualite")) or None,
                         p.get("roledebat"), p.get("code_grammaire"), sujet,
                         len(texte.split()), texte))
    return db.execute("SELECT count(*) FROM interventions").fetchone()[0]


# ---------------------------------------------------------------- amendements

def charger_amendements(db, chemins):
    db.execute("DELETE FROM amendements")
    db.execute("DELETE FROM amendements_cosignataires")
    for chemin in chemins:
        for _, contenu in fichiers_json(chemin):
            a = contenu["amendement"]
            uid = a["uid"]
            auteur = sous(a, "signataires", "auteur") or {}
            organe = ORGANE_DANS_UID.search(val(a.get("examenRef")) or uid)
            corps = sous(a, "corps", "contenuAuteur") or {}
            db.execute(
                "INSERT OR REPLACE INTO amendements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uid, lire(a, "identification", "numeroLong"),
                 val(a.get("texteLegislatifRef")), val(a.get("examenRef")),
                 organe.group(1) if organe else None, val(auteur.get("acteurRef")),
                 val(auteur.get("groupePolitiqueRef")), val(auteur.get("typeAuteur")),
                 date(lire(a, "cycleDeVie", "dateDepot")),
                 lire(a, "cycleDeVie", "etatDesTraitements", "etat", "libelle"),
                 lire(a, "cycleDeVie", "sort"),
                 lire(a, "pointeurFragmentTexte", "division", "articleDesignationCourte"),
                 texte_brut(corps.get("dispositif")),
                 texte_brut(corps.get("exposeSommaire"))))
            for ref in liste(sous(a, "signataires", "cosignataires", "acteurRef")):
                if isinstance(ref, str):
                    db.execute(
                        "INSERT OR REPLACE INTO amendements_cosignataires VALUES (?,?)",
                        (uid, ref))
    return db.execute("SELECT count(*) FROM amendements").fetchone()[0]


CHARGEURS = {
    "acteurs": charger_acteurs,
    "scrutins": charger_scrutins,
    "reunions": charger_reunions,
    "questions": charger_questions,
    "dossiers": charger_dossiers,
    "debats": charger_debats,
    "amendements": charger_amendements,
}
