"""Service web de la lettre : abonnement, confirmation, gestion, désabonnement.

Application WSGI sans dépendance. Elle ne stocke aucune adresse IP : la
limitation de débit se fait en mémoire, et s'efface au redémarrage.
"""

import json
import sqlite3
import sys
import time
from html import escape
from urllib.parse import parse_qs

from . import abonnes, courriel, envoi
from collecte.portrait import ordinal

TAILLE_MAX = 4096
LIMITE_PAR_IP = 10        # demandes d'abonnement par heure et par adresse IP
REPONSE_NEUTRE = ("Si cette adresse est valide, un e-mail vient de lui être envoyé. "
                  "Cliquez sur le lien qu'il contient pour confirmer votre abonnement.")
LIBELLES = {"hebdomadaire": "chaque semaine", "mensuelle": "chaque mois"}


class Application:
    def __init__(self, config, horloge=time.time):
        self.config = config
        self.horloge = horloge
        self.demandes = {}  # adresse IP -> instants des dernières demandes

    # ------------------------------------------------------------- outils

    def _abonnes(self):
        return abonnes.ouvrir(self.config.abonnes)

    def _circonscription(self, departement, circo):
        """Renvoie (département, numéro, nom du département) si la circonscription existe."""
        if not str(circo).isdigit():
            return None
        db = sqlite3.connect(f"file:{self.config.donnees}?mode=ro", uri=True)
        try:
            ligne = db.execute(
                "SELECT num_departement, departement FROM deputes"
                " WHERE num_departement = ? AND CAST(num_circo AS INTEGER) = ? LIMIT 1",
                (departement, int(circo))).fetchone()
        finally:
            db.close()
        return (ligne[0], str(int(circo)), ligne[1]) if ligne else None

    def _trop_de_demandes(self, ip):
        instant = self.horloge()
        recentes = [t for t in self.demandes.get(ip, []) if instant - t < 3600]
        if len(recentes) >= LIMITE_PAR_IP:
            self.demandes[ip] = recentes
            return True
        self.demandes[ip] = recentes + [instant]
        if len(self.demandes) > 10000:  # garde-fou mémoire
            self.demandes = {k: v for k, v in self.demandes.items() if v and instant - v[-1] < 3600}
        return False

    def _ip(self, environ):
        if self.config.derriere_proxy and environ.get("HTTP_X_FORWARDED_FOR"):
            return environ["HTTP_X_FORWARDED_FOR"].split(",")[-1].strip()
        return environ.get("REMOTE_ADDR", "")

    def _lien(self, chemin, identifiant, usage):
        return (f"{self.config.api_url}{chemin}?jeton="
                f"{abonnes.jeton(self.config.secret, identifiant, usage)}")

    def liens(self, identifiant):
        return {"confirmer": self._lien("/api/confirmer", identifiant, "confirmer"),
                "gerer": self._lien("/api/gerer", identifiant, "gerer"),
                "desabonner": self._lien("/api/desabonnement", identifiant, "gerer")}

    def _page(self, titre, corps, statut="200 OK"):
        html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{escape(titre)}</title>
