"""Composition et envoi d'une lettre à un abonné."""

from . import abonnes, contenu, courriel


def envoyer_lettre(cfg, liens, donnees, db, abonne, debut, fin, a_blanc=False, cache=None):
    """Compose la lettre de l'abonné pour la période et l'envoie.

    Renvoie (résultat, sujet) où résultat vaut « envoyee », « vide » (aucune
    activité : rien ne part et la période continue de courir) ou « vacant »
    (pas de député en exercice dans la circonscription). Une erreur d'envoi
    remonte à l'appelant.
    """
    cle = (abonne["num_departement"], abonne["num_circo"], debut, fin)
    cache = {} if cache is None else cache
    if cle not in cache:
        cache[cle] = contenu.composer(donnees, *cle)
    lettre = cache[cle]
    if lettre is None:
        return "vacant", None
    if lettre["vide"]:
        return "vide", None
    sujet, texte, html = contenu.rendre(lettre, cfg.site_url, liens["gerer"],
                                        liens["desabonner"])
    if not a_blanc:
        courriel.envoyer(cfg, courriel.construire(
            cfg, abonne["email"], sujet, texte, html, liens["desabonner"]))
        abonnes.marquer_envoye(db, abonne["id"], fin)
    return "envoyee", sujet
