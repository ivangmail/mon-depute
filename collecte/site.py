"""Génération du site statique : accueil, fiches et méthodologie.

Le site est un simple dossier de fichiers HTML, régénéré après chaque mise à
jour des données. Il peut être servi par n'importe quel hébergement.
"""

import json
import os
from html import escape

from . import fiche, indicateurs

NOM_SITE = "Mon député"
ICI = os.path.dirname(__file__)
CONTOURS = os.path.join(ICI, "contours")

STYLE = """
:root{--fond:#fbfaf7;--surface:#fff;--texte:#1c1f26;--doux:#5b6270;--trait:#dfe1e6;
--accent:#1d4e89;--pour:#1a7f4b;--contre:#b3261e;--neutre:#6b7280;--jauge:#e6e8ec;
--alerte:#fff6d6;--alerte-texte:#5c4400}
@media(prefers-color-scheme:dark){:root{--fond:#14161a;--surface:#1c1f25;--texte:#e9eaee;
--doux:#a0a6b2;--trait:#343943;--accent:#8fb8ee;--pour:#5fca93;--contre:#f08a82;
--neutre:#a0a6b2;--jauge:#2b3039;--alerte:#3a3214;--alerte-texte:#f2dfa0}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--texte);
font:17px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}a:focus-visible,input:focus-visible,select:focus-visible{
outline:3px solid var(--accent);outline-offset:2px}
.bandeau{background:var(--alerte);color:var(--alerte-texte);text-align:center;
font-size:.85rem;padding:5px 16px}
.barre{border-bottom:1px solid var(--trait);background:var(--surface)}
.barre div{max-width:900px;margin:0 auto;padding:12px 16px;display:flex;gap:20px;
flex-wrap:wrap;align-items:baseline}
.barre .marque{font-weight:700;text-decoration:none;color:var(--texte);margin-right:auto}
main{max-width:900px;margin:0 auto;padding:28px 16px 56px}
h1{font-size:2rem;line-height:1.2;margin:0 0 8px}
h2{font-size:1.3rem;margin:44px 0 16px;padding-bottom:8px;border-bottom:2px solid var(--trait)}
h3{font-size:1.02rem;margin:28px 0 8px}
p{margin:0 0 12px}.doux{color:var(--doux)}.petit{font-size:.875rem}
.sous{color:var(--doux);margin:0}.portrait{margin-top:20px;max-width:68ch}
.pastille{display:inline-block;width:.7em;height:.7em;border-radius:50%;margin-right:.4em}
.statut{display:inline-block;margin-left:.4em;padding:1px 10px;border-radius:99px;
border:1px solid var(--trait);font-size:.8rem;white-space:nowrap}
.statut.actif{border-color:var(--pour);color:var(--pour)}
.mesure{margin:0 0 22px}.mesure h3{margin:0 0 2px}
.chiffre{margin:0 0 6px}.chiffre b{font-size:1.7rem;font-variant-numeric:tabular-nums}
.jauge{position:relative;height:12px;border-radius:6px;background:var(--jauge);margin-bottom:6px}
.jauge .rempli{position:absolute;inset:0 auto 0 0;border-radius:6px;background:var(--accent)}
.jauge .repere{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--texte)}
.grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;
margin-bottom:12px}
.carte{background:var(--surface);border:1px solid var(--trait);border-radius:10px;
padding:12px 14px;display:flex;flex-direction:column}
.carte b{font-size:1.6rem;font-variant-numeric:tabular-nums}
.carte small{color:var(--doux);font-size:.8rem;margin-top:2px}
.defile{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th{text-align:left;font-weight:600;color:var(--doux);font-size:.8rem;
padding:6px 12px 6px 0;border-bottom:1px solid var(--trait)}
td{padding:8px 12px 8px 0;border-bottom:1px solid var(--trait);vertical-align:top}
td.d{white-space:nowrap;color:var(--doux);font-variant-numeric:tabular-nums}
.pos{font-weight:600;white-space:nowrap}.pos.pour{color:var(--pour)}
.pos.contre{color:var(--contre)}.pos.abstention,.pos.absent{color:var(--neutre)}
.pos.absent{font-weight:400;font-style:italic}
dl.contact{display:grid;grid-template-columns:max-content 1fr;gap:6px 18px;margin:0 0 16px}
dl.contact dt{color:var(--doux)}dl.contact dd{margin:0;overflow-wrap:anywhere}
.recherche{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0 8px}
.recherche input,.recherche select{font:inherit;padding:10px 12px;border-radius:8px;
border:1px solid var(--trait);background:var(--surface);color:var(--texte)}
.recherche input{flex:1 1 260px;min-width:0}
.recherche select{flex:1 1 220px;min-width:0;max-width:100%}
.bloc{background:var(--surface);border:1px solid var(--trait);border-radius:12px;
padding:18px 18px 12px;margin:24px 0}
.bloc h2{margin:0 0 6px;padding:0;border:0;font-size:1.15rem}
.bloc label{display:block;font-weight:600;margin-bottom:6px}
.bloc input{width:100%;font:inherit;padding:10px 12px;border-radius:8px;
border:1px solid var(--trait);background:var(--fond);color:var(--texte)}
#suggestions{list-style:none;margin:6px 0 0;padding:0}
#suggestions button{width:100%;text-align:left;font:inherit;padding:9px 12px;border:0;
border-bottom:1px solid var(--trait);background:none;color:var(--texte);cursor:pointer}
#suggestions button:hover,#suggestions button:focus-visible{background:var(--jauge)}
#resultat{margin-top:12px}#resultat p{margin:0 0 6px}
.bloc fieldset{border:0;padding:0;margin:14px 0 4px;display:flex;gap:6px 22px;flex-wrap:wrap}
.bloc legend{font-weight:600;padding:0;margin-bottom:4px}
.bloc fieldset label,.bloc label.case{display:inline;font-weight:400}
.bloc input[type=radio],.bloc input[type=checkbox]{width:auto;margin-right:6px}
.bloc button[type=submit],main form button{font:inherit;padding:10px 16px;border-radius:8px;
border:0;background:var(--accent);color:var(--fond);cursor:pointer;font-weight:600}
.piege{position:absolute;left:-9999px}
a.bouton{display:inline-block;padding:10px 16px;border-radius:8px;background:var(--accent);
color:var(--fond);font-weight:600;text-decoration:none}
a.interroger{display:table;margin:.4em 0 0;padding:1px 10px;border:1px solid var(--trait);
border-radius:99px;font-size:.8rem;text-decoration:none;white-space:nowrap}
a.interroger:hover,a.interroger:focus-visible{border-color:var(--accent)}
.alerte{background:var(--alerte);color:var(--alerte-texte);padding:8px 12px;border-radius:8px}
.lien{font:inherit;border:0;background:none;color:var(--accent);padding:0;cursor:pointer;
text-decoration:underline}
ul.liste{list-style:none;padding:0;margin:12px 0 0}
ul.liste li{border-bottom:1px solid var(--trait)}
ul.liste a{display:grid;grid-template-columns:1fr auto;gap:2px 16px;padding:10px 0;
text-decoration:none;color:var(--texte)}
ul.liste a:hover b{text-decoration:underline}
ul.liste span{color:var(--doux);font-size:.9rem}
ul.liste .g{grid-row:span 2;align-self:center;white-space:nowrap}
details{margin-top:32px}summary{cursor:pointer;font-weight:600}
footer{border-top:1px solid var(--trait);color:var(--doux);font-size:.85rem}
footer div{max-width:900px;margin:0 auto;padding:18px 16px 32px}
@media(max-width:520px){h1{font-size:1.6rem}dl.contact{grid-template-columns:1fr}
dl.contact dt{margin-top:8px}}
"""