<link rel="stylesheet" href="{escape(self.config.site_url)}/style.css"></head><body>
<nav class="barre"><div><a class="marque" href="{escape(self.config.site_url)}/index.html">Mon député</a></div></nav>
<main><h1>{escape(titre)}</h1>{corps}
<p><a href="{escape(self.config.site_url)}/index.html">Retour au site</a></p></main></body></html>"""
        return statut, [("Content-Type", "text/html; charset=utf-8"),
                        ("Cache-Control", "no-store"), ("Referrer-Policy", "no-referrer")], html

    def _json(self, donnees, statut="200 OK"):
        return statut, [("Content-Type", "application/json; charset=utf-8"),
                        ("Cache-Control", "no-store")], json.dumps(donnees, ensure_ascii=False)

    def _invalide(self):
        return self._page("Lien invalide", "<p>Ce lien n'est pas valide ou l'abonnement "
                          "n'existe plus. Vous pouvez vous réabonner depuis la fiche de votre "
                          "député.</p>", "404 Not Found")

    # ------------------------------------------------------------- routes

    def abonnement(self, champs, ip):
        if champs.get("site"):  # champ piège, invisible pour un humain
            return self._json({"message": REPONSE_NEUTRE})
        email = abonnes.normaliser(champs.get("email"))
        if not email:
            return self._json({"erreur": "Cette adresse e-mail ne semble pas valide."},
                              "400 Bad Request")
        if champs.get("frequence") not in abonnes.FREQUENCES:
            return self._json({"erreur": "Choisissez une fréquence."}, "400 Bad Request")
        if champs.get("consentement") not in ("1", "on", "true", True):
            return self._json({"erreur": "Cochez la case de consentement pour vous abonner."},
                              "400 Bad Request")
        circo = self._circonscription(champs.get("departement", ""), champs.get("circo", ""))
        if not circo:
            return self._json({"erreur": "Circonscription inconnue."}, "400 Bad Request")
        if self._trop_de_demandes(ip):
            return self._json({"erreur": "Trop de demandes. Réessayez dans une heure."},
                              "429 Too Many Requests")
        db = self._abonnes()
        try:
            abonne, envoi = abonnes.inscrire(db, email, circo[0], circo[1], champs["frequence"])
        finally:
            db.close()
        try:
            self._courriel_abonnement(abonne, envoi, email, circo)
        except Exception as erreur:  # panne du prestataire d'envoi, identifiants refusés…
            # L'erreur va dans le journal du service, sans l'adresse de la personne.
            print(f"Envoi impossible : {type(erreur).__name__} : {erreur}",
                  file=sys.stderr, flush=True)
            db = self._abonnes()
            try:
                abonnes.annuler_courriel(db, abonne["id"])
            finally:
                db.close()
            return self._json({"erreur": "L'envoi des e-mails est momentanément indisponible. "
                                         "Votre demande n'a pas été enregistrée : réessayez "
                                         "plus tard."}, "503 Service Unavailable")
        return self._json({"message": REPONSE_NEUTRE})

    def _courriel_abonnement(self, abonne, envoi, email, circo):
        if envoi:
            liens = self.liens(abonne["id"])
            lieu = f"{ordinal(circo[1], feminin=True)} circonscription, {circo[2]}"
            if envoi == "confirmation":
                sujet = "Confirmez votre abonnement à Mon député"
                texte = (f"Bonjour,\n\nVous avez demandé à recevoir {LIBELLES[abonne['frequence']]} "
                         f"l'activité du député de la {lieu}.\n\n"
                         f"Pour confirmer, ouvrez ce lien :\n{liens['confirmer']}\n\n"
                         "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : "
                         "sans confirmation, votre adresse sera effacée sous "
                         f"{abonnes.DELAI_CONFIRMATION} jours.\n")
            else:
                sujet = "Votre abonnement à Mon député"
                texte = (f"Bonjour,\n\nVous êtes déjà abonné à l'activité du député de la {lieu}.\n\n"
                         f"Pour changer la fréquence ou vous désabonner :\n{liens['gerer']}\n")
            courriel.envoyer(self.config, courriel.construire(self.config, email, sujet, texte))

    def confirmer(self, jeton):
        identifiant = abonnes.verifier(self.config.secret, jeton, "confirmer")
        db = self._abonnes()
        try:
            avant = abonnes.lire(db, identifiant) if identifiant is not None else None
            if avant is None:
                return self._invalide()
            abonne = abonnes.confirmer(db, identifiant)
            # La première lettre part à la confirmation, une seule fois : rouvrir
            # le lien ne renvoie rien.
            premiere = self._premiere_lettre(db, abonne) if avant["statut"] == "attente" else None
        finally:
            db.close()
        suite = {
            "envoyee": "Votre première lettre vient de partir : regardez votre boîte de réception.",
            "vide": "Aucune activité n'a été enregistrée pour votre député ces derniers jours : "
                    "votre première lettre partira dès qu'il y en aura.",
            "vacant": "Le siège de votre circonscription est actuellement vacant : vous "
                      "recevrez une lettre quand un député y siégera.",
        }.get(premiere, "")
        return self._page("Abonnement confirmé", (
            f"<p>Vous recevrez {LIBELLES[abonne['frequence']]} l'activité de votre député, "
            "quand il y en a. Chaque lettre contient un lien pour changer la fréquence ou "
            "vous désabonner.</p>" + (f"<p>{escape(suite)}</p>" if suite else "")))

    def _premiere_lettre(self, db, abonne):
        """Envoie la première lettre. Une panne ici ne doit pas faire échouer la
        confirmation : la lettre partira alors avec l'envoi quotidien."""
        donnees = None
        try:
            donnees = sqlite3.connect(f"file:{self.config.donnees}?mode=ro", uri=True)
            donnees.row_factory = sqlite3.Row
            debut, fin = abonnes.premiere_periode(abonne["frequence"])
            return envoi.envoyer_lettre(self.config, self.liens(abonne["id"]), donnees, db,
                                        abonne, debut, fin)[0]
        except Exception as erreur:
            print(f"Première lettre non envoyée : {type(erreur).__name__} : {erreur}",
                  file=sys.stderr, flush=True)
            return None
        finally:
            if donnees is not None:
                donnees.close()

    def gerer(self, jeton, champs=None):
        identifiant = abonnes.verifier(self.config.secret, jeton, "gerer")
        db = self._abonnes()
        try:
            abonne = abonnes.lire(db, identifiant) if identifiant is not None else None
            if abonne is None:
                return self._invalide()
            message = ""
            if champs is not None:
                if champs.get("frequence") not in abonnes.FREQUENCES:
                    return self._page("Fréquence inconnue", "", "400 Bad Request")
                abonnes.modifier(db, identifiant, champs["frequence"])
                abonne = abonnes.lire(db, identifiant)
                message = '<p class="alerte">Fréquence enregistrée.</p>'
        finally:
            db.close()
        choix = "".join(
            f'<p><label><input type="radio" name="frequence" value="{f}"'
            f'{" checked" if abonne["frequence"] == f else ""}> {escape(LIBELLES[f].capitalize())}'
            "</label></p>" for f in abonnes.FREQUENCES)
        j = escape(jeton)
        return self._page("Votre abonnement", f"""{message}
<p>Adresse : {escape(abonne['email'])}<br>Circonscription :
 {escape(ordinal(abonne['num_circo'], feminin=True))} du département {escape(abonne['num_departement'])}</p>
<form method="post" action="{escape(self.config.api_url)}/api/gerer">
<input type="hidden" name="jeton" value="{j}">{choix}
<p><button type="submit">Enregistrer la fréquence</button></p></form>
<form method="post" action="{escape(self.config.api_url)}/api/desabonnement">
<input type="hidden" name="jeton" value="{j}">
<p><button type="submit">Me désabonner et effacer mon adresse</button></p></form>""")

    def desabonnement(self, jeton, executer):
        identifiant = abonnes.verifier(self.config.secret, jeton, "gerer")
        if identifiant is None:
            return self._invalide()
        if not executer:
            # Les messageries ouvrent parfois les liens toutes seules : on demande
            # donc un clic avant d'effacer quoi que ce soit.
            return self._page("Vous désabonner", f"""
<form method="post" action="{escape(self.config.api_url)}/api/desabonnement">
<input type="hidden" name="jeton" value="{escape(jeton)}">
<p><button type="submit">Confirmer le désabonnement</button></p></form>""")
        db = self._abonnes()
        try:
            abonnes.supprimer(db, identifiant)
        finally:
            db.close()
        return self._page("Désabonnement enregistré",
                          "<p>Votre adresse a été effacée. Vous ne recevrez plus de lettre.</p>")

    # --------------------------------------------------------------- WSGI

    def __call__(self, environ, repondre):
        methode, chemin = environ["REQUEST_METHOD"], environ.get("PATH_INFO", "")
        requete = {k: v[0] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}
        cors = [("Access-Control-Allow-Origin", self.config.origine), ("Vary", "Origin"),
                ("Access-Control-Allow-Methods", "POST, OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type")]
        try:
            if methode == "OPTIONS":
                statut, entetes, corps = "204 No Content", [], ""
            elif (methode, chemin) == ("GET", "/api/sante"):
                statut, entetes, corps = self._json({"etat": "ok"})
            elif (methode, chemin) == ("POST", "/api/abonnement"):
                statut, entetes, corps = self.abonnement(self._champs(environ), self._ip(environ))
            elif (methode, chemin) == ("GET", "/api/confirmer"):
                statut, entetes, corps = self.confirmer(requete.get("jeton", ""))
            elif (methode, chemin) == ("GET", "/api/gerer"):
                statut, entetes, corps = self.gerer(requete.get("jeton", ""))
            elif (methode, chemin) == ("POST", "/api/gerer"):
                champs = self._champs(environ)
                statut, entetes, corps = self.gerer(champs.get("jeton", ""), champs)
            elif chemin == "/api/desabonnement" and methode in ("GET", "POST"):
                champs = self._champs(environ) if methode == "POST" else {}
                statut, entetes, corps = self.desabonnement(
                    champs.get("jeton") or requete.get("jeton", ""), methode == "POST")
            else:
                statut, entetes, corps = self._json({"erreur": "Introuvable."}, "404 Not Found")
        except DemandeInvalide as erreur:
            statut, entetes, corps = self._json({"erreur": str(erreur)}, "400 Bad Request")
        donnees = corps.encode("utf-8")
        repondre(statut, entetes + cors + [("Content-Length", str(len(donnees))),
                                           ("X-Content-Type-Options", "nosniff")])
        return [donnees]

    def _champs(self, environ):
        try:
            taille = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            raise DemandeInvalide("Demande illisible.")
        if taille > TAILLE_MAX:
            raise DemandeInvalide("Demande trop volumineuse.")
        brut = environ["wsgi.input"].read(taille).decode("utf-8", "replace")
        if environ.get("CONTENT_TYPE", "").startswith("application/json"):
            try:
                donnees = json.loads(brut or "{}")
            except ValueError:
                raise DemandeInvalide("Demande illisible.")
            if not isinstance(donnees, dict):
                raise DemandeInvalide("Demande illisible.")
            return donnees
        return {k: v[0] for k, v in parse_qs(brut).items()}


class DemandeInvalide(Exception):
    pass
