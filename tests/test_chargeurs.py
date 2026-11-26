"""Tests sur les cas qui ont posé problème avec les vraies données."""

import json
import os
import pathlib
import tempfile
import unittest
import zipfile

from collecte import base, chargeurs, fiche

NIL = {"@xsi:nil": "true"}


def archive(dossier, nom, fichiers):
    chemin = os.path.join(dossier, nom)
    with zipfile.ZipFile(chemin, "w") as z:
        for interne, contenu in fichiers.items():
            z.writestr(interne, contenu if isinstance(contenu, str) else json.dumps(contenu))
    return chemin


def mandat(uid, type_organe, organe, debut, fin=None, **extra):
    return {"uid": uid, "typeOrgane": type_organe, "legislature": "17",
            "dateDebut": debut, "dateFin": fin, "organes": {"organeRef": organe},
            "infosQualite": {"codeQualite": "membre"}, **extra}


def acteur(uid, prenom, nom, mandats, adresses=None):
    return {"acteur": {
        "uid": {"@xsi:type": "IdActeur_type", "#text": uid},
        "etatCivil": {"ident": {"civ": "Mme", "prenom": prenom, "nom": nom},
                      "infoNaissance": {"dateNais": "1980-01-02", "villeNais": "Lyon",
                                        "depNais": "Rhône"}},
        "profession": {"libelleCourant": NIL}, "uri_hatvp": None,
        "adresses": {"adresse": adresses} if adresses else None,
        "mandats": {"mandat": mandats}}}


ELECTION = {"election": {"lieu": {"region": "Grand Est", "departement": "Aube",
                                  "numDepartement": "10", "numCirco": "2"},
                         "causeMandat": "élections générales"}}


