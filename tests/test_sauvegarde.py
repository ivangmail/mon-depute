"""Tests de la copie de la base des abonnés hors du serveur."""

import datetime
import hashlib
import io
import os
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.parse
from email import message_from_bytes, policy

from lettre import abonnes, sauvegarde
from lettre.__main__ import sauvegarder
from lettre.config import Config, ConfigurationInvalide, depuis_environnement
from lettre.stockage import Depot, ErreurStockage, signer

T0 = datetime.datetime(2026, 11, 23, 4, 0, tzinfo=datetime.timezone.utc)
PHRASE = "une phrase secrète assez longue pour les essais"
VIDE = hashlib.sha256(b"").hexdigest()


class FauxS3:
    """Remplace urllib.request.urlopen : garde les objets en mémoire et vérifie
    que chaque requête porte une signature valide."""

    def __init__(self, espace="copies", par_page=1000, panne=None):
        self.espace, self.par_page, self.panne = espace, par_page, panne
        self.objets, self.requetes = {}, []

    def __call__(self, demande, timeout=None):
        url = urllib.parse.urlsplit(demande.full_url)
        methode = demande.get_method()
        self.requetes.append((methode, demande.full_url))
        if self.panne and self.panne(methode, url):
            raise urllib.error.HTTPError(demande.full_url, 403, "Forbidden", {},
                                         io.BytesIO(b"<Error>AccessDenied</Error>"))
        entetes = {n.lower(): v for n, v in demande.header_items()}
        corps = demande.data or b""
        assert entetes["x-amz-content-sha256"] == hashlib.sha256(corps).hexdigest()
        instant = datetime.datetime.strptime(entetes["x-amz-date"], "%Y%m%dT%H%M%SZ").replace(
            tzinfo=datetime.timezone.utc)
        requete = urllib.parse.parse_qsl(url.query, keep_blank_values=True)
        chemin = urllib.parse.unquote(url.path)
        attendu = signer(methode, chemin, requete,
                         {"host": url.netloc, "x-amz-date": entetes["x-amz-date"],
                          "x-amz-content-sha256": entetes["x-amz-content-sha256"]},
                         entetes["x-amz-content-sha256"], "fr-par", "CLE", "SECRET", instant)
        assert entetes["authorization"] == attendu, "signature invalide"
        assert url.netloc == f"{self.espace}.s3.fr-par.scw.cloud"
        cle = chemin.lstrip("/")
        if methode == "PUT":
            self.objets[cle] = corps
            return io.BytesIO(b"")
        if methode == "DELETE":
            self.objets.pop(cle, None)
            return io.BytesIO(b"")
        if cle:
            if cle not in self.objets:
                raise urllib.error.HTTPError(demande.full_url, 404, "Not Found", {},
                                             io.BytesIO(b"NoSuchKey"))
            return io.BytesIO(self.objets[cle])
        # Liste (ListObjectsV2), découpée en pages pour tester la suite.
        parametres = dict(requete)
        cles = sorted(c for c in self.objets if c.startswith(parametres.get("prefix", "")))
        debut = int(parametres.get("continuation-token") or 0)
        page = cles[debut:debut + self.par_page]
        suite = debut + self.par_page < len(cles)
        contenu = "".join(f"<Contents><Key>{c}</Key><Size>{len(self.objets[c])}</Size>"
                          f"<LastModified>2026-11-23T04:00:00.000Z</LastModified></Contents>"
                          for c in page)
        xml = ('<?xml version="1.0" encoding="UTF-8"?><ListBucketResult '
               'xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
               f"<IsTruncated>{'true' if suite else 'false'}</IsTruncated>{contenu}"
               + (f"<NextContinuationToken>{debut + self.par_page}</NextContinuationToken>"
                  if suite else "") + "</ListBucketResult>")
        return io.BytesIO(xml.encode())


def depot(faux):
    return Depot("s3.fr-par.scw.cloud", "fr-par", faux.espace, "CLE", "SECRET", ouvrir=faux,
                 horloge=lambda: T0)


class Signature(unittest.TestCase):
    def test_exemples_de_la_documentation_aws(self):
        # Exemples « GET Object » et « GET Bucket » de la documentation S3 d'AWS.
        t = datetime.datetime(2013, 5, 24, tzinfo=datetime.timezone.utc)
        commun = {"host": "examplebucket.s3.amazonaws.com", "x-amz-content-sha256": VIDE,
                  "x-amz-date": "20130524T000000Z"}
        cles = ("us-east-1", "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", t)
        self.assertTrue(signer("GET", "/test.txt", [], {**commun, "range": "bytes=0-9"}, VIDE,
                               *cles).endswith(
            "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"))
        self.assertTrue(signer("GET", "/", [("max-keys", "2"), ("prefix", "J")], commun, VIDE,
                               *cles).endswith(
            "Signature=34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"))


