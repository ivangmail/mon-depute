"""Schéma de la base SQLite.

Les dates sont stockées au format ISO (AAAA-MM-JJ), qui se trie correctement ;
elles sont converties en JJ/MM/AAAA à l'affichage.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    fichier        TEXT PRIMARY KEY,
    jeu            TEXT NOT NULL,
    url            TEXT NOT NULL,
    etag           TEXT,
    last_modified  TEXT,
    taille         INTEGER,
    telecharge_le  TEXT,
    charge_le      TEXT
);

CREATE TABLE IF NOT EXISTS organes (
    uid            TEXT PRIMARY KEY,
    code_type      TEXT,
    libelle        TEXT,
    libelle_abrege TEXT,
    legislature    TEXT,
    date_debut     TEXT,
    date_fin       TEXT,
    couleur        TEXT,
    parent_uid     TEXT
);

CREATE TABLE IF NOT EXISTS acteurs (
    uid              TEXT PRIMARY KEY,
    civilite         TEXT,
    prenom           TEXT,
    nom              TEXT,
    date_naissance   TEXT,
    lieu_naissance   TEXT,
    profession       TEXT,
    url_hatvp        TEXT
);

CREATE TABLE IF NOT EXISTS mandats (
    uid          TEXT PRIMARY KEY,
    acteur_uid   TEXT NOT NULL,
    organe_uid   TEXT,
    type_organe  TEXT,
    legislature  TEXT,
    date_debut   TEXT,
    date_fin     TEXT,
    qualite      TEXT
);
CREATE INDEX IF NOT EXISTS mandats_acteur ON mandats(acteur_uid);
CREATE INDEX IF NOT EXISTS mandats_organe ON mandats(organe_uid);

CREATE TABLE IF NOT EXISTS contacts (
    uid         TEXT PRIMARY KEY,
    acteur_uid  TEXT NOT NULL,
    type        TEXT,
    valeur      TEXT
);
CREATE INDEX IF NOT EXISTS contacts_acteur ON contacts(acteur_uid);

-- Une ligne par député de la législature, calculée à partir des mandats.
CREATE TABLE IF NOT EXISTS deputes (
    acteur_uid       TEXT PRIMARY KEY,
    en_exercice      INTEGER NOT NULL,
    mandat_uid       TEXT,
    date_debut       TEXT,
    date_fin         TEXT,
    cause_mandat     TEXT,
    region           TEXT,
    departement      TEXT,
    num_departement  TEXT,
    num_circo        TEXT,
    place_hemicycle  TEXT,
    groupe_uid       TEXT,
    groupe_sigle     TEXT,
    groupe_libelle   TEXT
);
CREATE INDEX IF NOT EXISTS deputes_circo ON deputes(num_departement, num_circo);

CREATE TABLE IF NOT EXISTS scrutins (
    uid           TEXT PRIMARY KEY,
    numero        INTEGER,
    date          TEXT,
    type_vote     TEXT,
    sort          TEXT,
    titre         TEXT,
    demandeur     TEXT,
    dossier_uid   TEXT,
    seance_uid    TEXT,
    nb_votants    INTEGER,
    nb_exprimes   INTEGER,
    nb_pour       INTEGER,
    nb_contre     INTEGER,
    nb_abstentions INTEGER
);
CREATE INDEX IF NOT EXISTS scrutins_date ON scrutins(date);

CREATE TABLE IF NOT EXISTS votes (
    scrutin_uid    TEXT NOT NULL,
    acteur_uid     TEXT NOT NULL,
    groupe_uid     TEXT,
    position       TEXT NOT NULL,  -- pour, contre, abstention, non_votant, non_votant_volontaire
    par_delegation INTEGER,
    PRIMARY KEY (scrutin_uid, acteur_uid)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS votes_acteur ON votes(acteur_uid);

CREATE TABLE IF NOT EXISTS reunions (
    uid              TEXT PRIMARY KEY,
    type             TEXT,   -- commission, seance, initiative_parlementaire
    debut            TEXT,
    fin              TEXT,
    organe_uid       TEXT,
    etat             TEXT,
    objet            TEXT,
    compte_rendu_uid TEXT
);
CREATE INDEX IF NOT EXISTS reunions_debut ON reunions(debut);

CREATE TABLE IF NOT EXISTS presences (
    reunion_uid  TEXT NOT NULL,
    acteur_uid   TEXT NOT NULL,
    presence     TEXT NOT NULL,  -- présent, absent, excusé
    PRIMARY KEY (reunion_uid, acteur_uid)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS presences_acteur ON presences(acteur_uid);

CREATE TABLE IF NOT EXISTS questions (
    uid             TEXT PRIMARY KEY,
    type            TEXT,   -- QE, QG, QOSD
    numero          INTEGER,
    acteur_uid      TEXT,
    groupe_sigle    TEXT,
    ministere       TEXT,
    rubrique        TEXT,
    analyse         TEXT,
    date_question   TEXT,
    date_reponse    TEXT,
    statut          TEXT,
    texte_question  TEXT,
    texte_reponse   TEXT
);
CREATE INDEX IF NOT EXISTS questions_acteur ON questions(acteur_uid);

CREATE TABLE IF NOT EXISTS dossiers (
    uid          TEXT PRIMARY KEY,
    type         TEXT,
    legislature  TEXT,
    titre        TEXT,
    chemin       TEXT,
    procedure    TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    uid           TEXT PRIMARY KEY,
    type          TEXT,
    denomination  TEXT,
    legislature   TEXT,
    titre         TEXT,
    date_depot    TEXT,
    dossier_uid   TEXT
);

CREATE TABLE IF NOT EXISTS documents_signataires (
    document_uid  TEXT NOT NULL,
    acteur_uid    TEXT NOT NULL,
    role          TEXT NOT NULL,  -- auteur, cosignataire (ou qualité fournie)
    PRIMARY KEY (document_uid, acteur_uid, role)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS documents_signataires_acteur ON documents_signataires(acteur_uid);

CREATE TABLE IF NOT EXISTS comptes_rendus (
    uid         TEXT PRIMARY KEY,
    seance_uid  TEXT,
    date        TEXT,
    session     TEXT,
    num_seance  TEXT,
    etat        TEXT
);

CREATE TABLE IF NOT EXISTS interventions (
    id               INTEGER PRIMARY KEY,
    compte_rendu_uid TEXT NOT NULL,
    ordre            INTEGER,
    acteur_uid       TEXT,
    orateur          TEXT,
    qualite          TEXT,
    role             TEXT,   -- « president » pour la présidence de séance
    code_grammaire   TEXT,
    sujet            TEXT,
    nb_mots          INTEGER,
    texte            TEXT
);
CREATE INDEX IF NOT EXISTS interventions_acteur ON interventions(acteur_uid);
CREATE INDEX IF NOT EXISTS interventions_cr ON interventions(compte_rendu_uid);

CREATE TABLE IF NOT EXISTS amendements (
    uid           TEXT PRIMARY KEY,
    numero        TEXT,
    texte_uid     TEXT,
    examen_uid    TEXT,
    organe_uid    TEXT,
    acteur_uid    TEXT,
    groupe_uid    TEXT,
    type_auteur   TEXT,
    date_depot    TEXT,
    etat          TEXT,
    sort          TEXT,
    article       TEXT,
    dispositif    TEXT,
    expose        TEXT
);
CREATE INDEX IF NOT EXISTS amendements_acteur ON amendements(acteur_uid);
CREATE INDEX IF NOT EXISTS amendements_texte ON amendements(texte_uid);

CREATE TABLE IF NOT EXISTS amendements_cosignataires (
    amendement_uid  TEXT NOT NULL,
    acteur_uid      TEXT NOT NULL,
    PRIMARY KEY (amendement_uid, acteur_uid)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS amendements_cosignataires_acteur
    ON amendements_cosignataires(acteur_uid);
"""


def ouvrir(chemin):
    connexion = sqlite3.connect(chemin)
    connexion.row_factory = sqlite3.Row
    connexion.execute("PRAGMA journal_mode = WAL")
    connexion.execute("PRAGMA synchronous = NORMAL")
    connexion.executescript(SCHEMA)
    return connexion
