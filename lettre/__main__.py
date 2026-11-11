"""Ligne de commande de la lettre.

    python -m lettre servir             lance le service web (essais locaux)
    python -m lettre envoyer            envoie les lettres dues
    python -m lettre envoyer --a-blanc  montre ce qui partirait, sans rien envoyer
    python -m lettre purger             efface les inscriptions non confirmées

La configuration vient des variables d'environnement MD_* (voir lettre/config.py).
"""

import argparse
import sqlite3
import sys

from . import abonnes, config as configuration, contenu, courriel
from .application import Application


def envoyer(cfg, a_blanc=False, instant=None, journal=print):
    """Envoie les lettres dues. Renvoie (envoyées, sans activité, sièges vacants, échecs)."""
    app = Application(cfg)
    donnees = sqlite3.connect(f"file:{cfg.donnees}?mode=ro", uri=True)
    donnees.row_factory = sqlite3.Row
    db = abonnes.ouvrir(cfg.abonnes)
    envoyees = vides = vacants = echecs = 0
    cache = {}
    try:
        for abonne, debut, fin in abonnes.dus(db, instant):
            cle = (abonne["num_departement"], abonne["num_circo"], debut, fin)
            if cle not in cache:
                cache[cle] = contenu.composer(donnees, *cle)
            lettre = cache[cle]
            if lettre is None:
                vacants += 1
                continue
            if lettre["vide"]:
                # Rien à dire : on n'écrit pas, et la période continue de courir.
                vides += 1
                continue
            liens = app.liens(abonne["id"])
            sujet, texte, html = contenu.rendre(lettre, cfg.site_url, liens["gerer"],
                                                liens["desabonner"])
            if a_blanc:
                journal(f"[à blanc] {abonne['email']} : {sujet}")
                envoyees += 1
                continue
            try:
                courriel.envoyer(cfg, courriel.construire(
                    cfg, abonne["email"], sujet, texte, html, liens["desabonner"]))
            except Exception as erreur:  # un échec n'empêche pas les autres envois
                echecs += 1
                journal(f"ÉCHEC pour l'abonné n° {abonne['id']} : "
                        f"{type(erreur).__name__} : {erreur}")
                continue
            abonnes.marquer_envoye(db, abonne["id"], fin)
            envoyees += 1
    finally:
        db.close()
        donnees.close()
    journal(f"{envoyees} lettres envoyées, {vides} sans activité, "
            f"{vacants} sièges vacants, {echecs} échecs")
    return envoyees, vides, vacants, echecs


def main():
    parseur = argparse.ArgumentParser(prog="lettre", description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    commandes = parseur.add_subparsers(dest="commande", required=True)
    p = commandes.add_parser("servir", help="lance le service web pour des essais locaux")
    p.add_argument("--port", type=int, default=8766)
    p = commandes.add_parser("envoyer", help="envoie les lettres dues")
    p.add_argument("--a-blanc", action="store_true")
    commandes.add_parser("purger", help="efface les inscriptions non confirmées")
    args = parseur.parse_args()
    try:
        cfg = configuration.depuis_environnement()
    except configuration.ConfigurationInvalide as erreur:
        print(f"Configuration invalide : {erreur}", file=sys.stderr)
        return 2
    if args.commande == "servir":
        from wsgiref.simple_server import make_server
        print(f"Service de la lettre sur http://127.0.0.1:{args.port} (essais uniquement)")
        make_server("127.0.0.1", args.port, Application(cfg)).serve_forever()
    elif args.commande == "envoyer":
        return 1 if envoyer(cfg, args.a_blanc)[3] else 0
    elif args.commande == "purger":
        db = abonnes.ouvrir(cfg.abonnes)
        print(f"{abonnes.purger(db)} inscriptions non confirmées effacées")
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
