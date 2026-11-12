"""Fiche d'un député : le corps de page HTML et les requêtes qui l'alimentent."""

import re
import unicodedata
from urllib.parse import quote
from email.utils import parsedate_to_datetime
from html import escape

from . import indicateurs, portrait
from .portrait import jour
from .sources import LEGISLATURE

URL_SCRUTIN = "https://www.assemblee-nationale.fr/dyn/" + LEGISLATURE + "/scrutins/{}"
URL_DEPUTE = "https://www.assemblee-nationale.fr/dyn/deputes/{}"

LIBELLES_POSITION = {"pour": "Pour", "contre": "Contre", "abstention": "Abstention",
                     "non_votant": "Non-votant",
                     "non_votant_volontaire": "Non-votant volontaire",
                     None: "N'a pas pris part au vote"}
CONTACTS_AFFICHES = ["Mèl", "Adresse publiée de circonscription",
                     "Adresse publiée pour Paris ou sa région", "Téléphone",
                     "Adresse officielle", "Site internet", "Twitter", "Facebook",
                     "Instagram", "Linkedin"]
LIBELLES_CONTACT = {"Mèl": "Courriel", "Adresse publiée de circonscription": "Permanence",
                    "Adresse publiée pour Paris ou sa région": "Adresse à Paris",
                    "Adresse officielle": "Adresse à l'Assemblée", "Twitter": "X (Twitter)",
                    "Linkedin": "LinkedIn"}


def sans_accents(texte):
    decompose = unicodedata.normalize("NFD", texte or "")
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn").lower()


def slug(prenom, nom):
    return re.sub(r"[^a-z0-9]+", "-", sans_accents(f"{prenom} {nom}")).strip("-")


def chercher(db, nom):
    cible = sans_accents(nom).strip()
    lignes = db.execute("""
        SELECT d.*, a.prenom, a.nom FROM deputes d JOIN acteurs a ON a.uid = d.acteur_uid
    """).fetchall()
    exacts = [l for l in lignes
              if sans_accents(f"{l['prenom']} {l['nom']}") == cible
              or l["acteur_uid"].lower() == cible]
    return exacts or [l for l in lignes
                      if cible in sans_accents(f"{l['prenom']} {l['nom']}")]


def date_source(entetes):
    """Date la plus récente parmi des en-têtes HTTP Last-Modified, en JJ/MM/AAAA."""
    dates = []
    for entete in entetes:
        try:
            dates.append(parsedate_to_datetime(entete))
        except (TypeError, ValueError):
            continue
    return max(dates).strftime("%d/%m/%Y") if dates else None


def pourcent(valeur):
    return "—" if valeur is None else f"{round(100 * valeur)} %"


def majuscule(texte):
    return texte[:1].upper() + texte[1:] if texte else ""


# ------------------------------------------------------------------- requêtes

def votes_solennels(db, uid, limite=10):
    """Derniers scrutins solennels tenus pendant le mandat, avec la position
    du député, y compris quand il n'a pas pris part au vote."""
    return db.execute("""
        SELECT s.numero, s.date, s.titre, s.sort, v.position FROM scrutins s
        LEFT JOIN votes v ON v.scrutin_uid = s.uid AND v.acteur_uid = :uid
        WHERE s.type_vote = :type AND EXISTS (
            SELECT 1 FROM mandats m WHERE m.acteur_uid = :uid
              AND m.type_organe = 'ASSEMBLEE' AND m.legislature = :leg
              AND s.date >= m.date_debut AND s.date <= coalesce(m.date_fin, '9999'))
        ORDER BY s.date DESC, s.numero DESC LIMIT :limite""",
                      {"uid": uid, "type": indicateurs.SOLENNEL, "leg": LEGISLATURE,
                       "limite": limite}).fetchall()


def votes_dissidents(db, uid, limite=5):
    return db.execute(f"""
        SELECT s.numero, s.date, s.titre, v.position, l.position AS ligne,
               o.libelle_abrege AS groupe
        FROM votes v JOIN lignes_groupe l
          ON l.scrutin_uid = v.scrutin_uid AND l.groupe_uid = v.groupe_uid
        JOIN scrutins s ON s.uid = v.scrutin_uid
        JOIN organes o ON o.uid = v.groupe_uid
        WHERE v.acteur_uid = ? AND v.position IN {indicateurs.EXPRIMES}
          AND v.position <> l.position AND coalesce(o.libelle_abrege, '') <> 'NI'
        ORDER BY (s.type_vote = ?) DESC, s.date DESC, s.numero DESC LIMIT ?""",
                      (uid, indicateurs.SOLENNEL, limite)).fetchall()


