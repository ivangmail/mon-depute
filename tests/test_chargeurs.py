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
        self.assertIn('class="bouton" href="mailto:Ada.Durand@assemblee-nationale.fr?subject=',
                      actif)
        self.assertIn("L’interroger sur ce vote", actif)
        self.assertIn("scrutin%20n%C2%B0%202", actif)
        for page in (ancien, sans_adresse):   # ancien député, ou pas d'adresse publiée
            self.assertNotIn('class="bouton"', page)
            self.assertNotIn("interroger", page)