RECHERCHE_JS = """
(function () {
  var champ = document.getElementById('q'), groupe = document.getElementById('g');
  var lignes = [].slice.call(document.querySelectorAll('#deputes li'));
  var compteur = document.getElementById('compteur');
  function norm(t) { return t.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase(); }
  function filtrer() {
    var mots = norm(champ.value).split(/\\s+/).filter(Boolean), g = groupe.value, n = 0;
    lignes.forEach(function (li) {
      var ok = (!g || li.dataset.g === g) &&
        mots.every(function (m) { return li.dataset.q.indexOf(m) !== -1; });
      li.hidden = !ok; if (ok) n++;
    });
    compteur.textContent = n + (n > 1 ? ' députés' : ' député');
  }
  champ.addEventListener('input', filtrer); groupe.addEventListener('change', filtrer);
  filtrer();
})();
"""


def page(titre, description, contenu, racine, fraicheur, mentions=False):
    lien_mentions = (f' · <a href="{racine}mentions-legales.html">Mentions légales</a>'
                     if mentions else "")
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(titre)}</title>
<meta name="description" content="{escape(description)}">
<link rel="stylesheet" href="{racine}style.css"></head><body>
<div class="bandeau">Données de l’Assemblée nationale à jour au {escape(fraicheur or 'date inconnue')}</div>
<nav class="barre"><div><a class="marque" href="{racine}index.html">{escape(NOM_SITE)}</a>
<a href="{racine}index.html">Trouver un député</a>
<a href="{racine}methodologie.html">Méthodologie</a></div></nav>
<main>{contenu}</main>
<footer><div>Source : Assemblée nationale, données ouvertes publiées sous Licence Ouverte
 (data.assemblee-nationale.fr). Ce site n’est pas un site officiel de l’Assemblée nationale.
 Seuls les documents officiels font foi.
 <a href="{racine}confidentialite.html">Confidentialité</a>{lien_mentions}</div></footer>
