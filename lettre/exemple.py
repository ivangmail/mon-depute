"""Lettre réelle publiée sur le site comme exemple (page exemple-lettre.html).

La circonscription est choisie par l'éditeur (MD_EXEMPLE_LETTRE, par exemple
« 69-3 ») ; la lettre est celle de la dernière semaine complète, composée avec
les mêmes règles que celles envoyées aux abonnés, sans thème mis en avant et
sans lien de gestion d'abonnement.
"""

import datetime

from collecte.portrait import jour, ordinal

from . import abonnes, contenu, visuel


def lire_circonscription(valeur):
    """« 69-3 » -> ("69", "3") ; « 2A-1 » -> ("2A", "1"). ValueError sinon."""
    departement, _, circo = (valeur or "").strip().upper().rpartition("-")
    if not departement or not circo.isdigit() or int(circo) < 1:
        raise ValueError(f"circonscription illisible : {valeur!r} (attendu : 69-3)")
    return departement, str(int(circo))


def composer(db, valeur, instant=None):
    """Renvoie le dict attendu par collecte.site.exemple_lettre, ou None si le
    siège est vacant ou si la semaine n'a aucune activité."""
    departement, circo = lire_circonscription(valeur)
    instant = instant or abonnes.maintenant()
    debut, fin = abonnes.periode("hebdomadaire", instant)
    aujourdhui = instant.date().isoformat()
    l = contenu.composer(db, departement, circo, debut, fin, aujourdhui)
    if l is None or l["vide"]:
        return None
    dernier = (datetime.date.fromisoformat(fin) - datetime.timedelta(days=1)).isoformat()
    return {"html": visuel.html(l, ".", None, None), "debut": jour(debut), "fin": jour(dernier),
            "compose_le": jour(aujourdhui), "depute": l["depute"],
            "lieu": f"{ordinal(l['num_circo'], feminin=True)} circonscription, "
                    f"{l['departement']} ({l['num_departement']})",
            "chemin_fiche": l["chemin_fiche"],
            # Aperçu de l'accueil : les lignes « En bref » de cette même lettre,
            # telles quelles ; la première décrit le vote à retenir s'il y en a un.
            "groupe": l["groupe"], "sigle": l["sigle"],
            "en_bref": contenu.en_bref(l), "vote": bool(l["majeurs"])}
