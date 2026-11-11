"""Indicateurs d'activité, calculés pour tous les députés à la fois.

Chaque règle appliquée ici est décrite en français courant dans la page
Méthodologie du site (collecte/site.py) : si l'une change, l'autre aussi.
"""

from .sources import LEGISLATURE

EXPRIMES = "('pour', 'contre', 'abstention')"
SOLENNEL = "scrutin public solennel"
# En dessous de ce nombre de scrutins solennels pendant le mandat, un taux
# n'a pas de sens (député arrivé récemment) : il n'est ni affiché ni moyenné.
MIN_SOLENNELS = 5
MIN_COMPARABLES = 20
MIN_REUNIONS = 10

SCHEMA = """
DROP TABLE IF EXISTS lignes_groupe;
CREATE TABLE lignes_groupe (
    scrutin_uid TEXT NOT NULL,
    groupe_uid  TEXT NOT NULL,
    position    TEXT NOT NULL,
    PRIMARY KEY (scrutin_uid, groupe_uid)
) WITHOUT ROWID;

DROP TABLE IF EXISTS indicateurs;
CREATE TABLE indicateurs (
    acteur_uid            TEXT PRIMARY KEY,
    scrutins_eligibles    INTEGER NOT NULL DEFAULT 0,
    scrutins_exprimes     INTEGER NOT NULL DEFAULT 0,
    solennels_eligibles   INTEGER NOT NULL DEFAULT 0,
    solennels_exprimes    INTEGER NOT NULL DEFAULT 0,
    votes_pour            INTEGER NOT NULL DEFAULT 0,
    votes_contre          INTEGER NOT NULL DEFAULT 0,
    votes_abstention      INTEGER NOT NULL DEFAULT 0,
    votes_non_votant      INTEGER NOT NULL DEFAULT 0,
    votes_comparables     INTEGER NOT NULL DEFAULT 0,
    votes_conformes       INTEGER NOT NULL DEFAULT 0,
    commission_present    INTEGER NOT NULL DEFAULT 0,
    commission_absent     INTEGER NOT NULL DEFAULT 0,
    commission_excuse     INTEGER NOT NULL DEFAULT 0,
    questions_ecrites     INTEGER NOT NULL DEFAULT 0,
    questions_gouvernement INTEGER NOT NULL DEFAULT 0,
    questions_orales      INTEGER NOT NULL DEFAULT 0,
    interventions_longues INTEGER NOT NULL DEFAULT 0,
    interventions_courtes INTEGER NOT NULL DEFAULT 0,
    amendements_deposes   INTEGER NOT NULL DEFAULT 0,
    amendements_adoptes   INTEGER NOT NULL DEFAULT 0,
    amendements_cosignes  INTEGER NOT NULL DEFAULT 0,
    propositions_auteur   INTEGER NOT NULL DEFAULT 0,
    propositions_cosignees INTEGER NOT NULL DEFAULT 0,
    nb_legislatures       INTEGER NOT NULL DEFAULT 1
);

DROP TABLE IF EXISTS moyennes;
CREATE TABLE moyennes (
    perimetre  TEXT NOT NULL,   -- 'tous' ou l'identifiant d'un groupe
    indicateur TEXT NOT NULL,   -- solennels, loyaute, commission
    valeur     REAL,
    effectif   INTEGER,
    PRIMARY KEY (perimetre, indicateur)
) WITHOUT ROWID;
"""


def _maj(db, colonnes, requete, parametres=()):
    """Reporte dans `indicateurs` le résultat d'une requête dont la première
    colonne est l'identifiant du député."""
    affectations = ", ".join(f"{c} = ?" for c in colonnes)
    for ligne in db.execute(requete, parametres).fetchall():
        db.execute(f"UPDATE indicateurs SET {affectations} WHERE acteur_uid = ?",
                   (*[v or 0 for v in ligne[1:]], ligne[0]))