</body></html>
"""


def _ligne(d, chemin):
    circo = f"{d['departement']} ({d['num_departement']}), circonscription n° {d['num_circo']}"
    cle = fiche.sans_accents(" ".join(str(x or "") for x in (
        d["prenom"], d["nom"], d["departement"], d["num_departement"],
        d["groupe_sigle"], d["groupe_libelle"])))
    return (f'<li data-q="{escape(cle)}" data-g="{escape(d["groupe_sigle"] or "")}">'
            f'<a href="{chemin}"><b>{escape(d["prenom"])} {escape(d["nom"])}</b>'
            f'<span class="g">{escape(d["groupe_sigle"] or "")}</span>'
            f'<span>{escape(circo)}</span></a></li>')


def accueil(deputes, chemins):
    actifs = [d for d in deputes if d["en_exercice"]]
    anciens = [d for d in deputes if not d["en_exercice"]]
    groupes = sorted({(d["groupe_sigle"], d["groupe_libelle"]) for d in actifs
                      if d["groupe_sigle"]}, key=lambda g: g[1])
    options = "".join(f'<option value="{escape(s)}">{escape(l)} ({escape(s)})</option>'
                      for s, l in groupes)
    return f"""
<h1>Que fait votre député ?</h1>
<p class="portrait">Le portrait de l’activité de chaque député à l’Assemblée nationale : ses votes,
 sa présence en commission, ses interventions, ses amendements et ses questions,
 à partir des données officielles.</p>
<section class="bloc">
<h2>Par votre adresse</h2>
<label for="adresse">Votre adresse postale</label>
<input id="adresse" type="search" autocomplete="off" placeholder="Ex. 8 boulevard du Port, 80000 Amiens">
<ul id="suggestions"></ul>
<div id="resultat" aria-live="polite"></div>
<p class="doux petit">Votre adresse est envoyée par votre navigateur au service public de géocodage
 de l’IGN, qui renvoie ses coordonnées (à défaut, votre code postal est envoyé au service public
 des communes). Ce site ne la reçoit pas et ne conserve rien.
 <a href="methodologie.html#adresse">Comment la circonscription est trouvée</a>.
 <button class="lien" id="etranger" type="button">J’habite à l’étranger</button></p>
</section>
<h2>Par nom ou département</h2>
<form class="recherche" role="search" onsubmit="return false">
<input id="q" type="search" autocomplete="off" aria-label="Rechercher un député"
 placeholder="Nom, département ou numéro de département">
