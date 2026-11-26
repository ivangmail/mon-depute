"""Génération du site statique : accueil, fiches et méthodologie.

Le site est un simple dossier de fichiers HTML, régénéré après chaque mise à
jour des données. Il peut être servi par n'importe quel hébergement.
"""

import json
import os
from html import escape

from . import fiche, indicateurs, themes

NOM_SITE = "Mon député"
ICI = os.path.dirname(__file__)
CONTOURS = os.path.join(ICI, "contours")

STYLE = """
:root{--fond:#fbfaf7;--surface:#fff;--texte:#1c1f26;--doux:#5b6270;--trait:#dfe1e6;
--accent:#1d4e89;--pour:#1a7f4b;--contre:#b3261e;--neutre:#6b7280;--jauge:#e6e8ec;
--alerte:#fff6d6;--alerte-texte:#5c4400;--une-a:#e8f0f8;--une-b:#f3f6f9;--une-c:#ebf3ee;
--appel:#183f5b;--appel-texte:#d5e5f0;--abstention:#c9971f}
@media(prefers-color-scheme:dark){:root{--fond:#14161a;--surface:#1c1f25;--texte:#e9eaee;
--doux:#a0a6b2;--trait:#343943;--accent:#8fb8ee;--pour:#5fca93;--contre:#f08a82;
--neutre:#a0a6b2;--jauge:#2b3039;--alerte:#3a3214;--alerte-texte:#f2dfa0;--une-a:#18202b;
--une-b:#16191f;--une-c:#17211d;--appel:#1f3550;--appel-texte:#d5e5f0;--abstention:#e0b850}}
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
details.themes{margin:6px 0 10px}details.themes summary{font-weight:600}
details.themes .cases{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));
gap:4px 16px;margin-top:6px}
.bloc textarea{width:100%;font:inherit;padding:10px 12px;border-radius:8px;resize:vertical;
border:1px solid var(--trait);background:var(--fond);color:var(--texte);line-height:1.45}
.bloc input[type=text]+label,.bloc label[for=courrier-texte]{margin-top:12px}
.envois{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:14px 0 6px}
.envois span{color:var(--doux);font-size:.9rem;margin-right:4px}
.bouton{display:inline-block;font:inherit;font-weight:600;font-size:.92rem;padding:8px 14px;
border-radius:8px;border:1px solid var(--accent);background:var(--surface);color:var(--accent);
text-decoration:none;cursor:pointer}
.bouton:hover,.bouton:focus-visible{background:var(--accent);color:var(--fond)}
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
.vbarre{display:flex;height:8px;border-radius:4px;overflow:hidden;min-width:150px;
margin:6px 0 3px;background:var(--jauge)}
.vbarre span{display:block;height:100%}.vbarre .p{background:var(--pour)}
.vbarre .a{background:var(--abstention)}.vbarre .c{background:var(--contre)}
td small{display:block;font-size:.78rem;white-space:nowrap}
details.parcours{margin:6px 0 0}details.parcours summary{font-weight:400;font-size:.85rem;
color:var(--accent)}details.parcours p{margin:6px 0 0}
ol.frise{list-style:none;padding:0;margin:8px 0 4px;display:flex;flex-wrap:wrap;gap:10px 16px;
align-items:flex-start}
ol.frise li{display:grid;grid-template-columns:auto 1fr;align-content:start;column-gap:6px;
font-size:.8rem;line-height:1.3;width:11em}
ol.frise li span{grid-row:span 2;width:20px;height:20px;border-radius:50%;display:grid;
place-items:center;background:var(--neutre);color:var(--fond);font-weight:700;font-size:.75rem}
ol.frise li.ok span{background:var(--pour)}ol.frise li.ko span{background:var(--contre)}
ol.frise li b{font-weight:600}ol.frise li small{color:var(--doux)}
.accroche{font-size:1.1rem;max-width:62ch;color:var(--doux);margin:0 0 4px}
.bloc.adresse{margin-top:20px}
.bloc.adresse input{font-size:1.05rem;padding:12px 14px}
.reassurance{margin:12px 0 6px;font-size:.9rem;font-weight:600}
.etapes{list-style:none;padding:0;margin:8px 0 0;display:grid;gap:14px;
grid-template-columns:repeat(auto-fit,minmax(220px,1fr));counter-reset:etape}
.etapes li{counter-increment:etape;display:flex;gap:12px;align-items:flex-start}
.etapes li::before{content:counter(etape);flex:none;width:28px;height:28px;border-radius:50%;
background:var(--accent);color:var(--fond);display:grid;place-items:center;font-weight:700;
font-size:.9rem}
.etapes span{display:block;color:var(--doux);font-size:.9rem}
.depute-trouve{background:var(--fond);border:1px solid var(--trait);border-radius:10px;
padding:12px 14px;margin:0 0 10px}
#resultat .depute-trouve .nom{font-size:1.15rem;font-weight:700;margin:0}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.bouton.plein{background:var(--accent);color:var(--fond)}
.bouton.plein:hover,.bouton.plein:focus-visible{background:var(--texte);border-color:var(--texte)}
.lettre-exemple{margin:20px 0 0;border:1px solid var(--trait);border-radius:12px;
overflow:hidden}
/* Accueil */
.une{background:linear-gradient(125deg,var(--une-a),var(--une-b) 62%,var(--une-c));
border:1px solid var(--trait);border-radius:16px;padding:28px 24px 8px;margin:0 0 8px}
.une.avec-apercu{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr);gap:28px;
align-items:start}
.surtitre{font-size:.75rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
color:var(--accent);margin:0 0 10px}
.une h1{font-size:2.4rem;line-height:1.1;letter-spacing:-.02em}
.une .bloc.adresse{box-shadow:0 8px 24px rgba(23,61,88,.08)}
.apercu{background:var(--surface);border:1px solid var(--trait);border-radius:14px;
padding:18px 18px 8px;margin:0 0 20px;box-shadow:0 12px 32px rgba(23,61,88,.08)}
.apercu-nom{font-size:1.2rem;font-weight:700;margin:0}
.apercu-nom a{color:var(--texte);text-decoration:none}
.apercu-nom a:hover,.apercu-nom a:focus-visible{text-decoration:underline}
.apercu .bref{list-style:none;padding:0;margin:14px 0 4px;font-size:.92rem}
.apercu .bref li{padding:10px 0;border-top:1px solid var(--trait)}
.apercu .bref li.vote{background:var(--fond);border:1px solid var(--trait);border-radius:10px;
padding:10px 12px;margin-bottom:6px}
.apercu .bref li.vote b{display:block;font-size:.72rem;letter-spacing:.06em;
text-transform:uppercase;color:var(--accent);margin-bottom:4px}
.apercu .bref li.vote+li{border-top:0}
.apercu .actions{margin:8px 0 12px}
h2.titre-etapes{border:0;padding:0;margin:40px 0 14px}
.etapes li{background:var(--surface);border:1px solid var(--trait);border-radius:12px;
padding:16px}
.appel-lettre{background:var(--appel);color:#fff;border-radius:16px;padding:26px 28px;
margin:32px 0 20px;display:flex;flex-wrap:wrap;gap:16px 28px;align-items:center}
.appel-lettre div{flex:1 1 380px;min-width:0}
.appel-lettre h2{color:#fff;border:0;padding:0;margin:0 0 8px;font-size:1.45rem}
.appel-lettre p{color:var(--appel-texte);margin:0}
.appel-lettre .bouton{background:#fff;color:#183f5b;border-color:#fff}
.appel-lettre .bouton:hover,.appel-lettre .bouton:focus-visible{background:var(--appel-texte);
color:#183f5b}
.appel-lettre a:focus-visible{outline-color:#fff}
@media(max-width:760px){.une.avec-apercu{grid-template-columns:minmax(0,1fr);gap:4px}
.une{padding:22px 16px 4px}.une h1{font-size:1.9rem}.appel-lettre{padding:22px 18px}}
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
  var liste = document.getElementById('deputes'), tout = document.getElementById('tout');
  var ouverte = false;  // sans JavaScript, la liste reste affichée en entier
  if (tout) {
    tout.hidden = false;
    tout.addEventListener('click', function () { ouverte = true; filtrer(); });
  }
  function norm(t) { return t.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase(); }
  function filtrer() {
    var mots = norm(champ.value).split(/\\s+/).filter(Boolean), g = groupe.value, n = 0;
    lignes.forEach(function (li) {
      var ok = (!g || li.dataset.g === g) &&
        mots.every(function (m) { return li.dataset.q.indexOf(m) !== -1; });
      li.hidden = !ok; if (ok) n++;
    });
    var recherche = mots.length > 0 || g !== '';
    if (tout) {
      liste.hidden = !(ouverte || recherche);
      tout.hidden = !liste.hidden;
    }
    compteur.textContent = n + (n > 1 ? ' députés' : ' député') +
      (recherche ? (n > 1 ? ' trouvés' : ' trouvé') : '');
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
<a href="{racine}pourquoi.html">Pourquoi ?</a>
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


def _apercu(exemple):
    """Carte d'exemple de l'accueil : la lettre réelle de la semaine passée
    (lettre.exemple.composer), réduite à ses lignes « En bref ». Aucun chiffre
    n'est écrit ici : tout vient de la lettre composée à partir de la base."""
    lignes = exemple.get("en_bref") or []
    if not lignes:
        return ""
    items = []
    for i, ligne in enumerate(lignes):
        if i == 0 and exemple.get("vote"):
            items.append(f'<li class="vote"><b>Le vote à retenir</b>{escape(ligne)}</li>')
        else:
            items.append(f"<li>{escape(ligne)}</li>")
    groupe = exemple.get("groupe") or ""
    if groupe and exemple.get("sigle"):
        groupe += f" ({exemple['sigle']})"
    origine = " · ".join(x for x in (groupe, exemple.get("lieu") or "") if x)
    return f"""<aside class="apercu" aria-labelledby="apercu-titre">
<p class="surtitre" id="apercu-titre">Exemple réel · semaine du {escape(exemple['debut'])}
 au {escape(exemple['fin'])}</p>
<p class="apercu-nom"><a href="{escape(exemple['chemin_fiche'])}">{escape(exemple['depute'])}</a></p>
<p class="doux petit">{escape(origine)}</p>
<ul class="bref">{''.join(items)}</ul>
<div class="actions"><a class="bouton" href="{escape(exemple['chemin_fiche'])}">Voir sa fiche</a>
<a class="bouton" href="exemple-lettre.html">Lire la lettre complète</a></div>
<p class="doux petit">Résumé « En bref » de sa lettre, repris tel quel ; lettre composée le
 {escape(exemple['compose_le'])} à partir des données officielles.</p>
</aside>"""


