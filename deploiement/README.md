# Déploiement sur un serveur

Ces fichiers décrivent l'installation sur un serveur Debian ou Ubuntu : le
site statique, le service de la lettre et la mise à jour quotidienne sur une
même machine, derrière Caddy.

Ce guide a été déroulé une fois, le 12/11/2026, sur une Instance Scaleway
STARDUST1-S (Debian 13, 1 Go de mémoire), avec le domaine et l'envoi d'e-mails
chez Scaleway : site en HTTPS, abonnement et e-mail de confirmation vérifiés.
Sur un autre hébergeur ou un autre système, des ajustements restent possibles.

## Ce qu'il faut avoir

- un serveur, même le plus petit : la mise à jour quotidienne complète a été
  mesurée à 145 Mo de mémoire au maximum, un peu plus de 2 minutes sur 4 cœurs
  et environ 2 Go de disque (1 Go de mémoire et 10 Go de disque suffisent) ;
- un nom de domaine dont l'enregistrement A pointe vers le serveur ;
- un compte chez un prestataire d'envoi d'e-mails, avec le domaine vérifié
  (enregistrements SPF, DKIM et DMARC fournis par le prestataire) et des
  identifiants SMTP.

## Étapes

Les commandes sont à lancer en tant que `root`.

```bash
apt install -y python3 gunicorn caddy git
useradd --system --home /srv/mon-depute --create-home --shell /usr/sbin/nologin mondepute
runuser -u mondepute -- git clone https://github.com/ivangmail/mon-depute /srv/mon-depute/code
runuser -u mondepute -- mkdir /srv/mon-depute/donnees /srv/mon-depute/site
```

Le serveur web doit pouvoir lire le site, mais pas la base des abonnés :

```bash
chmod 755 /srv/mon-depute
chmod 700 /srv/mon-depute/donnees
```

Configuration, à remplir (secret, domaine, identifiants SMTP) :

```bash
install -m 600 -o mondepute /srv/mon-depute/code/deploiement/mon-depute.env.exemple /etc/mon-depute.env
nano /etc/mon-depute.env
```

Services, depuis `/srv/mon-depute/code`, après avoir mis le nom de domaine
dans `deploiement/Caddyfile` :

```bash
cp deploiement/mon-depute-*.service deploiement/mon-depute-quotidien.timer /etc/systemd/system/
cp deploiement/Caddyfile /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl start mon-depute-quotidien.service
systemctl enable --now mon-depute-lettre.service mon-depute-quotidien.timer
systemctl reload caddy
```

La première collecte prend une dizaine de minutes sur un serveur à un cœur.

La mise à jour quotidienne ne régénère le site que si les données ont changé.
Après une modification de `/etc/mon-depute.env` (adresse du site, par exemple),
le régénérer à la main :

```bash
runuser -u mondepute -- bash -c 'set -a; . /etc/mon-depute.env; cd /srv/mon-depute/code; python3 -m collecte --donnees /srv/mon-depute/donnees --site /srv/mon-depute/site site'
```

## Envoi d'e-mails avec Scaleway Transactional Email

Dans `/etc/mon-depute.env` : hôte `smtp.tem.scaleway.com`, port `2465` (les
ports 25, 465 et 587 sont bloqués par défaut sur les Instances Scaleway),
utilisateur = identifiant du projet, mot de passe = clé secrète d'une clé d'API
autorisée pour Transactional Email. Une erreur `535 Invalid credentials` dans
`journalctl -u mon-depute-lettre.service` signale un identifiant ou une clé
erronés ; la connexion elle-même fonctionne alors.

Tant que le domaine n'est pas prêt, on peut tout essayer sans rien envoyer :
remplacer les variables `MD_SMTP_*` par `MD_DOSSIER_COURRIELS=/srv/mon-depute/donnees/courriels`,
les e-mails y sont écrits sous forme de fichiers.

## Vérifier

- `https://<domaine>/` affiche le site, et une fiche de député montre le
  formulaire « Suivre son activité par e-mail » ;
- `https://<domaine>/api/sante` répond `{"etat": "ok"}` ;
- s'abonner avec sa propre adresse, confirmer, relancer
  `systemctl start mon-depute-quotidien.service` et vérifier la réception.

Pour voir ce qui partirait sans rien envoyer :

```bash
runuser -u mondepute -- bash -c 'set -a; . /etc/mon-depute.env; cd /srv/mon-depute/code; python3 -m lettre envoyer --a-blanc'
```

## Sauvegarde

Le seul fichier à sauvegarder est `/srv/mon-depute/donnees/abonnes.sqlite`,
qui contient des adresses e-mail : la sauvegarde doit être protégée comme
l'original. Tout le reste se reconstruit à partir des données de l'Assemblée.

Une fois le serveur en service, la publication sur GitHub Pages devient
inutile : désactiver la tâche planifiée du dépôt, ou la garder comme miroir
sans formulaire d'abonnement.
