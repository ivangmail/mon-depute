"""Point d'entrée pour un serveur WSGI de production (gunicorn lettre.wsgi:application)."""

from .application import Application
from .config import depuis_environnement

application = Application(depuis_environnement())
