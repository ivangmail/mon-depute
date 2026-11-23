"""Base des abonnés.

Elle est séparée de la base des données de l'Assemblée et ne contient que le
strict nécessaire : une adresse e-mail, une circonscription, une fréquence et,
si l'abonné en a choisi, les thèmes mis en avant dans sa lettre. Ni nom, ni
adresse postale, ni adresse IP. La table « compteurs » ne garde que des nombres
par jour (inscriptions, confirmations, désabonnements), sans aucune adresse.
"""

import datetime
import gzip
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import tempfile

from collecte.themes import THEMES

# Périodes fixes : la semaine du lundi au dimanche, ou le mois calendaire. Tous les
# abonnés d'une même circonscription reçoivent ainsi la même lettre.
FREQUENCES = {"hebdomadaire": 7, "mensuelle": 30}
DELAI_CONFIRMATION = 7       # jours avant suppression d'une inscription non confirmée
DELAI_ENTRE_COURRIELS = 3600  # secondes entre deux e-mails de confirmation à la même adresse
MAX_PAR_ADRESSE = 5           # circonscriptions suivies par une même adresse
PERIODE_MAX = 60              # jours couverts au plus par une lettre
# L'Assemblée publie ses données avec retard : une lettre part deux jours après
# la fin de sa période (le mercredi pour une semaine, le 3 pour un mois), pour
# qu'un vote publié tardivement ne soit pas oublié.
DECALAGE = 2
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
    themes              TEXT,            -- liste JSON des thèmes mis en avant ; NULL : aucun
    UNIQUE (email, num_departement, num_circo)
);

-- Nombres par jour, sans aucune donnée personnelle : seul moyen de suivre les
-- désabonnements, puisqu'un désabonnement efface la ligne de l'abonné.
CREATE TABLE IF NOT EXISTS compteurs (
    jour      TEXT NOT NULL,
    evenement TEXT NOT NULL,           -- inscription, confirmation, desabonnement
    nombre    INTEGER NOT NULL,
    PRIMARY KEY (jour, evenement)
);
"""
EVENEMENTS = ("inscription", "confirmation", "desabonnement")


def ouvrir(chemin):
    db = sqlite3.connect(chemin)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript(SCHEMA)
    # Base créée avant le choix des thèmes : la colonne manque encore.
    if "themes" not in [c[1] for c in db.execute("PRAGMA table_info(abonnes)")]:
        db.execute("ALTER TABLE abonnes ADD COLUMN themes TEXT")
        db.commit()
    return db


def compter(db, evenement, instant=None):
    """Ajoute 1 au compteur du jour pour cet événement (aucune donnée personnelle)."""
    if evenement not in EVENEMENTS:
        raise ValueError("événement inconnu")
    jour = (instant or maintenant()).date().isoformat()
    db.execute("INSERT INTO compteurs VALUES (?, ?, 1) ON CONFLICT (jour, evenement)"
               " DO UPDATE SET nombre = nombre + 1", (jour, evenement))


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
    compter(db, "inscription", instant)
    db.commit()
    return db.execute("SELECT * FROM abonnes WHERE id = ?", (curseur.lastrowid,)).fetchone(), \
        "confirmation"


def annuler_courriel(db, identifiant):
    """L'e-mail n'est pas parti : on lève le délai d'attente, pour que la personne
    puisse réessayer, et on efface l'inscription si elle n'avait jamais été confirmée."""
    db.execute("DELETE FROM abonnes WHERE id = ? AND statut = 'attente'", (identifiant,))
    db.execute("UPDATE abonnes SET dernier_courriel_le = NULL WHERE id = ?", (identifiant,))
    db.commit()


def lire(db, identifiant):
    return db.execute("SELECT * FROM abonnes WHERE id = ?", (identifiant,)).fetchone()


def confirmer(db, identifiant, instant=None):
    instant = instant or maintenant()
    if db.execute("SELECT 1 FROM abonnes WHERE id = ? AND statut = 'attente'",
                  (identifiant,)).fetchone():
        compter(db, "confirmation", instant)
    db.execute("UPDATE abonnes SET statut = 'actif', confirme_le = coalesce(confirme_le, ?)"
               " WHERE id = ?", (_iso(instant), identifiant))
    db.commit()
    return lire(db, identifiant)


def modifier(db, identifiant, frequence):
    if frequence not in FREQUENCES:
        raise ValueError("fréquence inconnue")
    db.execute("UPDATE abonnes SET frequence = ? WHERE id = ?", (frequence, identifiant))
    db.commit()


def choisir_themes(db, identifiant, choisis):
    """Enregistre les thèmes mis en avant dans la lettre. Aucun thème, ou tous,
    revient à n'en mettre aucun en avant : la colonne est alors vide."""
    inconnus = set(choisis) - set(THEMES)
    if inconnus:
        raise ValueError("thème inconnu")
    retenus = [t for t in THEMES if t in set(choisis)]
    valeur = json.dumps(retenus, ensure_ascii=False) if 0 < len(retenus) < len(THEMES) else None
    db.execute("UPDATE abonnes SET themes = ? WHERE id = ?", (valeur, identifiant))
    db.commit()


def themes_de(abonne):
    """Thèmes mis en avant par l'abonné, ou None s'il n'en a choisi aucun."""
    try:
        valeur = abonne["themes"]
    except (IndexError, KeyError):
        return None
    return json.loads(valeur) if valeur else None


