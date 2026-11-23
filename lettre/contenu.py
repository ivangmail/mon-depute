"""Contenu d'une lettre : l'activité d'un député sur une période.

Uniquement des faits tirés des données de l'Assemblée, selon les mêmes règles
que le site (voir collecte/indicateurs.py et la page Méthodologie).
"""

import datetime
import re
import statistics
from html import escape

from collecte import etapes, fiche, indicateurs, site, themes
from collecte.portrait import jour, ordinal
from collecte.sources import LEGISLATURE

URL_DOSSIER = "https://www.assemblee-nationale.fr/dyn/" + LEGISLATURE + "/dossiers/{}"
LIMITE = 5  # éléments listés par rubrique
LONGUEUR_OBJET = 160  # caractères conservés de l'objet d'une réunion
LONGUEUR_EXTRAIT = 220  # caractères cités d'une intervention ou d'un exposé d'amendement
MOTS_MIN_EXTRAIT = 100  # une prise de parole plus courte n'est pas citée
EXEMPLES_AMENDEMENTS = 2
LIMITE_MAJEURS = 8  # votes listés dans « L'essentiel »
LIMITE_ETATS = 8  # textes listés dans « Où en sont ces textes »
LIMITE_AGENDA = 8  # textes listés dans « À l'ordre du jour »
JOURS_AGENDA = 7  # l'ordre du jour couvre les sept jours qui suivent la composition
TYPES_AGENDA = ("Discussion", "Suite de la discussion", "Vote solennel", "Explications de vote")
JOURS_SEMAINE = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOTION = "motion de censure"
# Un scrutin est « serré » quand l'écart entre les pour et les contre ne dépasse pas ce nombre.
ECART_SERRE = 10
# En dessous de cette part des suffrages exprimés du groupe, sa position majoritaire
# n'est pas présentée comme une ligne : le groupe est dit partagé.
SEUIL_LIGNE = indicateurs.SEUIL_LIGNE  # même règle que le site
# Votes qui engagent un texte entier ou le Gouvernement : ils ouvrent la lettre.
MAJEUR = f"""(s.type_vote IN ('{indicateurs.SOLENNEL}', '{MOTION}')
    OR replace(s.titre, '’', char(39)) LIKE 'l' || char(39) || 'ensemble%'
    OR s.titre LIKE 'la première partie%' OR s.titre LIKE 'la deuxième partie%'
    OR s.titre LIKE 'la troisième partie%' OR s.titre LIKE 'la quatrième partie%')"""
ABSENCE = ("Une absence à un vote peut avoir une raison légitime (autre réunion au même "
           "moment, déplacement, maladie) : elle ne suffit pas à juger du travail d'un député.")


PUCES = re.compile(r"([:;])(?:\s*[;-])+\s*")


def intitule(titre):
    """Intitulé d'un scrutin : majuscule initiale, sans le point final."""
    return fiche.majuscule(titre or "").rstrip(". ")


MARQUE = "\x00"  # encadre, dans un élément de liste, la partie qui porte le lien


def lier(avant, lie, apres=""):
    """Élément de liste dont seule la partie « lie » sera cliquable : une ligne
    entièrement soulignée est pénible à lire dans une messagerie."""
    return f"{avant}{MARQUE}{lie}{MARQUE}{apres}"


def _element_html(texte, url):
    if not url:
        return escape(texte.replace(MARQUE, ""))
    if MARQUE not in texte:
        return f'<a href="{escape(url)}">{escape(texte)}</a>'
    avant, lie, apres = texte.split(MARQUE, 2)
    return f'{escape(avant)}<a href="{escape(url)}">{escape(lie)}</a>{escape(apres)}'


POSITIONS = (("pour", "pour", "pour"), ("contre", "contre", "contre"),
             ("abstention", "abstention", "abstentions"))


def _repartition(decompte):
    """{"pour": 1, "contre": 4} -> ["1 pour", "4 contre"]."""
    return [f"{decompte[p]} {libelle if decompte[p] < 2 else pluriel}"
            for p, libelle, pluriel in POSITIONS if decompte.get(p)]


def votes_par_texte(votes, scrutins=()):
    """Regroupe des votes par dossier législatif, du plus voté au moins voté.

    Chaque groupe donne le titre du texte, le nombre de votes, leur répartition
    (« 1 pour, 4 contre ») et le lien vers le dossier sur le site de l'Assemblée.
    « scrutins » donne, par texte, le nombre de scrutins tenus pendant la période
    (dossier_uid, texte, n) : les scrutins sans participation entrent alors dans
    le décompte, et un texte sans aucun vote du député apparaît quand même.
    """
    groupes = {}

    def groupe(cle, texte):
        return groupes.setdefault(cle or "", {
            "texte": fiche.majuscule(texte or "") or "Textes non identifiés",
            "lien": URL_DOSSIER.format(cle) if cle else None, "uid": cle or None,
            "total": 0, "pour": 0, "contre": 0, "abstention": 0, "sans": 0})

    for v in votes:
        g = groupe(v.get("dossier_uid"), v.get("texte"))
        g["total"] += 1
        g[v["position"]] += 1
    for t in scrutins:
        g = groupe(t.get("dossier_uid"), t.get("texte"))
        g["sans"] = max(t["n"] - g["total"], 0)
    for g in groupes.values():
        morceaux = _repartition(g)
        g["detail"] = ", ".join(morceaux)
        if g["sans"]:
            morceaux.append(_pluriel(g["sans"], "scrutin") + " sans participation")
        g["decompte"] = ", ".join(morceaux)
    return sorted(groupes.values(), key=lambda g: (-g["total"], -g["sans"], g["texte"]))