# ----------------------------------------------------------------------- HTML

def _jauge(titre, valeur, detail, moyenne, moyenne_groupe, sigle, aide):
    if valeur is None:
        return (f'<div class="mesure"><h3>{escape(titre)}</h3>'
                f'<p class="doux">Pas assez de données pour calculer ce taux'
                f' ({escape(detail)}).</p></div>')
    repere = (f'<span class="repere" style="left:{100 * moyenne:.1f}%"></span>'
              if moyenne is not None else "")
    comparaison = []
    if moyenne is not None:
        comparaison.append(f"moyenne des députés : {pourcent(moyenne)}")
    if moyenne_groupe is not None and sigle and sigle != "NI":
        comparaison.append(f"moyenne du groupe {escape(sigle)} : {pourcent(moyenne_groupe)}")
    return f"""<div class="mesure">
<h3>{escape(titre)}</h3>
<p class="chiffre"><b>{pourcent(valeur)}</b> <span class="doux">{escape(detail)}</span></p>
<div class="jauge" role="img" aria-label="{escape(titre)} : {pourcent(valeur)}">
<span class="rempli" style="width:{100 * valeur:.1f}%"></span>{repere}</div>
<p class="doux petit">{'Trait vertical : ' + ' · '.join(comparaison) + '.' if comparaison else ''}
 {aide}</p></div>"""


def _position(position):
    classe = position if position in ("pour", "contre", "abstention") else "absent"
    return f'<span class="pos {classe}">{escape(LIBELLES_POSITION.get(position, position))}</span>'


def adresse_officielle(contacts):
    """Adresse e-mail à laquelle écrire au député : celle de l'Assemblée si elle
    est publiée, sinon la première adresse connue."""
    adresses = [c["valeur"] for c in contacts if c["type"] == "Mèl" and "@" in c["valeur"]]
    officielles = [a for a in adresses if a.lower().endswith("@assemblee-nationale.fr")]
    return (officielles or adresses or [None])[0]


def lien_courriel(adresse, objet, corps_message):
    """Lien qui ouvre la messagerie du visiteur avec un message pré-rempli.
    Le message part de sa propre messagerie : le site n'en voit rien."""
    return (f"mailto:{quote(adresse, safe='@')}?subject={quote(objet, safe='')}"
            f"&body={quote(corps_message, safe='')}")


def message_au_depute(acteur, depute, scrutin=None):
    """Objet et texte du message pré-rempli, à compléter par le visiteur.

    scrutin : s'il est fourni (numero, date, titre, position), le message
    rappelle le vote sur lequel porte la question.
    """
    femme = acteur["civilite"] == "Mme"
    salutation = "Madame la députée," if femme else "Monsieur le député,"
    lieu = ""
    if depute["num_circo"]:
        lieu = (f" ({portrait.ordinal(depute['num_circo'], feminin=True)} circonscription, "
                f"{depute['departement']})")
    lignes = [salutation, "", f"J'habite votre circonscription{lieu}.", ""]
    objet = "Message d'un habitant de votre circonscription"
    if scrutin:
        e = "e" if femme else ""
        constat = {
            "pour": "vous avez voté pour",
            "contre": "vous avez voté contre",
            "abstention": f"vous vous êtes abstenu{e}",
            None: "vous n'avez pas pris part au vote",
        }.get(scrutin["position"], f"vous étiez noté{e} non-votant{e}")
        objet = f"Votre vote du {jour(scrutin['date'])} (scrutin n° {scrutin['numero']})"
        lignes += [f"Lors du scrutin public n° {scrutin['numero']} du {jour(scrutin['date'])}, "
                   f"portant sur {(scrutin['titre'] or 'un texte').rstrip('. ')}, {constat}.",
                   URL_SCRUTIN.format(scrutin["numero"]), "",
                   "[Votre question sur ce vote]", ""]
    else:
        lignes += ["[Votre message]", ""]
    lignes += ["Je vous remercie de votre réponse.", "", "[Vos prénom, nom et commune]"]
    return objet, "\n".join(lignes)


