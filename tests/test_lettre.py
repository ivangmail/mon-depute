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
        # Lundi 05/01/2026 : dernière semaine complète terminée depuis deux jours, celle
        # du 22/12 au 28/12/2025 ; dernier mois complet, décembre 2025.
        actif("nouveau@exemple.fr", "hebdomadaire")                    # première lettre
        actif("hebdo-envoye@exemple.fr", "hebdomadaire", "2025-12-29")  # déjà traitée
        actif("hebdo-glissant@exemple.fr", "hebdomadaire", "2025-12-27")  # ancien système
        actif("hebdo-retard@exemple.fr", "hebdomadaire", "2025-12-15")  # envoi manqué
        actif("mensuel@exemple.fr", "mensuelle", "2025-12-20")
        actif("mensuel-envoye@exemple.fr", "mensuelle", "2026-01-01")
        actif("ancien@exemple.fr", "mensuelle", "2025-01-01")          # très ancien : plafonné
        abonnes.inscrire(self.db, "attente@exemple.fr", "10", "2", "hebdomadaire", T0)
        dus = {a["email"]: (debut, fin) for a, debut, fin in abonnes.dus(self.db, T0)}
        self.assertEqual(dus, {
            "nouveau@exemple.fr": ("2025-12-22", "2025-12-29"),
            # La lettre couvre toujours au moins la semaine entière…
            "hebdo-glissant@exemple.fr": ("2025-12-22", "2025-12-29"),
            # … et reprend là où la précédente s'arrêtait, s'il y a un trou.
            "hebdo-retard@exemple.fr": ("2025-12-15", "2025-12-29"),
            "mensuel@exemple.fr": ("2025-12-01", "2026-01-01"),
            "ancien@exemple.fr": ("2025-11-02", "2026-01-01")})

    def test_periodes_fixes(self):
        def le(annee, mois, jour_):
            return datetime.datetime(annee, mois, jour_, 17, 23, tzinfo=datetime.timezone.utc)
        # La semaine du lundi 16 au dimanche 22/11/2026 part le mercredi 25/11.
        self.assertEqual(abonnes.periode("hebdomadaire", le(2026, 11, 25)),
                         ("2026-11-16", "2026-11-23"))
        self.assertEqual(abonnes.periode("hebdomadaire", le(2026, 11, 24)),
                         ("2026-11-09", "2026-11-16"))  # mardi : encore la précédente
        self.assertEqual(abonnes.periode("hebdomadaire", le(2026, 11, 29)),
                         ("2026-11-16", "2026-11-23"))  # dimanche : rien de nouveau
        # Le mois de novembre part le 3 décembre ; passage d'année.
        self.assertEqual(abonnes.periode("mensuelle", le(2026, 12, 3)),
                         ("2026-11-01", "2026-12-01"))
        self.assertEqual(abonnes.periode("mensuelle", le(2026, 12, 2)),
                         ("2026-10-01", "2026-11-01"))
        self.assertEqual(abonnes.periode("mensuelle", le(2027, 1, 3)),
                         ("2026-12-01", "2027-01-01"))


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
        self.assertIn("Préférences enregistrées", page)
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
        # Confirmation le jeudi 17/07/2025 : la première lettre couvre la semaine du 07/07.
        jour_j = datetime.datetime(2025, 7, 17, 8, 0, tzinfo=datetime.timezone.utc)
        self.demande()
        lien = [m for m in self.courriels()[0].get_content().split()
                if "/api/confirmer?jeton=" in m][0].split("?")[1]
        with mock.patch("lettre.abonnes.maintenant", return_value=jour_j):
            _, _, page = self.appeler("GET", "/api/confirmer", requete=lien)
            self.assertIn("première lettre vient de partir", page)
            messages = self.courriels()
            self.assertEqual(len(messages), 2)
            self.assertIn("du 07/07/2025 au 13/07/2025", messages[1]["Subject"])
            self.assertEqual(self.lignes()[0]["dernier_envoi"], "2025-07-14")
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
        self.assertIn("votre première lettre partira avec la prochaine", page)
        # La période sans activité est marquée comme traitée : la lettre suivante
        # couvrira la période fixe suivante, et non deux périodes d'un coup.
        self.assertEqual(self.lignes()[0]["dernier_envoi"], abonnes.periode("hebdomadaire")[1])
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
        # Jeudi 17/07/2025 : semaine du lundi 07/07 au dimanche 13/07 (scrutins S2, S3, S4).
        instant = datetime.datetime(2025, 7, 17, 8, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(envoyer(self.config, instant=instant, journal=journal.append),
                         (1, 0, 1, 0))
        message = self.courriels()[0]
        self.assertEqual(message["To"], "ada@exemple.fr")
        self.assertIn("du 07/07/2025 au 13/07/2025", message["Subject"])
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

    def test_mise_en_avant_ne_retire_rien(self):
        # Régression du 26/11/2026 : les textes des thèmes choisis passaient devant
        # AVANT la coupe à 8 de l'ordre du jour, et d'autres textes disparaissaient.
        import sqlite3
        self.assertEqual(contenu.devant([1, 2, 3, 4, 5], 3, lambda x: x == 3), [3, 1, 2, 4, 5])
        db = sqlite3.connect(self.config.donnees)
        db.row_factory = sqlite3.Row
        lettre = contenu.composer(db, "10", "2", "2025-07-08", "2025-07-15")
        db.close()
        lettre["agenda"] = [{"dossier_uid": f"D{i}", "titre": f"Texte {i}",
                             "date": f"2025-07-{16 + i:02d}", "vote": None,
                             "sa_commission": False} for i in range(12)]
        lettre["themes_agenda"] = {f"D{i}": ("Défense" if i >= 9 else "Budget et fiscalité")
                                   for i in range(12)}
        def agenda(l):
            return [u for t, _, e in contenu.rubriques(l, "https://s")
                    if t.startswith("À l'ordre du jour") for _, u in e if u]
        sans = agenda(lettre)
        avec = agenda(contenu.mettre_en_avant(lettre, ["Défense"]))
        self.assertEqual(sorted(sans), sorted(avec))   # mêmes textes, seul l'ordre change
        self.assertNotIn(contenu.URL_DOSSIER.format("D9"), avec)  # hors des 8 premiers

    def test_barres_en_caracteres(self):
        self.assertEqual(contenu.barre_texte(0, 300), "░" * 20)
        self.assertEqual(contenu.barre_texte(1, 300), "█" + "░" * 19)   # jamais invisible
        self.assertEqual(contenu.barre_texte(41, 300), "███" + "░" * 17)
        self.assertEqual(contenu.barre_texte(5, 0), "")

    def test_frise_et_presences(self):
        from lettre import visuel
        etapes = [{"libelle": "Dépôt, Assemblée", "date": "2026-10-01", "sens": "neutre"},
                  {"libelle": "Assemblée, 1re lecture", "date": "2026-11-04", "sens": "rejeté"}]
        html = visuel.frise(etapes)
        self.assertIn("✕", html)
        self.assertIn("Assemblée, 1re lecture", html)
        self.assertIn("04/11/2026", html)
        self.assertEqual(visuel.frise([]), "")
        l = {"feminin": True, "feuilles": [
            {"date": "2026-11-03", "presence": "absent", "organe": "X"},
            {"date": "2026-11-04", "presence": "présent", "organe": "X"}]}
        cases = visuel._commission(l, ["Présente à 1 des 2 réunions."], [])
        self.assertIn("absente", cases)
        self.assertIn("présente", cases)

    def test_exemple_publie_sur_le_site(self):
        import sqlite3
        from lettre import exemple
        self.assertEqual(exemple.lire_circonscription(" 2a-01 "), ("2A", "1"))
        for illisible in ("", "69", "69-x", "69-0"):
            with self.assertRaises(ValueError):
                exemple.lire_circonscription(illisible)
        db = sqlite3.connect(self.config.donnees)
        db.row_factory = sqlite3.Row
        mercredi = datetime.datetime(2025, 7, 16, 8, tzinfo=datetime.timezone.utc)
        e = exemple.composer(db, "10-2", mercredi)   # semaine du 07/07 au 13/07/2025
        self.assertEqual((e["debut"], e["fin"], e["compose_le"]),
                         ("07/07/2025", "13/07/2025", "16/07/2025"))
        self.assertIn('role="presentation"', e["html"])
        self.assertNotIn("Vous désabonner", e["html"])   # aucun lien d'abonné
        self.assertIn('href="./' + e["chemin_fiche"], e["html"])
        # L'aperçu de l'accueil reprend les lignes « En bref » de cette même lettre.
        import html as html_module
        self.assertTrue(e["en_bref"])
        self.assertTrue(e["en_bref"][-1].startswith("Hors votes"))
        for ligne in e["en_bref"]:
            self.assertIn(ligne, html_module.unescape(e["html"]))
        self.assertIsInstance(e["vote"], bool)
        self.assertIsNone(exemple.composer(db, "10-7", mercredi))   # siège vacant
        self.assertIsNone(exemple.composer(            # semaine sans activité
            db, "10-2", datetime.datetime(2030, 1, 9, tzinfo=datetime.timezone.utc)))
        db.close()

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
        # Version visuelle : tableaux, phrase de résultat, position, lien de désabonnement.
        self.assertIn('role="presentation"', html)
        self.assertIn("L’Assemblée <span", html)
        self.assertIn(">a rejeté</span> le texte B", html)
        self.assertIn(">Contre</span>", html)
        self.assertIn('href="https://a/d"', html)
        self.assertIn("Vous désabonner</a>", html)
        self.assertNotIn("<script", html)
        self.assertNotIn(contenu.MARQUE, texte + html + sujet)
        # Trop lourde, la lettre repart dans sa version simple, désabonnement compris.
        from unittest import mock
        with mock.patch.object(contenu, "TAILLE_HTML_MAX", 100):
            _, _, simple = contenu.rendre(lettre, "https://s.fr", "https://a/g", "https://a/d")
        # Seul l'intitulé du scrutin est cliquable, pas la ligne entière.
        self.assertIn('<li>10/07/2025 · Contre · <a href="https://www.assemblee-nationale.fr'
                      '/dyn/17/scrutins/2">Le texte B</a> (rejeté) · son groupe : contre '
                      '(1 pour, 2 contre)</li>', simple)
        self.assertIn("<a href=\"https://a/d\">Vous désabonner</a>", simple)
        db.close()

    def test_barres(self):
        from lettre import visuel
        import re
        largeurs = lambda h: [int(x) for x in re.findall(r'<td width="(\d+)%"', h)]
        self.assertEqual(largeurs(visuel.barre([(1, "a"), (1, "b"), (1, "c")])), [34, 33, 33])
        # Une valeur infime reste visible, et le total fait toujours 100.
        self.assertEqual(largeurs(visuel.barre([(1, "a"), (299, "b")])), [1, 99])
        self.assertEqual(largeurs(visuel.barre([(0, "a"), (5, "b")])), [100])
        self.assertEqual(visuel.barre([(0, "a")]), "")

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
        # D1 est examiné au fond par la commission des lois, dont Ada et Léo sont membres.
        db.execute("INSERT INTO dossiers (uid, titre, commission_fond)"
                   " VALUES ('D1', 'projet de loi eau', 'C1')")
        db.executemany("INSERT INTO mandats VALUES (?,?, 'C1', 'COMPER', '17', '2024-07-20',"
                       " NULL, 'Membre')", [("MC1", "PA1"), ("MC2", "PA2")])
        db.executemany("INSERT INTO etapes VALUES ('D1', ?,?,?,?, NULL)", [
            (1, "AN1-DEBATS-DEC", "2025-07-11", "adopté"), (2, "SN1-DEPOT", "2025-07-12", None)])
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
        self.assertNotIn(contenu.NOTE_LIBELLES, texte)
        # Avec un libellé validé pour D1, il remplace le titre officiel dans les listes.
        from unittest import mock
        from collecte import libelles
        with mock.patch.object(libelles, "_VALIDES", {"D1": "L'eau, en clair"}):
            avec = contenu.composer(db, "10", "2", "2025-07-08", "2025-07-15")
            _, texte_clair, html_clair = contenu.rendre(avec, "https://s.fr", "https://a/g",
                                                        "https://a/d")
        self.assertIn("(adopté) · son groupe : pour (1 pour) · en clair : L'eau, en clair",
                      texte_clair)
        self.assertIn("- Institutions, justice et sécurité — L'eau, en clair : 2 scrutins sans "
                      "participation", texte_clair)
        self.assertIn("- Institutions, justice et sécurité — L'eau, en clair : Texte adopté par",
                      texte_clair)
        self.assertIn(contenu.NOTE_LIBELLES, texte_clair)
        self.assertIn("<b>En clair :</b> L&#x27;eau, en clair", html_clair)
        db.close()
        self.assertIn("10/07/2025 · N'a pas pris part au vote · Le texte B (rejeté, à 4 voix "
                      "près) · son groupe était partagé (1 pour, 1 contre)", texte)
        self.assertIn(contenu.ABSENCE, texte)
        self.assertIn("11/07/2025 · N'a pas voté la censure · La motion de censure (rejeté)\n",
                      texte)
        self.assertIn("Pour une motion de censure, seuls les votes pour sont recensés.", texte)
        self.assertIn("- Institutions, justice et sécurité — 11/07/2025 · Pour · L’ensemble de"
                      " la proposition de loi eau (adopté) · son groupe : pour (1 pour)", texte)
        # Le texte B n'est rattaché à aucun dossier : pas de thème.
        self.assertIn("- 10/07/2025 · N'a pas pris part au vote · Le texte B", texte)
        # S3, S6 et S7 portent sur D1 ; Ada a voté sur S6 seulement, Léo sur aucun.
        self.assertIn("Sur les textes examinés au fond par sa commission (LOIS), elle a pris "
                      "part à 1 des 3 scrutins (médiane des membres de la commission : 0,5).",
                      texte)
        self.assertIn("Ses votes par thème : Institutions, justice et sécurité (1).", texte)
        # Où en est le texte : une seule ligne par dossier, même s'il a plusieurs votes.
        self.assertIn("OÙ EN SONT CES TEXTES\n", texte)
        self.assertRegex(texte, r"Dernière étape connue de chaque texte, au \d\d/\d\d/\d{4} :")
        self.assertEqual(texte.count("— Projet de loi eau : Texte adopté"), 1)
        self.assertIn("- Institutions, justice et sécurité — Projet de loi eau : Texte adopté par "
                      "l'Assemblée nationale le 11/07/2025, en 1re lecture, puis transmis au Sénat"
                      " le 12/07/2025\n  https://www.assemblee-nationale.fr/dyn/17/dossiers/D1",
                      texte)
        # S2 et S7 sont serrés ; la motion de censure n'entre pas dans ce décompte.
        self.assertIn("2 scrutins se sont joués à 10 voix ou moins : elle a pris part à 0 "
                      "d'entre eux.", texte)
        # Le vote sur le texte entier n'est pas recompté dans le détail par texte.
        self.assertIn("- Institutions, justice et sécurité — Projet de loi eau : 2 scrutins sans"
                      " participation", texte)
        self.assertIn("- Texte eau : 3 amendements (2 rejetés, 1 irrecevable)\n"
                      "- Amendement n° 12 (rejeté), selon l'exposé de son auteur : « Cet "
                      "amendement vise à protéger l'eau. »\n\n", texte)
        self.assertIn("Sa plus longue prise de parole (09/07/2025, 150 mots, sur « Eau »), "
                      "début : « Madame la présidente, l'eau manque. »", texte)
        self.assertIn("Une erreur dans cette lettre ? Signalez-la : contact@exemple.fr", texte)
        self.assertIn('<a href="mailto:contact@exemple.fr" style="color:#1f4e79">Signalez-la</a>',
                      html)

    def test_ordre_du_jour_et_commission_principale(self):
        import sqlite3
        db = sqlite3.connect(self.config.donnees)
        db.row_factory = sqlite3.Row
        db.execute("INSERT INTO organes (uid, code_type, libelle, libelle_abrege) VALUES"
                   " ('C2', 'COMPER', 'Commission des finances', 'FIN')")
        # Ada siège à la commission des lois depuis 2024, et à celle des finances depuis
        # la veille seulement (remplacement temporaire) : sa commission reste C1.
        db.executemany("INSERT INTO mandats VALUES (?, 'PA1', ?, 'COMPER', '17', ?, ?, 'Membre')",
                       [("MC1", "C1", "2024-07-20", "2025-07-14"),
                        ("MC2", "C2", "2025-07-15", None)])
        db.executemany("INSERT INTO dossiers (uid, titre, commission_fond) VALUES (?,?,?)",
                       [("D1", "projet de loi eau", "C1"), ("D2", "projet de loi air", None)])
        db.executemany("INSERT INTO reunions (uid, type, debut, etat) VALUES (?, 'seance', ?, ?)",
                       [("R1", "2025-07-16T15:00:00.000+02:00", "Confirmé"),
                        ("R2", "2025-07-17T15:00:00.000+02:00", "Supprimé"),
                        ("R3", "2025-07-22T15:00:00.000+02:00", "Confirmé"),
                        ("R4", "2025-07-23T15:00:00.000+02:00", "Confirmé")])
        db.executemany("INSERT INTO points_odj VALUES (?,?,?,?,?,?,?,?)", [
            ("P1", "R1", "2025-07-16T15:00:00.000+02:00", 0, "Confirmé", "Discussion",
             "Discussion du projet de loi eau", "D1"),
            ("P2", "R1", "2025-07-16T15:00:00.000+02:00", 1, "Supprimé", "Discussion",
             "Discussion du projet de loi air", "D2"),           # point supprimé
            ("P3", "R2", "2025-07-17T15:00:00.000+02:00", 0, "Confirmé", "Discussion",
             "Discussion du projet de loi air", "D2"),           # séance supprimée
            ("P4", "R3", "2025-07-22T15:00:00.000+02:00", 0, "Confirmé", "Vote solennel",
             "Vote solennel sur l'ensemble du projet de loi eau", None),
            ("P5", "R3", "2025-07-22T15:00:00.000+02:00", 1, "Confirmé",
             "Questions au Gouvernement", "Questions au Gouvernement", None),
            ("P6", "R4", "2025-07-23T15:00:00.000+02:00", 0, "Confirmé", "Discussion",
             "Discussion du projet de loi air", "D2")])          # au-delà de sept jours
        self.assertEqual(contenu.commissions_principales(db, "2025-07-16")["PA1"], "C1")
        lettre = contenu.composer(db, "10", "2", "2025-07-08", "2025-07-15",
                                  aujourdhui="2025-07-16")
        _, texte, _ = contenu.rendre(lettre, "https://s.fr", "https://a/g", "https://a/d")
        db.close()
        self.assertIn(
            "À L'ORDRE DU JOUR DE L'ASSEMBLÉE\nTextes inscrits à l'ordre du jour des séances du "
            "16/07/2025 au 22/07/2025, d'après l'agenda publié par l'Assemblée. Il peut encore "
            "changer, et tous les textes inscrits ne sont pas toujours examinés :\n"
            "- Institutions, justice et sécurité — mercredi 16/07/2025 : Projet de loi eau (texte "
            "examiné par sa commission)\n  https://www.assemblee-nationale.fr/dyn/17/dossiers/D1\n"
            "- mardi 22/07/2025 : Vote solennel sur l'ensemble du projet de loi eau\n"
            "- Écrire à votre députée avant le débat\n"
            "  https://s.fr/deputes/ada-durand.html#courrier\n", texte)
        self.assertNotIn("loi air", texte)
        self.assertNotIn("Questions au Gouvernement", texte)

    def test_signalement_des_textes_sans_intitule(self):
        import dataclasses
        import sqlite3
        from unittest import mock
        from collecte import libelles
        from lettre.__main__ import signaler_libelles
        db = sqlite3.connect(self.config.donnees)
        db.executemany("INSERT INTO dossiers (uid, titre, procedure) VALUES (?,?,?)", [
            ("D1", "Texte voté", "Proposition de loi ordinaire"),
            ("D2", "Texte à l'ordre du jour", "Projet de loi ordinaire"),
            ("D3", "Motion", "Engagement de la responsabilité gouvernementale"),
            ("D4", "Texte déjà clair", "Proposition de loi ordinaire"),
            ("D5", "Texte proposé", "Proposition de loi ordinaire")])
        db.executemany("INSERT INTO scrutins (uid, numero, date, dossier_uid) VALUES (?,?,?,?)",
                       [("S9", 9, "2025-07-10", "D1"), ("S10", 10, "2025-07-10", "D3"),
                        ("S11", 11, "2025-07-11", "D4"), ("S12", 12, "2025-07-11", "D5"),
                        ("S13", 13, "2025-06-01", "D2")])   # trop ancien
        db.execute("INSERT INTO points_odj VALUES ('P1', 'R1', '2025-07-16T15:00:00', 0,"
                   " 'Confirmé', 'Discussion', 'Discussion', 'D2')")
        db.commit()
        db.close()
        csv = os.path.join(self.tmp.name, "libelles.csv")
        with open(csv, "w", encoding="utf-8") as f:
            f.write("dossier;statut;libelle;titre_officiel\nD4;titre officiel;;Texte déjà clair\n"
                    "D5;proposé;Libellé;Texte proposé\n")
        config = dataclasses.replace(self.config, contact="editeur@exemple.fr")
        journal = []
        with mock.patch.object(libelles, "FICHIER", csv):
            # Lundi 14/07/2025 : liste dans le journal et e-mail à l'éditeur.
            self.assertEqual(signaler_libelles(config, "2025-07-14", True, journal.append), 3)
            # Mardi : la liste reste dans le journal, mais aucun nouvel e-mail.
            signaler_libelles(config, "2025-07-15", True, lambda m: None)
        self.assertIn("Sans intitulé en langage courant : D1 · Texte voté", journal)
        self.assertIn("Sans intitulé en langage courant : D2 · Texte à l'ordre du jour", journal)
        self.assertIn("Intitulé proposé, pas encore validé : D5 · Texte proposé", journal)
        self.assertFalse(any("D3" in m or "D4" in m for m in journal))
        messages = self.courriels()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["To"], "editeur@exemple.fr")
        self.assertEqual(messages[0]["Subject"], "Mon député : point du lundi, 3 intitulés à décider")
        contenu_point = messages[0].get_content()
        self.assertIn("- Texte voté (D1)", contenu_point)
        self.assertIn("ABONNEMENTS (nombres seulement, aucune adresse)", contenu_point)
        self.assertIn("- Abonnés actifs : 0", contenu_point)
        self.assertNotIn("@exemple.fr", contenu_point.replace("editeur@exemple.fr", ""))

    def test_point_du_lundi_signale_les_rattachements_douteux(self):
        import dataclasses
        import sqlite3
        from unittest import mock
        from collecte import libelles, rattachements
        from lettre.__main__ import _plages, signaler_libelles
        self.assertEqual(_plages([10063, 10064, 10065, 10070]), "10063 à 10065, 10070")
        db = sqlite3.connect(self.config.donnees)
        db.execute("INSERT INTO dossiers (uid, titre, procedure) VALUES ('DX', 'Pérenniser "
                   "l’expérimentation territoires zéro chômeur de longue durée',"
                   " 'Proposition de loi ordinaire')")
        db.executemany("INSERT INTO scrutins (uid, numero, date, titre, dossier_uid) VALUES "
                       "(?,?,?,?,?)", [
                           (f"S{n}", n, "2025-07-10", f"l'amendement n° {n} à l'article 2 de la "
                            "proposition de loi visant à lutter contre la vie chère outre-mer",
                            "DX") for n in (40, 41, 42)])
        db.commit()
        db.close()
        vide = os.path.join(self.tmp.name, "vide.csv")
        open(vide, "w").close()
        config = dataclasses.replace(self.config, contact="editeur@exemple.fr")
        journal = []
        with mock.patch.object(libelles, "FICHIER", vide), \
                mock.patch.object(rattachements, "FICHIER", vide):
            signaler_libelles(config, "2025-07-14", True, journal.append)
        self.assertIn("Rattachement douteux : scrutins 40 à 42 du 2025-07-10 rattachés à DX",
                      journal)
        message = self.courriels()[-1]
        self.assertTrue(message["Subject"].endswith("1 rattachement à vérifier"))
        self.assertIn("RATTACHEMENTS À VÉRIFIER", message.get_content())
        self.assertIn("/scrutins/42", message.get_content())

    def test_bilan_des_abonnements(self):
        db = abonnes.ouvrir(self.config.abonnes)
        a, _ = abonnes.inscrire(db, "ada@exemple.fr", "10", "2", "hebdomadaire", T0)
        abonnes.confirmer(db, a["id"], T0)
        abonnes.confirmer(db, a["id"], T0)            # rouvrir le lien ne compte pas deux fois
        b, _ = abonnes.inscrire(db, "leo@exemple.fr", "10", "2", "mensuelle", T0)
        c, _ = abonnes.inscrire(db, "zoe@exemple.fr", "10", "2", "hebdomadaire", T0)
        abonnes.confirmer(db, c["id"], T0)
        abonnes.choisir_themes(db, c["id"], ["Défense"])
        abonnes.supprimer(db, c["id"], T0)
        abonnes.supprimer(db, c["id"], T0)            # déjà effacé : pas compté
        bilan = abonnes.bilan(db, T0 + datetime.timedelta(days=1))
        self.assertEqual((bilan["actifs"], bilan["par_frequence"], bilan["en_attente"]),
                         (1, {"hebdomadaire": 1}, 1))
        self.assertEqual((bilan["inscription"], bilan["confirmation"], bilan["desabonnement"]),
                         (3, 2, 1))
        self.assertEqual(abonnes.bilan(db, T0 + datetime.timedelta(days=30))["inscription"], 0)
        # Les compteurs ne contiennent aucune adresse.
        self.assertEqual({tuple(r)[1] for r in db.execute("SELECT * FROM compteurs")},
                         {"inscription", "confirmation", "desabonnement"})
        db.close()

    def test_en_bref(self):
        import sqlite3
        db = sqlite3.connect(self.config.donnees)
        db.row_factory = sqlite3.Row
        lettre = contenu.composer(db, "10", "2", "2025-07-08", "2025-07-15")
        db.close()
        lignes = contenu.en_bref(lettre)
        # S2 et S4 sont solennels ; à nombre de votants égal, le plus récent l'emporte.
        self.assertEqual(lignes[0], "A voté pour le texte C — résultat : adopté.")
        self.assertEqual(lignes[1], "A pris part à 2 des 3 scrutins publics (médiane de "
                                    "l'Assemblée : 1,5).")
        self.assertEqual(lignes[2], "Hors votes : aucune intervention en séance, aucun "
                                    "amendement ni question enregistrés pendant la période.")
        _, texte, html = contenu.rendre(lettre, "https://s.fr", "https://a/g", "https://a/d")
        self.assertTrue(texte.split("\n\n", 1)[1].startswith("EN BREF\n- A voté pour le texte C"))
        self.assertIn(contenu.CE_QUI_NEST_PAS_MESURE, texte)
        self.assertIn("A pris part à 2 des 3 scrutins publics", html)

    def test_themes_mis_en_avant(self):
        votes = [{"dossier_uid": "D1", "texte": "budget", "position": "pour"}] * 3 + \
                [{"dossier_uid": "D2", "texte": "santé", "position": "contre"}]
        l = {"autres_votes": votes, "scrutins_par_texte": [], "themes":
             {"D1": "Budget et fiscalité", "D2": "Santé, travail et solidarités"},
             "themes_agenda": {"D3": "Défense"},
             "amendements_par_texte": [("Texte budget", 3, "3 rejetés", "D1"),
                                       ("Texte santé", 1, "1 adopté", "D2")],
             "amendements_exemples": [{"texte": "Texte budget", "numero": "1"},
                                      {"texte": "Texte santé", "numero": "2"}]}
        self.assertEqual([g["uid"] for g in contenu.textes_votes(l)], ["D1", "D2"])
        self.assertIs(contenu.mettre_en_avant(l, None), l)
        avant = contenu.mettre_en_avant(l, ["Santé, travail et solidarités", "Défense"])
        self.assertEqual([g["uid"] for g in contenu.textes_votes(avant)], ["D2", "D1"])
        self.assertEqual([t[3] for t in avant["amendements_par_texte"]], ["D2", "D1"])
        self.assertEqual([a["numero"] for a in avant["amendements_exemples"]], ["2", "1"])
        self.assertEqual(avant["dossiers_en_avant"], {"D2", "D3"})
        self.assertEqual(avant["themes_choisis"], ["Santé, travail et solidarités", "Défense"])
        # Rien n'est retiré, et la lettre commune n'est pas modifiée.
        self.assertEqual(len(avant["amendements_par_texte"]), 2)
        self.assertEqual([t[3] for t in l["amendements_par_texte"]], ["D1", "D2"])

    def test_choix_des_themes(self):
        import json
        from collecte import themes
        db = abonnes.ouvrir(self.config.abonnes)
        a, _ = abonnes.inscrire(db, "ada@exemple.fr", "10", "2", "hebdomadaire", T0)
        abonnes.confirmer(db, a["id"], T0)
        self.assertIsNone(abonnes.themes_de(abonnes.lire(db, a["id"])))
        db.close()
        jeton = abonnes.jeton(SECRET, a["id"], "gerer")
        _, _, page = self.appeler("GET", "/api/gerer", requete=f"jeton={jeton}")
        self.assertEqual(page.count('type="checkbox" name="themes"'), len(themes.THEMES))
        self.assertEqual(page.count(" checked>"), 1)   # la fréquence seulement
        self.assertIn("Rien n'est retiré", page)
        corps = (f"jeton={jeton}&frequence=hebdomadaire&choix_themes=1"
                 "&themes=D%C3%A9fense&themes=Affaires+%C3%A9trang%C3%A8res")
        _, _, page = self.appeler("POST", "/api/gerer", corps, json_=False)
        self.assertIn("Préférences enregistrées", page)
        self.assertEqual(json.loads(self.lignes()[0]["themes"]), ["Affaires étrangères", "Défense"])
        # Une fréquence envoyée seule ne touche pas aux thèmes.
        self.appeler("POST", "/api/gerer", f"jeton={jeton}&frequence=mensuelle", json_=False)
        self.assertIsNotNone(self.lignes()[0]["themes"])
        # Rien coché : aucun thème en avant ; un thème inconnu est refusé.
        self.appeler("POST", "/api/gerer", f"jeton={jeton}&frequence=mensuelle&choix_themes=1",
                     json_=False)
        self.assertIsNone(self.lignes()[0]["themes"])
        statut, _, _ = self.appeler("POST", "/api/gerer", f"jeton={jeton}&frequence=mensuelle"
                                    "&choix_themes=1&themes=Inconnu", json_=False)
        self.assertEqual(statut, "400 Bad Request")

    def test_themes_choisis_a_l_inscription(self):
        import json
        self.assertEqual(self.demande(themes=["Inconnu"])[0], "400 Bad Request")
        statut, _, _ = self.demande(themes=["Défense", "Affaires étrangères"])
        self.assertEqual(statut, "200 OK")
        self.assertEqual(json.loads(self.lignes()[0]["themes"]), ["Affaires étrangères", "Défense"])
        texte = self.courriels()[-1].get_body(("plain",)).get_content()
        self.assertIn("Thèmes mis en avant : Affaires étrangères, Défense", texte)
        # Un abonnement confirmé ne se modifie pas par le formulaire public : quelqu'un
        # qui saisit l'adresse d'un autre ne peut pas changer ses thèmes.
        db = abonnes.ouvrir(self.config.abonnes)
        abonnes.confirmer(db, self.lignes()[0]["id"])
        db.execute("UPDATE abonnes SET dernier_courriel_le = NULL")
        db.commit()
        db.close()
        self.demande(themes=["Défense"])
        self.assertEqual(json.loads(self.lignes()[0]["themes"]), ["Affaires étrangères", "Défense"])
        # Un seul thème, envoyé comme simple texte, est accepté.
        self.assertEqual(self.demande(email="bob@exemple.fr", themes="Défense")[0], "200 OK")

    def test_base_des_abonnes_sans_colonne_themes(self):
        import sqlite3
        ancienne = sqlite3.connect(self.config.abonnes)
        ancienne.execute("CREATE TABLE abonnes (id INTEGER PRIMARY KEY, email TEXT NOT NULL,"
                         " num_departement TEXT NOT NULL, num_circo TEXT NOT NULL, frequence TEXT"
                         " NOT NULL, statut TEXT NOT NULL, cree_le TEXT NOT NULL, confirme_le"
                         " TEXT, dernier_envoi TEXT, dernier_courriel_le TEXT,"
                         " UNIQUE (email, num_departement, num_circo))")
        ancienne.execute("INSERT INTO abonnes (email, num_departement, num_circo, frequence,"
                         " statut, cree_le) VALUES ('a@b.fr', '10', '2', 'hebdomadaire', 'actif',"
                         " 'x')")
        ancienne.commit()
        ancienne.close()
        self.assertIsNone(self.lignes()[0]["themes"])

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
