# Mon député

Collecte quotidienne des données ouvertes de l'Assemblée nationale
(17ᵉ législature) dans une base SQLite, calcul d'indicateurs d'activité et
génération d'un site statique : une fiche par député, une recherche par nom ou
par adresse postale, une page Méthodologie et une lettre d'information par
circonscription. Reste à faire : l'interpellation.

Python 3.10 ou plus, aucune dépendance à installer.

## Utilisation

```bash
python3 -m collecte maj
```

Télécharge les archives qui ont changé, recharge les jeux concernés, puis
recalcule les indicateurs et régénère le site dans `site/`. Première exécution :
environ 540 Mo téléchargés, base d'environ 1,3 Go, 3 à 4 minutes. Les exécutions
suivantes ne retéléchargent que ce qui a changé.

```bash
python3 -m collecte site
```

Recalcule les indicateurs et régénère le site sans rien télécharger (environ
30 secondes). Pour le consulter en local :

```bash
python3 -m http.server 8000 --directory site
```

```bash
python3 -m collecte etat
```

Affiche la date de chaque source et le nombre de lignes par table.

```bash
python3 -m unittest
```

Options de `maj` : `--jeux acteurs scrutins` (limiter à certains jeux),
`--forcer` (tout retélécharger), `--sans-telechargement` (recharger à partir
des archives déjà présentes), `--sans-site` (ne pas régénérer le site).

Pour une mise à jour quotidienne, planifier `python3 -m collecte maj` une fois
par jour en fin de matinée : les sources sont régénérées par l'Assemblée dans
la nuit et la matinée. La commande renvoie un code d'erreur si un jeu échoue ;
les autres jeux sont tout de même mis à jour.

## Publication automatique

Le fichier `.github/workflows/publication.yml` lance chaque jour les tests, la
collecte, le calcul des indicateurs et la génération du site, puis publie le
dossier `site/` sur GitHub Pages. Il se lance aussi à chaque modification de la
branche `main` et à la demande (onglet Actions, bouton « Run workflow »).

Si un jeu de données échoue, rien n'est publié : la version de la veille reste
en ligne. GitHub suspend les tâches planifiées d'un dépôt resté 60 jours sans
activité ; il suffit alors de les réactiver dans l'onglet Actions.

## Données chargées

| Jeu | Tables | Contenu |
|---|---|---|
| acteurs | `acteurs`, `deputes`, `mandats`, `organes`, `contacts` | députés de la législature, ministres, groupes, commissions, adresses |
| scrutins | `scrutins`, `votes` | scrutins publics et position de chaque député |
| reunions | `reunions`, `presences` | agenda des commissions et des séances, feuilles de présence |
| questions | `questions` | questions écrites, au gouvernement, orales sans débat |
| dossiers | `dossiers`, `documents`, `documents_signataires` | dossiers législatifs, textes et rapports, auteurs et cosignataires |
| debats | `comptes_rendus`, `interventions` | prises de parole en hémicycle |
| amendements | `amendements`, `amendements_cosignataires` | amendements, auteur, sort |

La table `deputes` donne une ligne par député de la législature, avec sa
circonscription, son groupe et l'indicateur `en_exercice`. La table `imports`
garde la version de chaque archive chargée.

Les dates sont stockées au format ISO (AAAA-MM-JJ) et affichées en JJ/MM/AAAA.

## Indicateurs et site

Les règles de calcul sont dans `collecte/indicateurs.py` et sont décrites en
français courant dans la page Méthodologie du site (`collecte/site.py`) : toute
modification de l'un doit être reportée dans l'autre.

- Participation aux scrutins solennels, rapportée aux scrutins tenus pendant le
  mandat, avec la moyenne des députés et celle du groupe.
- Votes conformes à la ligne du groupe auquel le député appartenait le jour du
  scrutin, et liste des votes contraires.
- Présence en commission, sur les seules réunions dotées d'une feuille de présence.
- Décomptes : interventions, amendements, questions, propositions de loi.
- Portrait rédigé automatiquement (`collecte/portrait.py`), sans appréciation.

Le site est un dossier de fichiers statiques (environ 20 Mo, 655 fiches) qui
peut être servi par n'importe quel hébergement. Les liens vers les scrutins et
les fiches officielles suivent les adresses du site de l'Assemblée
(`/dyn/17/scrutins/<numéro>`, `/dyn/deputes/<identifiant>`).

## Recherche par adresse

Elle fonctionne entièrement dans le navigateur (`collecte/adresse.js`) :
l'adresse saisie est envoyée au service public de géocodage de l'IGN
(`data.geopf.fr/geocodage`), qui renvoie ses coordonnées, puis la
circonscription est trouvée en cherchant dans quel contour tombe le point. Le
site ne reçoit ni l'adresse ni les coordonnées.