def position_du_groupe(decompte):
    """Décrit le vote d'un groupe à partir de son décompte {position: nombre}.

    Renvoie (position, texte) : la position n'est renseignée que si elle réunit
    plus de SEUIL_LIGNE des suffrages exprimés du groupe ; sinon il est dit partagé.
    """
    total = sum(decompte.get(p, 0) for p, _, _ in POSITIONS)
    if not total:
        return None, ""
    detail = ", ".join(_repartition(decompte))
    tete = max((p for p, _, _ in POSITIONS), key=lambda p: decompte.get(p, 0))
    if decompte[tete] / total > SEUIL_LIGNE:
        return tete, f"son groupe : {fiche.LIBELLES_POSITION[tete].lower()} ({detail})"
    return None, f"son groupe était partagé ({detail})"


def sort_amendement(sort, etat):
    """Libellé du sort d'un amendement, au singulier et en minuscules."""
    if sort:
        return sort.lower()
    if (etat or "").startswith("Irrecevable"):
        return "irrecevable"
    if etat == "Retiré":
        return "retiré"
    return "sans sort connu à ce jour"


ACCORDS = ("adopté", "rejeté", "tombé", "soutenu", "retiré", "irrecevable")


def _accorder(n, libelle):
    if n < 2:
        return f"{n} {libelle}"
    return f"{n} " + " ".join(m + "s" if m in ACCORDS else m for m in libelle.split())


def _cle_base(db):
    """Identifie la base et son dernier chargement : un calcul mis en cache n'est
    réutilisé que tant que les données n'ont pas été mises à jour."""
    chemin = db.execute("PRAGMA database_list").fetchone()[2]
    return chemin, db.execute("SELECT max(charge_le) FROM imports").fetchone()[0]


_MEDIANES = {}


def medianes(db, debut, fin, groupe_uid, scrutins):
    """Nombre médian de scrutins auxquels un député en exercice a pris part pendant
    la période : (médiane du groupe, médiane de l'Assemblée)."""
    cle = (_cle_base(db), debut, fin, scrutins)
    if cle not in _MEDIANES:
        if len(_MEDIANES) > 50:
            _MEDIANES.clear()
        votes = dict(tuple(l) for l in db.execute(f"""
            SELECT v.acteur_uid, count(*) FROM scrutins s JOIN votes v ON v.scrutin_uid = s.uid
            WHERE s.date >= ? AND s.date < ? AND v.position IN {indicateurs.EXPRIMES}
            GROUP BY v.acteur_uid""", (debut, fin)).fetchall())
        _MEDIANES[cle] = [(l[1], votes.get(l[0], 0)) for l in db.execute(
            "SELECT acteur_uid, groupe_uid FROM deputes WHERE en_exercice = 1").fetchall()]
    tous = [n for _, n in _MEDIANES[cle]]
    groupe = [n for g, n in _MEDIANES[cle] if g == groupe_uid]
    return (statistics.median(groupe) if groupe else None,
            statistics.median(tous) if tous else None)


_COMMISSIONS = {}


JOURS_COMMISSION = 90
_PRINCIPALES = {}


def commissions_principales(db, aujourdhui):
    """{député en exercice: sa commission permanente}.

    Les groupes inscrivent souvent un député, pour un à trois jours, dans une autre
    commission. Sa commission est donc celle où il a siégé le plus de jours sur les
    JOURS_COMMISSION derniers jours, et non la dernière en date."""
    cle = (_cle_base(db), aujourdhui)
    if cle not in _PRINCIPALES:
        if len(_PRINCIPALES) > 20:
            _PRINCIPALES.clear()
        debut = (datetime.date.fromisoformat(aujourdhui)
                 - datetime.timedelta(days=JOURS_COMMISSION)).isoformat()
        jours = {}
        for acteur, organe, n in db.execute("""
                SELECT m.acteur_uid, m.organe_uid,
                       sum(julianday(min(coalesce(m.date_fin, :fin), :fin))
                           - julianday(max(m.date_debut, :debut)) + 1)
                FROM mandats m JOIN deputes d ON d.acteur_uid = m.acteur_uid AND d.en_exercice = 1
                WHERE m.type_organe = 'COMPER' AND m.qualite = 'Membre'
                  AND m.date_debut <= :fin AND coalesce(m.date_fin, :fin) >= :debut
                GROUP BY m.acteur_uid, m.organe_uid""",
                {"debut": debut, "fin": aujourdhui}).fetchall():
            if n and n > jours.get(acteur, (None, 0))[1]:
                jours[acteur] = (organe, n)
        _PRINCIPALES[cle] = {acteur: organe for acteur, (organe, _) in jours.items()}
    return _PRINCIPALES[cle]


def participation_commission(db, debut, fin, organe):
    """Scrutins de la période sur les textes examinés au fond par une commission.

    Renvoie (nombre de scrutins, {député: votes exprimés sur ces scrutins})."""
    cle = (_cle_base(db), debut, fin, organe)
    if cle not in _COMMISSIONS:
        if len(_COMMISSIONS) > 100:
            _COMMISSIONS.clear()
        ids = [r[0] for r in db.execute(
            "SELECT s.uid FROM scrutins s JOIN dossiers d ON d.uid = s.dossier_uid"
            " WHERE d.commission_fond = ? AND s.date >= ? AND s.date < ?",
            (organe, debut, fin)).fetchall()]
        votes = {}
        for i in range(0, len(ids), 500):
            morceau = ids[i:i + 500]
            for acteur, n in db.execute(
                    f"SELECT acteur_uid, count(*) FROM votes WHERE scrutin_uid IN"
                    f" ({','.join('?' * len(morceau))}) AND position IN {indicateurs.EXPRIMES}"
                    " GROUP BY acteur_uid", morceau).fetchall():
                votes[acteur] = votes.get(acteur, 0) + n
        _COMMISSIONS[cle] = (len(ids), votes)
    return _COMMISSIONS[cle]


def _nombre(valeur):
    """12.0 -> « 12 », 12.5 -> « 12,5 »."""
    return str(int(valeur)) if valeur == int(valeur) else str(valeur).replace(".", ",")