def calculer(db):
    db.executescript(SCHEMA)
    db.execute("INSERT INTO indicateurs (acteur_uid) SELECT acteur_uid FROM deputes")

    # Ligne d'un groupe sur un scrutin : la position exprimée la plus fréquente
    # parmi ses membres ce jour-là. En cas d'égalité, le groupe n'a pas de ligne.
    db.execute(f"""
        INSERT INTO lignes_groupe
        WITH decompte AS (
            SELECT scrutin_uid, groupe_uid, position, count(*) AS n FROM votes
            WHERE position IN {EXPRIMES} AND groupe_uid IS NOT NULL
            GROUP BY scrutin_uid, groupe_uid, position),
        classe AS (
            SELECT *, max(n) OVER (PARTITION BY scrutin_uid, groupe_uid) AS maxi
            FROM decompte)
        SELECT scrutin_uid, groupe_uid, min(position) FROM classe WHERE n = maxi
        GROUP BY scrutin_uid, groupe_uid HAVING count(*) = 1""")

    # Scrutins tenus pendant que le député siégeait (un passage au gouvernement
    # interrompt le mandat : ces périodes ne comptent pas).
    _maj(db, ("scrutins_eligibles", "solennels_eligibles"), """
        SELECT m.acteur_uid, count(DISTINCT s.uid),
               count(DISTINCT CASE WHEN s.type_vote = ? THEN s.uid END)
        FROM mandats m JOIN scrutins s
          ON s.date >= m.date_debut AND s.date <= coalesce(m.date_fin, '9999')
        WHERE m.type_organe = 'ASSEMBLEE' AND m.legislature = ?
        GROUP BY m.acteur_uid""", (SOLENNEL, LEGISLATURE))

    _maj(db, ("scrutins_exprimes", "solennels_exprimes", "votes_pour", "votes_contre",
              "votes_abstention", "votes_non_votant"), f"""
        SELECT v.acteur_uid,
               sum(v.position IN {EXPRIMES}),
               sum(v.position IN {EXPRIMES} AND s.type_vote = ?),
               sum(v.position = 'pour'), sum(v.position = 'contre'),
               sum(v.position = 'abstention'),
               sum(v.position NOT IN {EXPRIMES})
        FROM votes v JOIN scrutins s ON s.uid = v.scrutin_uid
        GROUP BY v.acteur_uid""", (SOLENNEL,))

    # Loyauté : le vote est comparé à la ligne du groupe auquel le député
    # appartenait le jour du scrutin (l'Assemblée publie ce groupe vote par vote).
    _maj(db, ("votes_comparables", "votes_conformes"), f"""
        SELECT v.acteur_uid, count(*), sum(v.position = l.position)
        FROM votes v JOIN lignes_groupe l
          ON l.scrutin_uid = v.scrutin_uid AND l.groupe_uid = v.groupe_uid
        JOIN organes o ON o.uid = v.groupe_uid
        WHERE v.position IN {EXPRIMES} AND coalesce(o.libelle_abrege, '') <> 'NI'
        GROUP BY v.acteur_uid""")

    _maj(db, ("commission_present", "commission_absent", "commission_excuse"), """
        SELECT p.acteur_uid, sum(p.presence = 'présent'), sum(p.presence = 'absent'),
               sum(p.presence = 'excusé')
        FROM presences p JOIN reunions r ON r.uid = p.reunion_uid
        WHERE r.type = 'commission' GROUP BY p.acteur_uid""")

    _maj(db, ("questions_ecrites", "questions_gouvernement", "questions_orales"), """
        SELECT acteur_uid, sum(type = 'QE'), sum(type = 'QG'), sum(type = 'QOSD')
        FROM questions GROUP BY acteur_uid""")

    _maj(db, ("interventions_longues", "interventions_courtes"), """
        SELECT acteur_uid, sum(nb_mots >= 20), sum(nb_mots < 20) FROM interventions
        WHERE acteur_uid IS NOT NULL AND role IS NOT 'president' GROUP BY acteur_uid""")

    _maj(db, ("amendements_deposes", "amendements_adoptes"), """
        SELECT acteur_uid, count(*), sum(sort = 'Adopté') FROM amendements
        WHERE acteur_uid IS NOT NULL AND type_auteur = 'Député' GROUP BY acteur_uid""")
    _maj(db, ("amendements_cosignes",), """
        SELECT acteur_uid, count(*) FROM amendements_cosignataires GROUP BY acteur_uid""")

    _maj(db, ("propositions_auteur", "propositions_cosignees"), """
        SELECT s.acteur_uid, sum(s.role = 'auteur'), sum(s.role = 'cosignataire')
        FROM documents_signataires s JOIN documents d ON d.uid = s.document_uid
        WHERE d.type = 'PION' AND d.legislature = ? GROUP BY s.acteur_uid""",
         (LEGISLATURE,))

    _maj(db, ("nb_legislatures",), """
        SELECT acteur_uid, count(DISTINCT legislature) FROM mandats
        WHERE type_organe = 'ASSEMBLEE' AND legislature IS NOT NULL
        GROUP BY acteur_uid""")

    # Moyennes de comparaison : moyenne des taux individuels des députés en
    # exercice, pour tous puis groupe par groupe.
    taux = {
        "solennels": ("1.0 * i.solennels_exprimes / i.solennels_eligibles",
                      f"i.solennels_eligibles >= {MIN_SOLENNELS}"),
        "loyaute": ("1.0 * i.votes_conformes / i.votes_comparables",
                    f"i.votes_comparables >= {MIN_COMPARABLES}"),
        "commission": ("1.0 * i.commission_present / (i.commission_present"
                       " + i.commission_absent + i.commission_excuse)",
                       "(i.commission_present + i.commission_absent"
                       f" + i.commission_excuse) >= {MIN_REUNIONS}"),
    }
    for nom, (formule, condition) in taux.items():
        base = (f"FROM indicateurs i JOIN deputes d ON d.acteur_uid = i.acteur_uid"
                f" WHERE d.en_exercice = 1 AND {condition}")
        db.execute(f"INSERT INTO moyennes SELECT 'tous', ?, avg({formule}), count(*) {base}",
                   (nom,))
        db.execute(f"INSERT INTO moyennes SELECT d.groupe_uid, ?, avg({formule}), count(*)"
                   f" {base} AND d.groupe_uid IS NOT NULL GROUP BY d.groupe_uid", (nom,))
    return db.execute("SELECT count(*) FROM indicateurs").fetchone()[0]