class Stockage(unittest.TestCase):
    def test_depot_lecture_liste_et_suppression(self):
        faux = FauxS3(par_page=2)
        d = depot(faux)
        for nom in ("abonnes/b", "abonnes/a", "abonnes/c", "autre/x"):
            d.deposer(nom, nom.encode())
        self.assertEqual(d.lire("abonnes/a"), b"abonnes/a")
        self.assertEqual([c for c, _, _ in d.lister("abonnes/")],
                         ["abonnes/a", "abonnes/b", "abonnes/c"])  # sur deux pages
        d.supprimer("abonnes/b")
        self.assertEqual([c for c, _, _ in d.lister("abonnes/")], ["abonnes/a", "abonnes/c"])
        self.assertEqual(faux.requetes[0],
                         ("PUT", "https://copies.s3.fr-par.scw.cloud/abonnes/b"))
        with self.assertRaisesRegex(ErreurStockage, "HTTP 404"):
            d.lire("absent")

    def test_style_chemin(self):
        vus = []
        Depot("localhost:9000", "fr-par", "copies", "CLE", "SECRET", schema="http",
              style="chemin", ouvrir=lambda r, timeout: vus.append(r.full_url) or io.BytesIO(),
              horloge=lambda: T0).deposer("abonnes/a", b"x")
        self.assertEqual(vus, ["http://localhost:9000/copies/abonnes/a"])


class Chiffrement(unittest.TestCase):
    def test_aller_retour_et_mauvaise_phrase(self):
        chiffre = sauvegarde.chiffrer(b"des adresses", PHRASE)
        self.assertTrue(chiffre.startswith(b"Salted__"))
        self.assertNotIn(b"adresses", chiffre)
        self.assertNotEqual(chiffre, sauvegarde.chiffrer(b"des adresses", PHRASE))  # sel
        self.assertEqual(sauvegarde.dechiffrer(chiffre, PHRASE), b"des adresses")
        with self.assertRaises(sauvegarde.EchecSauvegarde):
            sauvegarde.dechiffrer(chiffre, "une autre phrase secrète, fausse")

    def test_dechiffrement_a_la_main(self):
        # La commande donnée dans la documentation suffit, sans ce code.
        chiffre = sauvegarde.chiffrer(b"contenu", PHRASE)
        resultat = subprocess.run(
            ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "600000",
             "-pass", "env:PHRASE"], input=chiffre, capture_output=True, check=True,
            env={"PATH": os.environ["PATH"], "PHRASE": PHRASE})
        self.assertEqual(resultat.stdout, b"contenu")