def accueil(deputes, chemins, lettre=False, exemple_lettre=False, apercu=None):
    """lettre : le service d'abonnement est en place ; exemple_lettre : la page
    exemple-lettre.html est publiée ; apercu : la lettre d'exemple (dict de
    lettre.exemple.composer), résumée dans une carte à côté de la recherche."""
    actifs = [d for d in deputes if d["en_exercice"]]
    anciens = [d for d in deputes if not d["en_exercice"]]
    groupes = sorted({(d["groupe_sigle"], d["groupe_libelle"]) for d in actifs
                      if d["groupe_sigle"]}, key=lambda g: g[1])
    options = "".join(f'<option value="{escape(s)}">{escape(l)} ({escape(s)})</option>'
                      for s, l in groupes)
    exemple = (' <a href="exemple-lettre.html">Voir un exemple</a>.' if exemple_lettre
               else "")
    carte = _apercu(apercu) if (apercu and exemple_lettre) else ""
    return f"""
<div class="une{' avec-apercu' if carte else ''}">
<div class="une-texte">
<p class="surtitre">Assemblée nationale · 17ᵉ législature</p>
<h1>Que fait votre député ?</h1>
<p class="accroche">Ses votes, ses amendements, ses interventions et sa présence en commission,
 à partir des données officielles de l’Assemblée nationale.</p>
<section class="bloc adresse" aria-label="Trouver votre député par votre adresse">
<label for="adresse">Votre adresse postale</label>
<input id="adresse" type="search" autocomplete="off" placeholder="Ex. 8 bd du Port, Amiens">
<ul id="suggestions"></ul>
<div id="resultat" aria-live="polite" data-lettre="{'1' if lettre else ''}"></div>
<p class="reassurance">Données officielles de l’Assemblée nationale · Sans compte · Sans cookie</p>
<p class="doux petit">Votre adresse est envoyée par votre navigateur au service public de géocodage
 de l’IGN, qui renvoie ses coordonnées (à défaut, votre code postal est envoyé au service public
 des communes). Ce site ne la reçoit pas et ne conserve rien.
 <a href="methodologie.html#adresse">Comment la circonscription est trouvée</a>.
 <button class="lien" id="etranger" type="button">J’habite à l’étranger</button></p>
</section>
</div>
{carte}
</div>
<h2 class="titre-etapes">Comment ça marche</h2>
<ol class="etapes">
<li><div><b>Votre adresse</b><span>pour trouver votre circonscription.</span></div></li>
<li><div><b>Votre député</b><span>ses votes et son activité, comparés aux médianes des
 députés.</span></div></li>
{f"""<li><div><b>Sa lettre, si vous le souhaitez</b><span>chaque semaine ou chaque mois, par
 e-mail. Les textes des thèmes que vous choisissez passent en premier ; rien n’est
 retiré.{exemple}</span></div></li>""" if lettre else ""}
</ol>
{"""<section class="appel-lettre" aria-label="La lettre">
<div><h2>Votre député, dans votre boîte mail</h2>
<p>Chaque semaine ou chaque mois : ses votes, son activité et les textes débattus les
 sept jours suivants, avec un bouton pour lui écrire avant le débat. Chaque fait renvoie
 à sa source officielle. Sans compte : une adresse e-mail suffit, et chaque lettre
 contient un lien pour vous désabonner.</p></div>
