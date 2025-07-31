
import os
from datetime import time

# Configuration du Bot Telegram Éducatif

# Token de votre bot Telegram (obtenu via @BotFather)
TELEGRAM_TOKEN = os.getenv("TOKEN")

# ID de votre groupe Telegram (utilisez @userinfobot pour l'obtenir)
GROUP_CHAT_ID = -1002391261450  # Remplacez par l'ID réel de votre groupe

# Configuration de la base de données
DATABASE_PATH = "bot_data.db"

# Fuseau horaire pour le quiz quotidien (Tchad - WAT)
TIMEZONE = "Africa/Ndjamena"

# Heure du quiz quotidien (format 24h)
QUIZ_HOUR = 21
QUIZ_MINUTE = 0

# Configuration du quiz quotidien
DAILY_QUIZ_QUESTIONS_COUNT = 3
QUIZ_ANSWER_TIME_SECONDS = 60
QUIZ_QUESTION_DELAY_SECONDS = 10

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

# Configuration des points
POINTS_PER_CORRECT_ANSWER = 5

# Message de bienvenue personnalisé
WELCOME_MESSAGE = (
    "👋 Bienvenue {user_name} dans notre groupe d'études ! 📚\n"
    "N'hésitez pas à participer aux discussions et aux quiz quotidiens à 21h00."
)

# Messages du système
MESSAGES = {
    "menu_title": "🎓 **MENU PRINCIPAL - BOT ÉDUCATIF**\n\n📚 Choisissez une option ci-dessous :",
    "quiz_launched": "🎯 Quiz lancé !",
    "admin_only": "❌ Cette fonction est réservée aux administrateurs en groupe.",
    "no_data": "📊 Aucune donnée disponible. Participez aux quiz pour voir vos stats !",
    "error_general": "❌ Une erreur s'est produite. Veuillez réessayer.",
    "spam_detected": "🚫 Message supprimé pour spam.",
    "user_banned": "🚫 {username} a été banni pour spam répété.",
    "warning_message": "⚠️ {username}, message supprimé pour spam.\nAvertissement {warning_count}/3. Encore {remaining} avant bannissement."
}

# Configuration du logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Configuration des nettoyages automatiques
CLEANUP_OLD_DATA_DAYS = 30  # Supprimer les données de plus de 30 jours

# Questions par défaut (chemin vers le fichier JSON)
QUESTIONS_FILE = "questions.json"

# Configuration des quiz thématiques
QUIZ_THEMES = {
    'histoire': {
        'name': '🏛️ Histoire',
        'emoji': '🏛️',
        'description': 'Questions d\'histoire de l\'Antiquité à nos jours'
    },
    'geographie': {
        'name': '🌍 Géographie', 
        'emoji': '🌍',
        'description': 'Géographie physique, humaine et économique'
    },
    'histoire_geographie': {
        'name': '📚 Histoire-Géographie',
        'emoji': '📚', 
        'description': 'Mix Histoire et Géographie (mode classique)'
    }
}
