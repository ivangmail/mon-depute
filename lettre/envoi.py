"""Composition et envoi d'une lettre à un abonné."""

from . import abonnes, contenu, courriel


def envoyer_lettre(cfg, liens, donnees, db, abonne, debut, fin, a_blanc=False, cache=None):
    """Compose la lettre de l'abonné pour la période et l'envoie.

    Renvoie (résultat, sujet) où résultat vaut « envoyee », « vide » (aucune
    activité : rien ne part) ou « vacant » (pas de député en exercice dans la
    circonscription). Dans les trois cas la période est marquée comme traitée,
    pour que la lettre suivante couvre la période fixe suivante. Une erreur
    d'envoi remonte à l'appelant, et la période reste alors à traiter.
    """
    cle = (abonne["num_departement"], abonne["num_circo"], debut, fin)
    cache = {} if cache is None else cache
    if cle not in cache:
        cache[cle] = contenu.composer(donnees, *cle)
    lettre = cache[cle]
    if lettre is None or lettre["vide"]:
        if not a_blanc:
            abonnes.marquer_envoye(db, abonne["id"], fin)
        return ("vacant" if lettre is None else "vide"), None
    # Les thèmes choisis par l'abonné changent seulement l'ordre de présentation, après
    # la composition commune à la circonscription : rien n'est recalculé ni retiré.
    lettre = contenu.mettre_en_avant(lettre, abonnes.themes_de(abonne))
    sujet, texte, html = contenu.rendre(lettre, cfg.site_url, liens["gerer"],
                                        liens["desabonner"], contact=cfg.contact)
    if not a_blanc:
        courriel.envoyer(cfg, courriel.construire(
            cfg, abonne["email"], sujet, texte, html, liens["desabonner"]))
        abonnes.marquer_envoye(db, abonne["id"], fin)
    return "envoyee", sujet
