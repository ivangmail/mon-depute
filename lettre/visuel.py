"""Mise en page visuelle de la lettre, pour les messageries.

Les messageries n'acceptent qu'un HTML ancien : Outlook sur ordinateur ignore
flex, grid et la plupart des feuilles de style. Tout est donc fait de tableaux
et de styles écrits sur chaque élément, sans image ni script. Les barres sont
des cellules de tableau colorées. Le contenu est celui de contenu.rubriques(),
qui sert aussi à la version texte : seule la présentation change.
"""

from html import escape

from collecte import fiche
from collecte.portrait import jour, ordinal

from . import contenu

# Couleurs. Pour, contre et abstention sont toujours doublés d'un libellé : la
# couleur seule ne porte aucune information (daltonisme, mode sombre).
FOND, CARTE, BORD, FILET = "#f4f2ec", "#ffffff", "#e3e0d6", "#ece9e0"
TEXTE, DOUX, LIEN = "#1c1f26", "#5b6270", "#1f4e79"
POUR, CONTRE, ABSTENTION, SANS = "#2f7d4f", "#b23f27", "#8a6a10", "#d5d1c6"
BARRE_ABSTENTION = "#d9a92b"
ABSENT = "#6b7280"
POLICE = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

PASTILLES = {"pour": ("Pour", POUR), "contre": ("Contre", CONTRE),
             "abstention": ("Abstention", ABSTENTION)}
TYPES = {"scrutin public solennel": "VOTE SOLENNEL", "motion de censure": "MOTION DE CENSURE"}


def _e(texte):
    return escape(str(texte or ""))


def _style(**proprietes):
    return ";".join(f"{nom.replace('_', '-')}:{valeur}" for nom, valeur in proprietes.items())


def _lien(texte, url, gras=False):
    return (f'<a href="{_e(url)}" style="{_style(color=LIEN)}">'
            + (f"<b>{_e(texte)}</b>" if gras else _e(texte)) + "</a>")


def _element(texte, url):
    """Élément de liste de contenu.rubriques() : seule la partie marquée est un lien."""
    if not url:
        return _e(texte.replace(contenu.MARQUE, ""))
    if contenu.MARQUE not in texte:
        return _lien(texte, url)
    avant, lie, apres = texte.split(contenu.MARQUE, 2)
    return _e(avant) + _lien(lie, url) + _e(apres)


def _etiquette(texte, fond=FILET, couleur=TEXTE):
    return (f'<span style="{_style(background=fond, color=couleur, font_size="11px", font_weight="bold", letter_spacing="0.05em", padding="2px 7px", border_radius="4px", white_space="nowrap")}">'
            f"{_e(texte)}</span>")


def _pastille(texte, fond):
    return (f'<span style="{_style(background=fond, color="#ffffff", font_size="13px", font_weight="bold", padding="3px 10px", border_radius="12px", white_space="nowrap")}">'
            f"{_e(texte)}</span>")


def barre(segments, hauteur=12):
    """Barre empilée : segments = [(valeur, couleur)]. Les largeurs, en pour cent
    entiers, totalisent toujours 100 ; un segment nul n'est pas dessiné."""
    segments = [(v, c) for v, c in segments if v > 0]
    total = sum(v for v, _ in segments)
    if not total:
        return ""
    largeurs = [int(100 * v / total) for v, _ in segments]
    restes = sorted(range(len(segments)), key=lambda i: -(100 * segments[i][0] / total
                                                            - largeurs[i]))
    for i in restes[:100 - sum(largeurs)]:
        largeurs[i] += 1
    # Une valeur non nulle reste visible : 1 % au moins, pris sur le plus large segment.
    for i, largeur in enumerate(largeurs):
        if not largeur:
            largeurs[i] = 1
            largeurs[largeurs.index(max(largeurs))] -= 1
    cellules = "".join(
        f'<td width="{l}%" bgcolor="{c}" style="{_style(background=c, height=f"{hauteur}px", font_size="0", line_height="0")}">&nbsp;</td>'
        for l, (_, c) in zip(largeurs, segments) if l)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="{_style(border_collapse="collapse")}"><tr>{cellules}</tr></table>')


def _jauge(valeur, total, couleur, hauteur=10):
    """Barre de longueur valeur/total sur fond clair."""
    if not total:
        return ""
    return barre([(valeur, couleur), (max(total - valeur, 0), FILET)], hauteur)


