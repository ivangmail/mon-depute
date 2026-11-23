# Mon député : état du projet au 23/11/2026

Résumé de travail, pour reprendre le projet dans une nouvelle session sans rien
redemander. Il décrit ce qui existe, les décisions prises et pourquoi, la façon
de travailler avec l'éditeur, et ce qui reste à faire.

## Objet

Site non commercial qui dresse le portrait de l'activité de chaque député
(17ᵉ législature) et permet aux citoyens de l'interpeller. Chacun indique sa
circonscription et reçoit une lettre sur son député, chaque semaine ou chaque
mois. Éditeur : Ivan Jouravleff. Nom affiché : « Mon député ».

- Site : https://legislatives-2027.fr (le nom de domaine ne signifie pas que des
  législatives sont prévues en 2027 ; la page « Pourquoi ? » le précise).
- Code : dépôt GitHub `ivangmail/mon-d-put-` (l'éditeur l'appelle `mon-depute` ;
  la constante `DEPOT` du site pointe vers ce nom), branche `main`.
- Python 3.13, bibliothèque standard uniquement, SQLite. Tests : `python3 -m unittest`.

## Façon de travailler avec l'éditeur

- Répondre en français. Vérité et exactitude d'abord : signaler toute incertitude
  (« À VÉRIFIER »), ne rien inventer (sources, chiffres, fonctions), dire ce qui
  n'a pas pu être vérifié. Dates au format JJ/MM/AAAA, montants en euros HT.
- Présenter un plan et poser les questions avant d'exécuter une étape nouvelle ;
  ne rien supprimer sans accord.
