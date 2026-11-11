"""Base des abonnés.

Elle est séparée de la base des données de l'Assemblée et ne contient que le
strict nécessaire : une adresse e-mail, une circonscription et une fréquence.
Ni nom, ni adresse postale, ni adresse IP.
"""

import datetime
import hashlib
import hmac
import re
import sqlite3

FREQUENCES = {"hebdomadaire": 7, "mensuelle": 30}
DELAI_CONFIRMATION = 7       # jours avant suppression d'une inscription non confirmée
DELAI_ENTRE_COURRIELS = 3600  # secondes entre deux e-mails de confirmation à la même adresse
MAX_PAR_ADRESSE = 5           # circonscriptions suivies par une même adresse
PERIODE_MAX = 60              # jours couverts au plus par une lettre
COURRIEL = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[^@\s<>\"',;]{2,}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS abonnes (
    id                  INTEGER PRIMARY KEY,
    email               TEXT NOT NULL,
    num_departement     TEXT NOT NULL,
    num_circo           TEXT NOT NULL,
    frequence           TEXT NOT NULL,
    statut              TEXT NOT NULL,   -- attente, actif
    cree_le             TEXT NOT NULL,
    confirme_le         TEXT,
    dernier_envoi       TEXT,            -- fin de la période couverte par la dernière lettre
    dernier_courriel_le TEXT,            -- dernier e-mail de confirmation ou de gestion
    UNIQUE (email, num_departement, num_circo)
);
"""


def ouvrir(chemin):
    db = sqlite3.connect(chemin)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript(SCHEMA)
    return db


def maintenant():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _iso(instant):
    return instant.isoformat()


def _lire(iso):
    return datetime.datetime.fromisoformat(iso)


def normaliser(email):
    """Renvoie l'adresse nettoyée, ou None si elle n'est pas plausible."""
    email = (email or "").strip().lower()
    if len(email) > 254 or not COURRIEL.match(email):
        return None
    return email


# ------------------------------------------------------------------- jetons

def jeton(secret, identifiant, usage):
    """Lien signé : il prouve que son porteur a reçu l'e-mail, sans rien stocker."""
    signature = hmac.new(secret, f"{usage}:{identifiant}".encode(), hashlib.sha256)
    return f"{identifiant}.{signature.hexdigest()[:40]}"


def verifier(secret, valeur, usage):
    """Renvoie l'identifiant de l'abonné si le jeton est valide, sinon None."""
    identifiant, _, _ = (valeur or "").partition(".")
    if not identifiant.isdigit():
        return None
    if not hmac.compare_digest(jeton(secret, int(identifiant), usage), valeur):
        return None
    return int(identifiant)


# -------------------------------------------------------------- opérations

def inscrire(db, email, departement, circo, frequence, instant=None):
    """Enregistre une demande d'abonnement.

    Renvoie (abonné, courriel) où courriel vaut « confirmation », « gestion »
    (l'adresse est déjà abonnée : on lui renvoie son lien de gestion) ou None
    (un e-mail vient déjà de partir, ou la limite par adresse est atteinte).
    L'appelant répond la même chose dans tous les cas, pour ne pas révéler
    quelles adresses sont abonnées.
    """
    instant = instant or maintenant()
    if frequence not in FREQUENCES:
        raise ValueError("fréquence inconnue")
    existant = db.execute(
        "SELECT * FROM abonnes WHERE email = ? AND num_departement = ? AND num_circo = ?",
        (email, departement, circo)).fetchone()
    if existant:
        dernier = existant["dernier_courriel_le"]
        if dernier and (instant - _lire(dernier)).total_seconds() < DELAI_ENTRE_COURRIELS:
            return existant, None
        if existant["statut"] == "attente":
            db.execute("UPDATE abonnes SET frequence = ?, dernier_courriel_le = ? WHERE id = ?",
                       (frequence, _iso(instant), existant["id"]))
        else:
            db.execute("UPDATE abonnes SET dernier_courriel_le = ? WHERE id = ?",
                       (_iso(instant), existant["id"]))
        db.commit()
        abonne = db.execute("SELECT * FROM abonnes WHERE id = ?", (existant["id"],)).fetchone()
        return abonne, "confirmation" if abonne["statut"] == "attente" else "gestion"
    nombre = db.execute("SELECT count(*) FROM abonnes WHERE email = ?", (email,)).fetchone()[0]
    if nombre >= MAX_PAR_ADRESSE:
        return None, None
    curseur = db.execute(
        "INSERT INTO abonnes (email, num_departement, num_circo, frequence, statut, cree_le,"
        " dernier_courriel_le) VALUES (?,?,?,?, 'attente', ?, ?)",
        (email, departement, circo, frequence, _iso(instant), _iso(instant)))
    db.commit()
    return db.execute("SELECT * FROM abonnes WHERE id = ?", (curseur.lastrowid,)).fetchone(), \
        "confirmation"


def lire(db, identifiant):
    return db.execute("SELECT * FROM abonnes WHERE id = ?", (identifiant,)).fetchone()


def confirmer(db, identifiant, instant=None):
    instant = instant or maintenant()
    db.execute("UPDATE abonnes SET statut = 'actif', confirme_le = coalesce(confirme_le, ?)"
               " WHERE id = ?", (_iso(instant), identifiant))
    db.commit()
    return lire(db, identifiant)


def modifier(db, identifiant, frequence):
    if frequence not in FREQUENCES:
        raise ValueError("fréquence inconnue")
    db.execute("UPDATE abonnes SET frequence = ? WHERE id = ?", (frequence, identifiant))
    db.commit()


def supprimer(db, identifiant):
    """Désabonnement : la ligne est effacée, rien n'est conservé."""
    db.execute("DELETE FROM abonnes WHERE id = ?", (identifiant,))
    db.commit()


def purger(db, instant=None):
    """Efface les inscriptions restées sans confirmation."""
    instant = instant or maintenant()
    limite = _iso(instant - datetime.timedelta(days=DELAI_CONFIRMATION))
    curseur = db.execute("DELETE FROM abonnes WHERE statut = 'attente' AND cree_le < ?",
                         (limite,))
    db.commit()
    return curseur.rowcount


def dus(db, instant=None):
    """Abonnés actifs dont la période est écoulée, avec les bornes de leur lettre.

    Renvoie une liste de (abonné, début, fin) ; les dates sont au format
    AAAA-MM-JJ, début inclus et fin exclue.
    """
    instant = instant or maintenant()
    fin = instant.date()
    resultat = []
    for a in db.execute("SELECT * FROM abonnes WHERE statut = 'actif' ORDER BY id"):
        jours = FREQUENCES[a["frequence"]]
        if a["dernier_envoi"]:
            debut = datetime.date.fromisoformat(a["dernier_envoi"])
            if (fin - debut).days < jours:
                continue
            debut = max(debut, fin - datetime.timedelta(days=PERIODE_MAX))
        else:
            debut = fin - datetime.timedelta(days=jours)
        resultat.append((a, debut.isoformat(), fin.isoformat()))
    return resultat


def marquer_envoye(db, identifiant, fin):
    db.execute("UPDATE abonnes SET dernier_envoi = ? WHERE id = ?", (fin, identifiant))
    db.commit()