<a class="bouton" href="#adresse">Trouver mon député pour m’abonner</a>
</section>""" if lettre else ""}
<p class="petit"><a href="pourquoi.html">Pourquoi suivre son député ?</a></p>
<h2>Par nom ou département</h2>
<form class="recherche" role="search" onsubmit="return false">
<input id="q" type="search" autocomplete="off" aria-label="Rechercher un député"
 placeholder="Nom, département ou numéro de département">
<select id="g" aria-label="Filtrer par groupe politique"><option value="">Tous les groupes</option>{options}</select>
</form>
<p class="doux petit" id="compteur" aria-live="polite">{len(actifs)} députés</p>
<button class="lien" id="tout" type="button" hidden>Afficher la liste des {len(actifs)} députés</button>
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
<p>Sur la fiche, chaque vote sur un texte entier est accompagné de la répartition des voix
 (pour, abstention, contre) et de la majorité requise, égale à la moitié des suffrages exprimés
 plus un, comme la publie l’Assemblée pour ces scrutins. « Où en est ce texte » donne la
 dernière étape connue et les étapes déjà franchies, selon les règles de la lettre
 (<a href="#lettre">voir plus bas</a>) ; aucune étape à venir n’est affichée.</p>
<p>Médiane actuelle des députés en exercice : {moy('solennels')}.</p>

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
 fréquente parmi les membres du groupe qui ont voté, à condition qu’elle réunisse plus de
 {int(indicateurs.SEUIL_LIGNE * 100)} % de leurs voix. En dessous, le groupe est partagé :
 il n’a pas de ligne sur ce scrutin, qui est écarté. Un vote différent de la majorité d’un
 groupe presque partagé n’est donc pas présenté comme un vote contre son groupe.</p>
<p><b>Calcul :</b> nombre de votes du député identiques à la ligne de son groupe, divisé par le
 nombre de ses votes exprimés sur des scrutins où son groupe avait une ligne.</p>
<p>D’autres sites, comme Datan, retiennent la simple majorité du groupe : leurs chiffres peuvent
 donc différer des nôtres.</p>
<ul>
<li>Le vote est comparé au groupe auquel le député appartenait le jour du scrutin, tel que
 l’Assemblée le publie pour chaque vote. Un changement de groupe ne fausse donc pas le calcul.</li>
<li>Les députés non inscrits n’ont pas de ligne de groupe : l’indicateur ne s’applique pas à eux.</li>
<li>Le taux n’est pas affiché en dessous de {indicateurs.MIN_COMPARABLES} votes comparables.</li>
</ul>
<p>Un taux élevé est la norme dans tous les groupes (médiane : {moy('loyaute')}). Voter contre
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
<p>Médiane actuelle des députés en exercice : {moy('commission')}. La présence en hémicycle,
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

<h2 id="medianes">Les médianes de comparaison</h2>
<p>Chaque taux est accompagné de la médiane des députés en exercice et de celle du groupe du
 député, calculées sur les seuls députés pour lesquels le taux est affichable.</p>
<p>La médiane est la valeur du milieu : la moitié des députés font plus, l’autre moitié
 moins. Contrairement à la moyenne, elle n’est pas tirée vers le haut ou vers le bas par
 quelques valeurs extrêmes, comme un député presque toujours absent parce qu’il est malade
 ou qu’il exerce une autre fonction. C’est aussi le repère qu’utilise la lettre
 d’information.</p>

<h2 id="portrait">Le portrait rédigé</h2>
<p>Le texte de présentation en haut de chaque fiche est assemblé automatiquement à partir des
 données de l’Assemblée (état civil, circonscription, mandats, groupe, commission, profession
 déclarée). Il ne contient aucune appréciation.</p>
<p>L’historique des mandats publié par l’Assemblée ne remonte qu’à juin 2002. Un mandat de
 député antérieur n’apparaît donc pas, et l’absence de mandat précédent sur une fiche ne
 signifie pas qu’il s’agit d’un premier mandat.</p>

<h2 id="contacts">Contacts des députés</h2>
<p>Les contacts affichés sur chaque fiche (courriel, permanence, téléphone, site, réseaux
 sociaux) sont ceux que publie l’Assemblée nationale, et eux seuls : ils ne sont complétés par
 aucune autre source, pour que la même règle s’applique à tous. Un compte absent des données de
 l’Assemblée n’est donc pas affiché. Le message proposé dans « Lui écrire » part vers l’adresse
 @assemblee-nationale.fr du député ; si aucun courriel n’est publié, la fiche le dit et renvoie
 à son adresse à l’Assemblée. Quand une permanence est publiée, la fiche rappelle qu’on peut y
 demander un rendez-vous.</p>

<h2 id="lettre">La lettre d’information</h2>
<p>La lettre applique les règles de cette page à la période qu’elle couvre, avec quelques
 règles propres.</p>
<ul>
<li><b>Période :</b> la lettre hebdomadaire part le mercredi et couvre la semaine du lundi au
 dimanche précédents ; la lettre mensuelle part le 3 et couvre le mois précédent. Ces deux
 jours d’écart laissent à l’Assemblée le temps de publier ses données. Tous les abonnés d’une
 même circonscription reçoivent donc la même lettre. Si une lettre n’a pas pu partir, la
 suivante reprend là où la précédente s’arrêtait, sur 60 jours au plus.</li>
<li><b>« En bref » :</b> trois lignes en tête de lettre. La première cite le vote le plus
 important de la période : d’abord les scrutins solennels et les motions de censure, puis celui
 qui a réuni le plus de députés ; l’intitulé est celui du scrutin, suivi de son résultat. La
 deuxième donne le nombre de scrutins publics auxquels le député a pris part, avec la médiane
 de l’Assemblée. La troisième résume le reste de son activité de la période (amendements,
 interventions, questions, propositions de loi, réunions de commission). Ces lignes sont
 produites par des règles fixes, sans rédaction automatique.</li>
<li><b>Thèmes mis en avant :</b> à l’inscription (cases facultatives) ou depuis la page de
 gestion de son abonnement, chacun peut choisir des thèmes. Les textes de ces thèmes sont alors présentés en premier dans chaque
 rubrique, et signalés comme tels. Rien n’est retiré : la lettre reste complète, et tous les
 abonnés d’une circonscription reçoivent les mêmes informations.</li>
<li><b>« L’essentiel » :</b> les scrutins solennels, les motions de censure et les votes sur
 l’ensemble d’un texte ou sur une partie d’un projet de loi de finances. Au-delà de huit, la
 lettre garde les scrutins solennels et les motions de censure, puis les votes qui ont réuni
 le plus de députés.</li>
<li><b>Motions de censure :</b> seuls les votes pour sont recensés par l’Assemblée. La lettre
 dit donc qu’un député a voté la censure ou ne l’a pas votée, sans parler d’absence.</li>
<li><b>Position du groupe :</b> elle n’est donnée que si elle réunit plus de 60 % des voix
 exprimées par le groupe sur ce scrutin. En dessous, le groupe est dit partagé, et un vote
 différent n’est pas présenté comme un vote contre sa ligne.</li>
<li><b>Vote serré :</b> scrutin où l’écart entre les pour et les contre ne dépasse pas
 dix voix.</li>
<li><b>Médianes :</b> nombre de scrutins de la période auxquels a pris part le député médian
 du groupe, puis de l’Assemblée, parmi les députés en exercice.</li>
<li><b>Amendements :</b> le sort affiché est celui que publie l’Assemblée au jour de l’envoi.
 Le texte cité est le début de l’exposé rédigé par l’auteur de l’amendement : il présente
 son point de vue.</li>
<li><b>Prise de parole citée :</b> la plus longue de la période, hors interruptions et rappels
 au règlement, si elle compte au moins cent mots. C’est un critère de longueur, pas de
 qualité.</li>
<li><b>Textes de sa commission :</b> scrutins de la période sur les textes examinés au fond par
 la commission permanente du député. C’est là que porte sa spécialité. Les groupes inscrivent
 souvent un député, pour un à trois jours, dans une autre commission : sa commission est donc
 celle où il a siégé le plus de jours sur les 90 derniers jours. La médiane est celle des
 députés dont c’est aussi la commission.</li>
<li><b>Intitulés en langage courant :</b> pour certains textes au titre long, technique ou peu
 explicite, la lettre affiche une reformulation (par exemple « Budget de l’État pour 2027 » pour
 « Projet de loi de finances pour 2027 »). Elle reprend le titre officiel ou dit ce que fait le
 texte, d’après le texte déposé, sans jugement ni appréciation ; le contenu d’un texte peut
 changer au cours de son examen. Chaque libellé est
 relu par l’éditeur du site avant d’être affiché, et le lien mène au dossier officiel. Les
 libellés sont publiés dans le fichier <code>collecte/libelles_textes.csv</code> du code
 source.</li>
<li><b>À l’ordre du jour :</b> textes inscrits aux séances des sept jours qui suivent
 l’envoi, d’après l’agenda publié par l’Assemblée. Seuls les points confirmés de séances
 confirmées sont retenus ; l’agenda peut encore changer, et un texte inscrit n’est pas
 toujours examiné. Au-delà de huit textes, la lettre garde d’abord ceux qui font l’objet d’un
 vote solennel, puis ceux de la commission du député.</li>
<li><b>Où en sont ces textes :</b> la dernière étape datée publiée par l’Assemblée dans le
 dossier de chaque texte (vote d’une assemblée, commission mixte paritaire, Conseil
 constitutionnel, promulgation, retrait). Elle est décrite telle quelle, sans en déduire la
 suite de la procédure. Un texte est dit « adopté définitivement » après un vote conforme des
 deux assemblées, l’adoption du texte de la commission mixte paritaire par chacune d’elles,
 ou une lecture définitive à l’Assemblée. Un texte sur lequel le Gouvernement a engagé sa
 responsabilité (article 49, alinéa 3, de la Constitution) est dit « considéré comme adopté »,
 puisqu’il n’y a pas eu de vote sur le texte. L’état affiché est celui connu le jour où la
 lettre est composée ; ces étapes sont publiées avec quelques jours de retard. Une frise
 montre les étapes déjà franchies et datées (dépôt, votes de chaque assemblée, commission mixte
 paritaire, Conseil constitutionnel, promulgation), huit au plus, les plus récentes : ✓ pour
 un texte adopté, ✕ pour un texte rejeté ou un désaccord, • pour les autres étapes. Elle ne
 montre aucune étape à venir. Un texte adopté sans vote (article 49, alinéa 3) est signalé
 « sans vote (49.3) ».</li>
<li><b>En commission :</b> une case par réunion de la période dotée d’une feuille de présence,
 avec la mention publiée par l’Assemblée (présent, absent, excusé).</li>
<li><b>Version texte :</b> les barres y sont dessinées en caractères (█ pour la part
 mesurée, ░ pour le reste), sur vingt caractères.</li>
</ul>

<h2 id="themes">Les thèmes</h2>
<p>Avant d’arriver en séance, chaque texte est examiné « au fond » par une commission de
 l’Assemblée. Le thème d’un texte est celui de cette commission, lors de la première lecture
 à l’Assemblée qui en a eu une. Le contenu des textes n’est ni lu ni interprété pour les
 classer : seul leur titre sert, pour une commission, comme expliqué sous le tableau.</p>
<table class="themes"><tr><th>Commission saisie au fond</th><th>Thème affiché</th></tr>
{"".join(f"<tr><td>{escape(c)}…</td><td>{escape(t)}</td></tr>" for c, t in themes.COMMISSIONS)}
</table>
{"".join(f"""<p>Les textes de la {escape(c[0].lower() + c[1:])} sont répartis d’après leur
 titre. {" ".join(f"Thème « {escape(t)} » si le titre contient l’un de ces mots : "
 f"{escape(', '.join(mots))} (sauf s’il contient aussi : {escape(', '.join(exclus))})."
 for t, mots, exclus in regles)} Un mot terminé par « … » vaut pour tous les mots qui
 commencent ainsi. Un titre qui contient les mots de deux thèmes, ou aucun, garde le thème
 de la commission. Ce tri peut se tromper ; les erreurs repérées sont corrigées à la main.</p>"""
 for c, regles in themes.MOTS_CLES.items())}
<p>Une commission couvre souvent plusieurs domaines, d’où des thèmes larges : la commission des
 lois traite aussi bien de justice que d’élections ou de police. Les textes confiés à une
 commission spéciale, créée pour un seul texte, sont classés à la main ; ces choix sont
 publiés, avec leur motif, dans le fichier <code>collecte/themes_corrections.csv</code> du
 <a href="{DEPOT}">code source</a>. Les résolutions et les motions de censure, qui ne passent
 pas en commission, n’ont pas de thème.</p>

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


URL_AN = "https://www.assemblee-nationale.fr/dyn/17"
SOURCES_POURQUOI = {
    "legislatives_2022": ("LCP, « Législatives 2022 : Ensemble loin de la majorité absolue »",
                          "https://lcp.fr/actualites/legislatives-2022-ensemble-loin-de-la-"
                          "majorite-absolue-le-rn-cree-la-surprise-la-nupes"),
    "demission_2024": ("Élysée, communiqué du 16/07/2024 sur la démission du gouvernement",
                       "https://www.elysee.fr/emmanuel-macron/2024/07/16/le-president-de-la-"
                       "republique-a-accepte-ce-jour-la-demission-du-gouvernement-de-m-gabriel-attal"),
    "barnier_2024": ("info.gouv.fr, « Michel Barnier nommé Premier ministre » (05/09/2024)",
                     "https://www.info.gouv.fr/actualite/michel-barnier-nomme-premier-ministre"),
    "constitution": ("Constitution du 4 octobre 1958, texte en vigueur (Conseil constitutionnel)",
                     "https://www.conseil-constitutionnel.fr/le-bloc-de-constitutionnalite/"
                     "texte-integral-de-la-constitution-du-4-octobre-1958-en-vigueur"),
    "senat_lois": ("Sénat, bilan annuel de l’application des lois, session 2024-2025",
                   "https://www.senat.fr/rap/r25-802/r25-802.html"),
    "duree_mandat": ("Assemblée nationale, fiche « L’élection des députés » (article L.O. 121 du "
                     "code électoral)",
                     "https://questions.assemblee-nationale.fr/contenu/telechargement/625543/file/"
                     "Fiche%203%20-%20Election%20des%20d%C3%A9put%C3%A9s.pdf"),
}


EXEMPLE_SCRUTIN = 8430  # vote solennel sur la protection des enfants, 21/07/2026


def _exemple(db):
    """Paragraphe « Un exemple », lu dans la base : aucun chiffre écrit à la main.
    Vide si le scrutin manque ou est incomplet."""
    try:
        s = db.execute("SELECT numero, date, titre, nb_pour, nb_contre, nb_abstentions"
                       " FROM scrutins WHERE numero = ?", (EXEMPLE_SCRUTIN,)).fetchone()
    except Exception:
        return ""
    if not s or None in tuple(s):
        return ""
    numero, date_vote, titre, pour, contre, abstentions = tuple(s)
    sujet = fiche.majuscule(titre or "").rstrip(". ")
    sujet = (sujet[0].lower() + sujet[1:]).replace("'", "’")
    return (f"<p><b>Un exemple.</b> Le {fiche.jour(date_vote)}, sur {escape(sujet)}, {pour} "
            f"députés ont voté pour, {contre} contre, et {abstentions} se sont abstenus "
            f"(<a href=\"{URL_AN}/scrutins/{numero}\">scrutin n° {numero}</a>). Comment a voté "
            "le vôtre ? Sa fiche vous le dit, et vous pouvez lui écrire pour lui demander "
            "pourquoi.</p>")


def pourquoi(db):
    """Page « Pourquoi suivre son député ? ». Chaque fait est relié à sa source ;
    les chiffres de l'Assemblée sont recalculés à chaque génération du site."""
    def source(cle):
        titre, url = SOURCES_POURQUOI[cle]
        return f'<a href="{escape(url)}">{escape(titre)}</a>'

    def scrutin(numero, texte):
        return f'<a href="{URL_AN}/scrutins/{numero}">{escape(texte)}</a>'

    def dossier(uid, texte):
        return f'<a href="{URL_AN}/dossiers/{uid}">{escape(texte)}</a>'

    sources = "".join(f"<li>{source(c)}</li>" for c in SOURCES_POURQUOI)
    return f"""
<h1>Pourquoi suivre son député ?</h1>
<p class="portrait"><b>En bref.</b> Depuis 2022, aucune force politique n’a seule la majorité
 absolue à l’Assemblée nationale. Ce que fait chaque député, ce qu’il vote, propose et défend,
 pèse donc sur les décisions. Ce site permet de le suivre, semaine après semaine.</p>

<h2>Une Assemblée sans majorité absolue</h2>
<p>Aux élections législatives de juin 2022, la coalition présidentielle est restée loin de la
 majorité absolue de 289 sièges ({source("legislatives_2022")}). Après la dissolution de juin
 2024, l’Assemblée élue en juillet 2024 compte plusieurs blocs, dont aucun ne peut gouverner
 seul. Depuis :</p>
<ul>
<li>les budgets de 2025 et de 2026 ont été adoptés sans vote sur le texte, le Gouvernement ayant
 engagé sa responsabilité en application de l’article 49, alinéa 3, de la Constitution
 ({dossier("DLR5L17N50198", "budget 2025")}, {dossier("DLR5L17N52428", "budget 2026")})&nbsp;;</li>
<li>le gouvernement de Michel Barnier a été renversé par une motion de censure le 04/12/2024
 ({scrutin(519, "scrutin n° 519")})&nbsp;;</li>
<li>celui de François Bayrou n’a pas obtenu la confiance de l’Assemblée le 08/09/2025
 ({scrutin(3054, "scrutin n° 3054")})&nbsp;;</li>
<li>du 16/07/2024 au 05/09/2024, pendant 51 jours, un gouvernement démissionnaire a expédié les
 affaires courantes ({source("demission_2024")} ; {source("barnier_2024")}).</li>
</ul>

<h2>2027 : une élection présidentielle, pas forcément des législatives</h2>
<p>L’élection présidentielle de 2027 désignera un chef de l’État ; elle n’élira pas de députés.
 L’Assemblée actuelle est élue jusqu’en juin 2029 ({source("duree_mandat")}). Il n’y aura
 d’élections législatives en 2027 que si le Président élu dissout l’Assemblée (article 12 de la
 Constitution), et rien ne garantit qu’une majorité absolue en sortirait. Dans les deux cas,
 aucune loi ne sera votée sans les députés.</p>

<h2>Ce que font les députés</h2>
<p>Les députés proposent, amendent et votent la loi, et contrôlent le Gouvernement. Les textes
 d’origine parlementaire occupent une large place : selon le Sénat, 45 des 56 lois adoptées
 définitivement pendant la session 2024-2025, soit 80 %, étaient d’origine parlementaire, contre
 58 % la session précédente ({source("senat_lois")}).</p>
<p>Certaines décisions, dont les budgets, ont en revanche été adoptées sans vote sur le texte. Ce
 que les députés font de leur mandat mérite donc d’être suivi.</p>

<h2>Savoir ce que fait son député</h2>
<p>Nous confions à un député, pour cinq ans au plus, le pouvoir de voter la loi. L’Assemblée
 publie chaque vote, chaque amendement, chaque intervention, mais ces informations sont
 dispersées et difficiles à lire. Ce site les rassemble :</p>
<ul>
<li>sur la fiche de chaque député : ses votes solennels, ses votes conformes ou non à la ligne de
 son groupe, ses amendements et ce qu’ils sont devenus, ses interventions, sa présence en
 commission ;</li>
<li>dans une lettre, chaque semaine ou chaque mois : les votes de la période, dont les votes
 serrés, l’avancement des textes votés et les textes inscrits à l’ordre du jour.</li>
</ul>
{_exemple(db)}

<h2>Lui demander des comptes</h2>
<p>Un député représente la Nation tout entière : « Tout mandat impératif est nul » (article 27 de
 la {source("constitution")}). Il n’est donc pas tenu par les consignes de ses électeurs, et rien
 ne l’oblige à leur répondre. Mais lui écrire, l’interroger lors d’une permanence, lui demander
 pourquoi il a voté de telle façon sur un texte important : c’est l’exercice normal de la
 citoyenneté entre deux élections.</p>

<h2>Ce que ce site n’est pas</h2>
<ul>
<li><b>Un classement ou une note.</b> Un taux de participation mesure un volume, pas la qualité
 d’un travail. Chaque chiffre est comparé à la médiane des députés et à celle de son groupe.</li>
<li><b>Un site militant.</b> Les mêmes règles valent pour tous les députés, quel que soit leur
 groupe, et la méthode est publiée : <a href="methodologie.html">Méthodologie</a>.</li>
<li><b>Un site officiel.</b> Seuls les documents de l’Assemblée nationale font foi.</li>
</ul>

<h2>Sources</h2>
<ul>
<li>Votes, dossiers et activité des députés : Assemblée nationale, données ouvertes
 (data.assemblee-nationale.fr), Licence Ouverte. Les scrutins et dossiers cités sont liés
 ci-dessus.</li>
<li>Recherche par adresse : géocodage de l’IGN (Géoplateforme) et contours des circonscriptions
 publiés sur data.gouv.fr.</li>
{sources}
</ul>"""


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


