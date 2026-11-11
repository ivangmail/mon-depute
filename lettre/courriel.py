"""Envoi des e-mails, par SMTP ou, pour les essais, dans un dossier."""

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid, parseaddr


# Ports où la connexion est chiffrée d'emblée ; sur les autres (587, 2587),
# le chiffrement est négocié après la connexion (STARTTLS).
PORTS_TLS_DIRECT = (465, 2465)


def construire(config, destinataire, sujet, texte, html=None, desabonnement=None):
    # Sans repli de ligne : un lien long dans un en-tête replié serait encodé,
    # et le désabonnement en un clic ne fonctionnerait plus.
    message = EmailMessage(policy=SMTP.clone(max_line_length=998))
    message["From"] = config.expediteur
    message["To"] = destinataire
    message["Subject"] = sujet
    message["Date"] = formatdate(localtime=False)
    domaine = parseaddr(config.expediteur)[1].rpartition("@")[2] or "localhost"
    message["Message-ID"] = make_msgid(domain=domaine)
    if desabonnement:
        # Désabonnement en un clic, proposé directement par les messageries (RFC 8058).
        message["List-Unsubscribe"] = f"<{desabonnement}>"
        message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    message.set_content(texte)
    if html:
        message.add_alternative(html, subtype="html")
    return message


def envoyer(config, message):
    if config.dossier_courriels:
        os.makedirs(config.dossier_courriels, exist_ok=True)
        numero = len(os.listdir(config.dossier_courriels)) + 1
        chemin = os.path.join(config.dossier_courriels, f"{numero:04d}.eml")
        with open(chemin, "wb") as f:
            f.write(bytes(message))
        return chemin
    contexte = ssl.create_default_context()
    if config.smtp_port in PORTS_TLS_DIRECT:
        serveur = smtplib.SMTP_SSL(config.smtp_hote, config.smtp_port, timeout=30,
                                   context=contexte)
    else:
        serveur = smtplib.SMTP(config.smtp_hote, config.smtp_port, timeout=30)
    with serveur:
        if config.smtp_port not in PORTS_TLS_DIRECT:
            serveur.starttls(context=contexte)
        if config.smtp_utilisateur:
            serveur.login(config.smtp_utilisateur, config.smtp_mot_de_passe)
        serveur.send_message(message)
    return None