- Le développeur, c'est Claude : coder, tester, commiter, pousser sur `main`.
  L'éditeur applique les mises à jour sur le serveur avec les commandes qu'on lui
  donne (il ne les connaît pas par cœur) et rend compte (« c'est fait »).
- Ne jamais demander ni recevoir de secret dans la conversation (clés Scaleway,
  phrase secrète, contenu de `/etc/mon-depute.env`).
- Pas d'IA générative pour les contenus propres à chaque député. Les intitulés en
  langage courant des textes sont proposés par Claude et **validés par l'éditeur**
  avant affichage.
- D'autres IA relisent parfois le travail : vérifier leurs affirmations sur le
  code et les données avant de les suivre.

## Serveur

Scaleway, instance STARDUST1-S, région Varsovie (WAW 2), Debian 13, IP
151.115.78.185, accès `ssh root@151.115.78.185` (clé de l'éditeur). Caddy (HTTPS,
`Cache-Control: no-cache` sur le site), gunicorn pour l'API de la lettre,
utilisateur système `mondepute`, dossiers `/srv/mon-depute/{code,donnees,site}`,
configuration `/etc/mon-depute.env` (variables `MD_*`, voir
`deploiement/mon-depute.env.exemple`).

Tâche quotidienne (`mon-depute-quotidien.timer`, 17:23 UTC) : sauvegarde des
abonnés (copie locale + copie chiffrée dans Scaleway Object Storage, région
Paris), collecte et régénération du site, purge des inscriptions non
confirmées, signalement des textes sans intitulé (e-mail le lundi), envoi des
lettres dues.

Commandes types pour l'éditeur (toujours en blocs séparés) :

```bash
cd /srv/mon-depute/code && runuser -u mondepute -- git pull && systemctl restart mon-depute-lettre.service
```

```bash
runuser -u mondepute -- bash -c 'set -a; . /etc/mon-depute.env; cd /srv/mon-depute/code; python3 -m collecte --donnees /srv/mon-depute/donnees --site /srv/mon-depute/site maj --jeux dossiers --sans-telechargement'
```

(`--jeux reunions` pour recharger l'agenda ; `site` au lieu de `maj …` pour
régénérer le site seul ; un fichier de `deploiement/` modifié doit être recopié
dans `/etc/systemd/system/` puis `systemctl daemon-reload`.)

## Organisation du code

- `collecte/` : téléchargement des données ouvertes de l'Assemblée, chargement
  dans `assemblee.sqlite` (`chargeurs.py`, schéma dans `base.py`), indicateurs
  (`indicateurs.py`), thèmes (`themes.py`, `themes_corrections.csv`), état des
  textes (`etapes.py`), intitulés (`libelles.py`, `libelles_textes.csv`),
  génération du site statique (`site.py`, `fiche.py`, scripts JS).
- `lettre/` : abonnements (`abonnes.py`, base séparée `abonnes.sqlite`), API WSGI
  (`application.py`), contenu (`contenu.py`), mise en page e-mail en tableaux
  (`visuel.py`), envoi SMTP (`courriel.py`), sauvegarde chiffrée
  (`sauvegarde.py`, `stockage.py` : S3 signé SigV4 à la main), commandes
  (`__main__.py`).
- `deploiement/` : guide, Caddyfile, services systemd, exemple de configuration.
- `docs/` : ce résumé et le modèle conceptuel des données (`mcd.md`).

## Règles et décisions (toutes décrites dans la page Méthodologie)

- **Participation** : taux sur les scrutins solennels ; le taux « tous scrutins »
  est bas pour tous et expliqué.
- **Ligne d'un groupe** : position la plus fréquente, seulement si elle dépasse
  **60 %** des voix exprimées du groupe ; sinon le groupe est « partagé ». Même
  règle sur le site et dans la lettre (choix de l'éditeur, différent de Datan).
- **Repères de comparaison** : **médianes** (députés en exercice, puis groupe),
  sur le site comme dans la lettre.
- **Présence en commission** : seulement les réunions confirmées, passées, avec
  au moins un présent.
- **Commission d'un député** : celle où il a siégé le plus de jours sur 90 jours
  (les groupes font des remplacements de 1 à 3 jours).
- **Thèmes** : commission saisie au fond ; affaires économiques réparties par
  mots-clés publiés (logement, agriculture, économie) ; commissions spéciales
  classées à la main (validé par l'éditeur).
- **État d'un texte** : dernière étape datée, décrite sans en déduire la suite ;
  « adopté définitivement » seulement après vote conforme, texte de CMP adopté
  par les deux assemblées ou lecture définitive ; 49.3 = « considéré comme adopté,
  sans vote sur le texte ».
- **Lettre** : périodes fixes (hebdomadaire le mercredi pour la semaine lundi–
  dimanche précédente ; mensuelle le 3 pour le mois précédent) ; rubriques
  L'essentiel, participation, votes contre le groupe, où en sont ces textes, ordre
  du jour des 7 jours suivants avec bouton « Écrire avant le débat », séance,
  commission, amendements, questions ; version visuelle en tableaux HTML, retour
  à la version simple au-delà de 90 Ko.
- **Résumé « En bref »** (3 lignes, règles fixes, sans IA) en tête de lettre ;
  **thèmes mis en avant** au choix de l'abonné (page de gestion) : les textes de
  ces thèmes passent en premier, rien n'est retiré ; **point du lundi** envoyé à
  l'éditeur (abonnements de la semaine, intitulés à décider).
- **Accueil** : adresse d'abord, réassurance (données officielles, sans compte,
  sans cookie), parcours en 3 étapes, résultat avec « Voir son activité » et
  « Recevoir sa lettre » (formulaire de la fiche), liste des députés repliée
  (affichée sans JavaScript). Exemple de lettre réelle publié si
  `MD_EXEMPLE_LETTRE` est renseigné (circonscription choisie par l'éditeur).
- **Ordre du jour** : seuls les points confirmés de séances confirmées (le résumé
  publié par l'Assemblée garde les points supprimés).

## Points ouverts

- Rendu réel de la lettre visuelle dans Gmail, Outlook, mode sombre et téléphone :
  jamais vérifié ; attendre la capture de l'éditeur après l'envoi du 25/11/2026.
- Liens vers les pages externes de la page « Pourquoi ? » : à cliquer par
  l'éditeur (domaines non accessibles depuis la session).
- Intitulés : à proposer chaque semaine pour les nouveaux textes, sur demande de
  l'éditeur (« propose les libellés des nouveaux textes »).
- Fiche du site : maquette visuelle de l'éditeur (hémicycle SVG, bloc
  « Comprendre », votes par thème) pas encore réalisée ; parcours d'un texte à
  dessiner sans étapes futures.
- Cas à vérifier : texte sur les réseaux sociaux et les mineurs, promulgué après
  une décision « non conforme » du Conseil constitutionnel.
- Licence du code : décision de l'éditeur attendue.
- Étape 5b (questions publiques modérées) et 5c (réponse du député) : en attente
  d'un avis juridique. Étape 6 (débats en commission) : pas commencée.