<select id="g" aria-label="Filtrer par groupe politique"><option value="">Tous les groupes</option>{options}</select>
</form>
<p class="doux petit" id="compteur" aria-live="polite">{len(actifs)} députés</p>
<ul class="liste" id="deputes">{''.join(_ligne(d, chemins[d['acteur_uid']]) for d in actifs)}</ul>
<details><summary>Députés ayant quitté l’Assemblée depuis le début de la législature ({len(anciens)})</summary>
<ul class="liste">{''.join(_ligne(d, chemins[d['acteur_uid']]) for d in anciens)}</ul></details>
<script src="recherche.js"></script>
<script src="adresse.js"></script>
"""


def methodologie(db):
    m = {(l["perimetre"], l["indicateur"]): l for l in db.execute("SELECT * FROM moyennes")}
    n = lambda requete: db.execute(requete).fetchone()[0]
    solennels = n(f"SELECT count(*) FROM scrutins WHERE type_vote = '{indicateurs.SOLENNEL}'")
    scrutins = n("SELECT count(*) FROM scrutins")
    commissions = n("SELECT count(*) FROM reunions WHERE type = 'commission'")
    feuilles = n("SELECT count(*) FROM reunions_comptees")
    moy = lambda cle: fiche.pourcent(m[("tous", cle)]["valeur"]) if ("tous", cle) in m else "—"
    return f"""
<h1>Méthodologie</h1>
<p class="portrait">Un chiffre sans méthode n’est qu’une affirmation. Cette page décrit comment
 chaque indicateur est calculé, et ce qu’il ne mesure pas. La même règle s’applique à tous
 les députés, sans ajustement au cas par cas.</p>

<h2 id="source">D’où viennent les données</h2>
<p>Toutes les données viennent de la plateforme de données ouvertes de l’Assemblée nationale
 (data.assemblee-nationale.fr), publiées sous Licence Ouverte. Elles sont téléchargées une
 fois par jour. La date des données les plus récentes est affichée en haut de chaque page.</p>
<p>Le site ne publie ni classement général ni note : aucun chiffre ne résume à lui seul
 le travail d’un député.</p>

<h2 id="solennels">Participation aux scrutins solennels</h2>
<p>Un scrutin solennel porte sur l’ensemble d’un texte important. Sa date et son heure sont
 fixées à l’avance, et tous les députés sont attendus. C’est donc le seul type de scrutin
 où ne pas voter a une signification claire. La législature en compte {solennels} à ce jour,
 sur {scrutins} scrutins publics.</p>
<p><b>Calcul :</b> nombre de scrutins solennels où le député a voté pour, contre ou s’est abstenu,
 divisé par le nombre de scrutins solennels tenus pendant qu’il siégeait.</p>
<ul>
<li>Les scrutins antérieurs à son arrivée ou postérieurs à son départ ne comptent pas.
 Un passage au Gouvernement interrompt le mandat : cette période ne compte pas non plus.</li>
<li>Un vote par délégation compte comme un vote : le député a confié sa voix à un collègue.</li>
<li>Les positions « non-votant » ne comptent pas comme une participation.</li>
<li>Le taux n’est pas affiché en dessous de {indicateurs.MIN_SOLENNELS} scrutins solennels pendant le mandat.</li>
</ul>
<p>Moyenne actuelle des députés en exercice : {moy('solennels')}.</p>

<h2 id="tous-scrutins">Pourquoi le taux « tous scrutins » est bas</h2>
<p>La très grande majorité des scrutins publics portent sur des amendements. Ils se succèdent
 à toute heure, souvent pendant des réunions de commission, et seuls les députés qui suivent
 le texte sont dans l’hémicycle. Un taux bas sur l’ensemble des scrutins est donc la règle,
 et ne dit pas qu’un député est absent de l’Assemblée. Ce taux est indiqué à titre
 d’information, jamais mis en avant.</p>