def _interroger(adresse, acteur, depute, scrutin):
    if not adresse:
        return ""
    objet, texte = message_au_depute(acteur, depute, scrutin)
    return (f' <a class="interroger" href="{escape(lien_courriel(adresse, objet, texte))}">'
            "L’interroger sur ce vote</a>")


def _lien_scrutin(numero, titre):
    return (f'<a href="{URL_SCRUTIN.format(numero)}" rel="noopener">'
            f'{escape(majuscule(titre or "Scrutin n° " + str(numero)))}</a>')


def _tableau(entetes, lignes, vide):
    if not lignes:
        return f'<p class="doux">{escape(vide)}</p>'
    tete = "".join(f"<th>{escape(e)}</th>" for e in entetes)
    corps = "".join("<tr>" + "".join(f"<td{' class=d' if i == 0 else ''}>{c}</td>"
                                     for i, c in enumerate(l)) + "</tr>" for l in lignes)
    return (f'<div class="defile"><table><thead><tr>{tete}</tr></thead>'
            f'<tbody>{corps}</tbody></table></div>')


def _carte(valeur, libelle, detail=""):
    return (f'<div class="carte"><b>{valeur}</b><span>{escape(libelle)}</span>'
            + (f'<small>{escape(detail)}</small>' if detail else "") + "</div>")


def formulaire_abonnement(nom, d, racine, api_url):
    """Formulaire d'abonnement à la lettre, pour un député en exercice."""
    return f"""
<section class="bloc">
<h2>Suivre son activité par e-mail</h2>
<form id="abonnement" method="post" action="{escape(api_url)}/api/abonnement">
<input type="hidden" name="departement" value="{escape(d['num_departement'] or '')}">
<input type="hidden" name="circo" value="{escape(str(d['num_circo'] or ''))}">
<p class="piege" aria-hidden="true"><label>Ne pas remplir <input name="site" tabindex="-1" autocomplete="off"></label></p>
<label for="abonnement-email">Votre adresse e-mail</label>
<input id="abonnement-email" name="email" type="email" required autocomplete="email">
<fieldset><legend>Fréquence</legend>
<label><input type="radio" name="frequence" value="hebdomadaire" checked> Chaque semaine</label>
<label><input type="radio" name="frequence" value="mensuelle"> Chaque mois</label></fieldset>
<p><label class="case"><input type="checkbox" name="consentement" value="1" required>
 J’accepte que mon adresse e-mail soit conservée pour recevoir cette lettre.</label></p>
<p><button type="submit">Recevoir l’activité de {escape(nom)}</button></p>
<p id="abonnement-retour" aria-live="polite"></p>
</form>
<p class="doux petit">Un e-mail vous demandera de confirmer. Seules votre adresse, cette circonscription
 et la fréquence sont conservées, jusqu’à votre désabonnement, possible en un clic depuis chaque
 lettre. Aucune lettre n’est envoyée quand il n’y a pas d’activité.
 <a href="{racine}confidentialite.html">Confidentialité</a>.</p>
</section>
<script src="{racine}abonnement.js"></script>
"""