def _carte(contenu_html):
    return (f'<tr><td style="padding:0 0 14px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'bgcolor="{CARTE}" style="{_style(background=CARTE, border=f"1px solid {BORD}", border_radius="8px")}">'
            f'<tr><td style="padding:16px">{contenu_html}</td></tr></table></td></tr>')


def _titre(texte):
    return (f'<tr><td style="{_style(padding="12px 0 8px", font_size="17px", font_weight="bold", color=TEXTE)}">'
            f"{_e(texte)}</td></tr>")


def _p(texte_html, taille=15, couleur=TEXTE, marge="0 0 8px"):
    return (f'<p style="{_style(margin=marge, font_size=f"{taille}px", line_height="1.5", color=couleur)}">'
            f"{texte_html}</p>")


def _bloc(contenu_html, haut=True):
    """Sous-partie d'une carte, séparée de la précédente par un filet."""
    bord = f"border-top:1px solid {FILET};padding-top:12px;margin-top:12px" if haut else ""
    return f'<div style="{bord}">{contenu_html}</div>'


# ------------------------------------------------------------------- rubriques

def _essentiel(l, phrases):
    themes = l.get("themes") or {}
    blocs, absent = [], False
    for i, m in enumerate(l["majeurs"]):
        etiquettes = [_etiquette(TYPES.get(m["type_vote"], "TEXTE ENTIER"), LIEN, "#ffffff")]
        if themes.get(m.get("dossier_uid")):
            etiquettes.append(_etiquette(themes[m["dossier_uid"]].upper()))
        entete = " ".join(etiquettes) + f' <span style="color:{DOUX};font-size:13px">{_e(jour(m["date"]))}</span>'
        sort = (m["sort"] or "").lower()
        verbe = {"adopté": ("#dcefe2", "a adopté"), "rejeté": ("#f6dcd5", "a rejeté")}.get(sort)
        phrase = contenu.intitule(m["titre"])
        phrase = phrase[0].lower() + phrase[1:] if phrase else ""
        if verbe:
            texte = (f'L’Assemblée <span style="background:{verbe[0]};font-weight:bold;padding:0 3px">'
                     f"{verbe[1]}</span> {_e(phrase)}")
        else:
            texte = f"{_e(contenu.intitule(m['titre']))} ({_e(sort)})"
        corps = [_p(entete, 13, DOUX), _p(texte, 17, TEXTE, "0 0 10px")]
        clair = (l.get("libelles") or {}).get(m.get("dossier_uid"))
        if clair and not m["censure"]:
            corps.insert(2, _p(f"<b>En clair :</b> {_e(clair)}", 15, TEXTE, "-4px 0 10px"))
        if m["censure"]:
            corps.append(_p(f"{_e(m['nb_pour'] or 0)} voix pour la censure. Seuls les votes pour "
                            "sont recensés.", 13, DOUX))
            pastille = (_pastille("A voté la censure", LIEN) if m["position"] == "pour"
                        else _pastille("N’a pas voté la censure", ABSENT))
            corps.append(_p(f"Sa position&nbsp; {pastille}", 14, TEXTE, "0"))
        else:
            pour, contre = m["nb_pour"] or 0, m["nb_contre"] or 0
            abst = m.get("nb_abstentions") or 0
            corps.append(barre([(pour, POUR), (abst, BARRE_ABSTENTION), (contre, CONTRE)]))
            details = [f'<b style="color:{POUR}">Pour</b> {pour}',
                       f'<b style="color:{ABSTENTION}">Abstention</b> {abst}',
                       f'<b style="color:{CONTRE}">Contre</b> {contre}']
            if m.get("nb_exprimes"):
                details.append(f"majorité requise : {m['nb_exprimes'] // 2 + 1}")
            if m["ecart"] is not None and m["ecart"] <= contenu.ECART_SERRE:
                details.append("<b>vote serré</b>")
            corps.append(_p(" · ".join(details), 13, DOUX, "6px 0 10px"))
            if m["position"]:
                libelle, couleur = PASTILLES[m["position"]]
                pastille = _pastille(libelle, couleur)
            else:
                pastille, absent = _pastille("N’a pas pris part au vote", ABSENT), True
            groupe = m["groupe"][0].upper() + m["groupe"][1:] if m["groupe"] else ""
            corps.append(_p(f"Sa position&nbsp; {pastille}"
                            + (f' <span style="color:{DOUX};font-size:14px">&nbsp;{_e(groupe)}</span>'
                               if groupe else ""), 14, TEXTE, "0 0 8px"))
        corps.append(_p(_lien("Voir le scrutin et le détail par groupe",
                              fiche.URL_SCRUTIN.format(m["numero"])), 14, TEXTE, "0"))
        blocs.append(_bloc("".join(corps), haut=i > 0))
    notes = [p for p in phrases if not p.startswith("Les votes de la période")
             and not p.startswith("Pour une motion de censure")]
    if not l["majeurs"]:
        return _carte(_p(_e(phrases[0]) if phrases else "", 15, TEXTE, "0"))
    pied = "".join(_p(_e(p), 13, DOUX, "12px 0 0") for p in notes if p != contenu.ABSENCE)
    if absent:
        pied += _p(_e(contenu.ABSENCE), 13, DOUX, "12px 0 0")
    return _carte("".join(blocs) + pied)