<p>Seuls les scrutins publics sont enregistrés nominativement. Les votes à main levée
 ne laissent aucune trace individuelle.</p>

<h2 id="loyaute">Votes conformes à la ligne du groupe</h2>
<p><b>Ligne d’un groupe sur un scrutin :</b> la position (pour, contre ou abstention) la plus
 fréquente parmi les membres du groupe qui ont voté. En cas d’égalité entre deux positions,
 le groupe n’a pas de ligne sur ce scrutin et celui-ci est écarté.</p>
<p><b>Calcul :</b> nombre de votes du député identiques à la ligne de son groupe, divisé par le
 nombre de ses votes exprimés sur des scrutins où son groupe avait une ligne.</p>
<ul>
<li>Le vote est comparé au groupe auquel le député appartenait le jour du scrutin, tel que
 l’Assemblée le publie pour chaque vote. Un changement de groupe ne fausse donc pas le calcul.</li>
<li>Les députés non inscrits n’ont pas de ligne de groupe : l’indicateur ne s’applique pas à eux.</li>
<li>Le taux n’est pas affiché en dessous de {indicateurs.MIN_COMPARABLES} votes comparables.</li>
</ul>
<p>Un taux élevé est la norme dans tous les groupes (moyenne : {moy('loyaute')}). Voter contre
 son groupe n’est ni une qualité ni un défaut : la fiche liste simplement les votes concernés.</p>

<h2 id="commission">Présence en commission</h2>
<p><b>Calcul :</b> nombre de réunions de commission où le député est noté présent, divisé par
 le nombre de réunions où il figure sur la feuille de présence (présent, absent ou excusé).</p>
<ul>
<li>L’Assemblée ne publie une feuille de présence que pour une partie des réunions :
 {feuilles} sur {commissions} réunions de commission à ce jour. L’indicateur ne porte que sur celles-ci.</li>
<li>Ne sont retenues que les réunions confirmées et déjà tenues. L’agenda de l’Assemblée inscrit
 d’avance les membres convoqués comme « absents » : une réunion à venir, annulée, ou dont la
 feuille ne compte aucun présent (feuille non remplie) est donc écartée.</li>
<li>Une absence excusée reste comptée comme une absence, mais elle est indiquée séparément.</li>
<li>Le taux n’est pas affiché en dessous de {indicateurs.MIN_REUNIONS} réunions.</li>
</ul>
<p>Moyenne actuelle des députés en exercice : {moy('commission')}. La présence en hémicycle,
 elle, n’est enregistrée nulle part : aucun indicateur ne peut la mesurer.</p>

<h2 id="volumes">Interventions, amendements, questions, propositions</h2>
<p>Ces chiffres sont des décomptes. Ils mesurent un volume, pas une qualité ni une influence,
 et ne doivent pas servir à comparer deux députés sans précaution.</p>
<ul>
<li><b>Interventions :</b> prises de parole en séance publique, d’après les comptes rendus.
 Celles de moins de 20 mots (interruptions, formules de procédure) sont comptées à part.
 Les prises de parole faites en présidant la séance sont exclues. Les débats en commission
 ne sont pas publiés sous une forme exploitable et ne sont pas comptés.</li>
<li><b>Amendements déposés :</b> ceux dont le député est le premier signataire. Un amendement
 cosigné, parfois par tout un groupe, est compté à part. Certains groupes déposent des
 amendements en très grand nombre : le volume dépend beaucoup de la stratégie du groupe.</li>
<li><b>Questions :</b> questions écrites, questions au Gouvernement et questions orales sans débat.</li>
<li><b>Propositions de loi :</b> textes déposés pendant la législature, comme auteur ou cosignataire.</li>
</ul>

<h2 id="moyennes">Les moyennes de comparaison</h2>
<p>Chaque taux est accompagné de la moyenne des députés en exercice et de celle du groupe
 du député. Il s’agit de la moyenne des taux individuels, calculée sur les seuls députés
 pour lesquels le taux est affichable.</p>