def confidentialite(api_url, editeur=None, contact=None, sauvegarde_distante=False):
    responsable = ""
    if editeur:
        responsable = (f"<p>Le responsable du traitement est {escape(editeur)}."
                       + (f" Pour exercer vos droits, écrivez à {escape(contact)}." if contact else "")
                       + "</p>")
    distante = (" et, chiffrées, dans un espace de stockage de l’hébergeur distinct du serveur,"
                " pour ne pas perdre les abonnements si celui-ci disparaissait. L’hébergeur ne"
                " peut pas les lire") if sauvegarde_distante else ""
    lettre = """
<h2>La lettre d’information</h2>
<p>Si vous vous abonnez à l’activité d’un député, sont conservées : votre adresse e-mail, la
 circonscription suivie, la fréquence choisie et, si vous en avez choisi, les thèmes à mettre en
 avant. Rien d’autre : ni nom, ni adresse postale, ni adresse IP.</p>
<ul>
<li><b>Finalité :</b> vous envoyer cette lettre, et rien d’autre. Votre adresse n’est ni cédée,
 ni utilisée pour un autre envoi.</li>
<li><b>Base légale :</b> votre consentement, donné en cochant la case du formulaire puis en
 confirmant par e-mail.</li>
<li><b>Durée :</b> jusqu’à votre désabonnement. Une inscription non confirmée est effacée
 sous 7 jours.</li>
<li><b>Désabonnement :</b> en un clic depuis chaque lettre. Votre adresse est alors effacée de
 la base ; elle disparaît des copies de sauvegarde au plus tard 14 jours après.</li>
<li><b>Sauvegarde :</b> une copie de la base est faite chaque jour, et seules les 14 dernières
 sont gardées, sur le serveur{distante}.</li>
<li><b>Statistiques :</b> le site compte, jour par jour, le nombre d’inscriptions, de
 confirmations et de désabonnements. Ces nombres ne sont reliés à aucune adresse.</li>
<li><b>Envoi :</b> les lettres sont acheminées par un prestataire d’envoi d’e-mails, qui reçoit
 votre adresse pour cette seule opération.</li>
</ul>
<p>Vous disposez d’un droit d’accès, de rectification et d’effacement de ces données, et du droit
 d’introduire une réclamation auprès de la CNIL.</p>""".replace("{distante}", distante) \
        + responsable if api_url else ""
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
<p>Le bloc « Lui écrire » et les liens « L’interroger sur ce vote » préparent un message dans votre
 navigateur. Vous l’envoyez ensuite avec votre propre messagerie (Gmail, Outlook.com, Yahoo Mail,
 le logiciel de votre appareil) ou en le copiant. Il part de votre adresse, directement vers celle
 du député : ce site ne le voit pas, ne le transmet pas et n’en garde aucune trace.</p>