class Chargeurs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = base.ouvrir(os.path.join(self.tmp.name, "t.sqlite"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def charger_acteurs(self, acteurs):
        fichiers = {"json/organe/PO1.json": {"organe": {
            "uid": "PO1", "codeType": "GP", "libelle": "Groupe Test",
            "libelleAbrege": "GT", "legislature": "17", "couleurAssociee": "#123456",
            "viMoDe": {"dateDebut": "2024-07-18", "dateFin": None}}}}
        for a in acteurs:
            fichiers[f"json/acteur/{a['acteur']['uid']['#text']}.json"] = a
        chemin = archive(self.tmp.name, "amo.zip", fichiers)
        with self.db:
            return chargeurs.charger_acteurs(self.db, [chemin])

    def test_retour_du_gouvernement_garde_le_mandat_en_cours(self):
        # Deux mandats débutant le même jour : l'un clos, l'autre en cours.
        # L'ordre des mandats dans le fichier ne doit pas changer le résultat.
        clos = mandat("PM1", "ASSEMBLEE", "PO0", "2024-07-07", "2024-10-21", **ELECTION)
        ouvert = mandat("PM2", "ASSEMBLEE", "PO0", "2024-07-07", None, **ELECTION)
        groupe = mandat("PM3", "GP", "PO1", "2024-07-19")
        for ordre in ([clos, ouvert, groupe], [ouvert, clos, groupe]):
            self.assertEqual(self.charger_acteurs([acteur("PA1", "Ada", "Durand", ordre)]), 1)
            d = self.db.execute("SELECT * FROM deputes").fetchone()
            self.assertEqual((d["en_exercice"], d["mandat_uid"], d["groupe_sigle"],
                              d["num_departement"], d["num_circo"]),
                             (1, "PM2", "GT", "10", "2"))

    def test_mandat_multi_organes_et_contacts(self):
        ministre = mandat("PM9", "MINISTERE", ["PO7", "PO8"], "2024-09-22")
        adresses = [{"uid": "AD1", "typeLibelle": "Mèl", "valElec": "a@exemple.fr"},
                    {"uid": "AD2", "typeLibelle": "Adresse officielle", "numeroRue": "126",
                     "nomRue": "Rue de l'Université,", "codePostal": "75355", "ville": "Paris"}]
        self.charger_acteurs([acteur("PA2", "Léa", "Martin", [ministre], adresses)])
        self.assertEqual(self.db.execute("SELECT organe_uid FROM mandats").fetchone()[0], "PO7")
        self.assertEqual(self.db.execute("SELECT count(*) FROM deputes").fetchone()[0], 0)
        contacts = dict(self.db.execute("SELECT type, valeur FROM contacts").fetchall())
        self.assertEqual(contacts["Mèl"], "a@exemple.fr")
        self.assertEqual(contacts["Adresse officielle"], "126 Rue de l'Université, 75355 Paris")
        a = self.db.execute("SELECT * FROM acteurs").fetchone()
        self.assertEqual((a["lieu_naissance"], a["profession"]), ("Lyon, Rhône", None))

    def test_votes_un_seul_votant_ou_plusieurs(self):
        scrutin = {"scrutin": {
            "uid": "VT1", "numero": "1", "dateScrutin": "2025-01-15",
            "typeVote": {"libelleTypeVote": "scrutin public ordinaire"},
            "sort": {"code": "adopté"}, "titre": "l'article 1", "demandeur": {"texte": None},
            "objet": {"dossierLegislatif": None},
            "syntheseVote": {"nombreVotants": "3", "suffragesExprimes": "3",
                             "decompte": {"pour": "2", "contre": "1", "abstentions": "0"}},
            "ventilationVotes": {"organe": {"groupes": {"groupe": [
                {"organeRef": "PO1", "vote": {"decompteNominatif": {
                    "nonVotants": None,
                    "pours": {"votant": [{"acteurRef": "PA1", "parDelegation": "false"},
                                         {"acteurRef": "PA2", "parDelegation": "true"}]},
                    # un seul votant : objet seul, pas une liste
                    "contres": {"votant": {"acteurRef": "PA3", "parDelegation": "false"}},
                    "abstentions": None}}}]}}}}}
        chemin = archive(self.tmp.name, "s.zip", {"json/VT1.json": scrutin})
        with self.db:
            self.assertEqual(chargeurs.charger_scrutins(self.db, [chemin]), 1)
            # Recharger ne doit pas dupliquer.
            chargeurs.charger_scrutins(self.db, [chemin])
        votes = self.db.execute("SELECT acteur_uid, position, par_delegation FROM votes"
                                " ORDER BY acteur_uid").fetchall()
        self.assertEqual([tuple(v) for v in votes],
                         [("PA1", "pour", 0), ("PA2", "pour", 1), ("PA3", "contre", 0)])

    def test_debats_sujet_et_orateurs_sans_fiche(self):
        ns = "http://schemas.assemblee-nationale.fr/referentiel"

        def para(ordre, acteur_id, nom, texte):
            return (f'<paragraphe ordre_absolu_seance="{ordre}" id_acteur="{acteur_id}" '
                    f'code_grammaire="PAROLE_GENERIQUE"><orateurs><orateur><nom>{nom}</nom>'
                    f'<qualite/></orateur></orateurs><texte>{texte}</texte></paragraphe>')
        xml = f"""<compteRendu xmlns="{ns}"><uid>CR1</uid><seanceRef>RU1</seanceRef>
<metadonnees><dateSeance>20261109160000000</dateSeance><numSeance>57</numSeance>
<etat>provisoire</etat><session>Session ordinaire</session></metadonnees><contenu>
<point nivpoint="1"><orateurs/><texte>Budget <italique>2027</italique></texte></point>
<point nivpoint="2"><orateurs/><texte>Présentation</texte>
{para(1, "PA1", "Mme Durand", "Un deux trois")}
<point nivpoint="4"><interExtraction>{para(2, "PA0", "Un député", "Non !")}</interExtraction>
{para(3, "PA-12", "M. Invité", "Merci.")}</point></point>
<point nivpoint="1"><orateurs/><texte>Questions</texte></point>
<point nivpoint="2">{para(4, "PA1", "Mme Durand", "Ma question.")}</point>
</contenu></compteRendu>"""
        chemin = archive(self.tmp.name, "d.zip", {"xml/compteRendu/CR1.xml": xml})
        with self.db:
            self.assertEqual(chargeurs.charger_debats(self.db, [chemin]), 4)
        lignes = [tuple(l) for l in self.db.execute(
            "SELECT ordre, acteur_uid, sujet, nb_mots FROM interventions ORDER BY ordre")]
        self.assertEqual(lignes, [(1, "PA1", "Budget 2027", 3), (2, None, "Budget 2027", 2),
                                  (3, None, "Budget 2027", 1), (4, "PA1", "Questions", 2)])
        self.assertEqual(self.db.execute("SELECT date FROM comptes_rendus").fetchone()[0],
                         "2026-11-09")


class Affichage(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(fiche.jour("2026-11-09"), "09/11/2026")
        self.assertEqual(fiche.jour(None), "—")
        # La plus récente au sens du calendrier, pas de l'ordre alphabétique.
        self.assertEqual(fiche.date_source(["Tue, 10 Nov 2026 13:23:19 GMT",
                                            "Wed, 02 Dec 2026 01:00:00 GMT", None]),
                         "02/12/2026")

    def test_recherche_sans_accents(self):
        self.assertEqual(fiche.sans_accents("Émeline K/Bidi"), "emeline k/bidi")


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------- étape 2

from collecte import indicateurs, portrait, site  # noqa: E402


def base_indicateurs(dossier):
    """Petite base : deux groupes, trois députés, quatre scrutins."""
    db = base.ouvrir(os.path.join(dossier, "i.sqlite"))
    db.executemany("INSERT INTO organes (uid, code_type, libelle, libelle_abrege, legislature)"
                   " VALUES (?,?,?,?,'17')",
                   [("G1", "GP", "Groupe Un", "UN"), ("G2", "GP", "Groupe Deux", "DEUX"),
                    ("GNI", "GP", "Non inscrit", "NI"),
                    ("C1", "COMPER", "Commission des lois", "LOIS")])
    for uid, prenom, nom, civ, groupe, sigle, debut in [
            ("PA1", "Ada", "Durand", "Mme", "G1", "UN", "2024-07-07"),
            ("PA2", "Léo", "Martin", "M.", "G1", "UN", "2024-07-07"),
            ("PA3", "Zoé", "Petit", "Mme", "G1", "UN", "2025-06-01"),
            ("PA4", "Max", "Roux", "M.", "GNI", "NI", "2024-07-07")]:
        db.execute("INSERT INTO acteurs (uid, civilite, prenom, nom, date_naissance,"
                   " lieu_naissance, profession) VALUES (?,?,?,?,'1980-01-02','Lyon, Rhône',"
                   " '(47) - Technicien')", (uid, civ, prenom, nom))
        db.execute("INSERT INTO deputes VALUES (?,1,?,?,NULL,'élections générales','Région',"
                   " 'Aube','10','2',NULL,?,?,?)",
                   (uid, "M" + uid, debut, groupe, sigle,
                    "Groupe Un" if groupe == "G1" else "Non inscrit"))
        db.execute("INSERT INTO mandats VALUES (?,?,'PO0','ASSEMBLEE','17',?,NULL,'membre')",
                   ("M" + uid, uid, debut))
    # S1 et S2 solennels ; S3 ordinaire ; S4 solennel où le groupe est à égalité.
    db.executemany("INSERT INTO scrutins (uid, numero, date, type_vote, sort, titre)"
                   " VALUES (?,?,?,?,?,?)",
                   [("S1", 1, "2025-01-10", indicateurs.SOLENNEL, "adopté", "le texte A"),
                    ("S2", 2, "2025-07-10", indicateurs.SOLENNEL, "rejeté", "le texte B"),
                    ("S3", 3, "2025-07-11", "scrutin public ordinaire", "rejeté", "l'amdt 1"),
                    ("S4", 4, "2025-07-12", indicateurs.SOLENNEL, "adopté", "le texte C")])
    db.executemany("INSERT INTO votes VALUES (?,?,?,?,0)", [
        ("S1", "PA1", "G1", "pour"), ("S1", "PA2", "G1", "pour"),
        ("S2", "PA1", "G1", "contre"), ("S2", "PA2", "G1", "contre"), ("S2", "PA3", "G1", "pour"),
        ("S3", "PA1", "G1", "non_votant"), ("S3", "PA4", "GNI", "pour"),
        ("S4", "PA1", "G1", "pour"), ("S4", "PA2", "G1", "contre")])
    db.execute("INSERT INTO imports VALUES ('f.zip','scrutins','u',NULL,"
               "'Tue, 10 Nov 2026 13:23:19 GMT',1,NULL,NULL)")
    with db:
        indicateurs.calculer(db)
    return db


class Indicateurs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = base_indicateurs(self.tmp.name)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def ligne(self, uid):
        return dict(self.db.execute("SELECT * FROM indicateurs WHERE acteur_uid = ?",
                                    (uid,)).fetchone())

    def test_eligibilite_selon_le_mandat(self):
        # PA3 est arrivée le 01/06/2025 : le scrutin S1 de janvier ne compte pas.
        self.assertEqual(self.ligne("PA1")["solennels_eligibles"], 3)
        self.assertEqual(self.ligne("PA3")["solennels_eligibles"], 2)
        self.assertEqual(self.ligne("PA3")["solennels_exprimes"], 1)

    def test_non_votant_n_est_pas_une_participation(self):
        i = self.ligne("PA1")
        self.assertEqual((i["scrutins_eligibles"], i["scrutins_exprimes"],
                          i["votes_non_votant"]), (4, 3, 1))

    def test_ligne_de_groupe_et_egalite(self):
        lignes = dict(((l[0], l[1]), l[2]) for l in self.db.execute(
            "SELECT scrutin_uid, groupe_uid, position FROM lignes_groupe"))
        self.assertEqual(lignes[("S1", "G1")], "pour")
        self.assertEqual(lignes[("S2", "G1")], "contre")
        self.assertNotIn(("S4", "G1"), lignes)  # un pour, un contre : pas de ligne

    def test_ligne_nette_au_dela_de_60_pour_cent(self):
        # S5 : trois pour, deux contre dans le groupe, soit 60 % tout juste : groupe partagé,
        # le vote contre de PA2 n'est pas compté comme un vote contre sa ligne.
        self.db.execute("INSERT INTO scrutins (uid, numero, date, type_vote, sort, titre)"
                        " VALUES ('S5', 5, '2025-07-13', 'scrutin public ordinaire', 'adopté', 'x')")
        self.db.executemany("INSERT INTO votes VALUES ('S5', ?, 'G1', ?, 0)", [
            ("PA1", "pour"), ("PA3", "pour"), ("PX1", "pour"), ("PA2", "contre"),
            ("PX2", "contre")])
        with self.db:
            indicateurs.calculer(self.db)
        nettes = dict(((l[0], l[1]), (l[2], l[3])) for l in self.db.execute(
            "SELECT scrutin_uid, groupe_uid, position, nette FROM lignes_groupe"))
        self.assertEqual(nettes[("S5", "G1")], ("pour", 0))
        self.assertEqual(nettes[("S2", "G1")], ("contre", 1))  # deux sur trois : 67 %
        self.assertEqual((self.ligne("PA2")["votes_comparables"],
                          self.ligne("PA2")["votes_conformes"]), (2, 2))

    def test_reperes_en_mediane(self):
        # Taux de votes conformes : PA1 100 %, PA2 100 %, PA3 0 %. La médiane vaut
        # 100 %, là où la moyenne vaudrait 67 %.
        from unittest import mock
        with mock.patch.object(indicateurs, "MIN_COMPARABLES", 1), self.db:
            indicateurs.calculer(self.db)
        reperes = {(m[0], m[1]): (m[2], m[3]) for m in self.db.execute("SELECT * FROM moyennes")}
        self.assertEqual(reperes[("tous", "loyaute")], (1.0, 3))
        self.assertEqual(reperes[("G1", "loyaute")], (1.0, 3))

    def test_loyaute(self):
        # PA3 a voté pour quand son groupe votait contre ; S4 est écarté pour tous.
        self.assertEqual((self.ligne("PA3")["votes_comparables"],
                          self.ligne("PA3")["votes_conformes"]), (1, 0))
        self.assertEqual((self.ligne("PA1")["votes_comparables"],
                          self.ligne("PA1")["votes_conformes"]), (2, 2))
        # Les non-inscrits n'ont pas de ligne de groupe.
        self.assertEqual(self.ligne("PA4")["votes_comparables"], 0)

    def test_taux_sous_le_seuil_non_affiche(self):
        i = indicateurs.pour_depute(self.db, "PA1")
        self.assertIsNone(i["taux_solennels"])  # 3 scrutins solennels < seuil de 5
        self.assertEqual(indicateurs.taux(3, 4), 0.75)
        self.assertIsNone(indicateurs.taux(0, 0))

    def test_site_complet(self):
        dossier = os.path.join(self.tmp.name, "site")
        chemins = site.generer(self.db, dossier, journal=lambda m: None)
        self.assertEqual(chemins["PA1"], "deputes/ada-durand.html")
        accueil = pathlib.Path(dossier, "index.html").read_text(encoding="utf-8")
        self.assertIn("deputes/zoe-petit.html", accueil)
        self.assertIn("à jour au 10/11/2026", accueil)
        page = pathlib.Path(dossier, chemins["PA3"]).read_text(encoding="utf-8")
        self.assertIn("Zoé Petit", page)
        self.assertIn("scrutins/2", page)                 # lien vers le scrutin officiel
        self.assertIn("N&#x27;a pas pris part au vote", page)  # S4 : pas de vote enregistré
        self.assertIn("UN : contre", page)                # son vote dissident sur S2
        self.assertTrue(os.path.exists(os.path.join(dossier, "methodologie.html")))
        # Accueil : adresse d'abord, réassurance, parcours ; sans service de lettre,
        # ni étape « lettre » ni page d'exemple.
        self.assertIn("Sans compte · Sans cookie", accueil)
        self.assertIn('class="etapes"', accueil)
        self.assertIn('id="tout" type="button" hidden', accueil)  # liste repliée par le script
        self.assertIn('data-lettre=""', accueil)
        self.assertNotIn("Sa lettre, si vous le souhaitez", accueil)
        self.assertNotIn('class="appel-lettre"', accueil)
        self.assertNotIn('class="apercu"', accueil)
        self.assertFalse(os.path.exists(os.path.join(dossier, "exemple-lettre.html")))
        # Éléments validés de l'accueil, conservés par la nouvelle présentation.
        for attendu in ("<a class=\"marque\" href=\"index.html\">Mon député</a>",
                        "service public de géocodage\n de l’IGN",
                        'id="etranger"', 'id="q"', 'id="g"', "Par nom ou département",
                        "Députés ayant quitté l’Assemblée", 'href="pourquoi.html"',
                        'href="methodologie.html"', 'href="confidentialite.html"',
                        "Ce site n’est pas un site officiel de l’Assemblée nationale"):
            self.assertIn(attendu, accueil)
        self.assertNotIn("Législatives-2027", accueil)
        self.assertNotIn("LÉGISLATIVES", accueil)

    def test_accueil_avec_la_lettre_et_son_exemple(self):
        dossier = os.path.join(self.tmp.name, "site-lettre")
        exemple = {"html": "<table><tr><td>LETTRE</td></tr></table>", "debut": "09/11/2026",
                   "fin": "15/11/2026", "compose_le": "18/11/2026", "depute": "Ada Durand",
                   "lieu": "2e circonscription, Ain (01)",
                   "chemin_fiche": "deputes/ada-durand.html",
                   "groupe": "Groupe Un", "sigle": "UN", "vote": True,
                   "en_bref": ["A voté pour le texte <test> — résultat : adopté.",
                               "Hors votes : 2 amendements déposés."]}
        site.generer(self.db, dossier, journal=lambda m: None, api_url="https://x.fr",
                     exemple=exemple)
        accueil = pathlib.Path(dossier, "index.html").read_text(encoding="utf-8")
        self.assertIn('data-lettre="1"', accueil)
        # Carte d'exemple : les lignes « En bref » de la lettre, échappées, rien d'autre.
        self.assertIn('class="une avec-apercu"', accueil)
        self.assertIn("<b>Le vote à retenir</b>A voté pour le texte &lt;test&gt;", accueil)
        self.assertIn("<li>Hors votes : 2 amendements déposés.</li>", accueil)
        self.assertIn("Groupe Un (UN) · 2e circonscription, Ain (01)", accueil)
        self.assertIn("semaine du 09/11/2026\n au 15/11/2026", accueil)
        self.assertIn('class="appel-lettre"', accueil)
        self.assertIn("rien n’est\n retiré", accueil)
        # Sans lignes « En bref », pas de carte ; le reste de l'accueil est inchangé.
        site.generer(self.db, dossier, journal=lambda m: None, api_url="https://x.fr",
                     exemple=dict(exemple, en_bref=[]))
        sans_carte = pathlib.Path(dossier, "index.html").read_text(encoding="utf-8")
        self.assertNotIn('class="apercu"', sans_carte)
        self.assertIn('class="une"', sans_carte)
        self.assertIn('href="exemple-lettre.html"', sans_carte)
        site.generer(self.db, dossier, journal=lambda m: None, api_url="https://x.fr",
                     exemple=exemple)
        accueil = pathlib.Path(dossier, "index.html").read_text(encoding="utf-8")
        self.assertIn('Sa lettre, si vous le souhaitez', accueil)
        self.assertIn('href="exemple-lettre.html"', accueil)
        page = pathlib.Path(dossier, "exemple-lettre.html").read_text(encoding="utf-8")
        self.assertIn("LETTRE", page)
        self.assertIn('href="deputes/ada-durand.html#abonnement"', page)
        self.assertIn("du 09/11/2026 au 15/11/2026", page)
        self.assertIn("<b>Ada Durand</b>, 2e circonscription, Ain (01)", page)
        # Sans exemple, la page précédente est retirée et l'accueil n'y renvoie plus.
        site.generer(self.db, dossier, journal=lambda m: None, api_url="https://x.fr")
        self.assertFalse(os.path.exists(os.path.join(dossier, "exemple-lettre.html")))
        self.assertNotIn("exemple-lettre.html",
                         pathlib.Path(dossier, "index.html").read_text(encoding="utf-8"))


class Portrait(unittest.TestCase):
    ACTEUR = {"civilite": "Mme", "prenom": "Ada", "nom": "Durand",
              "date_naissance": "1980-06-15", "lieu_naissance": "Lyon, Rhône",
              "profession": "(47) - Technicien"}
    DEPUTE = {"en_exercice": 1, "num_circo": "1", "departement": "Ain",
              "num_departement": "01", "date_debut": "2024-07-07", "date_fin": None,
              "cause_mandat": "élections générales", "groupe_libelle": "Groupe Un",
              "groupe_sigle": "UN"}

    def test_accords_et_contenu(self):
        import datetime
        texte = " ".join(portrait.rediger(
            self.ACTEUR, self.DEPUTE,
            [("Commission des lois", "Membre"), ("Commission des lois", "Secrétaire")],
            ["15", "16", "17"], aujourdhui=datetime.date(2026, 6, 14)))
        self.assertIn("née le 15/06/1980 à Lyon (Rhône), est députée de la"
                      " 1re circonscription (Ain, 01). Elle a 45 ans.", texte)
        self.assertIn("Elle siège depuis le 07/07/2024.", texte)
        self.assertIn("Depuis 2002, elle a aussi été députée sous les 15e et 16e législatures.",
                      texte)
        self.assertIn("membre de la commission des lois (secrétaire).", texte)
        self.assertIn("Profession déclarée : technicien.", texte)

    def test_ancien_depute_premier_mandat(self):
        depute = dict(self.DEPUTE, en_exercice=0, date_fin="2025-03-01",
                      cause_mandat="remplacement d'un député nommé au Gouvernement")
        texte = " ".join(portrait.rediger(dict(self.ACTEUR, civilite="M."), depute, [], ["17"]))
        self.assertIn("a été député de la 1re circonscription", texte)
        self.assertIn("du 07/07/2024 au 01/03/2025, en remplacement d'un député nommé"
                      " au Gouvernement.", texte)
        # L'historique ne remonte qu'à 2002 : jamais d'affirmation de premier mandat.
        self.assertNotIn("premier mandat", texte)


# --------------------------------------------------------------- étape 3

class Circonscriptions(unittest.TestCase):
    def test_conversion_des_contours(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "preparer_contours",
            os.path.join(os.path.dirname(__file__), "..", "outils", "preparer_contours.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        carre = [[2.0000001, 48.0], [2.1, 48.0], [2.1, 48.123456789], [2.0000001, 48.0]]
        resultat = module.convertir({"features": [
            {"properties": {"codeDepartement": "ZA", "codeCirconscription": "ZA03"},
             "geometry": {"type": "Polygon", "coordinates": [carre]}},
            {"properties": {"codeDepartement": "2A", "codeCirconscription": "2A01"},
             "geometry": {"type": "MultiPolygon", "coordinates": [[carre], [carre]]}}]})
        # Code outre-mer du ministère traduit, numéro sans zéro initial, 5 décimales.
        self.assertEqual(resultat["971"]["3"],
                         [[[2.0, 48.0, 2.1, 48.0, 2.1, 48.12346, 2.0, 48.0]]])
        self.assertEqual(len(resultat["2A"]["1"]), 2)

    def test_depute_associe_a_chaque_contour(self):
        with tempfile.TemporaryDirectory() as dossier:
            pathlib.Path(dossier, "10.json").write_text(
                json.dumps({"2": [[[0, 0, 1, 0, 1, 1]]], "3": [[[5, 5, 6, 5, 6, 6]]]}))
            deputes = [
                {"acteur_uid": "PA1", "prenom": "Ada", "nom": "Durand", "en_exercice": 1,
                 "num_departement": "10", "departement": "Aube", "num_circo": "2",
                 "groupe_sigle": "UN"},
                # Ancien député de la même circonscription : ne doit pas être retenu.
                {"acteur_uid": "PA2", "prenom": "Léo", "nom": "Martin", "en_exercice": 0,
                 "num_departement": "10", "departement": "Aube", "num_circo": "2",
                 "groupe_sigle": "UN"}]
            resultat = site.circonscriptions(
                deputes, {"PA1": "deputes/ada-durand.html", "PA2": "deputes/leo-martin.html"},
                dossier)
        self.assertEqual(resultat["10"]["nom"], "Aube")
        self.assertEqual(resultat["10"]["circos"]["2"]["depute"],
                         {"nom": "Ada Durand", "groupe": "UN", "lien": "deputes/ada-durand.html"})
        self.assertIsNone(resultat["10"]["circos"]["3"]["depute"])  # siège vacant

    def test_contours_livres_avec_le_code(self):
        fichiers = os.listdir(site.CONTOURS)
        self.assertEqual(len(fichiers), 102)
        total = sum(len(json.loads(pathlib.Path(site.CONTOURS, f).read_text()))
                    for f in fichiers)
        self.assertEqual(total, 559)


class PresenceEnCommission(unittest.TestCase):
    def test_seules_les_feuilles_exploitables_comptent(self):
        with tempfile.TemporaryDirectory() as dossier:
            db = base_indicateurs(dossier)
            reunions = [  # uid, état, date, présences de PA1 et PA2
                ("R1", "Confirmé", "2025-03-01", "présent", "absent"),   # comptée
                ("R2", "Confirmé", "2025-03-02", "excusé", "présent"),   # comptée
                ("R3", "Confirmé", "2025-03-03", "absent", "absent"),    # feuille non remplie
                ("R4", "Annulé", "2025-03-04", "absent", "présent"),     # annulée
                ("R5", "Confirmé", "2099-01-01", "absent", "présent")]   # à venir
            for uid, etat, jour, p1, p2 in reunions:
                db.execute("INSERT INTO reunions VALUES (?, 'commission', ?, NULL, 'C1', ?,"
                           " NULL, NULL)", (uid, jour + "T09:00:00", etat))
                db.executemany("INSERT INTO presences VALUES (?,?,?)",
                               [(uid, "PA1", p1), (uid, "PA2", p2)])
            with db:
                indicateurs.calculer(db, aujourdhui="2026-01-01")
            i = dict(db.execute("SELECT * FROM indicateurs WHERE acteur_uid = 'PA1'").fetchone())
            self.assertEqual((i["commission_present"], i["commission_absent"],
                              i["commission_excuse"]), (1, 0, 1))
            comptees = [l[0] for l in db.execute("SELECT uid FROM reunions_comptees ORDER BY 1")]
            self.assertEqual(comptees, ["R1", "R2"])
            db.close()


class MentionsLegales(unittest.TestCase):
    def test_page_generee_seulement_avec_un_editeur(self):
        with tempfile.TemporaryDirectory() as dossier:
            db = base_indicateurs(dossier)
            sans = os.path.join(dossier, "sans")
            site.generer(db, sans, journal=lambda m: None)
            self.assertFalse(os.path.exists(os.path.join(sans, "mentions-legales.html")))
            self.assertNotIn("mentions-legales", pathlib.Path(sans, "index.html").read_text("utf-8"))
            avec = os.path.join(dossier, "avec")
            site.generer(db, avec, journal=lambda m: None, api_url="https://a.fr",
                         editeur="Ada <Durand>", contact="contact@exemple.fr")
            db.close()
            mentions = pathlib.Path(avec, "mentions-legales.html").read_text("utf-8")
            self.assertIn("Ada &lt;Durand&gt;", mentions)   # le nom est échappé
            self.assertIn("contact@exemple.fr", mentions)
            self.assertIn("Scaleway SAS", mentions)
            fiche_html = pathlib.Path(avec, "deputes", "ada-durand.html").read_text("utf-8")
            self.assertIn('href="../mentions-legales.html"', fiche_html)
            confidentialite = pathlib.Path(avec, "confidentialite.html").read_text("utf-8")
            self.assertIn("Le responsable du traitement est Ada &lt;Durand&gt;.", confidentialite)
            self.assertIn("écrivez à contact@exemple.fr", confidentialite)
            # Page « Pourquoi », liée depuis la barre de navigation de chaque page.
            pourquoi = pathlib.Path(avec, "pourquoi.html").read_text("utf-8")
            self.assertIn("<h1>Pourquoi suivre son député ?</h1>", pourquoi)
            self.assertIn("senat.fr/rap/r25-802", pourquoi)
            self.assertIn("Tout mandat impératif est nul", pourquoi)
            self.assertIn('href="../pourquoi.html"', fiche_html)

    def test_exemple_lu_dans_la_base(self):
        with tempfile.TemporaryDirectory() as dossier:
            db = base.ouvrir(os.path.join(dossier, "e.sqlite"))
            self.assertNotIn("Un exemple", site.pourquoi(db))     # scrutin absent : omis
            db.execute("INSERT INTO scrutins (uid, numero, date, titre, nb_pour, nb_contre,"
                       " nb_abstentions) VALUES ('S', 8430, '2026-07-21', 'l''ensemble du projet"
                       " de loi relatif à la protection des enfants (première lecture).', 378,"
                       " 7, 173)")
            page = site.pourquoi(db)
            self.assertIn("Le 21/07/2026, sur l’ensemble du projet de loi relatif à la "
                          "protection des enfants (première lecture), 378 députés ont voté pour, "
                          "7 contre, et 173 se sont abstenus", page)
            self.assertIn("80 %", page)
            db.close()


class EcrireAuDepute(unittest.TestCase):
    ACTEUR = {"civilite": "Mme", "prenom": "Ada", "nom": "Durand"}
    DEPUTE = {"num_circo": "2", "departement": "Aube"}

    def test_adresse_officielle_preferee(self):
        contacts = [{"type": "Mèl", "valeur": "permanence@exemple.fr"},
                    {"type": "Twitter", "valeur": "@ada"},
                    {"type": "Mèl", "valeur": "Ada.Durand@assemblee-nationale.fr"}]
        self.assertEqual(fiche.adresse_officielle(contacts), "Ada.Durand@assemblee-nationale.fr")
        self.assertEqual(fiche.adresse_officielle(contacts[:2]), "permanence@exemple.fr")
        self.assertIsNone(fiche.adresse_officielle(contacts[1:2]))

    def test_message_et_lien(self):
        from urllib.parse import parse_qs, unquote, urlsplit
        objet, texte = fiche.message_au_depute(self.ACTEUR, self.DEPUTE)
        self.assertTrue(texte.startswith("Madame la députée,\n\nJ'habite votre circonscription"
                                         " (2e circonscription, Aube)."))
        self.assertIn("[Votre message]", texte)
        scrutin = {"numero": 12, "date": "2026-11-04", "titre": "le projet de loi & annexes.",
                   "position": "abstention"}
        objet, texte = fiche.message_au_depute(self.ACTEUR, self.DEPUTE, scrutin)
        self.assertEqual(objet, "Votre vote du 04/11/2026 (scrutin n° 12)")
        self.assertIn("portant sur le projet de loi & annexes, vous vous êtes abstenue.", texte)
        self.assertIn("https://www.assemblee-nationale.fr/dyn/17/scrutins/12", texte)
        absente = dict(scrutin, position=None)
        self.assertIn("vous n'avez pas pris part au vote",
                      fiche.message_au_depute(dict(self.ACTEUR, civilite="M."), self.DEPUTE,
                                              absente)[1])
        # Le lien ne doit contenir aucun caractère brut qui casserait l'adresse.
        lien = fiche.lien_courriel("ada@exemple.fr", objet, texte)
        parties = urlsplit(lien)
        self.assertEqual((parties.scheme, parties.path), ("mailto", "ada@exemple.fr"))
        self.assertNotRegex(parties.query, r"[ \n&]annexes")
        champs = parse_qs(parties.query)
        self.assertEqual((champs["subject"][0], champs["body"][0]), (objet, texte))

    def test_fiche(self):
        with tempfile.TemporaryDirectory() as dossier:
            db = base_indicateurs(dossier)
            db.execute("INSERT INTO contacts VALUES ('AD1', 'PA1', 'Mèl',"
                       " 'Ada.Durand@assemblee-nationale.fr')")
            db.execute("UPDATE deputes SET en_exercice = 0 WHERE acteur_uid = 'PA2'")
            db.execute("INSERT INTO contacts VALUES ('AD2', 'PA2', 'Mèl', 'leo@exemple.fr')")
            _, _, actif = fiche.corps(db, "PA1")
            _, _, ancien = fiche.corps(db, "PA2")
            _, _, sans_adresse = fiche.corps(db, "PA3")
            db.close()
        self.assertIn('id="courrier" data-adresse="Ada.Durand@assemblee-nationale.fr"', actif)
        self.assertIn('id="envoi-defaut" href="mailto:Ada.Durand@assemblee-nationale.fr?subject=',
                      actif)
        self.assertIn('id="envoi-gmail" target="_blank" rel="noopener" href="https://mail.google.com'
                      '/mail/?view=cm&amp;fs=1&amp;tf=cm&amp;to=Ada.Durand%40assemblee-nationale.fr'
                      '&amp;su=', actif)
        self.assertIn("L’interroger sur ce vote", actif)
        self.assertIn('data-objet="Votre vote du 10/07/2025 (scrutin n° 2)"', actif)
        for page in (ancien, sans_adresse):   # ancien député, ou pas d'adresse publiée
            self.assertNotIn('id="courrier"', page)
            self.assertNotIn("interroger", page)

    def test_liens_des_messageries(self):
        from urllib.parse import parse_qs, urlsplit
        liens = fiche.liens_envoi("ada@exemple.fr", "Objet & co", "Ligne 1\nLigne 2")
        gmail = parse_qs(urlsplit(liens["gmail"]).query)
        self.assertEqual((gmail["to"][0], gmail["su"][0], gmail["body"][0]),
                         ("ada@exemple.fr", "Objet & co", "Ligne 1\nLigne 2"))
        for nom in ("outlook", "yahoo"):
            champs = parse_qs(urlsplit(liens[nom]).query)
            self.assertEqual((champs["to"][0], champs["subject"][0], champs["body"][0]),
                             ("ada@exemple.fr", "Objet & co", "Ligne 1\nLigne 2"))
        self.assertTrue(liens["defaut"].startswith("mailto:ada@exemple.fr?subject="))


from collecte import themes  # noqa: E402


class Themes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_commission_saisie_au_fond(self):
        def acte(code, organe=None, enfants=None):
            a = {"codeActe": code, "organeRef": organe}
            if enfants:
                a["actesLegislatifs"] = {"acteLegislatif": enfants}
            return a
        # Le Sénat a été saisi en premier, puis l'Assemblée en première et en
        # nouvelle lecture : seule la première saisie de l'Assemblée compte.
        dossier = {"dossierParlementaire": {
            "uid": "DL1", "@xsi:type": "DossierLegislatif_Type", "legislature": "17",
            "titreDossier": {"titre": "Protéger l'eau", "titreChemin": "eau"},
            "procedureParlementaire": {"libelle": "Proposition de loi ordinaire"},
            "actesLegislatifs": {"acteLegislatif": [
                acte("SN1", enfants=acte("SN1-COM", "PO_SN", acte("SN1-COM-FOND-SAISIE", "PO_SN"))),
                acte("AN1", enfants=[acte("AN1-DEPOT"), acte("AN1-COM", "PO1", [
                    acte("AN1-COM-AVIS-SAISIE", "PO9"), acte("AN1-COM-FOND-SAISIE", "PO1")])]),
                acte("ANNLEC", enfants=acte("ANNLEC-COM-FOND-SAISIE", "PO2"))]}}}
        sans = {"dossierParlementaire": {"uid": "DL2", "legislature": "17",
                                         "titreDossier": {"titre": "Résolution"}}}
        chemin = archive(self.tmp.name, "d.zip", {
            "json/dossierParlementaire/DL1.json": dossier,
            "json/dossierParlementaire/DL2.json": sans})
        db = base.ouvrir(os.path.join(self.tmp.name, "b.sqlite"))
        chargeurs.charger_dossiers(db, [chemin])
        self.assertEqual(dict(db.execute("SELECT uid, commission_fond FROM dossiers")),
                         {"DL1": "PO1", "DL2": None})
        db.close()

    def test_colonne_ajoutee_a_une_base_existante(self):
        import sqlite3
        chemin = os.path.join(self.tmp.name, "ancienne.sqlite")
        ancienne = sqlite3.connect(chemin)
        ancienne.execute("CREATE TABLE dossiers (uid TEXT PRIMARY KEY, type TEXT,"
                         " legislature TEXT, titre TEXT, chemin TEXT, procedure TEXT)")
        ancienne.execute("INSERT INTO dossiers (uid) VALUES ('DL1')")
        ancienne.commit()
        self.assertFalse(themes.disponible(ancienne))
        self.assertEqual(themes.pour_dossiers(ancienne, ["DL1"]), {})
        ancienne.close()
        db = base.ouvrir(chemin)
        self.assertTrue(themes.disponible(db))
        self.assertEqual(db.execute("SELECT commission_fond FROM dossiers").fetchone()[0], None)
        db.close()

    def test_theme_selon_la_commission_et_corrections(self):
        self.assertEqual(themes.theme_de_commission(
            "Commission des finances, de l'économie générale et du contrôle budgétaire"),
            "Budget et fiscalité")
        self.assertIsNone(themes.theme_de_commission("Commission spéciale chargée d'examiner…"))
        self.assertIsNone(themes.theme_de_commission(None))
        # Les textes de la commission des affaires économiques sont répartis d'après leur titre.
        eco = "Commission des affaires économiques"
        self.assertEqual(themes.theme_de_commission(eco, "Relancer le secteur du logement"),
                         "Logement et urbanisme")
        self.assertEqual(themes.theme_de_commission(eco, "Encadrer les loyers"),
                         "Logement et urbanisme")
        self.assertEqual(themes.theme_de_commission(eco, "Sauver la filière noisette et noix"),
                         "Agriculture et alimentation")
        for titre in ("Plafonner l'indice des loyers commerciaux",   # mot exclu
                      "Prolonger les titres restaurant pour tout produit alimentaire",
                      "La construction en zone agricole et le logement",  # deux thèmes
                      "Soutenir les commerces de proximité",          # aucun mot
                      "Interdire le vinyle", None):                   # « vin » : mot entier
            self.assertEqual(themes.theme_de_commission(eco, titre),
                             "Économie, énergie et consommation", titre)
        # Les mots-clés ne valent que pour la commission des affaires économiques.
        self.assertEqual(themes.theme_de_commission("Commission des lois", "Le logement"),
                         "Institutions, justice et sécurité")
        db = base.ouvrir(os.path.join(self.tmp.name, "t.sqlite"))
        db.executemany("INSERT INTO organes (uid, libelle) VALUES (?,?)",
                       [("PO1", "Commission des lois constitutionnelles"),
                        ("PO2", "Commission spéciale chargée d'examiner le texte")])
        db.executemany("INSERT INTO dossiers (uid, commission_fond) VALUES (?,?)",
                       [("D1", "PO1"), ("D2", "PO2"), ("D3", None), ("D4", "PO1")])
        corrections = {"D2": "Défense", "D4": "Affaires étrangères"}
        self.assertEqual(themes.pour_dossiers(db, ["D1", "D2", "D3", "D4", None], corrections),
                         {"D1": "Institutions, justice et sécurité", "D2": "Défense",
                          "D4": "Affaires étrangères"})
        db.close()

    def test_fichier_de_corrections(self):
        chemin = os.path.join(self.tmp.name, "c.csv")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("# commentaire\ndossier;theme;motif\nD1;Défense;parce que\n\n")
        self.assertEqual(themes.lire_corrections(chemin), {"D1": "Défense"})
        with open(chemin, "a", encoding="utf-8") as f:
            f.write("D2;Défence;faute de frappe\n")
        with self.assertRaises(ValueError):
            themes.lire_corrections(chemin)
        self.assertEqual(themes.lire_corrections(os.path.join(self.tmp.name, "absent.csv")), {})
        # Le fichier livré avec le code ne contient que des thèmes connus.
        self.assertTrue(themes.lire_corrections())


from collecte import etapes  # noqa: E402


def etape(code, date, statut=None, code_loi=None):
    return {"code": code, "date": date, "statut": statut, "code_loi": code_loi}


class Etapes(unittest.TestCase):
    def test_navette_jusqu_a_la_promulgation(self):
        suite = [etape("AN1-DEPOT", "2025-12-01"),
                 etape("AN1-DEBATS-SEANCE", "2025-12-11"),
                 etape("AN1-DEBATS-DEC", "2025-12-11", "adoptée")]
        self.assertEqual(etapes.decrire(suite), "Texte adopté par l'Assemblée nationale le "
                                                "11/12/2025, en 1re lecture")
        suite.append(etape("SN1-DEPOT", "2025-12-12"))
        self.assertEqual(etapes.decrire(suite), "Texte adopté par l'Assemblée nationale le "
                         "11/12/2025, en 1re lecture, puis transmis au Sénat le 12/12/2025")
        suite += [etape("SN1-DEBATS-SEANCE", "2026-05-27")]
        self.assertTrue(etapes.decrire(suite).endswith(
            "en 1re lecture ; examen en séance au Sénat depuis le 27/05/2026"))
        suite += [etape("SN1-DEBATS-DEC", "2026-05-28", "modifiée"),
                  etape("AN2-DEPOT", "2026-05-29")]
        self.assertEqual(etapes.decrire(suite), "Texte modifié par le Sénat le 28/05/2026, en 1re "
                         "lecture, puis transmis à l'Assemblée nationale le 29/05/2026")
        # Vote conforme : les deux assemblées ont adopté le même texte.
        suite.append(etape("AN2-DEBATS-DEC", "2026-07-01", "adoptée sans modification"))
        self.assertEqual(etapes.decrire(suite), "Texte adopté définitivement par le Parlement "
                                                "le 01/07/2026, pas encore promulgué")
        suite.append(etape("PROM-PUB", "2026-07-13", code_loi="2026-630"))
        self.assertEqual(etapes.decrire(suite), "Loi promulguée le 13/07/2026 (loi n° 2026-630)")

    def test_commission_mixte_paritaire_et_conseil_constitutionnel(self):
        # Les dates ne suivent pas toujours l'ordre du dossier : on trie par date.
        suite = [etape("SN1-DEBATS-DEC", "2026-04-14", "adopté"),
                 etape("AN1-DEBATS-DEC", "2026-07-07", "modifié"),
                 etape("CMP-DEPOT", "2026-07-07"),
                 etape("CMP-DEBATS-AN-DEC", "2026-07-08", "adopté, dans les conditions prévues à "
                       "l'article 45, alinéa 3, de la Constitution"),
                 etape("CMP-DEC", "2026-07-08", "Accord")]
        self.assertEqual(etapes.decrire(suite), "Texte adopté par l'Assemblée nationale le "
                         "08/07/2026, sur le texte de la commission mixte paritaire")
        suite.append(etape("CMP-DEBATS-SN-DEC", "2026-07-09", "adopté"))
        self.assertEqual(etapes.decrire(suite), "Texte adopté définitivement par le Parlement "
                                                "le 09/07/2026, pas encore promulgué")
        suite.append(etape("CC-CONCLUSION", "2026-07-23", "Partiellement conforme"))
        self.assertEqual(etapes.decrire(suite), "Décision du Conseil constitutionnel le 23/07/2026"
                         " : partiellement conforme ; loi pas encore promulguée")
        suite.append(etape("PROM-PUB", "2026-07-23", code_loi="2026-651"))
        self.assertEqual(etapes.decrire(suite), "Loi promulguée le 23/07/2026 (loi n° 2026-651), "
                         "après une décision du Conseil constitutionnel : partiellement conforme")

    def test_autres_cas(self):
        self.assertEqual(etapes.decrire([etape("CMP-DEC", "2026-06-03", "Désaccord")]),
                         "Désaccord en commission mixte paritaire le 03/06/2026")
        self.assertEqual(etapes.decrire([etape("ANLDEF-DEBATS-DEC", "2026-07-15", "adoptée")]),
                         "Texte adopté définitivement par le Parlement le 15/07/2026, pas encore "
                         "promulgué")
        self.assertEqual(etapes.decrire([etape("ANLUNI-DEBATS-DEC", "2026-10-08", "rejetée")]),
                         "Texte rejeté par l'Assemblée nationale le 08/10/2026, en lecture unique")
        self.assertEqual(etapes.decrire([etape("AN1-DEPOT", "2026-06-23"),
                                         etape("AN1-DEBATS-SEANCE", "2026-10-08"),
                                         etape("AN1-DEBATS-SEANCE", "2026-10-09")]),
                         "Examen en séance commencé à l'Assemblée nationale le 08/10/2026, sans "
                         "vote sur l'ensemble du texte à ce jour")
        self.assertEqual(etapes.decrire([etape("AN1-DEPOT", "2026-01-05"),
                                         etape("AN1-RTRINI", "2026-04-09")]),
                         "Texte retiré par son auteur le 09/04/2026")
        self.assertEqual(etapes.decrire([etape("SN1-DEPOT", "2024-10-15")]),
                         "Texte déposé au Sénat le 15/10/2024")
        self.assertEqual(etapes.decrire([etape("AN1-DEPOT", None)]), "")

    def test_chargement(self):
        with tempfile.TemporaryDirectory() as tmp:
            acte = lambda code, type_, date=None, **extra: {
                "codeActe": code, "@xsi:type": type_, "dateActe": date, **extra}
            dossier = {"dossierParlementaire": {
                "uid": "DL1", "legislature": "17", "titreDossier": {"titre": "Eau"},
                "actesLegislatifs": {"acteLegislatif": {
                    **acte("AN1", "Etape_Type"), "actesLegislatifs": {"acteLegislatif": [
                        acte("AN1-DEPOT", "DepotInitiative_Type", "2026-01-05T00:00:00.000+01:00"),
                        {**acte("AN1-DEBATS", "Etape_Type"), "actesLegislatifs": {
                            "acteLegislatif": acte(
                                "AN1-DEBATS-DEC", "Decision_Type", "2026-02-01T00:00:00.000+01:00",
                                statutConclusion={"libelle": "adoptée"})}}]}}}}}
            chemin = archive(tmp, "d.zip", {"json/dossierParlementaire/DL1.json": dossier})
            db = base.ouvrir(os.path.join(tmp, "b.sqlite"))
            chargeurs.charger_dossiers(db, [chemin])
            self.assertEqual([tuple(r) for r in db.execute(
                "SELECT code, date, statut FROM etapes ORDER BY ordre")],
                [("AN1-DEPOT", "2026-01-05", None), ("AN1-DEBATS-DEC", "2026-02-01", "adoptée")])
            self.assertEqual(etapes.pour_dossiers(db, ["DL1", "DL2"]), {
                "DL1": "Texte adopté par l'Assemblée nationale le 01/02/2026, en 1re lecture"})
            db.close()


class Etapes493(unittest.TestCase):
    """Textes adoptés sans vote, le Gouvernement ayant engagé sa responsabilité."""
    ADOPTE = ("considéré comme adopté par l'Assemblée nationale en application de l'article 49, "
              "alinéa 3 de la Constitution")
    REJETE = ADOPTE.replace("adopté", "rejeté")
    SUITE = ", sans vote sur le texte, le Gouvernement ayant engagé sa responsabilité " \
            "(article 49, alinéa 3, de la Constitution)"

    def test_premiere_lecture(self):
        self.assertEqual(etapes.decrire([etape("AN1-DEBATS-DEC", "2026-01-10", self.ADOPTE),
                                         etape("SN1-DEPOT", "2026-01-12")]),
                         "Texte considéré comme adopté par l'Assemblée nationale le 10/01/2026, "
                         "en 1re lecture" + self.SUITE + ", puis transmis au Sénat le 12/01/2026")

    def test_nouvelle_lecture_n_est_pas_definitive(self):
        # Chemin suivi par le budget 2026.
        suite = [etape("AN1-DEBATS-DEC", "2025-11-21", "rejeté"),
                 etape("SN1-DEBATS-DEC", "2025-12-15", "modifié"),
                 etape("CMP-DEC", "2026-01-02", "Désaccord"),
                 etape("ANNLEC-DEBATS-DEC", "2026-01-27", self.ADOPTE)]
        self.assertEqual(etapes.decrire(suite), "Texte considéré comme adopté par l'Assemblée "
                         "nationale le 27/01/2026, en nouvelle lecture" + self.SUITE)
        suite.append(etape("ANLDEF-DEBATS-DEC", "2026-02-02", self.ADOPTE))
        self.assertEqual(etapes.decrire(suite), "Texte adopté définitivement par le Parlement le "
                                                "02/02/2026, pas encore promulgué")

    def test_parcours_etapes_franchies(self):
        # Budget 2026 : seules les étapes passées et datées, aucune étape à venir.
        suite = [etape("AN1-DEPOT", "2025-10-14"),
                 etape("AN1-DEBATS-SEANCE", "2025-10-24"),
                 etape("AN1-DEBATS-DEC", "2025-11-21", "rejeté"),
                 etape("SN1-DEPOT", "2025-11-22"),
                 etape("SN1-DEBATS-DEC", "2025-12-15", "modifié"),
                 etape("CMP-DEC", "2026-01-02", "Désaccord"),
                 etape("ANNLEC-DEBATS-DEC", "2026-01-27", self.ADOPTE),
                 etape("ANLDEF-DEPOT", None)]
        self.assertEqual([(e["libelle"], e["date"], e["sens"]) for e in etapes.parcours(suite)], [
            ("Dépôt, Assemblée", "2025-10-14", "neutre"),
            ("Assemblée, 1re lecture", "2025-11-21", "rejeté"),
            ("Sénat, 1re lecture", "2025-12-15", "adopté"),
            ("Commission mixte paritaire, désaccord", "2026-01-02", "rejeté"),
            ("Assemblée, nouvelle lecture, sans vote (49.3)", "2026-01-27", "adopté")])
        longue = [etape("AN1-DEPOT", "2025-01-01")] + [
            etape(f"AN{i}-DEBATS-DEC", f"2025-02-{i:02d}", "adopté") for i in range(1, 12)]
        self.assertEqual(len(etapes.parcours(longue)), etapes.PARCOURS_MAX)
        self.assertEqual(etapes.parcours(longue)[-1]["date"], "2025-02-11")  # les plus récentes
        self.assertEqual(etapes.parcours([etape("AN1-DEPOT", None)]), [])

    def test_texte_de_cmp(self):
        cmp = [etape("CMP-DEC", "2025-01-31", "Accord"),
               etape("CMP-DEBATS-AN-DEC", "2025-02-05", self.ADOPTE)]
        self.assertTrue(etapes.decrire(cmp).startswith(
            "Texte considéré comme adopté par l'Assemblée nationale le 05/02/2025, sur le texte "
            "de la commission mixte paritaire, sans vote"))
        cmp.append(etape("CMP-DEBATS-SN-DEC", "2025-02-06", "adopté"))
        self.assertEqual(etapes.decrire(cmp), "Texte adopté définitivement par le Parlement le "
                                              "06/02/2025, pas encore promulgué")
        # Motion de censure adoptée : le texte est considéré comme rejeté.
        self.assertTrue(etapes.decrire([etape("CMP-DEBATS-AN-DEC", "2024-12-04", self.REJETE)])
                        .startswith("Texte considéré comme rejeté par l'Assemblée nationale le "
                                    "04/12/2024"))

    def test_resolution_europeenne(self):
        self.assertEqual(etapes.decrire([etape(
            "ANLUNI-DEBATS-DEC", "2026-03-01",
            "considérée comme définitive en application de l'article 151-7 du Règlement")]),
            "Texte considéré comme définitif par l'Assemblée nationale le 01/03/2026")


from collecte import libelles  # noqa: E402


class Libelles(unittest.TestCase):
    def test_seuls_les_libelles_valides_sont_retenus(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "l.csv")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write("# commentaire\ndossier;statut;libelle;titre_officiel\n"
                        "D1;validé;Budget de l'État pour 2027;Projet de loi de finances\n"
                        "D2;proposé;Pas encore relu;Titre\n")
            self.assertEqual(libelles.valides(chemin), {"D1": "Budget de l'État pour 2027"})
            self.assertEqual(libelles.pour_dossiers(["D1", "D2", "D3", None], chemin),
                             {"D1": "Budget de l'État pour 2027"})
            for ligne in ("D3;validee;Faute;T\n", "D4;validé;;T\n", "D5;validé;" + "x" * 121 + ";T\n"):
                with open(chemin, "a", encoding="utf-8") as f:
                    f.write(ligne)
                with self.assertRaises(ValueError):
                    libelles.lire(chemin)
                with open(chemin, encoding="utf-8") as f:
                    contenu = f.read().replace(ligne, "")
                with open(chemin, "w", encoding="utf-8") as f:
                    f.write(contenu)
        # Le fichier livré avec le code se lit sans erreur.
        self.assertTrue(libelles.lire())