def _participation(l, phrases):
    il = "Elle" if l["feminin"] else "Il"
    total = l["scrutins"]
    lignes = [(il, l["exprimes"], LIEN)]
    if l.get("mediane_groupe") is not None and l["sigle"] != "NI":
        lignes.append((f"Médiane {l['sigle']}", l["mediane_groupe"], "#9fb3c8"))
    if l.get("mediane_tous") is not None:
        lignes.append(("Médiane Assemblée", l["mediane_tous"], "#9fb3c8"))
    tableau = "".join(
        f'<tr><td width="34%" style="{_style(font_size="14px", padding="3px 8px 3px 0", color=TEXTE)}">'
        f"{'<b>' + _e(nom) + '</b>' if i == 0 else _e(nom)}</td>"
        f'<td style="padding:3px 0">{_jauge(valeur, total, couleur)}</td>'
        f'<td width="14%" align="right" style="{_style(font_size="14px", padding="3px 0 3px 8px", color=TEXTE)}">'
        f"<b>{_e(contenu._nombre(valeur))}</b></td></tr>"
        for i, (nom, valeur, couleur) in enumerate(lignes))
    corps = [_p(f"Scrutins publics de la période auxquels chacun a pris part, sur "
                f"{_e(total)} au total :", 14, DOUX),
             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{tableau}</table>']
    autres = [p for p in phrases if not p.startswith(f"{il} a pris part")
              and not p.startswith("Amendements et articles")]
    corps += [_p(_e(p), 14, TEXTE, "10px 0 0") for p in autres]
    groupes = contenu.votes_par_texte(l.get("autres_votes") or [], l.get("scrutins_par_texte") or [])
    if groupes:
        themes = l.get("themes") or {}
        textes = [_p("<b>Amendements et articles, texte par texte</b>", 15, TEXTE, "16px 0 4px")]
        for g in groupes[:contenu.LIMITE]:
            theme = themes.get(g["uid"])
            nom = (l.get("libelles") or {}).get(g["uid"]) or g["texte"]
            titre = _lien(nom, g["lien"]) if g["lien"] else _e(nom)
            textes.append(_bloc(
                (_p(_etiquette(theme.upper()), 13, DOUX, "0 0 4px") if theme else "")
                + _p(titre, 15, TEXTE, "0 0 6px")
                + barre([(g["pour"], POUR), (g["abstention"], BARRE_ABSTENTION),
                         (g["contre"], CONTRE), (g["sans"], SANS)], 10)
                + _p(_e(g["decompte"]), 13, DOUX, "6px 0 0")))
        if len(groupes) > contenu.LIMITE:
            reste = len(groupes) - contenu.LIMITE
            textes.append(_p(f"Et {reste} autre{'s' if reste > 1 else ''} texte"
                             f"{'s' if reste > 1 else ''} : voir sa fiche.", 13, DOUX, "10px 0 0"))
        corps += textes
    return _carte("".join(corps))


def _generique(phrases, elements):
    corps = [_p(_e(p), 15) for p in phrases]
    for i, (texte, url) in enumerate(elements):
        if url and url.endswith("#courrier"):
            corps.append(
                f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
                f'style="margin-top:12px"><tr><td bgcolor="{LIEN}" style="{_style(background=LIEN, border_radius="6px", padding="10px 16px")}">'
                f'<a href="{_e(url)}" style="{_style(color="#ffffff", font_weight="bold", text_decoration="none", font_size="15px")}">'
                f"{_e(texte.replace(contenu.MARQUE, ''))}</a></td></tr></table>")
            continue
        corps.append(_bloc(_p(_element(texte, url), 15, TEXTE, "0"), haut=i > 0 or bool(phrases)))
    return _carte("".join(corps))


def html(l, site_url, lien_gestion, lien_desabonnement, contact=None):
    """Version HTML visuelle de la lettre (corps du message)."""
    periode = f"du {jour(l['debut'])} au {jour(contenu._dernier_jour(l['fin']))}"
    lieu = (f"{ordinal(l['num_circo'], feminin=True)} circonscription, {l['departement']} "
            f"({l['num_departement']})")
    lignes = [
        f'<tr><td style="{_style(padding="4px 0 14px")}">'
        f'<p style="{_style(margin="0 0 4px", font_size="12px", letter_spacing="0.06em", color=DOUX)}">'
        f"MON DÉPUTÉ · {_e(periode.upper())}</p>"
        f'<p style="{_style(margin="0", font_size="24px", font_weight="bold", line_height="1.25", color=TEXTE)}">'
        f"{_e(l['depute'])}</p>"
        f'<p style="{_style(margin="2px 0 0", font_size="15px", color=DOUX)}">'
        f"{_e(l['groupe'] or '')}{' (' + _e(l['sigle']) + ')' if l.get('sigle') else ''} · {_e(lieu)}</p>"
        "</td></tr>"]

    tuiles = []
    participe, total = l.get("majeurs_bilan") or (0, 0)
    if total:
        tuiles.append((f"{participe} / {total}", "votes sur des textes entiers"))
    if l["scrutins"]:
        reperes = (f", médiane de l’Assemblée : {contenu._nombre(l['mediane_tous'])}"
                   if l.get("mediane_tous") is not None else "")
        tuiles.append((str(l["exprimes"]), f"scrutin{'s' if l['exprimes'] > 1 else ''} "
                                            f"sur {l['scrutins']}{reperes}"))
    tuiles.append((str(l["amendements"]),
                   f"amendement{'s' if l['amendements'] > 1 else ''} "
                   f"déposé{'s' if l['amendements'] > 1 else ''} en premier signataire"))
    cellules = "".join(
        f'<td width="{100 // len(tuiles)}%" valign="top" style="padding:0 {"6px" if i < len(tuiles) - 1 else "0"} 0 0">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{CARTE}" '
        f'style="{_style(background=CARTE, border=f"1px solid {BORD}", border_radius="8px")}"><tr><td style="padding:12px">'
        f'<p style="{_style(margin="0", font_size="24px", font_weight="bold", line_height="1.1", color=TEXTE)}">{_e(valeur)}</p>'
        f'<p style="{_style(margin="4px 0 0", font_size="12px", line_height="1.35", color=DOUX)}">{_e(libelle)}</p>'
        "</td></tr></table></td>"
        for i, (valeur, libelle) in enumerate(tuiles))
    lignes.append(f'<tr><td style="padding:0 0 8px"><table role="presentation" width="100%" '
                  f'cellpadding="0" cellspacing="0" border="0"><tr>{cellules}</tr></table></td></tr>')

    for titre, phrases, elements in contenu.rubriques(l, site_url):
        lignes.append(_titre(titre))
        if titre == "L'essentiel":
            lignes.append(_essentiel(l, phrases))
        elif titre == "Sa participation aux scrutins":
            lignes.append(_participation(l, phrases))
        else:
            lignes.append(_generique(phrases, elements))

    lien_fiche = f"{site_url}/{l['chemin_fiche']}"
    pied = [_p(_lien("Sa fiche complète", lien_fiche) + " · "
               + _lien("Comment c’est calculé", f"{site_url}/methodologie.html"), 14, TEXTE),
            _p("Ces chiffres sont des décomptes tirés des données ouvertes de l’Assemblée "
               "nationale. Ils mesurent un volume, pas une qualité.", 13, DOUX)]
    if l.get("libelles"):
        pied.append(_p(_e(contenu.NOTE_LIBELLES), 13, DOUX))
    if contact:
        pied.append(_p("Une erreur dans cette lettre ? "
                       + _lien("Signalez-la", f"mailto:{contact}") + ".", 13, DOUX))
    pied.append(_p(_lien("Gérer votre abonnement", lien_gestion) + " · "
                   + _lien("Vous désabonner", lien_desabonnement), 13, DOUX, "0"))
    lignes.append(f'<tr><td style="{_style(border_top=f"1px solid {BORD}", padding="14px 0 0")}">'
                  + "".join(pied) + "</td></tr>")

    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'bgcolor="{FOND}" style="{_style(background=FOND)}"><tr><td align="center" '
            f'style="padding:16px 10px">'
            f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" '
            f'style="{_style(width="100%", max_width="600px", font_family=POLICE, color=TEXTE)}">'
            + "".join(lignes) + "</table></td></tr></table>")