def corps(db, uid, racine="", api_url=None):
    """Renvoie (titre, description, html du contenu principal)."""
    a = db.execute("SELECT * FROM acteurs WHERE uid = ?", (uid,)).fetchone()
    d = db.execute("SELECT * FROM deputes WHERE acteur_uid = ?", (uid,)).fetchone()
    i = indicateurs.pour_depute(db, uid)
    nom = f"{a['prenom']} {a['nom']}"
    sigle = d["groupe_sigle"]
    couleur = db.execute("SELECT couleur FROM organes WHERE uid = ?",
                         (d["groupe_uid"],)).fetchone()
    commissions = db.execute("""
        SELECT o.libelle, m.qualite FROM mandats m JOIN organes o ON o.uid = m.organe_uid
        WHERE m.acteur_uid = ? AND m.type_organe = 'COMPER' AND m.date_fin IS NULL
        ORDER BY m.qualite = 'Membre'""", (uid,)).fetchall()
    legislatures = [l[0] for l in db.execute(
        "SELECT DISTINCT legislature FROM mandats WHERE acteur_uid = ?"
        " AND type_organe = 'ASSEMBLEE'", (uid,))]
    phrases = portrait.rediger(a, d, [tuple(c) for c in commissions], legislatures)

    pastille = (f'<span class="pastille" style="background:{escape(couleur["couleur"])}"></span>'
                if couleur and couleur["couleur"] else "")
    statut = ('<span class="statut actif">En exercice</span>' if d["en_exercice"] else
              f'<span class="statut">Mandat clos le {jour(d["date_fin"])}</span>')

    solennels = votes_solennels(db, uid)
    dissidents = votes_dissidents(db, uid)
    nb_dissidents = i["votes_comparables"] - i["votes_conformes"]
    questions = db.execute("""
        SELECT date_question, type, analyse, ministere, statut FROM questions
        WHERE acteur_uid = ? ORDER BY date_question DESC LIMIT 5""", (uid,)).fetchall()
    interventions = db.execute("""
        SELECT c.date, i.sujet, i.texte FROM interventions i
        JOIN comptes_rendus c ON c.uid = i.compte_rendu_uid
        WHERE i.acteur_uid = ? AND i.role IS NOT 'president' AND i.nb_mots >= 20
        ORDER BY c.date DESC, i.ordre DESC LIMIT 5""", (uid,)).fetchall()
    contacts = db.execute("SELECT type, valeur FROM contacts WHERE acteur_uid = ?",
                          (uid,)).fetchall()

    # On n'écrit qu'à un député en exercice.
    adresse = adresse_officielle(contacts) if d["en_exercice"] else None
    ecrire = ""
    if adresse:
        objet, texte = message_au_depute(a, d)
        ecrire = f"""<p><a class="bouton" href="{escape(lien_courriel(adresse, objet, texte))}">Écrire à {escape(nom)}</a></p>
<p class="doux petit">Ce bouton ouvre votre messagerie avec un message à compléter, adressé à {escape(adresse)}.
 Le message part de votre propre adresse : ce site ne le voit pas et n’en garde aucune trace.
 Si rien ne s’ouvre, copiez l’adresse ci-dessous dans votre messagerie.</p>"""
    lignes_contact = []
    for genre in CONTACTS_AFFICHES:
        for c in contacts:
            if c["type"] != genre:
                continue
            valeur = escape(c["valeur"])
            if genre == "Mèl":
                valeur = f'<a href="mailto:{valeur}">{valeur}</a>'
            lignes_contact.append(
                f"<dt>{escape(LIBELLES_CONTACT.get(genre, genre))}</dt><dd>{valeur}</dd>")

    exprimes = i["votes_pour"] + i["votes_contre"] + i["votes_abstention"]
    repartition = ""
    if exprimes:
        repartition = (
            f'<p class="doux petit">Sur ses {exprimes} votes exprimés : '
            f'{i["votes_pour"]} pour ({pourcent(i["votes_pour"] / exprimes)}), '
            f'{i["votes_contre"]} contre ({pourcent(i["votes_contre"] / exprimes)}), '
            f'{i["votes_abstention"]} abstentions '
            f'({pourcent(i["votes_abstention"] / exprimes)}).</p>')

    meth = f'{racine}methodologie.html'
    html = f"""
<header class="entete">
<h1>{escape(nom)}</h1>
<p class="sous">{pastille}{escape(d['groupe_libelle'] or 'Groupe inconnu')}
 · {escape(d['departement'] or '')} ({escape(d['num_departement'] or '')}),
 {escape(portrait.ordinal(d['num_circo'], feminin=True)) if d['num_circo'] else ''} circonscription
 {statut}</p>
</header>

<section class="portrait"><p>{escape(' '.join(phrases[:2]))}</p>
<p>{escape(' '.join(phrases[2:]))}</p></section>

<section>
<h2>Ses votes</h2>
{_jauge("Participation aux scrutins solennels", i['taux_solennels'],
        f"{i['solennels_exprimes']} sur {i['solennels_eligibles']} pendant son mandat",
        i['moyenne_solennels'], i['moyenne_groupe_solennels'], sigle,
        f'Les scrutins solennels portent sur un texte entier et sont annoncés à l’avance. <a href="{meth}#solennels">Comment c’est calculé</a>.')}
{_jauge("Votes conformes à la ligne de son groupe", i['taux_loyaute'],
        f"{i['votes_conformes']} sur {i['votes_comparables']} votes comparables",
        i['moyenne_loyaute'], i['moyenne_groupe_loyaute'], sigle,
        f'<a href="{meth}#loyaute">Comment c’est calculé</a>.')}
{repartition}
<p class="doux petit">Tous scrutins publics confondus, {i['scrutins_exprimes']} votes exprimés
 sur {i['scrutins_eligibles']} scrutins ({pourcent(i['taux_scrutins'])}). Ce taux est bas pour
 presque tous les députés : la plupart des scrutins portent sur des amendements et se tiennent
 en même temps que d’autres réunions. <a href="{meth}#tous-scrutins">En savoir plus</a>.</p>

<h3>Ses votes sur les textes entiers</h3>
{_tableau(["Date", "Son vote", "Scrutin solennel", "Résultat"],
          [(jour(v['date']), _position(v['position']),
            _lien_scrutin(v['numero'], v['titre']) + _interroger(adresse, a, d, v),
            escape(majuscule(v['sort'] or ''))) for v in solennels],
          "Aucun scrutin solennel pendant son mandat.")}

<h3>Ses votes contre la ligne de son groupe</h3>
<p class="doux petit">{nb_dissidents} vote{'s' if nb_dissidents > 1 else ''} différent{'s' if nb_dissidents > 1 else ''}
 de la position majoritaire de son groupe, sur {i['votes_comparables']} comparables.
 Les scrutins solennels sont listés en premier.</p>
{_tableau(["Date", "Son vote", "Son groupe", "Scrutin"],
          [(jour(v['date']), _position(v['position']),
            f"{escape(v['groupe'] or '')} : {escape(LIBELLES_POSITION[v['ligne']].lower())}",
            _lien_scrutin(v['numero'], v['titre']) + _interroger(adresse, a, d, v))
           for v in dissidents],
          "Aucun vote contraire à la ligne de son groupe.")}
</section>

<section>
<h2>En commission</h2>
{_jauge("Présence aux réunions de commission", i['taux_commission'],
        f"{i['commission_present']} présences sur {i['commission_reunions']} réunions avec feuille de présence"
        + (f", dont {i['commission_excuse']} absences excusées" if i['commission_excuse'] else ""),
        i['moyenne_commission'], i['moyenne_groupe_commission'], sigle,
        f'Une feuille de présence n’est publiée que pour une partie des réunions. <a href="{meth}#commission">Comment c’est calculé</a>.')}
</section>

<section>
<h2>Son travail parlementaire</h2>
<div class="grille">
{_carte(i['interventions_longues'], "interventions en hémicycle", f"de 20 mots ou plus ; {i['interventions_courtes']} plus courtes")}
{_carte(i['amendements_deposes'], "amendements déposés", f"comme premier signataire ; {i['amendements_adoptes']} adoptés, {i['amendements_cosignes']} cosignés")}
{_carte(i['questions_ecrites'], "questions écrites", f"{i['questions_gouvernement']} au Gouvernement, {i['questions_orales']} orales sans débat")}
{_carte(i['propositions_auteur'], "propositions de loi", f"comme auteur ; {i['propositions_cosignees']} cosignées")}
</div>
<p class="doux petit">Ces décomptes mesurent un volume, pas une qualité ni une influence.
 <a href="{meth}#volumes">Ce qu’ils recouvrent</a>.</p>

<h3>Ses dernières questions</h3>
{_tableau(["Date", "Type", "Sujet", "Adressée au"],
          [(jour(q['date_question']), escape(q['type'] or ''), escape(q['analyse'] or ''),
            escape(q['ministere'] or '')) for q in questions],
          "Aucune question.")}

<h3>Ses dernières interventions en hémicycle</h3>
{_tableau(["Date", "Débat", "Extrait"],
          [(jour(x['date']), escape(x['sujet'] or ''),
            escape(x['texte'][:280] + ('…' if len(x['texte']) > 280 else ''))) for x in interventions],
          "Aucune intervention de 20 mots ou plus.")}
</section>

{formulaire_abonnement(nom, d, racine, api_url) if api_url and d['en_exercice'] else ''}
<section>
<h2>Lui écrire</h2>
{ecrire}
<dl class="contact">{''.join(lignes_contact) or '<dt>Contact</dt><dd>Aucun contact publié.</dd>'}</dl>
<p><a href="{URL_DEPUTE.format(escape(uid))}" rel="noopener">Sa fiche officielle sur le site de l’Assemblée nationale</a></p>
</section>
"""
    description = phrases[0]
    return nom, description, html
