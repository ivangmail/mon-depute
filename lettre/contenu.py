"""Contenu d'une lettre : l'activité d'un député sur une période.

Uniquement des faits tirés des données de l'Assemblée, selon les mêmes règles
que le site (voir collecte/indicateurs.py et la page Méthodologie).
"""

import datetime
import re
from html import escape

from collecte import fiche, indicateurs, site
from collecte.portrait import jour, ordinal
from collecte.sources import LEGISLATURE

URL_DOSSIER = "https://www.assemblee-nationale.fr/dyn/" + LEGISLATURE + "/dossiers/{}"
LIMITE = 5  # éléments listés par rubrique
LONGUEUR_OBJET = 160  # caractères conservés de l'objet d'une réunion


PUCES = re.compile(r"([:;])(?:\s*[;-])+\s*")


def intitule(titre):
    """Intitulé d'un scrutin : majuscule initiale, sans le point final."""
    return fiche.majuscule(titre or "").rstrip(". ")


def votes_par_texte(votes):
    """Regroupe des votes par dossier législatif, du plus voté au moins voté.

    Chaque groupe donne le titre du texte, le nombre de votes, leur répartition
    (« 1 pour, 4 contre ») et le lien vers le dossier sur le site de l'Assemblée.
    """
    groupes = {}
    for v in votes:
        cle = v.get("dossier_uid") or ""
        g = groupes.setdefault(cle, {
            "texte": fiche.majuscule(v.get("texte") or "") or "Textes non identifiés",
            "lien": URL_DOSSIER.format(cle) if cle else None,
            "total": 0, "pour": 0, "contre": 0, "abstention": 0})
        g["total"] += 1
        g[v["position"]] += 1
    for g in groupes.values():
        g["detail"] = ", ".join(
            f"{g[p]} {libelle if g[p] < 2 else pluriel}"
            for p, libelle, pluriel in (("pour", "pour", "pour"), ("contre", "contre", "contre"),
                                        ("abstention", "abstention", "abstentions")) if g[p])
    return sorted(groupes.values(), key=lambda g: (-g["total"], g["texte"]))


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


