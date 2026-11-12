"""Tests de la lettre d'information."""

import datetime
import io
import json
import os
import tempfile
import unittest
from email import message_from_bytes, policy

from lettre import abonnes, contenu, courriel
from lettre.__main__ import envoyer
from lettre.application import Application, LIMITE_PAR_IP
from lettre.config import Config, ConfigurationInvalide, depuis_environnement
from tests.test_chargeurs import base_indicateurs

SECRET = b"secret-de-test-0123456789abcdefghijklmnop"
T0 = datetime.datetime(2026, 1, 5, 9, 0, tzinfo=datetime.timezone.utc)


class Abonnes(unittest.TestCase):
    def setUp(self):
        self.db = abonnes.ouvrir(":memory:")

    def tearDown(self):
        self.db.close()

    def test_adresses(self):
        self.assertEqual(abonnes.normaliser("  Ada@Exemple.FR "), "ada@exemple.fr")
        for mauvaise in ("", "ada", "ada@", "a b@exemple.fr", "ada@exemple", "a@b.fr, c@d.fr",
                         "x" * 250 + "@exemple.fr"):
            self.assertIsNone(abonnes.normaliser(mauvaise), mauvaise)

    def test_jetons(self):
        j = abonnes.jeton(SECRET, 42, "gerer")
        self.assertEqual(abonnes.verifier(SECRET, j, "gerer"), 42)
        self.assertIsNone(abonnes.verifier(SECRET, j, "confirmer"))        # autre usage
        self.assertIsNone(abonnes.verifier(b"autre-secret", j, "gerer"))   # autre clé
        self.assertIsNone(abonnes.verifier(SECRET, "43." + j.split(".")[1], "gerer"))
        for faux in ("", "abc", "42", "42.", None):
            self.assertIsNone(abonnes.verifier(SECRET, faux, "gerer"))

    def test_inscription_et_limites(self):
        a, envoi = abonnes.inscrire(self.db, "a@exemple.fr", "10", "2", "mensuelle", T0)
        self.assertEqual((a["statut"], envoi), ("attente", "confirmation"))
        # Nouvelle demande dans l'heure : pas de second e-mail.
        _, envoi = abonnes.inscrire(self.db, "a@exemple.fr", "10", "2", "mensuelle",
                                    T0 + datetime.timedelta(minutes=5))
        self.assertIsNone(envoi)
        # Deux heures plus tard, toujours en attente : on renvoie la confirmation.
        _, envoi = abonnes.inscrire(self.db, "a@exemple.fr", "10", "2", "hebdomadaire",
                                    T0 + datetime.timedelta(hours=2))
        self.assertEqual(envoi, "confirmation")
        abonnes.confirmer(self.db, a["id"], T0)
        # Déjà abonné : on envoie le lien de gestion, sans toucher à la fréquence.
        b, envoi = abonnes.inscrire(self.db, "a@exemple.fr", "10", "2", "mensuelle",
                                    T0 + datetime.timedelta(hours=5))
        self.assertEqual((envoi, b["frequence"], b["statut"]), ("gestion", "hebdomadaire", "actif"))
        # Pas plus de MAX_PAR_ADRESSE circonscriptions pour une même adresse.
        for n in range(3, 3 + abonnes.MAX_PAR_ADRESSE - 1):
            abonnes.inscrire(self.db, "a@exemple.fr", "10", str(n), "mensuelle", T0)
        self.assertEqual(abonnes.inscrire(self.db, "a@exemple.fr", "10", "99", "mensuelle", T0),
                         (None, None))
        with self.assertRaises(ValueError):
            abonnes.inscrire(self.db, "z@exemple.fr", "10", "2", "quotidienne", T0)

    def test_purge_des_inscriptions_non_confirmees(self):
        vieux, _ = abonnes.inscrire(self.db, "vieux@exemple.fr", "10", "2", "mensuelle",
                                    T0 - datetime.timedelta(days=8))
        confirme, _ = abonnes.inscrire(self.db, "ok@exemple.fr", "10", "2", "mensuelle",
                                       T0 - datetime.timedelta(days=30))
        abonnes.confirmer(self.db, confirme["id"])
        abonnes.inscrire(self.db, "recent@exemple.fr", "10", "2", "mensuelle", T0)
        self.assertEqual(abonnes.purger(self.db, T0), 1)
        restants = [l[0] for l in self.db.execute("SELECT email FROM abonnes ORDER BY 1")]
        self.assertEqual(restants, ["ok@exemple.fr", "recent@exemple.fr"])

    def test_lettres_dues(self):
        def actif(email, frequence, dernier=None):
            a, _ = abonnes.inscrire(self.db, email, "10", "2", frequence, T0)
            abonnes.confirmer(self.db, a["id"], T0)
            if dernier:
                abonnes.marquer_envoye(self.db, a["id"], dernier)
        actif("nouveau@exemple.fr", "hebdomadaire")               # première lettre
        actif("hebdo-tot@exemple.fr", "hebdomadaire", "2026-01-01")   # il y a 4 jours
        actif("hebdo-du@exemple.fr", "hebdomadaire", "2025-12-29")    # il y a 7 jours
        actif("mensuel@exemple.fr", "mensuelle", "2025-12-20")        # il y a 16 jours
        actif("ancien@exemple.fr", "mensuelle", "2025-01-01")         # très ancien : plafonné
        abonnes.inscrire(self.db, "attente@exemple.fr", "10", "2", "hebdomadaire", T0)
        dus = {a["email"]: (debut, fin) for a, debut, fin in abonnes.dus(self.db, T0)}
        self.assertEqual(dus, {"nouveau@exemple.fr": ("2025-12-29", "2026-01-05"),
                               "hebdo-du@exemple.fr": ("2025-12-29", "2026-01-05"),
                               "ancien@exemple.fr": ("2025-11-06", "2026-01-05")})