<h2>Les données sur les députés</h2>
<p>Les informations affichées sur les députés (état civil, mandats, votes, contacts publics)
 sont celles que l’Assemblée nationale publie en données ouvertes, sous Licence Ouverte.</p>
"""


def exemple_lettre(exemple):
    """Page présentant une lettre réelle. exemple : dict renvoyé par
    lettre.exemple.composer (html, debut, fin, compose_le, depute, lieu, chemin_fiche)."""
    return f"""
<h1>Exemple de lettre</h1>
<p class="portrait"><b>{escape(exemple['depute'])}</b>, {escape(exemple['lieu'])} : voici, telle
 quelle, la lettre hebdomadaire envoyée aux abonnés de cette circonscription pour la semaine
 {f"du {escape(exemple['debut'])} au {escape(exemple['fin'])}"}, composée le
 {escape(exemple['compose_le'])}. Cet exemple est mis à jour chaque semaine. Chaque député en
 exercice a sa lettre, faite avec les mêmes règles.</p>
<p><a class="bouton plein" href="{escape(exemple['chemin_fiche'])}#abonnement">Recevoir la lettre de
 ce député</a> <a class="bouton" href="index.html">Trouver votre député</a></p>
<div class="lettre-exemple">{exemple['html']}</div>
<p class="doux petit">Les règles de la lettre sont décrites dans la
 <a href="methodologie.html#lettre">Méthodologie</a>.</p>"""


def generer(db, dossier, journal=print, api_url=None, editeur=None, contact=None,
            hebergeur=None, sauvegarde_distante=False, exemple=None):
    """editeur : nom de l'éditeur du site. S'il est fourni, la page Mentions
    légales est générée et liée depuis le pied de chaque page.
    exemple : lettre réelle à publier dans exemple-lettre.html (voir
    exemple_lettre), seulement si le service d'abonnement est en place."""
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
    for script in ("adresse.js", "abonnement.js", "ecrire.js"):
        with open(os.path.join(ICI, script), encoding="utf-8") as f:
            ecrire(script, f.read())
    ecrire("confidentialite.html", page(
        f"Confidentialité · {NOM_SITE}", "Ce que ce site reçoit, conserve, et ne conserve pas.",
        confidentialite(api_url, editeur, contact, sauvegarde_distante), "", fraicheur,
        mentions))
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
        accueil(deputes, chemins, lettre=bool(api_url),
                exemple_lettre=bool(api_url and exemple), apercu=exemple),
        "", fraicheur, mentions))
    if api_url and exemple:
        ecrire("exemple-lettre.html", page(
            f"Exemple de lettre · {NOM_SITE}",
            "Une lettre réelle, telle que la reçoivent les abonnés.",
            exemple_lettre(exemple), "", fraicheur, mentions))
    elif os.path.exists(os.path.join(dossier, "exemple-lettre.html")):
        os.remove(os.path.join(dossier, "exemple-lettre.html"))
    ecrire("methodologie.html", page(
        f"Méthodologie · {NOM_SITE}", "Comment chaque indicateur est calculé, et ses limites.",
        methodologie(db), "", fraicheur, mentions))
    ecrire("pourquoi.html", page(
        f"Pourquoi suivre son député ? · {NOM_SITE}",
        "Une Assemblée sans majorité absolue : ce que fait chaque député compte.",
        pourquoi(db), "", fraicheur, mentions))
    for d in deputes:
        titre, description, contenu = fiche.corps(db, d["acteur_uid"], racine="../",
                                                  api_url=api_url)
        ecrire(chemins[d["acteur_uid"]],
               page(f"{titre} · {NOM_SITE}", description, contenu, "../", fraicheur, mentions))
    journal(f"{len(deputes)} fiches écrites dans {dossier}")
    return chemins