def _decompte_groupe(db, scrutin_uid, groupe_uid):
    return dict(tuple(l) for l in db.execute(
        f"SELECT position, count(*) FROM votes WHERE scrutin_uid = ? AND groupe_uid = ?"
        f" AND position IN {indicateurs.EXPRIMES} GROUP BY position",
        (scrutin_uid, groupe_uid)).fetchall())


def raccourcir(texte, longueur=LONGUEUR_OBJET):
    """Nettoie l'objet d'une réunion et le coupe à la fin d'un mot."""
    texte = " ".join((texte or "").replace("\u2013", "-").split())
    # Les ordres du jour arrivent en listes à puces mises bout à bout.
    texte = PUCES.sub(lambda m: m.group(1) + " ", texte).lstrip("-; ").strip()
    if len(texte) <= longueur:
        return texte
    return texte[:longueur].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def _pluriel(n, singulier, pluriel=None):
    return f"{n} {singulier if n < 2 else (pluriel or singulier + 's')}"


def jour_long(iso):
    """AAAA-MM-JJ -> « mercredi 25/11/2026 »."""
    return f"{JOURS_SEMAINE[datetime.date.fromisoformat(iso[:10]).weekday()]} {jour(iso)}"


def agenda(db, aujourdhui, commission=None):
    """Textes inscrits à l'ordre du jour des séances des JOURS_AGENDA jours à venir.

    Seuls les points confirmés de séances confirmées comptent. Renvoie une liste
    de dictionnaires (dossier_uid ou None, titre, première date, date du vote
    solennel s'il y en a un, texte de sa commission ou non), dans l'ordre des dates.
    """
    if not any(r[0] == "points_odj" for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")):
        return []
    fin = (datetime.date.fromisoformat(aujourdhui)
           + datetime.timedelta(days=JOURS_AGENDA)).isoformat()
    textes = {}
    for p in db.execute(f"""
            SELECT p.debut, p.type, p.objet, p.dossier_uid, d.titre, d.commission_fond
            FROM points_odj p JOIN reunions r ON r.uid = p.reunion_uid
            LEFT JOIN dossiers d ON d.uid = p.dossier_uid
            WHERE p.etat = 'Confirmé' AND r.etat = 'Confirmé'
              AND substr(p.debut, 1, 10) >= ? AND substr(p.debut, 1, 10) < ?
              AND p.type IN ({','.join('?' * len(TYPES_AGENDA))})
            ORDER BY p.debut, p.ordre""", (aujourdhui, fin, *TYPES_AGENDA)).fetchall():
        cle = p["dossier_uid"] or p["objet"]
        if not cle:
            continue
        t = textes.setdefault(cle, {
            "dossier_uid": p["dossier_uid"],
            "titre": fiche.majuscule(p["titre"] or p["objet"] or ""),
            "date": p["debut"][:10], "vote": None,
            "sa_commission": bool(commission and p["commission_fond"] == commission)})
        if p["type"] == "Vote solennel" and not t["vote"]:
            t["vote"] = p["debut"][:10]
    return list(textes.values())


def composer(db, departement, circo, debut, fin, aujourdhui=None):
    """Renvoie le contenu de la lettre, ou None si le siège est vacant.

    debut inclus, fin exclue, au format AAAA-MM-JJ. Le champ « vide » indique
    qu'aucune activité n'a été enregistrée sur la période.
    """
    aujourdhui = aujourdhui or datetime.date.today().isoformat()
    d = db.execute("""
        SELECT d.*, a.prenom, a.nom, a.civilite FROM deputes d
        JOIN acteurs a ON a.uid = d.acteur_uid
        WHERE d.en_exercice = 1 AND d.num_departement = ?
          AND CAST(d.num_circo AS INTEGER) = ?""", (departement, int(circo))).fetchone()
    if d is None:
        return None
    uid = d["acteur_uid"]
    bornes = {"uid": uid, "debut": debut, "fin": fin}

    scrutins = db.execute("SELECT count(*) FROM scrutins WHERE date >= :debut AND date < :fin",
                          bornes).fetchone()[0]
    exprimes = db.execute(f"""
        SELECT count(*) FROM votes v JOIN scrutins s ON s.uid = v.scrutin_uid
        WHERE v.acteur_uid = :uid AND v.position IN {indicateurs.EXPRIMES}
          AND s.date >= :debut AND s.date < :fin""", bornes).fetchone()[0]
    sans_groupe = d["groupe_sigle"] == "NI"
    majeurs = []
    for s in db.execute(f"""
            SELECT s.uid, s.numero, s.date, s.titre, s.sort, s.type_vote, s.nb_pour, s.nb_contre,
                   s.nb_votants, s.dossier_uid,
                   v.position, v.groupe_uid FROM scrutins s
            LEFT JOIN votes v ON v.scrutin_uid = s.uid AND v.acteur_uid = :uid
            WHERE {MAJEUR} AND s.date >= :debut AND s.date < :fin
            ORDER BY s.date, s.numero""", bornes).fetchall():
        m = dict(s)
        m["censure"] = s["type_vote"] == MOTION
        if s["position"] not in ("pour", "contre", "abstention"):
            m["position"] = None
        # À une motion de censure, seuls les votes pour sont recensés : ni écart ni ligne.
        m["ecart"] = (abs(s["nb_pour"] - s["nb_contre"])
                      if not m["censure"] and s["nb_pour"] is not None
                      and s["nb_contre"] is not None else None)
        m["groupe"] = ""
        if not m["censure"] and not sans_groupe:
            m["groupe"] = position_du_groupe(_decompte_groupe(
                db, s["uid"], s["groupe_uid"] or d["groupe_uid"]))[1]
        majeurs.append(m)
    # S'il y en a trop, on garde les scrutins solennels et les motions de censure,
    # puis les votes qui ont réuni le plus de députés.
    majeurs_en_tout = len(majeurs)
    if majeurs_en_tout > LIMITE_MAJEURS:
        retenus = sorted(majeurs, key=lambda m: (
            m["type_vote"] not in (indicateurs.SOLENNEL, MOTION),
            -(m["nb_votants"] or 0)))[:LIMITE_MAJEURS]
        majeurs = sorted(retenus, key=lambda m: (m["date"], m["numero"]))
    autres_votes = db.execute(f"""
        SELECT s.numero, s.date, s.titre, s.sort, v.position, s.dossier_uid,
               d.titre AS texte
        FROM votes v JOIN scrutins s ON s.uid = v.scrutin_uid
        LEFT JOIN dossiers d ON d.uid = s.dossier_uid
        WHERE v.acteur_uid = :uid AND v.position IN {indicateurs.EXPRIMES}
          AND NOT {MAJEUR} AND s.date >= :debut AND s.date < :fin
        ORDER BY s.date DESC, s.numero DESC""", bornes).fetchall()
    scrutins_par_texte = db.execute(f"""
        SELECT s.dossier_uid, d.titre AS texte, count(*) AS n FROM scrutins s
        LEFT JOIN dossiers d ON d.uid = s.dossier_uid
        WHERE NOT {MAJEUR} AND s.date >= :debut AND s.date < :fin
        GROUP BY s.dossier_uid""", bornes).fetchall()
    serres = db.execute(f"""
        SELECT count(*), count(v.acteur_uid) FROM scrutins s
        LEFT JOIN votes v ON v.scrutin_uid = s.uid AND v.acteur_uid = :uid
          AND v.position IN {indicateurs.EXPRIMES}
        WHERE s.type_vote <> '{MOTION}' AND abs(s.nb_pour - s.nb_contre) <= {ECART_SERRE}
          AND s.date >= :debut AND s.date < :fin""", bornes).fetchone()
    mediane_groupe, mediane_tous = medianes(db, debut, fin, d["groupe_uid"], scrutins)
    dissidents = db.execute(f"""
        SELECT s.uid, v.groupe_uid, s.numero, s.date, s.titre, v.position, l.position AS ligne,
               l.nette
        FROM votes v JOIN lignes_groupe l
          ON l.scrutin_uid = v.scrutin_uid AND l.groupe_uid = v.groupe_uid
        JOIN scrutins s ON s.uid = v.scrutin_uid JOIN organes o ON o.uid = v.groupe_uid
        WHERE v.acteur_uid = :uid AND v.position IN {indicateurs.EXPRIMES}
          AND v.position <> l.position AND coalesce(o.libelle_abrege, '') <> 'NI'
          AND s.date >= :debut AND s.date < :fin
        ORDER BY (s.type_vote = :type) DESC, s.date DESC""",
                            {**bornes, "type": indicateurs.SOLENNEL}).fetchall()
    questions = db.execute("""
        SELECT date_question, type, analyse, ministere FROM questions
        WHERE acteur_uid = :uid AND date_question >= :debut AND date_question < :fin
        ORDER BY date_question DESC""", bornes).fetchall()
    reponses = db.execute("""
        SELECT count(*) FROM questions WHERE acteur_uid = :uid
          AND date_reponse >= :debut AND date_reponse < :fin""", bornes).fetchone()[0]
    sujets = db.execute("""
        SELECT i.sujet, count(*) AS n FROM interventions i
        JOIN comptes_rendus c ON c.uid = i.compte_rendu_uid
        WHERE i.acteur_uid = :uid AND i.role IS NOT 'president' AND i.nb_mots >= 20
          AND c.date >= :debut AND c.date < :fin
        GROUP BY i.sujet ORDER BY n DESC""", bornes).fetchall()
    amendements = db.execute("""
        SELECT count(*), sum(sort = 'Adopté') FROM amendements
        WHERE acteur_uid = :uid AND type_auteur = 'Député'
          AND date_depot >= :debut AND date_depot < :fin""", bornes).fetchone()
    deposes = db.execute("""
        SELECT coalesce(doc.titre, 'Texte non identifié') AS titre, a.numero, a.sort, a.etat,
               a.expose, doc.dossier_uid
        FROM amendements a LEFT JOIN documents doc ON doc.uid = a.texte_uid
        WHERE a.acteur_uid = :uid AND a.type_auteur = 'Député'
          AND a.date_depot >= :debut AND a.date_depot < :fin
        ORDER BY (a.sort IS NULL), a.date_depot DESC, a.uid""", bornes).fetchall()
    par_texte, exemples, dossier_du_texte = {}, [], {}
    for a in deposes:
        sort = sort_amendement(a["sort"], a["etat"])
        dossier_du_texte.setdefault(a["titre"], a["dossier_uid"])
        sorts = par_texte.setdefault(a["titre"], {})
        sorts[sort] = sorts.get(sort, 0) + 1
        expose = raccourcir(a["expose"], LONGUEUR_EXTRAIT)
        if (expose and len(exemples) < EXEMPLES_AMENDEMENTS
                and expose not in [e["expose"] for e in exemples]):
            exemples.append({"numero": a["numero"], "sort": sort, "texte": a["titre"],
                             "expose": expose})
    amendements_par_texte = sorted(
        ((titre, sum(sorts.values()),
          ", ".join(_accorder(n, s) for s, n in sorted(sorts.items(), key=lambda c: -c[1])),
          dossier_du_texte.get(titre))
         for titre, sorts in par_texte.items()),
        key=lambda t: (-t[1], t[0].lower()))
    themes_des_textes = themes.pour_dossiers(
        db, [m["dossier_uid"] for m in majeurs] + [v["dossier_uid"] for v in autres_votes]
        + [t["dossier_uid"] for t in scrutins_par_texte] + [a["dossier_uid"] for a in deposes])
    votes_par_theme = {}
    for v in [m for m in majeurs if m["position"] and not m["censure"]] + list(autres_votes):
        theme = themes_des_textes.get(v["dossier_uid"])
        if theme:
            votes_par_theme[theme] = votes_par_theme.get(theme, 0) + 1
    suivis = [m["dossier_uid"] for m in majeurs if m["dossier_uid"] and not m["censure"]] \
        + [t["dossier_uid"] for t in scrutins_par_texte if t["dossier_uid"]]
    etats = etapes.pour_dossiers(db, suivis)
    titres_dossiers, uniques = {}, sorted(set(suivis))
    for i in range(0, len(uniques), 500):
        morceau = uniques[i:i + 500]
        titres_dossiers.update(dict(tuple(r) for r in db.execute(
            f"SELECT uid, titre FROM dossiers WHERE uid IN ({','.join('?' * len(morceau))})",
            morceau).fetchall()))
    principales = commissions_principales(db, aujourdhui)
    sa_commission = db.execute(
        "SELECT uid AS organe_uid, libelle_abrege, libelle FROM organes WHERE uid = ?",
        (principales.get(uid),)).fetchone()
    commission_votes = None
    if sa_commission and themes.disponible(db):
        membres = [a for a, o in principales.items() if o == sa_commission["organe_uid"]]
        n, votes_membres = participation_commission(db, debut, fin, sa_commission["organe_uid"])
        if n:
            commission_votes = {
                "nom": sa_commission["libelle_abrege"] or sa_commission["libelle"],
                "scrutins": n, "exprimes": votes_membres.get(uid, 0),
                "mediane": (statistics.median(votes_membres.get(m, 0) for m in membres)
                            if membres else None)}
    parole = db.execute(f"""
        SELECT c.date, i.sujet, i.nb_mots, i.texte FROM interventions i
        JOIN comptes_rendus c ON c.uid = i.compte_rendu_uid
        WHERE i.acteur_uid = :uid AND i.role IS NOT 'president'
          AND i.nb_mots >= {MOTS_MIN_EXTRAIT}
          AND coalesce(i.code_grammaire, '') NOT LIKE 'INTERRUPTION%'
          AND coalesce(i.code_grammaire, '') NOT LIKE 'RAP_REGLEMENT%'
          AND c.date >= :debut AND c.date < :fin
        ORDER BY i.nb_mots DESC, i.id LIMIT 1""", bornes).fetchone()
    reunions = db.execute("""
        SELECT substr(r.debut, 1, 10) AS date, o.libelle AS organe, r.objet FROM presences p
        JOIN reunions_comptees rc ON rc.uid = p.reunion_uid
        JOIN reunions r ON r.uid = p.reunion_uid
        LEFT JOIN organes o ON o.uid = r.organe_uid
        WHERE p.acteur_uid = :uid AND p.presence = 'présent'
          AND substr(r.debut, 1, 10) >= :debut AND substr(r.debut, 1, 10) < :fin
        ORDER BY r.debut DESC""", bornes).fetchall()
    propositions = db.execute("""
        SELECT doc.titre, doc.date_depot FROM documents_signataires s
        JOIN documents doc ON doc.uid = s.document_uid
        WHERE s.acteur_uid = :uid AND s.role = 'auteur' AND doc.type = 'PION'
          AND doc.legislature = :leg AND doc.date_depot >= :debut AND doc.date_depot < :fin
        ORDER BY doc.date_depot DESC""", {**bornes, "leg": LEGISLATURE}).fetchall()
    commission = db.execute("""
        SELECT sum(p.presence = 'présent'), count(*) FROM presences p
        JOIN reunions_comptees rc ON rc.uid = p.reunion_uid
        JOIN reunions r ON r.uid = p.reunion_uid
        WHERE p.acteur_uid = :uid AND substr(r.debut, 1, 10) >= :debut
          AND substr(r.debut, 1, 10) < :fin""", bornes).fetchone()

    interventions = sum(s["n"] for s in sujets)
    nets = [dict(v) for v in dissidents if v["nette"]]
    partages = len(dissidents) - len(nets)
    chemins = site.adresses_fiches(site.lister_deputes(db))
    lettre = {
        "depute": f"{d['prenom']} {d['nom']}", "feminin": d["civilite"] == "Mme",
        "groupe": d["groupe_libelle"], "sigle": d["groupe_sigle"],
        "departement": d["departement"], "num_departement": d["num_departement"],
        "num_circo": str(int(d["num_circo"])), "chemin_fiche": chemins[uid],
        "debut": debut, "fin": fin,
        "scrutins": scrutins, "exprimes": exprimes,
        "majeurs": majeurs, "majeurs_en_tout": majeurs_en_tout,
        "autres_votes": [dict(v) for v in autres_votes],
        "scrutins_par_texte": [dict(t) for t in scrutins_par_texte],
        "serres": serres[0] or 0, "serres_exprimes": serres[1] or 0,
        "mediane_groupe": mediane_groupe, "mediane_tous": mediane_tous,
        "dissidents": nets, "dissidents_partages": partages,
        "parole": ({"date": parole["date"], "sujet": parole["sujet"],
                    "nb_mots": parole["nb_mots"],
                    "extrait": raccourcir(parole["texte"], LONGUEUR_EXTRAIT)}
                   if parole else None),
        "questions": [dict(q) for q in questions], "reponses": reponses,
        "interventions": interventions, "sujets": [(s["sujet"], s["n"]) for s in sujets],
        "amendements": amendements[0] or 0, "amendements_adoptes": amendements[1] or 0,
        "amendements_par_texte": amendements_par_texte, "amendements_exemples": exemples,
        "themes": themes_des_textes,
        "votes_par_theme": sorted(votes_par_theme.items(), key=lambda t: (-t[1], t[0])),
        "commission_votes": commission_votes,
        "etats": etats, "titres_dossiers": titres_dossiers,
        # Les états sont ceux connus le jour où la lettre est composée, pas à la fin de la période.
        "date_etats": aujourdhui,
        "agenda": agenda(db, aujourdhui, sa_commission["organe_uid"] if sa_commission else None),
        "themes_agenda": {},
        "reunions": [dict(r) for r in reunions],
        "propositions": [dict(p) for p in propositions],
        "commission_present": commission[0] or 0, "commission_reunions": commission[1] or 0,
    }
    lettre["themes_agenda"] = themes.pour_dossiers(db, [t["dossier_uid"] for t in lettre["agenda"]])
    lettre["vide"] = not any((exprimes, majeurs, questions, reponses, interventions,
                              lettre["amendements"], propositions,
                              lettre["commission_reunions"]))
    return lettre


def _dernier_jour(fin):
    """La période affichée se termine la veille de la borne de fin, exclue."""
    return (datetime.date.fromisoformat(fin) - datetime.timedelta(days=1)).isoformat()


def rubriques(l, site_url=None):
    """Structure commune aux versions texte et HTML : liste de (titre, phrases, éléments)."""
    il = "Elle" if l["feminin"] else "Il"
    sorties = []

    # 1. Les votes qui engagent un texte entier ou le Gouvernement.
    phrases, elements, absence = [], [], False
    for m in l["majeurs"]:
        if m["censure"]:
            position = "A voté la censure" if m["position"] == "pour" else "N'a pas voté la censure"
        elif m["position"]:
            position = fiche.LIBELLES_POSITION[m["position"]]
        else:
            position, absence = "N'a pas pris part au vote", True
        resultat = m["sort"] or ""
        if m["ecart"] is not None and m["ecart"] <= ECART_SERRE:
            resultat += (", " if resultat else "") + (
                "à égalité de voix" if m["ecart"] == 0 else
                f"à {_pluriel(m['ecart'], 'voix', 'voix')} près")
        apres = (f" ({resultat})" if resultat else "") + (f" · {m['groupe']}" if m["groupe"] else "")
        theme = (l.get("themes") or {}).get(m.get("dossier_uid"))
        elements.append((lier(f"{theme + ' — ' if theme else ''}{jour(m['date'])} · {position} · ",
                              intitule(m["titre"]), apres),
                         fiche.URL_SCRUTIN.format(m["numero"])))
    if elements:
        if any(m["censure"] for m in l["majeurs"]):
            phrases.append("Pour une motion de censure, seuls les votes pour sont recensés.")
        if absence:
            phrases.append(ABSENCE)
        en_tout = l.get("majeurs_en_tout") or len(elements)
        phrases.append(
            "Les votes de la période sur des textes entiers et sur des motions de censure :"
            if en_tout <= len(elements) else
            f"{en_tout} votes ont porté sur des textes entiers ou des motions de censure ; "
            f"les {len(elements)} qui ont réuni le plus de députés :")
    else:
        phrases.append("Aucun vote sur un texte entier ni sur une motion de censure pendant "
                       "la période.")
    sorties.append(("L'essentiel", phrases, elements))

    # 2. La participation, replacée dans son contexte, puis le détail par texte.
    if l["scrutins"]:
        reperes = []
        if l.get("mediane_groupe") is not None and l["sigle"] != "NI":
            reperes.append(f"médiane du groupe {l['sigle']} : {_nombre(l['mediane_groupe'])}")
        if l.get("mediane_tous") is not None:
            reperes.append(f"médiane de l'Assemblée : {_nombre(l['mediane_tous'])}")
        phrases = [f"{il} a pris part à {l['exprimes']} des "
                   f"{_pluriel(l['scrutins'], 'scrutin public', 'scrutins publics')} "
                   "de la période" + (f" ({' ; '.join(reperes)})" if reperes else "") + ".",
                   "La plupart portent sur des amendements, souvent examinés pendant que "
                   "d'autres réunions se tiennent."]
        if l.get("serres"):
            phrases.append(
                f"{_pluriel(l['serres'], 'scrutin s’est joué', 'scrutins se sont joués')} à "
                f"{ECART_SERRE} voix ou moins : {il.lower()} a pris part à "
                f"{l['serres_exprimes']} d'entre eux." if l["serres"] > 1 else
                f"1 scrutin s’est joué à {ECART_SERRE} voix ou moins : {il.lower()} "
                + ("y a pris part." if l["serres_exprimes"] else "n'y a pas pris part."))
        c = l.get("commission_votes")
        if c:
            phrases.append(
                f"Sur les textes examinés au fond par sa commission ({c['nom']}), "
                f"{il.lower()} a pris part à {c['exprimes']} des "
                f"{_pluriel(c['scrutins'], 'scrutin')}"
                + (f" (médiane des membres de la commission : {_nombre(c['mediane'])})"
                   if c["mediane"] is not None else "") + ".")
        if l.get("votes_par_theme"):
            phrases.append("Ses votes par thème : " + " ; ".join(
                f"{t} ({n})" for t, n in l["votes_par_theme"]) + ".")
        noms = l.get("themes") or {}
        groupes = votes_par_texte(l.get("autres_votes") or [], l.get("scrutins_par_texte") or [])
        elements = [(lier(f"{noms[g['uid']]} — " if noms.get(g["uid"]) else "", g["texte"],
                          f" : {g['decompte']}"), g["lien"])
                    for g in groupes[:LIMITE]]
        if len(groupes) > LIMITE:
            elements.append((f"Et {_pluriel(len(groupes) - LIMITE, 'autre texte', 'autres textes')}"
                             " : voir sa fiche.", None))
        if elements:
            phrases.append("Amendements et articles, texte par texte :")
        sorties.append(("Sa participation aux scrutins", phrases, elements))

    # 3. Où en sont les textes votés : un vote « adopté » à l'Assemblée n'est pas une loi.
    etats, noms = l.get("etats") or {}, l.get("themes") or {}
    ordre = [m["dossier_uid"] for m in l["majeurs"] if m.get("dossier_uid") and not m["censure"]]
    ordre += [g["uid"] for g in votes_par_texte(l.get("autres_votes") or [],
                                                l.get("scrutins_par_texte") or [])[:LIMITE]]
    vus, elements = set(), []
    for uid in ordre:
        if uid in vus or uid not in etats or len(elements) >= LIMITE_ETATS:
            continue
        vus.add(uid)
        titre = fiche.majuscule((l.get("titres_dossiers") or {}).get(uid) or "Texte")
        elements.append((lier(f"{noms[uid]} — " if noms.get(uid) else "", titre,
                              f" : {etats[uid]}"), URL_DOSSIER.format(uid)))
    if elements:
        sorties.append(("Où en sont ces textes", [
            "Un vote de l'Assemblée n'est souvent qu'une étape : un texte ne devient loi "
            "qu'après son adoption définitive par le Parlement, puis sa promulgation. "
            "Dernière étape connue de chaque texte"
            + (f", au {jour(l['date_etats'])}" if l.get("date_etats") else "") + " :"],
            elements))

    # 4. Ce qui vient : écrire à son député avant le débat plutôt qu'après.
    textes = l.get("agenda") or []
    if textes:
        noms = l.get("themes_agenda") or {}
        retenus = sorted(textes, key=lambda t: (not t["vote"], not t["sa_commission"],
                                                t["date"]))[:LIMITE_AGENDA]
        elements = []
        for t in sorted(retenus, key=lambda t: t["date"]):
            theme = noms.get(t["dossier_uid"])
            precisions = []
            if t["vote"] and t["dossier_uid"]:  # sans dossier, la ligne est le vote lui-même
                precisions.append(f"vote solennel le {jour_long(t['vote'])}")
            if t["sa_commission"]:
                precisions.append("texte examiné par sa commission")
            elements.append((lier(f"{theme + ' — ' if theme else ''}{jour_long(t['date'])} : ",
                                  t["titre"], f" ({' ; '.join(precisions)})" if precisions else ""),
                             URL_DOSSIER.format(t["dossier_uid"]) if t["dossier_uid"] else None))
        if len(textes) > LIMITE_AGENDA:
            elements.append((f"Et {_pluriel(len(textes) - LIMITE_AGENDA, 'autre texte', 'autres textes')}"
                             " inscrits à l'ordre du jour.", None))
        if site_url and l.get("chemin_fiche"):
            elements.append((lier("", f"Écrire à {'votre députée' if l['feminin'] else 'votre député'}"
                                  " avant le débat", ""),
                             f"{site_url}/{l['chemin_fiche']}#courrier"))
        debut = l.get("date_etats")
        sorties.append(("À l'ordre du jour de l'Assemblée", [
            "Textes inscrits à l'ordre du jour des séances"
            + (f" du {jour(debut)} au "
               f"{jour((datetime.date.fromisoformat(debut) + datetime.timedelta(days=JOURS_AGENDA - 1)).isoformat())}"
               if debut else "")
            + ", d'après l'agenda publié par l'Assemblée. Il peut encore changer, et tous les "
            "textes inscrits ne sont pas toujours examinés :"], elements))

    partages = l.get("dissidents_partages") or 0
    if l["dissidents"] or partages:
        n = len(l["dissidents"])
        phrases = []
        if n:
            phrases.append(
                f"{_pluriel(n, 'vote différent', 'votes différents')} de la position du groupe "
                f"{l['sigle']}, quand celui-ci votait nettement dans un sens"
                + (f" ; les {LIMITE} premiers :" if n > LIMITE else " :"))
        if partages:
            # Avant la liste, pour que la phrase qui l'annonce reste juste au-dessus.
            phrases.insert(0, (
                "Sur un scrutin où son groupe était partagé" if partages == 1 else
                f"Sur {partages} scrutins où son groupe était partagé")
                + f" (aucune position n'y dépassait {int(SEUIL_LIGNE * 100)} % de ses voix), "
                + ("son vote n'est pas compté comme un écart." if partages == 1 else
                   "ses votes ne sont pas comptés comme des écarts."))
        sorties.append((
            "Votes contre la ligne de son groupe", phrases,
            [(lier(f"{jour(v['date'])} · {fiche.LIBELLES_POSITION[v['position']]} (groupe : "
                   f"{fiche.LIBELLES_POSITION[v['ligne']].lower()}) · ", intitule(v["titre"])),
              fiche.URL_SCRUTIN.format(v["numero"])) for v in l["dissidents"][:LIMITE]]))

    if l["interventions"]:
        elements = [(f"{sujet or 'Sujet non précisé'} ({n})", None)
                    for sujet, n in l["sujets"][:LIMITE]]
        parole = l.get("parole")
        if parole:
            elements.append((
                f"Sa plus longue prise de parole ({jour(parole['date'])}, "
                f"{parole['nb_mots']} mots"
                + (f", sur « {parole['sujet']} »" if parole["sujet"] else "")
                + f"), début : « {parole['extrait']} »", None))
        sorties.append((
            "En séance publique",
            [f"{_pluriel(l['interventions'], 'intervention')} de 20 mots ou plus, sur :"],
            elements))

    if l["commission_reunions"]:
        elements = []
        for r in (l.get("reunions") or [])[:LIMITE]:
            morceaux = [jour(r["date"]), r["organe"], raccourcir(r["objet"])]
            elements.append((" · ".join(m for m in morceaux if m), None))
        e = "e" if l["feminin"] else ""
        if l["commission_reunions"] == 1:
            phrases = [(f"Présent{e} à" if l["commission_present"] else f"Absent{e} de")
                       + " la seule réunion de commission dotée d'une feuille de présence."]
        else:
            phrases = [f"Présent{e} à {l['commission_present']} des "
                       f"{l['commission_reunions']} réunions de commission dotées "
                       "d'une feuille de présence."]
        if len(l.get("reunions") or []) > LIMITE:
            phrases.append(f"Les {LIMITE} plus récentes :")
        sorties.append(("En commission", phrases, elements))

    phrases, elements = [], []
    if l["amendements"]:
        phrases.append(f"{_pluriel(l['amendements'], 'amendement déposé', 'amendements déposés')}"
                       " comme premier signataire"
                       + (f", dont {l['amendements_adoptes']} déjà adopté"
                          f"{'s' if l['amendements_adoptes'] > 1 else ''}"
                          if l["amendements_adoptes"] else "") + ".")
    par_texte = l.get("amendements_par_texte") or []
    noms = l.get("themes") or {}
    for titre, n, sorts, dossier in par_texte[:LIMITE]:
        theme = noms.get(dossier)
        elements.append((f"{theme + ' — ' if theme else ''}{fiche.majuscule(titre)} : "
                         f"{_pluriel(n, 'amendement')} ({sorts})", None))
    if len(par_texte) > LIMITE:
        reste = sum(t[1] for t in par_texte[LIMITE:])
        elements.append((f"Autres textes : {_pluriel(reste, 'amendement')}", None))
    for a in l.get("amendements_exemples") or []:
        elements.append((f"Amendement n° {a['numero']} ({a['sort']}), selon l'exposé de son "
                         f"auteur : « {a['expose']} »", None))
    for p in l["propositions"][:LIMITE]:
        elements.append((f"Proposition de loi déposée le {jour(p['date_depot'])} : "
                         f"{fiche.majuscule(p['titre'])}", None))
    if phrases or elements:
        sorties.append(("Amendements et propositions de loi", phrases, elements))

    if l["questions"] or l["reponses"]:
        phrases = []
        if l["questions"]:
            phrases.append(_pluriel(len(l["questions"]), "question posée", "questions posées")
                           + " :")
        if l["reponses"]:
            phrases.append(f"{_pluriel(l['reponses'], 'réponse reçue', 'réponses reçues')} "
                           "du Gouvernement à ses questions.")
        sorties.append(("Questions au Gouvernement", phrases, [
            (f"{jour(q['date_question'])} · {q['type']} · {q['analyse'] or 'Sans titre'}"
             f" ({q['ministere']})", None) for q in l["questions"][:LIMITE]]))
    return sorties


def rendre(l, site_url, lien_gestion, lien_desabonnement, contact=None):
    """Renvoie (sujet, version texte, version HTML).

    « contact » est l'adresse à laquelle signaler une erreur ; sans elle, la
    lettre n'en parle pas."""
    periode = f"du {jour(l['debut'])} au {jour(_dernier_jour(l['fin']))}"
    sujet = f"{l['depute']} : son activité {periode}"
    lien_fiche = f"{site_url}/{l['chemin_fiche']}"
    entete = (f"{l['depute']} ({l['sigle']}), {ordinal(l['num_circo'], feminin=True)} "
              f"circonscription, {l['departement']} ({l['num_departement']})")
    methode = f"{site_url}/methodologie.html"
    pied = ("Ces chiffres sont des décomptes tirés des données ouvertes de l'Assemblée "
            "nationale. Ils mesurent un volume, pas une qualité.")

    texte = [entete, f"Activité {periode}", ""]
    html = [f'<p style="margin:0 0 4px;font-size:18px"><b>{escape(l["depute"])}</b> '
            f'({escape(l["sigle"] or "")})</p>'
            f'<p style="margin:0 0 20px;color:#5b6270">{escape(entete.split(", ", 1)[1])}'
            f'<br>Activité {escape(periode)}</p>']
    for titre, phrases, elements in rubriques(l, site_url):
        texte += [titre.upper()] + phrases + [f"- {t.replace(MARQUE, '')}" + (f"\n  {u}" if u else "")
                                              for t, u in elements] + [""]
        html.append(f'<h2 style="font-size:16px;margin:22px 0 6px">{escape(titre)}</h2>')
        html += [f'<p style="margin:0 0 6px">{escape(p)}</p>' for p in phrases]
        if elements:
            html.append('<ul style="margin:0 0 6px;padding-left:20px">' + "".join(
                f"<li>{_element_html(t, u)}</li>" for t, u in elements) + "</ul>")
    texte += [f"Sa fiche complète : {lien_fiche}", f"Comment c'est calculé : {methode}", "",
              pied, "",
              *([f"Une erreur dans cette lettre ? Signalez-la : {contact}", ""] if contact else []),
              f"Changer la fréquence ou gérer votre abonnement : {lien_gestion}",
              f"Vous désabonner : {lien_desabonnement}"]
    html.append(
        f'<p style="margin:22px 0 6px"><a href="{escape(lien_fiche)}">Sa fiche complète</a> · '
        f'<a href="{escape(methode)}">Comment c’est calculé</a></p>'
        f'<p style="color:#5b6270;font-size:13px;margin:0 0 14px">{escape(pied)}</p>'
        + (f'<p style="color:#5b6270;font-size:13px;margin:0 0 14px">Une erreur dans cette '
           f'lettre ? <a href="mailto:{escape(contact)}">Signalez-la</a>.</p>' if contact else "")
        +
        f'<p style="color:#5b6270;font-size:13px;margin:0">'
        f'<a href="{escape(lien_gestion)}">Gérer votre abonnement</a> · '
        f'<a href="{escape(lien_desabonnement)}">Vous désabonner</a></p>')
    corps = ('<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;font-size:15px;'
             'line-height:1.5;color:#1c1f26;max-width:620px;margin:0 auto;padding:16px">'
             + "".join(html) + "</div>")
    return sujet, "\n".join(texte), corps
