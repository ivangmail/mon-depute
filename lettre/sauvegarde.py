"""Copie de la base des abonnés hors du serveur, chiffrée.

La copie locale datée (abonnes.sauvegarder) est chiffrée avec une phrase
secrète, puis déposée dans un espace de stockage objet. Le fournisseur ne voit
donc jamais les adresses en clair. Le chiffrement passe par l'outil openssl,
présent sur Debian, avec des réglages qui permettent aussi de déchiffrer une
copie à la main, sans ce code :

    openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in COPIE.enc -out COPIE.sqlite.gz

Sans la phrase secrète, les copies sont illisibles : elle doit être conservée
ailleurs que sur le serveur (gestionnaire de mots de passe).
"""

import gzip
import os
import sqlite3
import subprocess

from .stockage import Depot

PREFIXE = "abonnes/"
CONSERVER = 14
CHIFFREMENT = ["-aes-256-cbc", "-pbkdf2", "-iter", "600000", "-pass", "env:MD_PHRASE_OPENSSL"]


class EchecSauvegarde(Exception):
    pass


def depot(cfg):
    """Espace de stockage décrit par la configuration, ou None s'il n'y en a pas."""
    if not cfg.s3_espace:
        return None
    return Depot(cfg.s3_hote, cfg.s3_region, cfg.s3_espace, cfg.s3_cle_acces, cfg.s3_cle_secrete)


def _openssl(arguments, donnees, phrase):
    environnement = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "MD_PHRASE_OPENSSL": phrase}
    resultat = subprocess.run(["openssl", "enc", *arguments, *CHIFFREMENT], input=donnees,
                              capture_output=True, env=environnement, check=False)
    if resultat.returncode:
        raise EchecSauvegarde("openssl : " + resultat.stderr.decode("utf-8", "replace").strip())
    return resultat.stdout


def chiffrer(donnees, phrase):
    return _openssl(["-salt"], donnees, phrase)


def dechiffrer(donnees, phrase):
    try:
        return _openssl(["-d"], donnees, phrase)
    except EchecSauvegarde as erreur:
        raise EchecSauvegarde("déchiffrement impossible (mauvaise phrase secrète ou copie "
                              f"abîmée) : {erreur}") from None


def envoyer(chemin_local, depot, phrase, conserver=CONSERVER):
    """Chiffre la copie locale, la dépose, la relit pour vérifier qu'elle se
    déchiffre à l'identique, puis supprime les copies distantes les plus
    anciennes. Renvoie la clé de la copie déposée."""
    with open(chemin_local, "rb") as f:
        clair = f.read()
    cle = PREFIXE + os.path.basename(chemin_local) + ".enc"
    depot.deposer(cle, chiffrer(clair, phrase))
    if dechiffrer(depot.lire(cle), phrase) != clair:
        raise EchecSauvegarde(f"la copie relue ({cle}) ne correspond pas à l'original")
    copies = [c for c, _, _ in depot.lister(PREFIXE) if c.endswith(".enc")]
    if cle not in copies:
        raise EchecSauvegarde(f"la copie {cle} n'apparaît pas dans la liste de l'espace")
    for ancienne in copies[:-conserver]:
        depot.supprimer(ancienne)
    return cle


def restaurer(depot, phrase, destination, cle=None):
    """Écrit dans destination la base contenue dans une copie distante (la plus
    récente par défaut). Refuse d'écraser un fichier existant. Renvoie
    (clé de la copie, nombre d'abonnés qu'elle contient)."""
    if os.path.exists(destination):
        raise EchecSauvegarde(f"{destination} existe déjà : choisir un autre fichier")
    if cle is None:
        copies = [c for c, _, _ in depot.lister(PREFIXE) if c.endswith(".enc")]
        if not copies:
            raise EchecSauvegarde("aucune copie dans l'espace de stockage")
        cle = copies[-1]
    try:
        base = gzip.decompress(dechiffrer(depot.lire(cle), phrase))
    except (OSError, EOFError) as erreur:
        raise EchecSauvegarde(f"copie {cle} illisible : {erreur}") from None
    with open(destination, "xb") as f:
        f.write(base)
    os.chmod(destination, 0o600)
    db = sqlite3.connect(destination)
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise EchecSauvegarde(f"la base restaurée depuis {cle} est abîmée")
        nombre = db.execute("SELECT count(*) FROM abonnes").fetchone()[0]
    finally:
        db.close()
    return cle, nombre