<h2 id="portrait">Le portrait rédigé</h2>
<p>Le texte de présentation en haut de chaque fiche est assemblé automatiquement à partir des
 données de l’Assemblée (état civil, circonscription, mandats, groupe, commission, profession
 déclarée). Il ne contient aucune appréciation.</p>
<p>L’historique des mandats publié par l’Assemblée ne remonte qu’à juin 2002. Un mandat de
 député antérieur n’apparaît donc pas, et l’absence de mandat précédent sur une fiche ne
 signifie pas qu’il s’agit d’un premier mandat.</p>

<h2 id="adresse">Trouver son député par adresse</h2>
<p>L’adresse que vous saisissez est envoyée par votre navigateur au service public de géocodage
 de l’IGN (Géoplateforme), qui s’appuie sur la Base Adresse Nationale et renvoie ses coordonnées.
 Votre navigateur cherche ensuite dans quel contour de circonscription tombe ce point.
 Ce site ne reçoit ni l’adresse ni les coordonnées.</p>
<ul>
<li>Les contours viennent du jeu « Contours géographiques des circonscriptions législatives »
 publié sur data.gouv.fr par Jérôme Desboeufs sous Licence Ouverte 2.0, d’après les données du
 ministère de l’Intérieur et de l’INSEE. Ce n’est pas un tracé officiel, et il est simplifié.</li>
<li>À moins de 100 mètres d’une limite, le résultat peut être faux : le site l’indique et affiche
 aussi la circonscription voisine. Seule votre carte électorale fait foi.</li>
<li>Quand le service de géocodage ne répond pas, ou quand vous n’indiquez qu’une commune, le
 site s’appuie sur l’API publique du découpage administratif (geo.api.gouv.fr) : votre code postal
 donne votre commune, et le site liste la ou les circonscriptions qui la couvrent. Une grande
 ville en compte plusieurs : le site les affiche toutes, sans pouvoir trancher.</li>
<li>Il n’existe pas de contours pour la Nouvelle-Calédonie, la Polynésie française,
 Wallis-et-Futuna, Saint-Barthélemy et Saint-Martin, ni pour les Français établis hors de France :
 la liste des députés est alors filtrée sur le territoire.</li>
</ul>

<h2 id="limites">Limites connues</h2>
<ul>
<li>Le nombre de députés suivis dépasse 577 : il inclut ceux qui ont quitté l’Assemblée
 depuis le début de la législature et leurs remplaçants.</li>
<li>Quelques réunions sont rattachées à des organes que l’Assemblée ne décrit dans aucun
 de ses référentiels publiés.</li>
<li>Le contenu des amendements déclarés irrecevables n’est pas publié.</li>
<li>Les données sont celles que publie l’Assemblée : une erreur à la source se retrouve ici.</li>
</ul>
"""


def circonscriptions(deputes, chemins, dossier_contours=CONTOURS):
    """Associe à chaque contour de circonscription son député en exercice.

    Renvoie {code département: {"nom": ..., "circos": {numéro: {"depute", "g"}}}}.
    Un siège vacant donne "depute": None.
    """
    titulaires, noms = {}, {}
    for d in deputes:
        noms.setdefault(d["num_departement"], d["departement"])
        if d["en_exercice"] and d["num_circo"]:
            titulaires[(d["num_departement"], str(int(d["num_circo"])))] = {
                "nom": f"{d['prenom']} {d['nom']}", "groupe": d["groupe_sigle"] or "",
                "lien": chemins[d["acteur_uid"]]}
    resultat = {}
    for fichier in sorted(os.listdir(dossier_contours)):
        code = fichier[:-5]
        with open(os.path.join(dossier_contours, fichier), encoding="utf-8") as f:
            contours = json.load(f)
        resultat[code] = {"nom": noms.get(code, code), "circos": {
            numero: {"depute": titulaires.get((code, numero)), "g": geometrie}
            for numero, geometrie in contours.items()}}
    return resultat


def lister_deputes(db):
    return db.execute("""
        SELECT d.*, a.prenom, a.nom FROM deputes d JOIN acteurs a ON a.uid = d.acteur_uid
        ORDER BY a.nom COLLATE NOCASE, a.prenom COLLATE NOCASE""").fetchall()


def adresses_fiches(deputes):
    """Adresse de chaque fiche : prénom-nom, suffixé de l'identifiant en cas
    d'homonymie. La lettre d'information s'en sert pour ses liens."""
    chemins, pris = {}, set()
    for d in deputes:
        nom = fiche.slug(d["prenom"], d["nom"]) or d["acteur_uid"].lower()
        if nom in pris:
            nom = f"{nom}-{d['acteur_uid'].lower()}"
        pris.add(nom)
        chemins[d["acteur_uid"]] = f"deputes/{nom}.html"
    return chemins


