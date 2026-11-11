"""Ligne de commande.

    python -m collecte maj                 télécharge ce qui a changé et recharge
    python -m collecte maj --jeux acteurs scrutins
    python -m collecte etat                état des imports et volumes
    python -m collecte site                recalcule les indicateurs et régénère le site
"""

import argparse
import datetime
import os
import sys
import time

from . import base, indicateurs, site, telechargement
from .chargeurs import CHARGEURS
from .sources import JEUX, ORDRE


def maintenant():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def maj(args):
    db = base.ouvrir(args.base)
    dossier = os.path.join(args.donnees, "archives")
    echecs, charges = [], []
    for jeu in [j for j in ORDRE if not args.jeux or j in args.jeux]:
        debut = time.time()
        chemins, modifie = [], False
        try:
            for fichier, url in JEUX[jeu]:
                chemin = os.path.join(dossier, fichier)
                chemins.append(chemin)
                if args.sans_telechargement:
                    if not os.path.exists(chemin):
                        raise telechargement.EchecTelechargement(f"{chemin} absent")
                    continue
                etag, modif = telechargement.entetes_distants(url)
                connu = db.execute("SELECT * FROM imports WHERE fichier = ?",
                                   (fichier,)).fetchone()
                inchange = (connu and os.path.exists(chemin) and connu["charge_le"]
                            and (etag, modif) == (connu["etag"], connu["last_modified"]))
                if inchange and not args.forcer:
                    continue
                print(f"[{jeu}] téléchargement de {fichier}…", flush=True)
                recu = telechargement.telecharger(url, chemin)
                print(f"[{jeu}] {fichier} : {recu['taille'] / 1e6:.1f} Mo", flush=True)
                db.execute(
                    "INSERT OR REPLACE INTO imports (fichier, jeu, url, etag,"
                    " last_modified, taille, telecharge_le, charge_le)"
                    " VALUES (?,?,?,?,?,?,?,NULL)",
                    (fichier, jeu, url, recu["etag"], recu["last_modified"],
                     recu["taille"], maintenant()))
                db.commit()
                modifie = True
            if not (modifie or args.forcer or args.sans_telechargement):
                print(f"[{jeu}] inchangé")
                continue
            print(f"[{jeu}] chargement…", flush=True)
            with db:  # une transaction : tout le jeu ou rien
                nombre = CHARGEURS[jeu](db, chemins)
                db.execute("UPDATE imports SET charge_le = ? WHERE jeu = ?",
                           (maintenant(), jeu))
            charges.append(jeu)
            print(f"[{jeu}] {nombre} enregistrements en {time.time() - debut:.0f} s")
        except Exception as erreur:  # un jeu en échec ne bloque pas les autres
            echecs.append(jeu)
            print(f"[{jeu}] ÉCHEC : {type(erreur).__name__} : {erreur}", file=sys.stderr)
    if charges and not args.sans_site:
        publier(db, args)
    if echecs:
        print("Jeux en échec : " + ", ".join(echecs), file=sys.stderr)
        return 1
    return 0


def publier(db, args):
    """Recalcule les indicateurs puis régénère le site."""
    debut = time.time()
    print("[indicateurs] calcul…", flush=True)
    with db:
        indicateurs.calculer(db)
    print(f"[indicateurs] terminé en {time.time() - debut:.0f} s")
    debut = time.time()
    site.generer(db, args.site, journal=lambda m: print(f"[site] {m}"),
                 api_url=args.api or os.environ.get("MD_API_URL"))
    print(f"[site] terminé en {time.time() - debut:.0f} s")


def commande_site(args):
    publier(base.ouvrir(args.base), args)
    return 0


def etat(args):
    db = base.ouvrir(args.base)
    print("Imports :")
    for ligne in db.execute("SELECT * FROM imports ORDER BY jeu, fichier"):
        print(f"  {ligne['jeu']:<12} {ligne['fichier']:<34} "
              f"{(ligne['taille'] or 0) / 1e6:>7.1f} Mo  "
              f"source du {ligne['last_modified']}  chargé le {ligne['charge_le']}")
    print("Volumes :")
    for table in ("acteurs", "deputes", "organes", "mandats", "contacts", "scrutins",
                  "votes", "reunions", "presences", "questions", "dossiers",
                  "documents", "comptes_rendus", "interventions", "amendements",
                  "amendements_cosignataires"):
        print(f"  {table:<28} {db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:>9}")
    return 0


def main():
    parseur = argparse.ArgumentParser(prog="collecte", description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parseur.add_argument("--donnees", default="donnees",
                         help="dossier des archives et de la base (défaut : donnees)")
    parseur.add_argument("--base", help="chemin de la base SQLite")
    parseur.add_argument("--site", default="site",
                         help="dossier du site généré (défaut : site)")
    parseur.add_argument("--api", help="adresse du service de la lettre ; sans elle (ni la "
                         "variable MD_API_URL), le formulaire d'abonnement n'est pas affiché")
    commandes = parseur.add_subparsers(dest="commande", required=True)
    p = commandes.add_parser("maj", help="met à jour la base")
    p.add_argument("--jeux", nargs="+", choices=ORDRE)
    p.add_argument("--forcer", action="store_true",
                   help="retélécharge et recharge même si la source n'a pas changé")
    p.add_argument("--sans-telechargement", action="store_true",
                   help="recharge à partir des archives déjà présentes")
    p.add_argument("--sans-site", action="store_true",
                   help="ne recalcule pas les indicateurs et ne régénère pas le site")
    p.set_defaults(fonction=maj)
    p = commandes.add_parser("etat", help="affiche l'état de la base")
    p.set_defaults(fonction=etat)
    p = commandes.add_parser("site", help="recalcule les indicateurs et régénère le site")
    p.set_defaults(fonction=commande_site)
    args = parseur.parse_args()
    args.base = args.base or os.path.join(args.donnees, "assemblee.sqlite")
    os.makedirs(args.donnees, exist_ok=True)
    return args.fonction(args)


if __name__ == "__main__":
    sys.exit(main())