def composer(db, departement, circo, debut, fin):
    """Renvoie le contenu de la lettre, ou None si le siège est vacant.

    debut inclus, fin exclue, au format AAAA-MM-JJ. Le champ « vide » indique
    qu'aucune activité n'a été enregistrée sur la période.
    """
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
    solennels = db.execute("""
        SELECT s.numero, s.date, s.titre, s.sort, v.position FROM scrutins s
        LEFT JOIN votes v ON v.scrutin_uid = s.uid AND v.acteur_uid = :uid
        WHERE s.type_vote = :type AND s.date >= :debut AND s.date < :fin
        ORDER BY s.date, s.numero""", {**bornes, "type": indicateurs.SOLENNEL}).fetchall()
    autres_votes = db.execute(f"""
        SELECT s.numero, s.date, s.titre, s.sort, v.position, s.dossier_uid,
               d.titre AS texte
        FROM votes v JOIN scrutins s ON s.uid = v.scrutin_uid
        LEFT JOIN dossiers d ON d.uid = s.dossier_uid
        WHERE v.acteur_uid = :uid AND v.position IN {indicateurs.EXPRIMES}
          AND s.type_vote <> :type AND s.date >= :debut AND s.date < :fin
        ORDER BY s.date DESC, s.numero DESC""",
                              {**bornes, "type": indicateurs.SOLENNEL}).fetchall()
    dissidents = db.execute(f"""
        SELECT s.numero, s.date, s.titre, v.position, l.position AS ligne
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
    amendements_par_texte = db.execute("""
        SELECT coalesce(doc.titre, 'Texte non identifié') AS titre, count(*) AS n
        FROM amendements a LEFT JOIN documents doc ON doc.uid = a.texte_uid
        WHERE a.acteur_uid = :uid AND a.type_auteur = 'Député'
          AND a.date_depot >= :debut AND a.date_depot < :fin
        GROUP BY titre ORDER BY n DESC, titre COLLATE NOCASE""", bornes).fetchall()
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
    chemins = site.adresses_fiches(site.lister_deputes(db))
    lettre = {
        "depute": f"{d['prenom']} {d['nom']}", "feminin": d["civilite"] == "Mme",
        "groupe": d["groupe_libelle"], "sigle": d["groupe_sigle"],
        "departement": d["departement"], "num_departement": d["num_departement"],
        "num_circo": str(int(d["num_circo"])), "chemin_fiche": chemins[uid],
        "debut": debut, "fin": fin,
        "scrutins": scrutins, "exprimes": exprimes,
        "solennels": [dict(s) for s in solennels],
        "autres_votes": [dict(v) for v in autres_votes],
        "dissidents": [dict(v) for v in dissidents],
        "questions": [dict(q) for q in questions], "reponses": reponses,
        "interventions": interventions, "sujets": [(s["sujet"], s["n"]) for s in sujets],
        "amendements": amendements[0] or 0, "amendements_adoptes": amendements[1] or 0,
        "amendements_par_texte": [(a["titre"], a["n"]) for a in amendements_par_texte],
        "reunions": [dict(r) for r in reunions],
        "propositions": [dict(p) for p in propositions],
        "commission_present": commission[0] or 0, "commission_reunions": commission[1] or 0,
    }
    lettre["vide"] = not any((exprimes, solennels, questions, reponses, interventions,
                              lettre["amendements"], propositions,
                              lettre["commission_reunions"]))
    return lettre


def _dernier_jour(fin):
    """La période affichée se termine la veille de la borne de fin, exclue."""
    return (datetime.date.fromisoformat(fin) - datetime.timedelta(days=1)).isoformat()


def rubriques(l):
    """Structure commune aux versions texte et HTML : liste de (titre, phrases, éléments)."""
    il = "Elle" if l["feminin"] else "Il"
    sorties = []

    phrases, elements = [], []
    if l["scrutins"]:
        phrases.append(f"{il} a pris part à {l['exprimes']} des "
                       f"{_pluriel(l['scrutins'], 'scrutin public', 'scrutins publics')} "
                       "de la période, dont la plupart portent sur des amendements.")
    else:
        phrases.append("Aucun scrutin public ne s'est tenu pendant la période.")
    for s in l["solennels"]:
        elements.append((f"{jour(s['date'])} · {fiche.LIBELLES_POSITION[s['position']]} · "
                         f"{intitule(s['titre'])} ({s['sort']})",
                         fiche.URL_SCRUTIN.format(s["numero"])))
    if l["solennels"]:
        phrases.append("Ses votes sur les textes entiers (scrutins solennels) :")
    sorties.append(("Votes", phrases, elements))

    autres = l.get("autres_votes") or []
    if autres:
        n = len(autres)
        groupes = votes_par_texte(autres)
        elements = [(f"{g['texte']} : {_pluriel(g['total'], 'vote')} ({g['detail']})", g["lien"])
                    for g in groupes[:LIMITE]]
        if len(groupes) > LIMITE:
            reste = sum(g["total"] for g in groupes[LIMITE:])
            elements.append((f"Autres textes : {_pluriel(reste, 'vote')}", None))
        sorties.append((
            "Ses votes sur des amendements et des articles",
            [f"{_pluriel(n, 'vote')}, " + ("sur un seul texte :" if len(groupes) == 1 else
                                          f"répartis sur {len(groupes)} textes :")],
            elements))

    if l["dissidents"]:
        n = len(l["dissidents"])
        sorties.append((
            "Votes contre la ligne de son groupe",
            [f"{_pluriel(n, 'vote différent', 'votes différents')} de la position majoritaire "
             f"du groupe {l['sigle']}" + (f", dont les {LIMITE} premiers :" if n > LIMITE else " :")],
            [(f"{jour(v['date'])} · {fiche.LIBELLES_POSITION[v['position']]} (groupe : "
              f"{fiche.LIBELLES_POSITION[v['ligne']].lower()}) · {intitule(v['titre'])}",
              fiche.URL_SCRUTIN.format(v["numero"])) for v in l["dissidents"][:LIMITE]]))

    if l["interventions"]:
        sorties.append((
            "En séance publique",
            [f"{_pluriel(l['interventions'], 'intervention')} de 20 mots ou plus, sur :"],
            [(f"{sujet or 'Sujet non précisé'} ({n})", None) for sujet, n in l["sujets"][:LIMITE]]))

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
    for titre, n in par_texte[:LIMITE]:
        elements.append((f"{fiche.majuscule(titre)} : {_pluriel(n, 'amendement')}", None))
    if len(par_texte) > LIMITE:
        reste = sum(n for _, n in par_texte[LIMITE:])
        elements.append((f"Autres textes : {_pluriel(reste, 'amendement')}", None))
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


def rendre(l, site_url, lien_gestion, lien_desabonnement):
    """Renvoie (sujet, version texte, version HTML)."""
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
    for titre, phrases, elements in rubriques(l):
        texte += [titre.upper()] + phrases + [f"- {t}" + (f"\n  {u}" if u else "")
                                              for t, u in elements] + [""]
        html.append(f'<h2 style="font-size:16px;margin:22px 0 6px">{escape(titre)}</h2>')
        html += [f'<p style="margin:0 0 6px">{escape(p)}</p>' for p in phrases]
        if elements:
            html.append('<ul style="margin:0 0 6px;padding-left:20px">' + "".join(
                "<li>" + (f'<a href="{escape(u)}">{escape(t)}</a>' if u else escape(t)) + "</li>"
                for t, u in elements) + "</ul>")
    texte += [f"Sa fiche complète : {lien_fiche}", f"Comment c'est calculé : {methode}", "",
              pied, "",
              f"Changer la fréquence ou gérer votre abonnement : {lien_gestion}",
              f"Vous désabonner : {lien_desabonnement}"]
    html.append(
        f'<p style="margin:22px 0 6px"><a href="{escape(lien_fiche)}">Sa fiche complète</a> · '
        f'<a href="{escape(methode)}">Comment c’est calculé</a></p>'
        f'<p style="color:#5b6270;font-size:13px;margin:0 0 14px">{escape(pied)}</p>'
        f'<p style="color:#5b6270;font-size:13px;margin:0">'
        f'<a href="{escape(lien_gestion)}">Gérer votre abonnement</a> · '
        f'<a href="{escape(lien_desabonnement)}">Vous désabonner</a></p>')
    corps = ('<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;font-size:15px;'
             'line-height:1.5;color:#1c1f26;max-width:620px;margin:0 auto;padding:16px">'
             + "".join(html) + "</div>")
    return sujet, "\n".join(texte), corps