HEBERGEUR = "Scaleway SAS, 8 rue de la Ville-l’Évêque, 75008 Paris, RCS Paris 433 115 904"
DEPOT = "https://github.com/ivangmail/mon-depute"


def mentions_legales(editeur, contact, hebergeur):
    joindre = (f"<p>Contact : {escape(contact)}</p>" if contact else "")
    return f"""
<h1>Mentions légales</h1>

<h2>Éditeur</h2>
<p>Ce site est édité à titre personnel et non professionnel par {escape(editeur)},
 qui en est aussi le directeur de la publication.</p>
{joindre}

<h2>Hébergeur</h2>
<p>{escape(hebergeur)}.</p>

<h2>Nature du site</h2>
<p>{escape(NOM_SITE)} est un site indépendant. Ce n’est pas un site officiel de l’Assemblée nationale,
 et il n’est lié à aucun parti, groupe politique ni élu. Il ne publie ni classement ni note des députés.</p>

<h2>Données et sources</h2>
<p>Les données sur les députés et leur activité proviennent des données ouvertes de l’Assemblée
 nationale (data.assemblee-nationale.fr), réutilisées sous Licence Ouverte. Les contours des
 circonscriptions viennent du jeu « Contours géographiques des circonscriptions législatives »
 publié sur data.gouv.fr par Jérôme Desboeufs, sous Licence Ouverte 2.0. Les calculs sont décrits
 dans la page <a href="methodologie.html">Méthodologie</a>. Seuls les documents officiels font foi.</p>

<h2>Signaler une erreur</h2>
<p>Les chiffres affichés sont calculés automatiquement à partir des données publiées par
 l’Assemblée. Une erreur à la source se retrouve ici ; une erreur de calcul est aussi possible.
 {('Vous pouvez la signaler à l’adresse ci-dessus.' if contact else '')}</p>

<h2>Code source</h2>
<p>Le code de ce site est public : <a href="{DEPOT}">{DEPOT}</a>.</p>

<h2>Données personnelles</h2>
<p>Voir la page <a href="confidentialite.html">Confidentialité</a>.</p>
"""


