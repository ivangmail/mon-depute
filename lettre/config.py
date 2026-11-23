"""Configuration, lue dans les variables d'environnement.

Aucun secret ne doit figurer dans le dépôt : le mot de passe SMTP et la clé de
signature des liens sont fournis au service par son environnement.
"""

import os
from dataclasses import dataclass


class ConfigurationInvalide(Exception):
    pass


@dataclass
class Config:
    secret: bytes                 # clé de signature des liens envoyés par e-mail
    site_url: str                 # adresse publique du site, sans barre finale
    api_url: str                  # adresse publique de ce service, sans barre finale
    donnees: str                  # base des données de l'Assemblée (lecture seule)
    abonnes: str                  # base des abonnés (données personnelles)
    expediteur: str               # « Mon député <lettre@exemple.fr> »
    smtp_hote: str = ""
    smtp_port: int = 587
    smtp_utilisateur: str = ""
    smtp_mot_de_passe: str = ""
    dossier_courriels: str = ""   # si renseigné, les e-mails sont écrits ici au lieu d'être envoyés
    derriere_proxy: bool = False  # vrai si un serveur frontal renseigne X-Forwarded-For
    contact: str = ""             # adresse publiée pour signaler une erreur dans une lettre
    # Copie chiffrée de la base des abonnés hors du serveur (facultative).
    s3_espace: str = ""           # nom de l'espace de stockage (« bucket »)
    s3_region: str = "fr-par"
    s3_hote: str = ""             # point d'accès ; par défaut s3.<région>.scw.cloud
    s3_cle_acces: str = ""
    s3_cle_secrete: str = ""
    sauvegarde_phrase: str = ""   # phrase secrète de chiffrement des copies

    @property
    def origine(self):
        """Origine autorisée à appeler l'API depuis un navigateur."""
        morceaux = self.site_url.split("/")
        return "/".join(morceaux[:3])


def depuis_environnement(env=None):
    env = os.environ if env is None else env
    secret = env.get("MD_SECRET", "")
    if len(secret) < 32:
        raise ConfigurationInvalide(
            "MD_SECRET doit contenir au moins 32 caractères aléatoires "
            "(par exemple : python3 -c 'import secrets; print(secrets.token_urlsafe(48))').")
    manquantes = [n for n in ("MD_SITE_URL", "MD_API_URL", "MD_EXPEDITEUR") if not env.get(n)]
    if manquantes:
        raise ConfigurationInvalide("Variables manquantes : " + ", ".join(manquantes))
    if not env.get("MD_SMTP_HOTE") and not env.get("MD_DOSSIER_COURRIELS"):
        raise ConfigurationInvalide(
            "Renseigner MD_SMTP_HOTE (envoi réel) ou MD_DOSSIER_COURRIELS (essais).")
    espace = env.get("MD_S3_ESPACE", "").strip()
    if espace:
        manquantes = [n for n in ("MD_S3_CLE_ACCES", "MD_S3_CLE_SECRETE", "MD_SAUVEGARDE_PHRASE")
                      if not env.get(n)]
        if manquantes:
            raise ConfigurationInvalide("Sauvegarde hors serveur : variables manquantes : "
                                        + ", ".join(manquantes))
        if len(env["MD_SAUVEGARDE_PHRASE"]) < 20:
            raise ConfigurationInvalide("MD_SAUVEGARDE_PHRASE doit contenir au moins 20 caractères.")
    region = env.get("MD_S3_REGION", "").strip() or "fr-par"
    return Config(
        secret=secret.encode(),
        site_url=env["MD_SITE_URL"].rstrip("/"),
        api_url=env["MD_API_URL"].rstrip("/"),
        donnees=env.get("MD_DONNEES", "donnees/assemblee.sqlite"),
        abonnes=env.get("MD_ABONNES", "donnees/abonnes.sqlite"),
        expediteur=env["MD_EXPEDITEUR"],
        smtp_hote=env.get("MD_SMTP_HOTE", ""),
        smtp_port=int(env.get("MD_SMTP_PORT", "587")),
        smtp_utilisateur=env.get("MD_SMTP_UTILISATEUR", ""),
        smtp_mot_de_passe=env.get("MD_SMTP_MOT_DE_PASSE", ""),
        dossier_courriels=env.get("MD_DOSSIER_COURRIELS", ""),
        derriere_proxy=env.get("MD_DERRIERE_PROXY", "") == "1",
        contact=env.get("MD_CONTACT", "").strip(),
        s3_espace=espace, s3_region=region,
        s3_hote=env.get("MD_S3_HOTE", "").strip() or f"s3.{region}.scw.cloud",
        s3_cle_acces=env.get("MD_S3_CLE_ACCES", "").strip(),
        s3_cle_secrete=env.get("MD_S3_CLE_SECRETE", "").strip(),
        sauvegarde_phrase=env.get("MD_SAUVEGARDE_PHRASE", ""),
    )
