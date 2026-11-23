"""Dépôt de fichiers dans un espace de stockage objet compatible S3.

Sert à garder hors du serveur une copie de la base des abonnés (chez Scaleway :
Object Storage). Les requêtes sont signées selon la méthode « AWS Signature
Version 4 », que Scaleway accepte, avec la seule bibliothèque standard.
"""

import datetime
import hashlib
import hmac
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ESPACE_S3 = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class ErreurStockage(Exception):
    pass


def _encoder(texte, garder="~"):
    return urllib.parse.quote(texte, safe=garder)


def _hmac(cle, texte):
    return hmac.new(cle, texte.encode(), hashlib.sha256).digest()


def signer(methode, chemin, requete, entetes, empreinte_corps, region, cle_acces,
           cle_secrete, instant, service="s3"):
    """Valeur de l'en-tête Authorization d'une requête.

    chemin : chemin non encodé (« /dossier/fichier ») ; requete : liste de
    (nom, valeur) ; entetes : en-têtes signés, dont host et x-amz-date ;
    empreinte_corps : SHA-256 hexadécimal du corps de la requête.
    """
    date_longue = instant.strftime("%Y%m%dT%H%M%SZ")
    date_courte = instant.strftime("%Y%m%d")
    entetes = {nom.lower(): " ".join(str(valeur).split()) for nom, valeur in entetes.items()}
    noms = sorted(entetes)
    canonique = "\n".join([
        methode,
        _encoder(chemin, "/~"),
        "&".join(f"{_encoder(n)}={_encoder(v)}" for n, v in sorted(requete)),
        "".join(f"{n}:{entetes[n]}\n" for n in noms),
        ";".join(noms),
        empreinte_corps])
    portee = f"{date_courte}/{region}/{service}/aws4_request"
    a_signer = "\n".join(["AWS4-HMAC-SHA256", date_longue, portee,
                          hashlib.sha256(canonique.encode()).hexdigest()])
    cle = _hmac(f"AWS4{cle_secrete}".encode(), date_courte)
    for morceau in (region, service, "aws4_request"):
        cle = _hmac(cle, morceau)
    signature = hmac.new(cle, a_signer.encode(), hashlib.sha256).hexdigest()
    return (f"AWS4-HMAC-SHA256 Credential={cle_acces}/{portee}, "
            f"SignedHeaders={';'.join(noms)}, Signature={signature}")


class Depot:
    """Un espace de stockage (« bucket ») chez un fournisseur compatible S3.

    hote : point d'accès de la région, par exemple « s3.fr-par.scw.cloud ».
    Par défaut l'espace est adressé comme sous-domaine du point d'accès
    (https://espace.s3.fr-par.scw.cloud/cle) ; style="chemin" l'adresse dans le
    chemin (https://hote/espace/cle), pour les essais avec un serveur local.
    """

    def __init__(self, hote, region, espace, cle_acces, cle_secrete, schema="https",
                 style="sous-domaine", ouvrir=urllib.request.urlopen, horloge=None):
        self.hote, self.region, self.espace = hote, region, espace
        self.cle_acces, self.cle_secrete = cle_acces, cle_secrete
        self.schema, self.style, self.ouvrir = schema, style, ouvrir
        self.horloge = horloge or (lambda: datetime.datetime.now(datetime.timezone.utc))

    def _requete(self, methode, cle="", requete=(), corps=b""):
        if self.style == "chemin":
            hote, chemin = self.hote, f"/{self.espace}/{cle}"
        else:
            hote, chemin = f"{self.espace}.{self.hote}", f"/{cle}"
        instant = self.horloge().astimezone(datetime.timezone.utc)
        empreinte = hashlib.sha256(corps).hexdigest()
        entetes = {"host": hote, "x-amz-date": instant.strftime("%Y%m%dT%H%M%SZ"),
                   "x-amz-content-sha256": empreinte}
        autorisation = signer(methode, chemin, list(requete), entetes, empreinte, self.region,
                              self.cle_acces, self.cle_secrete, instant)
        url = f"{self.schema}://{hote}{_encoder(chemin, '/~')}"
        if requete:
            url += "?" + "&".join(f"{_encoder(n)}={_encoder(v)}" for n, v in sorted(requete))
        envoyes = {n: v for n, v in entetes.items() if n != "host"}
        envoyes["Authorization"] = autorisation
        if methode == "PUT":
            envoyes["Content-Type"] = "application/octet-stream"
        demande = urllib.request.Request(url, data=corps if methode == "PUT" else None,
                                         headers=envoyes, method=methode)
        try:
            with self.ouvrir(demande, timeout=60) as reponse:
                return reponse.read()
        except urllib.error.HTTPError as erreur:
            detail = erreur.read()[:300].decode("utf-8", "replace")
            raise ErreurStockage(f"{methode} {cle or '/'} : HTTP {erreur.code} {detail}") from None
        except (urllib.error.URLError, OSError) as erreur:
            raise ErreurStockage(f"{methode} {cle or '/'} : {erreur}") from None

    def deposer(self, cle, donnees):
        self._requete("PUT", cle, corps=donnees)

    def lire(self, cle):
        return self._requete("GET", cle)

    def supprimer(self, cle):
        self._requete("DELETE", cle)

    def lister(self, prefixe=""):
        """Objets dont la clé commence par prefixe, triés par clé :
        liste de (clé, taille en octets, date de dernière modification)."""
        objets, suite = [], None
        while True:
            requete = [("list-type", "2"), ("prefix", prefixe)]
            if suite:
                requete.append(("continuation-token", suite))
            racine = ET.fromstring(self._requete("GET", "", requete))
            for objet in racine.iter(f"{ESPACE_S3}Contents"):
                objets.append((objet.findtext(f"{ESPACE_S3}Key"),
                               int(objet.findtext(f"{ESPACE_S3}Size") or 0),
                               objet.findtext(f"{ESPACE_S3}LastModified")))
            suite = racine.findtext(f"{ESPACE_S3}NextContinuationToken")
            if racine.findtext(f"{ESPACE_S3}IsTruncated") != "true" or not suite:
                return sorted(objets)