class Sauvegarde(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(
            secret=b"s" * 40, site_url="https://site.exemple", api_url="https://api.exemple",
            donnees=os.path.join(self.tmp.name, "i.sqlite"),
            abonnes=os.path.join(self.tmp.name, "abonnes.sqlite"),
            expediteur="Mon député <lettre@exemple.fr>",
            dossier_courriels=os.path.join(self.tmp.name, "courriels"),
            contact="editeur@exemple.fr", s3_espace="copies", s3_hote="s3.fr-par.scw.cloud",
            s3_cle_acces="CLE", s3_cle_secrete="SECRET", sauvegarde_phrase=PHRASE)
        db = abonnes.ouvrir(self.config.abonnes)
        for email in ("ada@exemple.fr", "leo@exemple.fr"):
            abonnes.inscrire(db, email, "69", "3", "hebdomadaire", T0)
        db.close()
        self.dossier = os.path.join(self.tmp.name, "sauvegardes")

    def tearDown(self):
        self.tmp.cleanup()

    def test_envoi_verification_et_conservation(self):
        faux = FauxS3()
        d = depot(faux)
        for n in range(4):
            chemin = abonnes.sauvegarder(self.config.abonnes, self.dossier,
                                         instant=T0 + datetime.timedelta(days=n))
            cle = sauvegarde.envoyer(chemin, d, PHRASE, conserver=2)
        self.assertEqual(cle, "abonnes/abonnes-20261126-040000.sqlite.gz.enc")
        self.assertEqual(sorted(faux.objets), ["abonnes/abonnes-20261125-040000.sqlite.gz.enc",
                                               "abonnes/abonnes-20261126-040000.sqlite.gz.enc"])
        # Le fournisseur ne voit aucune adresse en clair.
        self.assertTrue(all(b"exemple.fr" not in o for o in faux.objets.values()))
        # Restauration de la plus récente, sans écraser un fichier existant.
        destination = os.path.join(self.tmp.name, "restauree.sqlite")
        self.assertEqual(sauvegarde.restaurer(d, PHRASE, destination), (cle, 2))
        self.assertEqual(os.stat(destination).st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(sauvegarde.EchecSauvegarde, "existe déjà"):
            sauvegarde.restaurer(d, PHRASE, destination)
        with self.assertRaisesRegex(sauvegarde.EchecSauvegarde, "phrase secrète"):
            sauvegarde.restaurer(d, "une autre phrase secrète, fausse",
                                 os.path.join(self.tmp.name, "autre.sqlite"))

    def test_copie_relue_differente(self):
        faux = FauxS3()
        d = depot(faux)
        d.lire = lambda cle: sauvegarde.chiffrer(b"autre chose", PHRASE)
        chemin = abonnes.sauvegarder(self.config.abonnes, self.dossier, instant=T0)
        with self.assertRaisesRegex(sauvegarde.EchecSauvegarde, "ne correspond pas"):
            sauvegarde.envoyer(chemin, d, PHRASE)

    def test_commande_en_panne_previent_l_editeur(self):
        faux = FauxS3(panne=lambda methode, url: methode == "PUT")
        journal = []
        self.assertEqual(sauvegarder(self.config, self.dossier, depot(faux), journal.append), 1)
        self.assertEqual(len(os.listdir(self.dossier)), 1)  # la copie locale est faite
        self.assertIn("HTTP 403", journal[-1])
        courriels = os.listdir(self.config.dossier_courriels)
        self.assertEqual(len(courriels), 1)
        with open(os.path.join(self.config.dossier_courriels, courriels[0]), "rb") as f:
            message = message_from_bytes(f.read(), policy=policy.default)
        self.assertEqual(message["To"], "editeur@exemple.fr")
        self.assertIn("échec de la sauvegarde", message["Subject"])
        self.assertNotIn("ada@exemple.fr", message.get_content())

    def test_commande_reussie(self):
        faux = FauxS3()
        journal = []
        self.assertEqual(sauvegarder(self.config, self.dossier, depot(faux), journal.append), 0)
        self.assertIn("Copie chiffrée déposée hors du serveur : copies/abonnes/", journal[-1])
        self.assertFalse(os.path.exists(self.config.dossier_courriels))


class Configuration(unittest.TestCase):
    BASE = {"MD_SECRET": "x" * 40, "MD_SITE_URL": "https://s", "MD_API_URL": "https://a",
            "MD_EXPEDITEUR": "a@b.fr", "MD_DOSSIER_COURRIELS": "/tmp/c"}

    def test_sans_sauvegarde_distante(self):
        cfg = depuis_environnement(self.BASE)
        self.assertEqual(cfg.s3_espace, "")
        self.assertIsNone(sauvegarde.depot(cfg))

    def test_avec_sauvegarde_distante(self):
        cfg = depuis_environnement({**self.BASE, "MD_S3_ESPACE": "copies",
                                    "MD_S3_CLE_ACCES": "SCW1", "MD_S3_CLE_SECRETE": "s",
                                    "MD_SAUVEGARDE_PHRASE": PHRASE})
        self.assertEqual((cfg.s3_region, cfg.s3_hote), ("fr-par", "s3.fr-par.scw.cloud"))
        cfg = depuis_environnement({**self.BASE, "MD_S3_ESPACE": "copies", "MD_S3_REGION": "nl-ams",
                                    "MD_S3_CLE_ACCES": "SCW1", "MD_S3_CLE_SECRETE": "s",
                                    "MD_SAUVEGARDE_PHRASE": PHRASE})
        self.assertEqual(cfg.s3_hote, "s3.nl-ams.scw.cloud")

    def test_refus(self):
        with self.assertRaisesRegex(ConfigurationInvalide, "MD_SAUVEGARDE_PHRASE"):
            depuis_environnement({**self.BASE, "MD_S3_ESPACE": "copies",
                                  "MD_S3_CLE_ACCES": "SCW1", "MD_S3_CLE_SECRETE": "s"})
        with self.assertRaisesRegex(ConfigurationInvalide, "20 caractères"):
            depuis_environnement({**self.BASE, "MD_S3_ESPACE": "copies",
                                  "MD_S3_CLE_ACCES": "SCW1", "MD_S3_CLE_SECRETE": "s",
                                  "MD_SAUVEGARDE_PHRASE": "trop courte"})
