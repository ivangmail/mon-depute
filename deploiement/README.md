# Déploiement sur un serveur

Ces fichiers décrivent l'installation sur un serveur Debian ou Ubuntu : le
site statique, le service de la lettre et la mise à jour quotidienne sur une
même machine, derrière Caddy.

**Ils n'ont pas encore été essayés sur un vrai serveur.** Seul le service
lui-même a été testé, en local, avec gunicorn. À relire et adapter lors de la
première installation.

## Ce qu'il faut avoir

- un serveur, même le plus petit : la mise à jour quotidienne complète a été
  mesurée à 145 Mo de mémoire au maximum, un peu plus de 2 minutes sur 4 cœurs
  et environ 2 Go de disque (1 Go de mémoire et 10 Go de disque suffisent) ;
- un nom de domaine dont l'enregistrement A pointe vers le serveur ;
- un compte chez un prestataire d'envoi d'e-mails, avec le domaine vérifié
  (enregistrements SPF, DKIM et DMARC fournis par le prestataire) et des
  identifiants SMTP.

## Étapes

```bash
sudo apt install python3 gunicorn caddy git
sudo useradd --system --home /srv/mon-depute --create-home mondepute
sudo -u mondepute git clone https://github.com/ivangmail/mon-depute /srv/mon-depute/code
sudo -u mondepute mkdir /srv/mon-depute/donnees /srv/mon-depute/site
```

Configuration, à remplir (secret, domaine, identifiants SMTP) :

```bash
sudo install -m 600 -o mondepute /srv/mon-depute/code/deploiement/mon-depute.env.exemple /etc/mon-depute.env
sudo nano /etc/mon-depute.env
```

Services, depuis `/srv/mon-depute/code`, après avoir mis le nom de domaine
dans `deploiement/Caddyfile` :

```bash
sudo cp deploiement/mon-depute-*.service deploiement/mon-depute-quotidien.timer /etc/systemd/system/
sudo cp deploiement/Caddyfile /etc/caddy/Caddyfile
sudo systemctl daemon-reload
sudo systemctl start mon-depute-quotidien.service
sudo systemctl enable --now mon-depute-lettre.service mon-depute-quotidien.timer
sudo systemctl reload caddy
```

La première collecte prend quelques minutes.

## Vérifier

- `https://<domaine>/` affiche le site, et une fiche de député montre le
  formulaire « Suivre son activité par e-mail » ;
- `https://<domaine>/api/sante` répond `{"etat": "ok"}` ;
- s'abonner avec sa propre adresse, confirmer, relancer
  `sudo systemctl start mon-depute-quotidien.service` et vérifier la réception.

Pour voir ce qui partirait sans rien envoyer :

```bash
sudo -u mondepute bash -c 'set -a; . /etc/mon-depute.env; cd /srv/mon-depute/code; python3 -m lettre envoyer --a-blanc'
```

## Sauvegarde

Le seul fichier à sauvegarder est `/srv/mon-depute/donnees/abonnes.sqlite`,
qui contient des adresses e-mail : la sauvegarde doit être protégée comme
l'original. Tout le reste se reconstruit à partir des données de l'Assemblée.

Une fois le serveur en service, la publication sur GitHub Pages devient
inutile : désactiver la tâche planifiée du dépôt, ou la garder comme miroir
sans formulaire d'abonnement.