def taux(numerateur, denominateur, minimum=1):
    """Taux entre 0 et 1, ou None si l'effectif est trop faible pour avoir un sens."""
    if not denominateur or denominateur < minimum:
        return None
    return numerateur / denominateur


def pour_depute(db, uid):
    """Indicateurs d'un député, avec les taux et les moyennes de comparaison."""
    i = dict(db.execute("SELECT * FROM indicateurs WHERE acteur_uid = ?", (uid,)).fetchone())
    groupe = db.execute("SELECT groupe_uid FROM deputes WHERE acteur_uid = ?",
                        (uid,)).fetchone()[0]
    reunions = i["commission_present"] + i["commission_absent"] + i["commission_excuse"]
    i["commission_reunions"] = reunions
    i["taux_solennels"] = taux(i["solennels_exprimes"], i["solennels_eligibles"], MIN_SOLENNELS)
    i["taux_scrutins"] = taux(i["scrutins_exprimes"], i["scrutins_eligibles"])
    i["taux_loyaute"] = taux(i["votes_conformes"], i["votes_comparables"], MIN_COMPARABLES)
    i["taux_commission"] = taux(i["commission_present"], reunions, MIN_REUNIONS)
    moyennes = {(m["perimetre"], m["indicateur"]): m["valeur"]
                for m in db.execute("SELECT * FROM moyennes")}
    for nom in ("solennels", "loyaute", "commission"):
        i[f"moyenne_{nom}"] = moyennes.get(("tous", nom))
        i[f"moyenne_groupe_{nom}"] = moyennes.get((groupe, nom))
    return i