def supprimer(db, identifiant, instant=None):
    """Désabonnement : la ligne est effacée, rien n'est conservé (seul le compteur
    du jour augmente)."""
    if db.execute("DELETE FROM abonnes WHERE id = ?", (identifiant,)).rowcount:
        compter(db, "desabonnement", instant)
    db.commit()


def bilan(db, instant=None, jours=7):
    """Chiffres agrégés pour l'éditeur : abonnés actifs par fréquence, inscriptions
    en attente, et événements des derniers jours. Aucune adresse."""
    instant = instant or maintenant()
    depuis = (instant.date() - datetime.timedelta(days=jours)).isoformat()
    actifs = dict(tuple(r) for r in db.execute(
        "SELECT frequence, count(*) FROM abonnes WHERE statut = 'actif' GROUP BY frequence"))
    evenements = dict(tuple(r) for r in db.execute(
        "SELECT evenement, sum(nombre) FROM compteurs WHERE jour > ? GROUP BY evenement",
        (depuis,)))
    return {
        "actifs": sum(actifs.values()), "par_frequence": actifs,
        "en_attente": db.execute("SELECT count(*) FROM abonnes WHERE statut = 'attente'")
                        .fetchone()[0],
        "themes_choisis": db.execute("SELECT count(*) FROM abonnes WHERE statut = 'actif'"
                                     " AND themes IS NOT NULL").fetchone()[0],
        "jours": jours, **{e: evenements.get(e, 0) for e in EVENEMENTS},
    }


def purger(db, instant=None):
    """Efface les inscriptions restées sans confirmation."""
    instant = instant or maintenant()
    limite = _iso(instant - datetime.timedelta(days=DELAI_CONFIRMATION))
    curseur = db.execute("DELETE FROM abonnes WHERE statut = 'attente' AND cree_le < ?",
                         (limite,))
    db.commit()
    return curseur.rowcount


def periode(frequence, instant=None):
    """Dernière période complète terminée depuis au moins DECALAGE jours :
    (début inclus, fin exclue), au format AAAA-MM-JJ."""
    repere = (instant or maintenant()).date() - datetime.timedelta(days=DECALAGE)
    if frequence == "hebdomadaire":
        fin = repere - datetime.timedelta(days=repere.weekday())   # lundi
        debut = fin - datetime.timedelta(days=7)
    else:
        fin = repere.replace(day=1)
        debut = (fin - datetime.timedelta(days=1)).replace(day=1)
    return debut.isoformat(), fin.isoformat()


def premiere_periode(frequence, instant=None):
    """Bornes de la première lettre d'un abonné : la dernière période complète."""
    return periode(frequence, instant)


def sauvegarder(chemin_base, dossier, conserver=14, instant=None):
    """Écrit une copie cohérente et datée de la base des abonnés, compressée,
    et ne garde que les plus récentes. Renvoie le chemin de la copie."""
    instant = instant or maintenant()
    os.makedirs(dossier, mode=0o700, exist_ok=True)
    destination = os.path.join(dossier, f"abonnes-{instant.strftime('%Y%m%d-%H%M%S')}.sqlite.gz")
    with tempfile.TemporaryDirectory(dir=dossier) as temporaire:
        copie = os.path.join(temporaire, "copie.sqlite")
        source, cible = sqlite3.connect(chemin_base), sqlite3.connect(copie)
        try:
            source.backup(cible)  # copie cohérente, même si le service écrit au même moment
        finally:
            source.close()
            cible.close()
        with open(copie, "rb") as lecture, gzip.open(destination, "wb") as ecriture:
            shutil.copyfileobj(lecture, ecriture)
    os.chmod(destination, 0o600)
    anciennes = sorted(f for f in os.listdir(dossier)
                       if f.startswith("abonnes-") and f.endswith(".sqlite.gz"))[:-conserver]
    for nom in anciennes:
        os.remove(os.path.join(dossier, nom))
    return destination


def dus(db, instant=None):
    """Abonnés actifs dont la dernière période complète n'a pas encore été traitée,
    avec les bornes de leur lettre.

    Renvoie une liste de (abonné, début, fin) ; les dates sont au format
    AAAA-MM-JJ, début inclus et fin exclue. Normalement la lettre couvre la
    période fixe (voir periode()). Si la lettre précédente s'arrêtait plus tôt
    (envoi manqué, changement de fréquence, passage aux périodes fixes), elle
    reprend là où la précédente s'arrêtait, sans remonter à plus de PERIODE_MAX
    jours ; elle couvre toujours au moins la période fixe entière.
    """
    resultat = []
    for a in db.execute("SELECT * FROM abonnes WHERE statut = 'actif' ORDER BY id"):
        debut, fin = periode(a["frequence"], instant)
        dernier = a["dernier_envoi"]
        if dernier and dernier >= fin:
            continue
        if dernier:
            plancher = (datetime.date.fromisoformat(fin)
                        - datetime.timedelta(days=PERIODE_MAX)).isoformat()
            debut = min(debut, max(dernier, plancher))
        resultat.append((a, debut, fin))
    return resultat


def marquer_envoye(db, identifiant, fin):
    db.execute("UPDATE abonnes SET dernier_envoi = ? WHERE id = ?", (fin, identifiant))
    db.commit()
