# Mon député

Collecte quotidienne des données ouvertes de l'Assemblée nationale
(17ᵉ législature) dans une base SQLite, calcul d'indicateurs d'activité et
génération d'un site statique : une fiche par député, une recherche et une page
Méthodologie. Restent à faire : la recherche par adresse, la newsletter et
l'interpellation.

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

Le site est un dossier de fichiers statiques (environ 11 Mo, 655 fiches) qui
peut être servi par n'importe quel hébergement. Les liens vers les scrutins et
les fiches officielles suivent les adresses du site de l'Assemblée
(`/dyn/17/scrutins/<numéro>`, `/dyn/deputes/<identifiant>`).

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
