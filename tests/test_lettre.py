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
        # Envoi le 05/01/2026 : la période s'arrête deux jours plus tôt, au 03/01 exclu.
        actif("nouveau@exemple.fr", "hebdomadaire")               # première lettre
        actif("hebdo-tot@exemple.fr", "hebdomadaire", "2025-12-30")   # 4 jours couverts
        actif("hebdo-du@exemple.fr", "hebdomadaire", "2025-12-27")    # 7 jours couverts
        actif("mensuel@exemple.fr", "mensuelle", "2025-12-20")        # 14 jours couverts
        actif("ancien@exemple.fr", "mensuelle", "2025-01-01")         # très ancien : plafonné
        abonnes.inscrire(self.db, "attente@exemple.fr", "10", "2", "hebdomadaire", T0)
        dus = {a["email"]: (debut, fin) for a, debut, fin in abonnes.dus(self.db, T0)}
        self.assertEqual(dus, {"nouveau@exemple.fr": ("2025-12-27", "2026-01-03"),
                               "hebdo-du@exemple.fr": ("2025-12-27", "2026-01-03"),
                               "ancien@exemple.fr": ("2025-11-04", "2026-01-03")})


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

    def test_premiere_lettre_a_la_confirmation(self):
        from unittest import mock
        # Confirmation le 17/07/2025 : la première lettre couvre du 08/07 au 14/07.
        jour_j = datetime.datetime(2025, 7, 17, 8, 0, tzinfo=datetime.timezone.utc)
        self.demande()
        lien = [m for m in self.courriels()[0].get_content().split()
                if "/api/confirmer?jeton=" in m][0].split("?")[1]
        with mock.patch("lettre.abonnes.maintenant", return_value=jour_j):
            _, _, page = self.appeler("GET", "/api/confirmer", requete=lien)
            self.assertIn("première lettre vient de partir", page)
            messages = self.courriels()
            self.assertEqual(len(messages), 2)
            self.assertIn("du 08/07/2025 au 14/07/2025", messages[1]["Subject"])
            self.assertEqual(self.lignes()[0]["dernier_envoi"], "2025-07-15")
            # Rouvrir le lien ne renvoie pas la lettre, et l'envoi quotidien non plus.
            _, _, page = self.appeler("GET", "/api/confirmer", requete=lien)
            self.assertNotIn("vient de partir", page)
            self.assertEqual(envoyer(self.config, instant=jour_j, journal=lambda m: None)[0], 0)
            self.assertEqual(len(self.courriels()), 2)

    def test_confirmation_sans_activite_ou_envoi_en_panne(self):
        from unittest import mock
        self.demande()
        lien = [m for m in self.courriels()[0].get_content().split()
                if "/api/confirmer?jeton=" in m][0].split("?")[1]
        # Aujourd'hui, le jeu d'essai (2025) n'a aucune activité récente.
        statut, _, page = self.appeler("GET", "/api/confirmer", requete=lien)
        self.assertEqual(statut, "200 OK")
        self.assertIn("votre première lettre partira", page)
        self.assertIsNone(self.lignes()[0]["dernier_envoi"])
        # Une panne d'envoi ne fait pas échouer la confirmation.
        self.demande(email="autre@exemple.fr")
        lien = [m for m in self.courriels()[-1].get_content().split()
                if "/api/confirmer?jeton=" in m][0].split("?")[1]
        jour_j = datetime.datetime(2025, 7, 17, 8, 0, tzinfo=datetime.timezone.utc)
        with mock.patch("lettre.abonnes.maintenant", return_value=jour_j), \
                mock.patch("lettre.courriel.envoyer", side_effect=OSError("refusé")), \
                mock.patch("sys.stderr"):
            statut, _, page = self.appeler("GET", "/api/confirmer", requete=lien)
        self.assertEqual(statut, "200 OK")
        self.assertIn("Abonnement confirmé", page)
        autre = [l for l in self.lignes() if l["email"] == "autre@exemple.fr"][0]
        self.assertEqual((autre["statut"], autre["dernier_envoi"]), ("actif", None))

    def test_sauvegarde(self):
        import gzip
        import sqlite3
        self.demande()
        dossier = os.path.join(self.tmp.name, "sauvegardes")
        chemins = [abonnes.sauvegarder(self.config.abonnes, dossier, conserver=2,
                                       instant=T0 + datetime.timedelta(days=n)) for n in range(4)]
        self.assertEqual(sorted(os.listdir(dossier)),
                         ["abonnes-20260107-090000.sqlite.gz", "abonnes-20260108-090000.sqlite.gz"])
        copie = os.path.join(self.tmp.name, "restaure.sqlite")
        with gzip.open(chemins[-1], "rb") as source, open(copie, "wb") as cible:
            cible.write(source.read())
        db = sqlite3.connect(copie)
        self.assertEqual(db.execute("SELECT email FROM abonnes").fetchall(), [("ada@exemple.fr",)])
        db.close()
        self.assertEqual(os.stat(chemins[-1]).st_mode & 0o777, 0o600)

    def test_envoi_en_panne(self):
        from unittest import mock
        with mock.patch("lettre.courriel.envoyer", side_effect=OSError("refusé")), \
                mock.patch("sys.stderr"):
            statut, _, corps = self.demande()
        self.assertEqual(statut, "503 Service Unavailable")
        self.assertIn("momentanément indisponible", json.loads(corps)["erreur"])
        self.assertEqual(self.lignes(), [])   # rien n'est gardé : la personne peut réessayer
        self.assertEqual(self.demande()[0], "200 OK")
        self.assertEqual(len(self.courriels()), 1)
        # Pour une personne déjà abonnée, la panne ne supprime pas l'abonnement.
        db = abonnes.ouvrir(self.config.abonnes)
        identifiant = self.lignes()[0]["id"]
        abonnes.confirmer(db, identifiant)
        db.execute("UPDATE abonnes SET dernier_courriel_le = NULL")
        db.commit()
        db.close()
        with mock.patch("lettre.courriel.envoyer", side_effect=OSError("refusé")), \
                mock.patch("sys.stderr"):
            self.assertEqual(self.demande()[0], "503 Service Unavailable")
        self.assertEqual([(l["statut"], l["dernier_courriel_le"]) for l in self.lignes()],
                         [("actif", None)])

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
        # Envoi le 17/07/2025, donc semaine du 08/07 au 14/07 : scrutins S2, S3 et S4.
        instant = datetime.datetime(2025, 7, 17, 8, 0, tzinfo=datetime.timezone.utc)
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
        self.assertEqual((lettre["scrutins"], len(lettre["majeurs"])), (3, 2))
        self.assertTrue(contenu.composer(db, "10", "2", "2030-01-01", "2030-01-08")["vide"])
        self.assertIsNone(contenu.composer(db, "10", "7", "2025-07-08", "2025-07-15"))
        sujet, texte, html = contenu.rendre(lettre, "https://s.fr", "https://a/g", "https://a/d")
        self.assertIn("10/07/2025 · Contre · Le texte B (rejeté) · son groupe : contre "
                      "(1 pour, 2 contre)", texte)
        # À égalité dans le groupe, aucune ligne n'est affichée.
        self.assertIn("Le texte C (adopté) · son groupe était partagé (1 pour, 1 contre)", texte)
        self.assertIn("Elle a pris part à 2 des 3 scrutins publics de la période (médiane du "
                      "groupe UN : 2 ; médiane de l'Assemblée : 1,5).", texte)
        self.assertNotIn("Signalez-la", texte)
        self.assertIn("<a href=\"https://a/d\">Vous désabonner</a>", html)
        # Seul l'intitulé du scrutin est cliquable, pas la ligne entière.
        self.assertIn('<li>10/07/2025 · Contre · <a href="https://www.assemblee-nationale.fr'
                      '/dyn/17/scrutins/2">Le texte B</a> (rejeté) · son groupe : contre '
                      '(1 pour, 2 contre)</li>', html)
        self.assertNotIn(contenu.MARQUE, texte + html + sujet)
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
        self.assertIn("Amendements et articles, texte par texte :\n"
                      "- Textes non identifiés : 1 pour", texte)
        self.assertIn("4 amendements déposés comme premier signataire, dont 1 déjà adopté.\n"
                      "- Projet de loi de finances : 2 amendements (1 adopté, 1 sans sort connu"
                      " à ce jour)\n"
                      "- Projet de loi santé : 1 amendement (1 sans sort connu à ce jour)\n"
                      "- Texte non identifié : 1 amendement (1 sans sort connu à ce jour)", texte)
        self.assertIn("Présente à la seule réunion de commission dotée d'une feuille de présence."
                      "\n- 09/07/2025 · Commission des lois · audition de la ministre ; examen"
                      " du texte", texte)

    def test_essentiel_absences_et_extraits(self):
        import sqlite3
        db = sqlite3.connect(self.config.donnees)
        db.row_factory = sqlite3.Row
        # S2 devient un vote serré où Ada est absente ; une motion de censure et un
        # scrutin sur un texte entier s'ajoutent ; S3 est rattaché à un dossier.
        db.execute("DELETE FROM votes WHERE scrutin_uid = 'S2' AND acteur_uid = 'PA1'")
        db.execute("UPDATE scrutins SET nb_pour = 100, nb_contre = 104 WHERE uid = 'S2'")
        db.execute("INSERT INTO dossiers (uid, titre) VALUES ('D1', 'projet de loi eau')")
        db.execute("UPDATE scrutins SET dossier_uid = 'D1', nb_pour = 5, nb_contre = 90"
                   " WHERE uid = 'S3'")
        db.executemany(
            "INSERT INTO scrutins (uid, numero, date, type_vote, sort, titre, dossier_uid,"
            " nb_pour, nb_contre) VALUES (?,?,?,?,?,?,?,?,?)",
            [("S5", 5, "2025-07-11", "motion de censure", "rejeté", "la motion de censure",
              None, 200, 0),
             ("S6", 6, "2025-07-11", "scrutin public ordinaire", "adopté",
              "l’ensemble de la proposition de loi eau", "D1", 60, 20),
             ("S7", 7, "2025-07-11", "scrutin public ordinaire", "rejeté", "l'amdt 2", "D1",
              40, 45)])
        db.execute("INSERT INTO votes VALUES ('S6', 'PA1', 'G1', 'pour', 0)")
        db.execute("INSERT INTO documents (uid, type, titre) VALUES ('T1', 'PRJL', 'texte eau')")
        db.executemany(
            "INSERT INTO amendements (uid, numero, texte_uid, acteur_uid, type_auteur,"
            " date_depot, sort, etat, expose) VALUES (?,?, 'T1', 'PA1', 'Député',"
            " '2025-07-09', ?,?,?)",
            [("A1", "12", "Rejeté", "Discuté", "Cet amendement vise à protéger l'eau."),
             ("A2", "13", "Rejeté", "Discuté", "Cet amendement vise à protéger l'eau."),
             ("A3", "14", None, "Irrecevable 40", None)])
        db.execute("INSERT INTO comptes_rendus (uid, date) VALUES ('CR1', '2025-07-09')")
        db.executemany(
            "INSERT INTO interventions (compte_rendu_uid, acteur_uid, code_grammaire, sujet,"
            " nb_mots, texte) VALUES ('CR1', 'PA1', ?, 'Eau', ?, ?)",
            [("INTERRUPTION_1_10", 400, "Une interruption."),
             ("PAROLE_GENERIQUE", 150, "Madame la présidente, l'eau manque."),
             ("PAROLE_GENERIQUE", 30, "Une remarque courte.")])
        lettre = contenu.composer(db, "10", "2", "2025-07-08", "2025-07-15")
        _, texte, html = contenu.rendre(lettre, "https://s.fr", "https://a/g", "https://a/d",
                                        contact="contact@exemple.fr")
        db.close()
        self.assertIn("10/07/2025 · N'a pas pris part au vote · Le texte B (rejeté, à 4 voix "
                      "près) · son groupe était partagé (1 pour, 1 contre)", texte)
        self.assertIn(contenu.ABSENCE, texte)
        self.assertIn("11/07/2025 · N'a pas voté la censure · La motion de censure (rejeté)\n",
                      texte)
        self.assertIn("Pour une motion de censure, seuls les votes pour sont recensés.", texte)
        self.assertIn("11/07/2025 · Pour · L’ensemble de la proposition de loi eau (adopté)"
                      " · son groupe : pour (1 pour)", texte)
        # S2 et S7 sont serrés ; la motion de censure n'entre pas dans ce décompte.
        self.assertIn("2 scrutins se sont joués à 10 voix ou moins : elle a pris part à 0 "
                      "d'entre eux.", texte)
        # Le vote sur le texte entier n'est pas recompté dans le détail par texte.
        self.assertIn("- Projet de loi eau : 2 scrutins sans participation", texte)
        self.assertIn("- Texte eau : 3 amendements (2 rejetés, 1 irrecevable)\n"
                      "- Amendement n° 12 (rejeté), selon l'exposé de son auteur : « Cet "
                      "amendement vise à protéger l'eau. »\n\n", texte)
        self.assertIn("Sa plus longue prise de parole (09/07/2025, 150 mots, sur « Eau »), "
                      "début : « Madame la présidente, l'eau manque. »", texte)
        self.assertIn("Une erreur dans cette lettre ? Signalez-la : contact@exemple.fr", texte)
        self.assertIn('<a href="mailto:contact@exemple.fr">Signalez-la</a>', html)

    def test_position_du_groupe(self):
        self.assertEqual(contenu.position_du_groupe({"pour": 7, "contre": 3}),
                         ("pour", "son groupe : pour (7 pour, 3 contre)"))
        # 60 % tout juste ne suffit pas : il faut dépasser le seuil.
        self.assertEqual(contenu.position_du_groupe({"pour": 6, "contre": 4}),
                         (None, "son groupe était partagé (6 pour, 4 contre)"))
        self.assertEqual(contenu.position_du_groupe({}), (None, ""))
        self.assertEqual(contenu.sort_amendement(None, "Irrecevable 40"), "irrecevable")
        self.assertEqual(contenu.sort_amendement(None, "A discuter"), "sans sort connu à ce jour")
        self.assertEqual(contenu._accorder(2, "non soutenu"), "2 non soutenus")

    def test_votes_regroupes_par_texte(self):
        votes = ([{"dossier_uid": "D1", "texte": "projet de loi de finances", "position": p}
                  for p in ("pour", "contre", "contre", "abstention", "abstention")]
                 + [{"dossier_uid": "D2", "texte": "Proposition de loi santé", "position": "pour"},
                    {"dossier_uid": None, "texte": None, "position": "contre"}])
        groupes = contenu.votes_par_texte(votes)
        self.assertEqual([(g["texte"], g["total"], g["detail"]) for g in groupes], [
            ("Projet de loi de finances", 5, "1 pour, 2 contre, 2 abstentions"),
            ("Proposition de loi santé", 1, "1 pour"),
            ("Textes non identifiés", 1, "1 contre")])
        self.assertEqual(groupes[0]["lien"],
                         "https://www.assemblee-nationale.fr/dyn/17/dossiers/D1")
        self.assertIsNone(groupes[2]["lien"])
        # Avec le nombre de scrutins tenus, les absences entrent dans le décompte.
        groupes = contenu.votes_par_texte(votes[:5], [
            {"dossier_uid": "D1", "texte": "projet de loi de finances", "n": 8},
            {"dossier_uid": "D3", "texte": "projet de loi eau", "n": 1}])
        self.assertEqual([(g["texte"], g["decompte"]) for g in groupes], [
            ("Projet de loi de finances",
             "1 pour, 2 contre, 2 abstentions, 3 scrutins sans participation"),
            ("Projet de loi eau", "1 scrutin sans participation")])

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
