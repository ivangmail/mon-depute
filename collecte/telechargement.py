"""Téléchargement des archives, avec reprise sur coupure.

Le serveur de l'Assemblée coupe régulièrement les gros transferts : on reprend
là où le transfert s'est arrêté (en-tête Range) au lieu de tout recommencer.

Son cache renvoie aussi, par moments, des en-têtes périmés aux requêtes HEAD.
La taille et la version de référence sont donc celles de la réponse de
téléchargement elle-même, et la reprise est conditionnée à cette version
(If-Range) pour ne jamais assembler deux versions différentes d'un fichier.
"""

import os
import re
import time
import urllib.error
import urllib.request
import zipfile

AGENT = "mon-depute/0.1 (collecte open data)"
TAILLE_BLOC = 1 << 16
ESSAIS_MAX = 80
DELAI = 60  # secondes, par requête
TOTAL_RANGE = re.compile(r"/(\d+)\s*$")


class EchecTelechargement(Exception):
    pass


def _ouvrir(url, entetes=None, methode="GET"):
    req = urllib.request.Request(url, method=methode,
                                 headers={"User-Agent": AGENT, **(entetes or {})})
    return urllib.request.urlopen(req, timeout=DELAI)


def entetes_distants(url):
    """Renvoie (etag, last_modified) annoncés par le serveur.

    Sert seulement à décider s'il faut retélécharger ; en cas d'en-têtes
    périmés, le pire effet est un téléchargement inutile.
    """
    derniere = None
    for essai in range(5):
        try:
            with _ouvrir(url, methode="HEAD") as rep:
                return rep.headers.get("ETag"), rep.headers.get("Last-Modified")
        except (urllib.error.URLError, OSError) as err:
            derniere = err
            time.sleep(1 + essai)
    raise EchecTelechargement(f"en-têtes inaccessibles pour {url} : {derniere}")


def telecharger(url, destination):
    """Télécharge url vers destination.

    Renvoie {"taille", "etag", "last_modified"} de la version reçue.
    Écrit d'abord dans « destination.part » : le fichier final n'est remplacé
    que si l'archive téléchargée est complète et lisible.
    """
    partiel = destination + ".part"
    if os.path.exists(partiel):
        os.remove(partiel)
    os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
    etag = modif = total = derniere = None
    for essai in range(1, ESSAIS_MAX + 1):
        position = os.path.getsize(partiel) if os.path.exists(partiel) else 0
        if total is not None and position == total:
            break
        if total is not None and position > total:
            os.remove(partiel)
            position = 0
        entetes = {}
        if position and etag:
            entetes = {"Range": f"bytes={position}-", "If-Range": etag}
        else:
            position = 0
        try:
            with _ouvrir(url, entetes) as rep:
                if rep.status == 206 and position:
                    trouve = TOTAL_RANGE.search(rep.headers.get("Content-Range") or "")
                    total = int(trouve.group(1)) if trouve else total
                    mode = "ab"
                else:
                    # Réponse complète : premier essai, ou la version distante
                    # a changé entre-temps. On repart de zéro sur cette version.
                    longueur = rep.headers.get("Content-Length")
                    total = int(longueur) if longueur else None
                    etag = rep.headers.get("ETag")
                    modif = rep.headers.get("Last-Modified")
                    mode = "wb"
                with open(partiel, mode) as sortie:
                    while True:
                        bloc = rep.read(TAILLE_BLOC)
                        if not bloc:
                            break
                        sortie.write(bloc)
            if total is None:
                break  # taille non annoncée : on se fie à la fin du flux
        except (urllib.error.URLError, OSError) as err:
            derniere = err
            time.sleep(min(essai, 10))
    taille = os.path.getsize(partiel) if os.path.exists(partiel) else 0
    if total is not None and taille != total:
        raise EchecTelechargement(
            f"{url} : {taille} octets reçus sur {total} "
            f"après {ESSAIS_MAX} essais ({derniere})")
    if not zipfile.is_zipfile(partiel):
        raise EchecTelechargement(f"{url} : le fichier reçu n'est pas une archive ZIP")
    os.replace(partiel, destination)
    return {"taille": taille, "etag": etag, "last_modified": modif}