def confidentialite(api_url, editeur=None, contact=None):
    responsable = ""
    if editeur:
        responsable = (f"<p>Le responsable du traitement est {escape(editeur)}."
                       + (f" Pour exercer vos droits, écrivez à {escape(contact)}." if contact else "")
                       + "</p>")
    lettre = """
<h2>La lettre d’information</h2>
<p>Si vous vous abonnez à l’activité d’un député, sont conservées : votre adresse e-mail, la
 circonscription suivie et la fréquence choisie. Rien d’autre : ni nom, ni adresse postale,
 ni adresse IP.</p>
<ul>
<li><b>Finalité :</b> vous envoyer cette lettre, et rien d’autre. Votre adresse n’est ni cédée,
 ni utilisée pour un autre envoi.</li>
<li><b>Base légale :</b> votre consentement, donné en cochant la case du formulaire puis en
 confirmant par e-mail.</li>
<li><b>Durée :</b> jusqu’à votre désabonnement. Une inscription non confirmée est effacée
 sous 7 jours.</li>
<li><b>Désabonnement :</b> en un clic depuis chaque lettre. Votre adresse est alors effacée,
 sans conservation.</li>
<li><b>Envoi :</b> les lettres sont acheminées par un prestataire d’envoi d’e-mails, qui reçoit
 votre adresse pour cette seule opération.</li>
</ul>
<p>Vous disposez d’un droit d’accès, de rectification et d’effacement de ces données, et du droit
 d’introduire une réclamation auprès de la CNIL.</p>""" + responsable if api_url else ""
    return f"""
<h1>Confidentialité</h1>
<p class="portrait">Ce site se consulte sans compte et ne dépose aucun cookie.</p>

<h2>La recherche par adresse</h2>
<p>L’adresse que vous saisissez est envoyée par votre navigateur au service public de géocodage
 de l’IGN ; à défaut, votre code postal est envoyé au service public du découpage administratif
 (geo.api.gouv.fr). La circonscription est ensuite déterminée dans votre navigateur.
 Ce site ne reçoit ni votre adresse ni vos coordonnées, et ne conserve rien.</p>
{lettre}
<h2>Écrire à un député</h2>
<p>Les boutons « Écrire à… » et « L’interroger sur ce vote » ouvrent votre propre messagerie avec un
 message à compléter. Ce message part de votre adresse, directement vers celle du député : ce site
 ne le voit pas, ne le transmet pas et n’en garde aucune trace.</p>

<h2>Les données sur les députés</h2>
<p>Les informations affichées sur les députés (état civil, mandats, votes, contacts publics)
 sont celles que l’Assemblée nationale publie en données ouvertes, sous Licence Ouverte.</p>
"""


def generer(db, dossier, journal=print, api_url=None, editeur=None, contact=None,
            hebergeur=None):
    """editeur : nom de l'éditeur du site. S'il est fourni, la page Mentions
    légales est générée et liée depuis le pied de chaque page."""
    api_url = (api_url or "").rstrip("/") or None
    mentions = bool(editeur)
    fraicheur = fiche.date_source(l[0] for l in db.execute("SELECT last_modified FROM imports"))
    deputes = lister_deputes(db)
    os.makedirs(os.path.join(dossier, "deputes"), exist_ok=True)

    chemins = adresses_fiches(deputes)

    def ecrire(chemin, contenu):
        with open(os.path.join(dossier, chemin), "w", encoding="utf-8") as f:
            f.write(contenu)

    ecrire("style.css", STYLE)
    ecrire("recherche.js", RECHERCHE_JS)
    for script in ("adresse.js", "abonnement.js"):
        with open(os.path.join(ICI, script), encoding="utf-8") as f:
            ecrire(script, f.read())
    ecrire("confidentialite.html", page(
        f"Confidentialité · {NOM_SITE}", "Ce que ce site reçoit, conserve, et ne conserve pas.",
        confidentialite(api_url, editeur, contact), "", fraicheur, mentions))
    if mentions:
        ecrire("mentions-legales.html", page(
            f"Mentions légales · {NOM_SITE}", "Éditeur, hébergeur et sources du site.",
            mentions_legales(editeur, contact, hebergeur or HEBERGEUR), "", fraicheur, mentions))
    os.makedirs(os.path.join(dossier, "circos"), exist_ok=True)
    for code, contenu in circonscriptions(deputes, chemins).items():
        ecrire(f"circos/{code}.json", json.dumps(contenu, ensure_ascii=False,
                                                 separators=(",", ":")))
    ecrire("index.html", page(
        NOM_SITE, "L’activité de chaque député à l’Assemblée nationale : votes, présence"
        " en commission, interventions, amendements, questions.",
        accueil(deputes, chemins), "", fraicheur, mentions))
    ecrire("methodologie.html", page(
        f"Méthodologie · {NOM_SITE}", "Comment chaque indicateur est calculé, et ses limites.",
        methodologie(db), "", fraicheur, mentions))
    for d in deputes:
        titre, description, contenu = fiche.corps(db, d["acteur_uid"], racine="../",
                                                  api_url=api_url)
        ecrire(chemins[d["acteur_uid"]],
               page(f"{titre} · {NOM_SITE}", description, contenu, "../", fraicheur, mentions))
    journal(f"{len(deputes)} fiches écrites dans {dossier}")
    return chemins
