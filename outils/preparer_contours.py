"""Prépare les contours des circonscriptions utilisés par la recherche par adresse.

À relancer seulement si le découpage électoral change. Source :
« Contours géographiques des circonscriptions législatives », Jérôme Desboeufs,
data.gouv.fr, Licence Ouverte 2.0 (version p20, du 13/06/2024), d'après les
données du ministère de l'Intérieur et de l'INSEE.

    python3 outils/preparer_contours.py circonscriptions-legislatives-p20.geojson

Écrit un fichier par département dans collecte/contours/, sous la forme
{numéro de circonscription: [polygone, ...]}, un polygone étant une liste
d'anneaux (le contour puis les éventuels trous) et un anneau une liste à plat
[longitude, latitude, longitude, latitude, ...] arrondie à 5 décimales (1 m).
"""

import json
import os
import sys

# Les contours utilisent les codes du ministère de l'Intérieur pour l'outre-mer.
OUTRE_MER = {"ZA": "971", "ZB": "972", "ZC": "973", "ZD": "974", "ZM": "976", "ZS": "975"}
SORTIE = os.path.join(os.path.dirname(__file__), "..", "collecte", "contours")


def anneau(points):
    plat = []
    for lon, lat in points:
        plat += [round(lon, 5), round(lat, 5)]
    return plat


def convertir(geojson):
    """Renvoie {département: {numéro de circonscription: [polygones]}}."""
    departements = {}
    for f in geojson["features"]:
        p, g = f["properties"], f["geometry"]
        code = OUTRE_MER.get(p["codeDepartement"], p["codeDepartement"])
        numero = str(int(p["codeCirconscription"][-2:]))
        polygones = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        departements.setdefault(code, {})[numero] = [
            [anneau(a) for a in polygone] for polygone in polygones]
    return departements


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        resultat = convertir(json.load(f))
    os.makedirs(SORTIE, exist_ok=True)
    for code, circos in sorted(resultat.items()):
        with open(os.path.join(SORTIE, f"{code}.json"), "w", encoding="utf-8") as f:
            json.dump(circos, f, separators=(",", ":"), sort_keys=True)
    print(f"{len(resultat)} départements, "
          f"{sum(len(c) for c in resultat.values())} circonscriptions")