Les contours sont livrés avec le code, dans `collecte/contours/` (un fichier
par département, 559 circonscriptions). Ils viennent du jeu « Contours
géographiques des circonscriptions législatives » publié sur data.gouv.fr par
Jérôme Desboeufs sous Licence Ouverte 2.0 (version p20 du 13/06/2024), d'après
les données du ministère de l'Intérieur et de l'INSEE. Ce n'est pas un tracé
officiel. Pour les régénérer après un redécoupage :

```bash
python3 outils/preparer_contours.py circonscriptions-legislatives-p20.geojson
```

Quand le service de géocodage ne répond pas, ou quand seule une commune est
indiquée, le site se rabat sur l'API publique du découpage administratif
(`geo.api.gouv.fr`) : le code postal donne la commune, et le site liste la ou
les circonscriptions qui la couvrent, sans pouvoir trancher entre elles.

À moins de 100 mètres d'une limite, le site prévient que le résultat peut être
faux et affiche la circonscription voisine. Il n'existe pas de contours pour la
Nouvelle-Calédonie, la Polynésie française, Wallis-et-Futuna, Saint-Barthélemy
et Saint-Martin, ni pour les Français de l'étranger : la liste des députés est
alors filtrée sur le territoire.

## Lettre d'information

Le dossier `lettre/` contient un petit service web et une commande d'envoi,
sans dépendance. Un visiteur s'abonne depuis la fiche d'un député, confirme
par e-mail, puis reçoit chaque semaine ou chaque mois l'activité du député de
sa circonscription. Aucune lettre ne part quand il n'y a rien à dire.

- **Période couverte :** une lettre s'arrête deux jours avant son envoi, pour
  laisser à l'Assemblée le temps de publier ses données.
- **Données conservées :** l'adresse e-mail, la circonscription et la
  fréquence, dans une base séparée (`abonnes.sqlite`). Ni nom, ni adresse
  postale, ni adresse IP. Le désabonnement efface la ligne.
- **Liens signés :** les liens de confirmation, de gestion et de
  désabonnement sont signés avec `MD_SECRET` ; aucun mot de passe.
- **Abus :** réponse identique que l'adresse soit abonnée ou non, un seul
  e-mail de confirmation par heure et par adresse, dix demandes par heure et
  par adresse IP, champ piège contre les robots.
- **Formulaire :** il n'apparaît sur les fiches que si le site est généré
  avec `--api` ou la variable `MD_API_URL`. Sur GitHub Pages, il est absent.

Essai en local, les e-mails étant écrits dans un dossier au lieu d'être
envoyés :

```bash
export MD_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export MD_SITE_URL=http://localhost:8000 MD_API_URL=http://localhost:8766
export MD_EXPEDITEUR="Mon député <lettre@exemple.fr>" MD_DOSSIER_COURRIELS=donnees/courriels
python3 -m collecte --api "$MD_API_URL" site
python3 -m lettre servir
```

Puis, dans un autre terminal, `python3 -m lettre envoyer` (ou `--a-blanc`
pour voir ce qui partirait). L'installation sur un serveur est décrite dans
`deploiement/README.md`.

## Limites connues de la source

- **Historique des mandats** : il ne remonte qu'à juin 2002. Le portrait ne
  dit donc jamais qu'un mandat est le premier.

- **Débats en commission** : non publiés en bloc. Seuls les débats en hémicycle
  sont chargés.
- **Présence en hémicycle** : non enregistrée par l'Assemblée. Seuls les
  scrutins publics laissent une trace individuelle, et un vote peut être
  exprimé par délégation.
- **Feuilles de présence en commission** : présentes pour environ la moitié des
  réunions de commission seulement.
- **Organes sans libellé** : environ 70 organes cités par l'agenda (un peu
  moins de 1 000 réunions) ne figurent dans aucun référentiel publié.
- **Amendements sans dispositif** : le contenu des amendements irrecevables
  n'est pas publié, et les amendements de crédits budgétaires ont un format
  propre qui n'est pas repris ici.
- **Orateurs sans fiche** : les prises de parole anonymes (« Un député du
  groupe… ») et celles de personnes extérieures n'ont pas d'identifiant.
- **Serveur** : il coupe les gros transferts et renvoie parfois des en-têtes
  périmés ; le téléchargement reprend automatiquement et vérifie la version.

## Licence des données

Données de l'Assemblée nationale, sous Licence Ouverte / Open Licence (Etalab) :
réutilisation libre avec mention de la source.
Source : https://data.assemblee-nationale.fr
