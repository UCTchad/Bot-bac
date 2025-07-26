import os
# Configuration du Bot Telegram Éducatif
# Copiez ce fichier vers config.py et modifiez les valeurs

# Token de votre bot Telegram (obtenu via @BotFather)
TELEGRAM_TOKEN = os.getenv("TOKEN")

# ID de votre groupe Telegram (utilisez @userinfobot pour l'obtenir)
GROUP_CHAT_ID = -1002391261450  # Remplacez par l'ID réel de votre groupe

# Fuseau horaire pour le quiz quotidien (par défaut Paris)
TIMEZONE = "Europe/Paris"

# Heure du quiz quotidien (format 24h)
QUIZ_HOUR = 21
QUIZ_MINUTE = 0

# Configuration anti-spam
MAX_WARNINGS = 3  # Nombre d'avertissements avant bannissement
SPAM_KEYWORDS = [
    "crypto",
    "forex", 
    "gagnez de l'argent",
    "investissement rapide",
    "http://",
    "https://"
]

# Message de bienvenue personnalisé
WELCOME_MESSAGE = (
    "👋 Bienvenue {user_name} dans notre groupe d'études ! 📚\n"
    "N'hésitez pas à participer aux discussions et aux quiz quotidiens à 21h00."
)