class Lettre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base_indicateurs(self.tmp.name).close()
        self.config = Config(
            secret=SECRET, site_url="https://site.exemple/mon-depute",
            api_url="https://api.exemple", donnees=os.path.join(self.tmp.name, "i.sqlite"),
            abonnes=os.path.join(self.tmp.name, "abonnes.sqlite"),
            expediteur="Mon député <lettre@exemple.fr>",
            dossier_courriels=os.path.join(self.tmp.name, "courriels"))
        self.app = Application(self.config, horloge=lambda: 1000.0)

    def tearDown(self):
        self.tmp.cleanup()

    # ---------------------------------------------------------- utilitaires

    def appeler(self, methode, chemin, corps=None, requete="", ip="1.2.3.4", json_=True):
        donnees = b""
        if corps is not None:
            donnees = (json.dumps(corps) if json_ else corps).encode()
        environ = {"REQUEST_METHOD": methode, "PATH_INFO": chemin, "QUERY_STRING": requete,
                   "CONTENT_LENGTH": str(len(donnees)), "wsgi.input": io.BytesIO(donnees),
                   "CONTENT_TYPE": "application/json" if json_ else
                   "application/x-www-form-urlencoded", "REMOTE_ADDR": ip}
        recu = {}
        corps_reponse = b"".join(self.app(environ, lambda s, e: recu.update(statut=s, entetes=e)))
        return recu["statut"], dict(recu["entetes"]), corps_reponse.decode()

    def demande(self, ip="1.2.3.4", **champs):
        base = {"email": "ada@exemple.fr", "frequence": "hebdomadaire", "consentement": "1",
                "departement": "10", "circo": "2"}
        return self.appeler("POST", "/api/abonnement", {**base, **champs}, ip=ip)

    def courriels(self):
        dossier = self.config.dossier_courriels
        if not os.path.isdir(dossier):
            return []
        messages = []
        for nom in sorted(os.listdir(dossier)):
            with open(os.path.join(dossier, nom), "rb") as f:
                messages.append(message_from_bytes(f.read(), policy=policy.default))
        return messages

    def lignes(self):
        db = abonnes.ouvrir(self.config.abonnes)
        try:
            return [dict(l) for l in db.execute("SELECT * FROM abonnes")]
        finally:
            db.close()

    # ---------------------------------------------------------------- tests

    def test_parcours_complet(self):
        statut, entetes, corps = self.demande(email=" Ada@Exemple.fr ")
        self.assertEqual(statut, "200 OK")
        self.assertEqual(entetes["Access-Control-Allow-Origin"], "https://site.exemple")
        self.assertEqual(self.lignes()[0]["statut"], "attente")
        message = self.courriels()[0]
        self.assertEqual(message["To"], "ada@exemple.fr")
        texte = message.get_content()
        self.assertIn("2e circonscription, Aube", texte)
        lien = [m for m in texte.split() if "/api/confirmer?jeton=" in m][0]
        statut, _, page = self.appeler("GET", "/api/confirmer", requete=lien.split("?")[1])
        self.assertEqual(statut, "200 OK")
        self.assertIn("Abonnement confirmé", page)
        abonne = self.lignes()[0]
        self.assertEqual(abonne["statut"], "actif")

        jeton = abonnes.jeton(SECRET, abonne["id"], "gerer")
        statut, _, page = self.appeler("POST", "/api/gerer", f"jeton={jeton}&frequence=mensuelle",
                                       json_=False)
        self.assertIn("Fréquence enregistrée", page)
        self.assertEqual(self.lignes()[0]["frequence"], "mensuelle")
        # Ouvrir le lien de désabonnement ne supprime rien : il faut un envoi explicite.
        _, _, page = self.appeler("GET", "/api/desabonnement", requete=f"jeton={jeton}")
        self.assertIn("Confirmer le désabonnement", page)
        self.assertEqual(len(self.lignes()), 1)
        self.appeler("POST", "/api/desabonnement", requete=f"jeton={jeton}")  # un clic (RFC 8058)
        self.assertEqual(self.lignes(), [])
        statut, _, _ = self.appeler("GET", "/api/gerer", requete=f"jeton={jeton}")
        self.assertEqual(statut, "404 Not Found")

    def test_demandes_refusees(self):
        for champs, attendu in [({"email": "pas-une-adresse"}, "valide"),
                                ({"consentement": ""}, "consentement"),
                                ({"frequence": "quotidienne"}, "fréquence"),
                                ({"circo": "99"}, "Circonscription"),
                                ({"circo": "2; DROP TABLE"}, "Circonscription")]:
            statut, _, corps = self.demande(**champs)
            self.assertEqual(statut, "400 Bad Request", champs)
            self.assertIn(attendu, json.loads(corps)["erreur"])
        self.assertEqual(self.lignes(), [])
        self.assertEqual(self.courriels(), [])
        self.assertEqual(self.appeler("GET", "/api/confirmer", requete="jeton=1.faux")[0],
                         "404 Not Found")
        self.assertEqual(self.appeler("POST", "/api/abonnement", "x" * 5000, json_=False)[0],
                         "400 Bad Request")

    def test_reponse_identique_et_champ_piege(self):
        premiere = self.demande()[2]
        self.assertEqual(self.demande()[2], premiere)             # déjà en attente
        self.assertEqual(self.demande(site="http://spam", email="robot@exemple.fr")[2], premiere)
        self.assertEqual(len(self.courriels()), 1)                # un seul e-mail est parti
        self.assertEqual([l["email"] for l in self.lignes()], ["ada@exemple.fr"])

    def test_limite_par_adresse_ip(self):
        for n in range(LIMITE_PAR_IP):
            self.assertEqual(self.demande(email=f"a{n}@exemple.fr")[0], "200 OK")
        self.assertEqual(self.demande(email="trop@exemple.fr")[0], "429 Too Many Requests")
        # Une autre adresse IP n'est pas concernée.
        self.assertEqual(self.demande(email="autre@exemple.fr", ip="5.6.7.8")[0], "200 OK")

    def test_envoi_des_lettres(self):
        db = abonnes.ouvrir(self.config.abonnes)
        for email, circo in [("ada@exemple.fr", "2"), ("vacant@exemple.fr", "7")]:
            a, _ = abonnes.inscrire(db, email, "10", circo, "hebdomadaire", T0)
            abonnes.confirmer(db, a["id"], T0)
        db.close()
        journal = []
        # Semaine du 08/07 au 14/07/2025 : les scrutins S2, S3 et S4 du jeu d'essai.
        instant = datetime.datetime(2025, 7, 15, 8, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(envoyer(self.config, instant=instant, journal=journal.append),
                         (1, 0, 1, 0))
        message = self.courriels()[0]
        self.assertEqual(message["To"], "ada@exemple.fr")
        self.assertIn("du 08/07/2025 au 14/07/2025", message["Subject"])
        # Dans le fichier tel qu'il part : le lien ne doit être ni replié ni encodé.
        dossier = self.config.dossier_courriels
        with open(os.path.join(dossier, sorted(os.listdir(dossier))[0]), encoding="utf-8") as f:
            brut = f.read()
        self.assertRegex(brut, r"List-Unsubscribe: <https://api\.exemple/api/desabonnement"
                               r"\?jeton=\d+\.[0-9a-f]{40}>\r?\n")
        self.assertEqual(message["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        texte = message.get_body(("plain",)).get_content()
        self.assertIn("https://site.exemple/mon-depute/deputes/", texte)
        self.assertIn("scrutins/2", texte)
        self.assertIsNotNone(message.get_body(("html",)))
        # Le même jour, rien ne repart ; une semaine sans activité n'envoie rien non plus.
        self.assertEqual(envoyer(self.config, instant=instant, journal=journal.append)[0], 0)
        plus_tard = instant + datetime.timedelta(days=7)
        self.assertEqual(envoyer(self.config, instant=plus_tard, journal=journal.append),
                         (0, 1, 1, 0))
        self.assertEqual(len(self.courriels()), 1)

    def test_contenu(self):
        import sqlite3
        db = sqlite3.connect(self.config.donnees)
        db.row_factory = sqlite3.Row
        lettre = contenu.composer(db, "10", "2", "2025-07-08", "2025-07-15")
        self.assertFalse(lettre["vide"])
        self.assertEqual((lettre["scrutins"], len(lettre["solennels"])), (3, 2))
        self.assertTrue(contenu.composer(db, "10", "2", "2030-01-01", "2030-01-08")["vide"])
        self.assertIsNone(contenu.composer(db, "10", "7", "2025-07-08", "2025-07-15"))
        sujet, texte, html = contenu.rendre(lettre, "https://s.fr", "https://a/g", "https://a/d")
        self.assertIn("10/07/2025 · Contre · Le texte B (rejeté)", texte)
        self.assertIn("<a href=\"https://a/d\">Vous désabonner</a>", html)
        db.close()

    def test_contenu_detaille(self):
        import sqlite3
        db = sqlite3.connect(self.config.donnees)
        db.row_factory = sqlite3.Row
        # Un vote ordinaire, des amendements sur deux textes, une réunion de commission.
        db.execute("UPDATE votes SET position = 'pour' WHERE scrutin_uid = 'S3'"
                   " AND acteur_uid = 'PA1'")
        db.executemany("INSERT INTO documents (uid, type, titre) VALUES (?, 'PRJL', ?)",
                       [("T1", "projet de loi de finances"), ("T2", "projet de loi santé")])
        db.executemany(
            "INSERT INTO amendements (uid, texte_uid, acteur_uid, type_auteur, date_depot, sort)"
            " VALUES (?,?, 'PA1', 'Député', '2025-07-09', ?)",
            [("A1", "T1", "Adopté"), ("A2", "T1", None), ("A3", "T2", None), ("A4", "TX", None)])
        db.execute("INSERT INTO reunions VALUES ('R1', 'commission', '2025-07-09T09:00:00',"
                   " NULL, 'C1', 'Confirmé', '- audition de la ministre ; ; - examen du texte',"
                   " NULL)")
        db.execute("INSERT INTO presences VALUES ('R1', 'PA1', 'présent')")
        db.execute("INSERT INTO reunions_comptees VALUES ('R1')")
        lettre = contenu.composer(db, "10", "2", "2025-07-08", "2025-07-15")
        _, texte, _ = contenu.rendre(lettre, "https://s.fr", "https://a/g", "https://a/d")
        db.close()
        self.assertIn("SES AUTRES VOTES\nUn vote sur un amendement ou un article :\n"
                      "- 11/07/2025 · Pour · L'amdt 1 (rejeté)\n"
                      "  https://www.assemblee-nationale.fr/dyn/17/scrutins/3", texte)
        self.assertIn("4 amendements déposés comme premier signataire, dont 1 déjà adopté.\n"
                      "- Projet de loi de finances : 2 amendements\n"
                      "- Projet de loi santé : 1 amendement\n"
                      "- Texte non identifié : 1 amendement", texte)
        self.assertIn("Présente à la seule réunion de commission dotée d'une feuille de présence."
                      "\n- 09/07/2025 · Commission des lois · audition de la ministre ; examen"
                      " du texte", texte)

    def test_objet_de_reunion_raccourci(self):
        self.assertEqual(contenu.raccourcir("-Nomination de rapporteurs sur : -la proposition"),
                         "Nomination de rapporteurs sur : la proposition")
        long = contenu.raccourcir("mot " * 100)
        self.assertLessEqual(len(long), contenu.LONGUEUR_OBJET + 1)
        self.assertTrue(long.endswith("mot…"))
        self.assertEqual(contenu.raccourcir(None), "")
        self.assertEqual(contenu.intitule("le texte B (première lecture)."),
                         "Le texte B (première lecture)")


class Configuration(unittest.TestCase):
    ENV = {"MD_SECRET": "x" * 40, "MD_SITE_URL": "https://s.fr/", "MD_API_URL": "https://a.fr/",
           "MD_EXPEDITEUR": "Mon député <l@s.fr>", "MD_DOSSIER_COURRIELS": "/tmp/c"}

    def test_lecture(self):
        cfg = depuis_environnement(self.ENV)
        self.assertEqual((cfg.site_url, cfg.api_url, cfg.origine),
                         ("https://s.fr", "https://a.fr", "https://s.fr"))

    def test_refus(self):
        for cle, valeur in [("MD_SECRET", "court"), ("MD_SITE_URL", ""),
                            ("MD_DOSSIER_COURRIELS", "")]:
            with self.assertRaises(ConfigurationInvalide):
                depuis_environnement({**self.ENV, cle: valeur})


if __name__ == "__main__":
    unittest.main()


class EnvoiSMTP(unittest.TestCase):
    def test_mode_de_chiffrement_selon_le_port(self):
        from unittest import mock
        for port, direct in [(2465, True), (465, True), (587, False), (2587, False)]:
            cfg = Config(secret=SECRET, site_url="https://s.fr", api_url="https://a.fr",
                         donnees="", abonnes="", expediteur="Mon député <l@s.fr>",
                         smtp_hote="smtp.exemple.fr", smtp_port=port,
                         smtp_utilisateur="projet", smtp_mot_de_passe="cle")
            message = courriel.construire(cfg, "ada@exemple.fr", "Sujet", "Texte")
            with mock.patch("smtplib.SMTP_SSL") as chiffre, mock.patch("smtplib.SMTP") as clair:
                courriel.envoyer(cfg, message)
            utilise, autre = (chiffre, clair) if direct else (clair, chiffre)
            autre.assert_not_called()
            serveur = utilise.return_value
            self.assertEqual(utilise.call_args.args[:2], ("smtp.exemple.fr", port))
            self.assertEqual(serveur.starttls.called, not direct, port)
            serveur.login.assert_called_once_with("projet", "cle")
            serveur.send_message.assert_called_once_with(message)
