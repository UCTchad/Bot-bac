import os
import logging
from datetime import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    filters,
    ContextTypes,
    JobQueue
)

# Import des modules personnalisés
from database import DatabaseManager
from user_manager import UserManager
from quiz_manager import QuizManager
from spam_manager import SpamManager
from badge_manager import BadgeManager
from analytics_manager import AnalyticsManager
from network_manager import network_manager, retry_on_network_error, safe_telegram_call
from rate_limiter import rate_limit, rate_limiter
from config import (
    TELEGRAM_TOKEN, GROUP_CHAT_ID, WELCOME_MESSAGE, MESSAGES,
    QUIZ_HOUR, QUIZ_MINUTE, LOG_LEVEL, LOG_FORMAT, CLEANUP_OLD_DATA_DAYS
)

# Configuration du logging
logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger(__name__)

# Initialisation des gestionnaires
db_manager = DatabaseManager()
user_manager = UserManager(db_manager)
quiz_manager = QuizManager(db_manager)
spam_manager = SpamManager(user_manager)
badge_manager = BadgeManager(db_manager)
analytics_manager = AnalyticsManager(db_manager)

# --- FONCTIONS UTILITAIRES ---

async def is_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Vérifie si un utilisateur est administrateur du groupe."""
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)

        if chat_member.status in ['creator', 'administrator']:
            logger.info(f"Utilisateur {user_id} est {chat_member.status} du groupe {chat_id}")
            return True

        logger.info(f"Utilisateur {user_id} n'est pas admin (statut: {chat_member.status})")
        return False

    except Exception as e:
        logger.error(f"Erreur vérification admin pour user {user_id} dans chat {chat_id}: {e}")

        try:
            chat_admins = await context.bot.get_chat_administrators(chat_id)
            admin_ids = [admin.user.id for admin in chat_admins]
            is_admin_result = user_id in admin_ids
            logger.info(f"Fallback: Utilisateur {user_id} admin status: {is_admin_result}")
            return is_admin_result
        except Exception as e2:
            logger.error(f"Erreur fallback vérification admin : {e2}")
            return False

def get_main_menu_keyboard(is_admin=False, is_private=True):
    """Retourne le clavier du menu principal avec style bleu."""
    if is_private:
        keyboard = [
            [InlineKeyboardButton("🔵 Quiz Thématiques", callback_data="menu_quiz_themes")],
            [InlineKeyboardButton("🔵 Mes Statistiques", callback_data="menu_stats"), InlineKeyboardButton("🏆 Mes Badges", callback_data="menu_badges")],
            [InlineKeyboardButton("🔵 Classements", callback_data="menu_leaderboards"), InlineKeyboardButton("🔥 Mes Streaks", callback_data="menu_streaks")],
            [InlineKeyboardButton("⚔️ Mes Défis", callback_data="menu_challenges"), InlineKeyboardButton("🎯 Créer Défi", callback_data="menu_create_challenge")],
            [InlineKeyboardButton("🔵 Mes Notes", callback_data="menu_notes")],
            [InlineKeyboardButton("🔵 Aide", callback_data="menu_help")]
        ]
    else:
        if is_admin:
            keyboard = [
                [InlineKeyboardButton("🔵 Quiz Thématiques (Admin)", callback_data="menu_quiz_themes")],
                [InlineKeyboardButton("🔵 Classements", callback_data="menu_leaderboards"), InlineKeyboardButton("📊 Analytics", callback_data="menu_analytics")],
                [InlineKeyboardButton("🔵 Mes Statistiques", callback_data="menu_stats"), InlineKeyboardButton("🔥 Mes Streaks", callback_data="menu_streaks")],
                [InlineKeyboardButton("⚔️ Mes Défis", callback_data="menu_challenges")],
                [InlineKeyboardButton("🔵 Aide", callback_data="menu_help")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("🔵 Classements", callback_data="menu_leaderboards"), InlineKeyboardButton("🔥 Mes Streaks", callback_data="menu_streaks")],
                [InlineKeyboardButton("🔵 Mes Statistiques", callback_data="menu_stats"), InlineKeyboardButton("⚔️ Mes Défis", callback_data="menu_challenges")],
                [InlineKeyboardButton("🔵 Mes Notes", callback_data="menu_notes")],
                [InlineKeyboardButton("🔵 Aide", callback_data="menu_help")]
            ]
    return InlineKeyboardMarkup(keyboard)

def get_quiz_themes_keyboard():
    """Retourne le clavier de sélection des thèmes de quiz."""
    from config import QUIZ_THEMES

    keyboard = []
    for theme_key, theme_info in QUIZ_THEMES.items():
        keyboard.append([InlineKeyboardButton(
            f"{theme_info['emoji']} {theme_info['name']}", 
            callback_data=f"quiz_theme_{theme_key}"
        )])

    keyboard.append([InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_main_reply_keyboard():
    """Retourne le clavier de menu principal physique."""
    keyboard = [
        [KeyboardButton("🔵 Menu")],
        [KeyboardButton("🎯 Quiz Maintenant"), KeyboardButton("🏆 Classement")],
        [KeyboardButton("📊 Mes Stats"), KeyboardButton("📝 Mes Notes")],
        [KeyboardButton("💡 Commandes")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# --- GESTIONNAIRES D'ÉVÉNEMENTS ---

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Message de bienvenue pour les nouveaux membres."""
    new_members = update.message.new_chat_members
    for member in new_members:
        if not member.is_bot:
            user_name = member.mention_html()
            await update.message.reply_text(
                WELCOME_MESSAGE.format(user_name=user_name),
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Nouveau membre accueilli : {member.username}")

async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les boutons du menu physique."""
    text = update.message.text

    if text == "🔵 Menu":
        await menu_command(update, context)
    elif text == "🎯 Quiz Maintenant":
        await quiz_now(update, context)
    elif text == "🏆 Classement":
        await ranking(update, context)
    elif text == "📊 Mes Stats":
        await stats(update, context)
    elif text == "📝 Mes Notes":
        await my_notes(update, context)
    elif text == "💡 Commandes":
        await commands_list(update, context)

async def handle_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestion des messages de spam."""
    await spam_manager.handle_spam_message(update, context)

# --- COMMANDES ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande de démarrage avec menu."""
    chat = update.effective_chat
    user = update.effective_user

    # Initialiser l'utilisateur en base
    user_manager.get_or_create_user(user.id, user.first_name or user.username or f"User{user.id}")

    if chat.type == 'private':
        menu_text = (
            f"👋 Salut {user.first_name} !\n\n"
            "🎓 **Bot Éducatif Personnel**\n\n"
            "📚 **Fonctionnalités disponibles :**\n"
            "• Quiz Histoire-Géographie (niveau Terminale)\n"
            "• Système d'étoiles : 5🌟 par bonne réponse\n"
            "• Suivi de vos performances\n"
            "• Classement général\n\n"
            "🎯 **Utilisez le menu bleu ci-dessous :**"
        )
        await update.message.reply_text(
            menu_text,
            reply_markup=get_main_reply_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await update.message.reply_text(
            "📱 **Menu Interactif :**",
            reply_markup=get_main_menu_keyboard(is_admin=False, is_private=True),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        user_is_admin = await is_admin(chat.id, user.id, context)

        menu_text = (
            "🎓 **Bot Éducatif Actif !**\n\n"
            "📚 **Fonctionnalités disponibles :**\n"
            "• 3 Quiz automatiques par jour à 21h00 (questions consécutives)\n"
            "• Format Poll Quiz interactif\n"
            "• Système d'étoiles : 5🌟 par bonne réponse\n"
            "• Classement TOP 20 avec notes détaillées\n"
            "• Messages de bienvenue automatiques\n"
            "• Protection anti-spam\n\n"
            "**Commandes disponibles :**\n"
            "/warn - Avertir un utilisateur (admins)\n\n"
            "🎯 **Utilisez le menu bleu ci-dessous :**"
        )
        await update.message.reply_text(
            menu_text,
            reply_markup=get_main_menu_keyboard(is_admin=user_is_admin, is_private=False),
            parse_mode=ParseMode.MARKDOWN
        )

async def commands_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les commandes disponibles."""
    commands_text = (
        "🎓 **Bot Éducatif Actif !**\n\n"
        "📚 Utilisez le menu bleu pour naviguer facilement :\n"
        "• Quiz Histoire-Géographie\n"
        "• Système d'étoiles : 5🌟 par bonne réponse\n"
        "• Classement TOP 20\n"
        "• Suivi de vos performances\n\n"
        "🎯 **Quiz quotidien automatique à 21h00 !**"
    )

    await update.message.reply_text(commands_text, parse_mode=ParseMode.MARKDOWN)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu principal."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == 'private':
        keyboard = get_main_menu_keyboard(is_admin=False, is_private=True)
    else:
        user_is_admin = await is_admin(chat.id, user.id, context)
        keyboard = get_main_menu_keyboard(is_admin=user_is_admin, is_private=False)

    await update.message.reply_text(
        MESSAGES["menu_title"],
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# --- GESTIONNAIRES DE CALLBACKS ---

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les callbacks du menu."""
    query = update.callback_query
    await query.answer()

    if query.data == "menu_quiz_themes":
        await quiz_themes_callback(update, context)
    elif query.data.startswith("quiz_theme_"):
        await quiz_theme_selected_callback(update, context)
    elif query.data == "menu_stats":
        await stats_callback(update, context)
    elif query.data == "menu_badges":
        await badges_callback(update, context)
    elif query.data == "menu_ranking":
        await ranking_callback(update, context)
    elif query.data == "menu_leaderboards":
        await leaderboards_callback(update, context)
    elif query.data.startswith("leaderboard_"):
        await leaderboard_period_callback(update, context)
    elif query.data == "menu_streaks":
        await streaks_callback(update, context)
    elif query.data == "menu_challenges":
        await challenges_callback(update, context)
    elif query.data == "menu_create_challenge":
        await create_challenge_callback(update, context)
    elif query.data == "menu_analytics":
        await analytics_callback(update, context)
    elif query.data == "menu_notes":
        await my_notes_callback(update, context)
    elif query.data == "menu_help":
        await help_callback(update, context)

async def quiz_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance un quiz depuis le menu."""
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user

    if chat.type != 'private' and not await is_admin(chat.id, user.id, context):
        await query.edit_message_text(MESSAGES["admin_only"])
        return

    success = await quiz_manager.send_single_poll_quiz(context, chat.id)
    if success:
        await query.edit_message_text(MESSAGES["quiz_launched"])
    else:
        await query.edit_message_text(MESSAGES["error_general"])

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les stats depuis le menu."""
    query = update.callback_query
    user = query.from_user

    stats = user_manager.get_user_stats(user.id)
    if not stats:
        await query.edit_message_text(
            MESSAGES["no_data"],
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )
        return

    score = stats['basic']
    percentage = stats['percentage']

    stats_text = (
        f"📊 **Vos Statistiques** - {user.first_name}\n\n"
        f"🌟 **Total étoiles :** {score['stars']}\n"
        f"✅ **Réussies :** {score['correct']}\n"
        f"❌ **Ratées :** {score['total'] - score['correct']}\n"
        f"📈 **Pourcentage :** {percentage:.1f}%\n"
        f"🎯 **Total questions :** {score['total']}"
    )

    await query.edit_message_text(
        stats_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
    )

async def ranking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le ranking depuis le menu."""
    query = update.callback_query
    await ranking_display(query, context)

async def my_notes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les notes depuis le menu."""
    query = update.callback_query
    await my_notes_display(query, context)

async def quiz_themes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu de sélection des thèmes."""
    query = update.callback_query

    themes_text = (
        "🎯 **CHOISISSEZ VOTRE THÈME DE QUIZ**\n\n"
        "📚 Sélectionnez le domaine qui vous intéresse :\n\n"
        "🏛️ **Histoire** : Antiquité, Moyen Âge, époque moderne...\n"
        "🌍 **Géographie** : Continents, pays, capitales, relief...\n"
        "📚 **Mix Histoire-Géo** : Questions variées des deux domaines\n\n"
        "💡 Chaque bonne réponse = 5🌟"
    )

    await query.edit_message_text(
        themes_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_quiz_themes_keyboard()
    )

async def quiz_theme_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance un quiz du thème sélectionné."""
    query = update.callback_query
    theme = query.data.replace("quiz_theme_", "")

    chat = query.message.chat
    user = query.from_user

    if chat.type != 'private' and not await is_admin(chat.id, user.id, context):
        await query.edit_message_text(MESSAGES["admin_only"])
        return

    from config import QUIZ_THEMES
    theme_info = QUIZ_THEMES.get(theme, {'name': 'Quiz', 'emoji': '🎯'})

    success = await quiz_manager.send_single_poll_quiz(context, chat.id, theme)
    if success:
        await query.edit_message_text(
            f"🎯 **Quiz {theme_info['name']} lancé !**\n\n"
            f"{theme_info['emoji']} Bonne chance !"
        )
    else:
        await query.edit_message_text(MESSAGES["error_general"])

@rate_limit('badges')
async def badges_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les badges de l'utilisateur."""
    query = update.callback_query
    user = query.from_user

    # Récupérer les stats pour vérifier les nouveaux badges
    stats = user_manager.get_user_stats(user.id)
    if stats:
        new_badges = badge_manager.check_user_badges(user.id, stats)
        if new_badges:
            # Notification de nouveaux badges (optionnel)
            pass

    # Afficher tous les badges
    user_badges = badge_manager.get_user_badges(user.id)
    badge_text = badge_manager.get_badge_display_text(user_badges)

    await query.edit_message_text(
        badge_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
    )

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche l'aide depuis le menu."""
    query = update.callback_query

    help_text = (
        "ℹ️ **AIDE - BOT ÉDUCATIF**\n\n"
        "🎯 **Quiz Automatiques :**\n"
        "• 3 questions consécutives chaque jour à 21h00\n"
        "• Format Poll interactif\n"
        "• 5🌟 par bonne réponse\n\n"
        "📊 **Système de Points :**\n"
        "• Bonne réponse = +5 étoiles\n"
        "• Mauvaise réponse = 0 étoile\n"
        "• Classement basé sur les étoiles totales\n\n"
        "🏆 **Classement :**\n"
        "• TOP 20 visible\n"
        "• Notes détaillées par utilisateur\n"
        "• Pourcentage de réussite\n\n"
        "📝 **Commandes utiles :**\n"
        "• /menu - Afficher ce menu\n"
        "• /ranking - Voir le classement\n"
        "• /my_notes - Vos notes personnelles"
    )

    await query.edit_message_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
    )

async def back_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Retour au menu principal."""
    query = update.callback_query
    await query.answer()

    chat = query.message.chat
    user = query.from_user

    if chat.type == 'private':
        keyboard = get_main_menu_keyboard(is_admin=False, is_private=True)
    else:
        user_is_admin = await is_admin(chat.id, user.id, context)
        keyboard = get_main_menu_keyboard(is_admin=user_is_admin, is_private=False)

    await query.edit_message_text(
        MESSAGES["menu_title"],
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# --- COMMANDES SPÉCIALISÉES ---

async def warn_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande pour avertir un membre."""
    user = update.effective_user
    chat = update.effective_chat

    logger.info(f"Commande /warn utilisée par {user.first_name} (ID: {user.id}) dans le chat {chat.id}")

    if chat.type == 'private':
        await update.message.reply_text(
            "❌ La commande `/warn` ne peut être utilisée qu'en groupe.\n"
            "💡 Allez dans votre groupe d'études pour utiliser cette commande."
        )
        return

    is_user_admin = await is_admin(chat.id, user.id, context)

    if not is_user_admin:
        await update.message.reply_text(
            f"❌ Cette commande est réservée aux administrateurs du groupe.\n"
            f"🔍 Debug: Votre ID est {user.id}, statut admin vérifié: {is_user_admin}"
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❓ Utilisez cette commande en répondant au message de l'utilisateur à avertir.\n"
            "Exemple : Répondez à un message avec `/warn Comportement inapproprié`"
        )
        return

    user_to_warn = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Comportement inapproprié"

    warning_count = user_manager.add_user_warning(user_to_warn.id)

    warning_text = (
        f"⚠️ **AVERTISSEMENT OFFICIEL** ⚠️\n\n"
        f"👤 Utilisateur : {user_to_warn.mention_html()}\n"
        f"📝 Motif : {reason}\n"
        f"🔢 Avertissement : {warning_count}/3\n\n"
        f"⚡ Bannissement automatique au 3ème avertissement."
    )

    await update.message.reply_to_message.reply_text(warning_text, parse_mode=ParseMode.HTML)
    logger.info(f"Avertissement donné à {user_to_warn.username} par {user.username}")

@rate_limit('quiz_now')
async def quiz_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lancer un quiz immédiatement."""
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != 'private' and not await is_admin(chat.id, user.id, context):
        await update.message.reply_text(MESSAGES["admin_only"])
        return

    await quiz_manager.send_single_poll_quiz(context, chat.id)

async def my_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Afficher les notes personnelles de l'utilisateur."""
    user = update.effective_user
    stats = user_manager.get_user_stats(user.id)

    if not stats:
        await update.message.reply_text(
            "📝 **Vous n'avez pas encore de notes !**\n\n"
            "Participez aux quiz pour voir vos résultats ici ! 🎯"
        )
        return

    await display_user_notes(update.message.reply_text, user, stats)

async def my_notes_display(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Afficher les notes depuis le callback."""
    user = query.from_user
    stats = user_manager.get_user_stats(user.id)

    if not stats:
        await query.edit_message_text(
            "📝 **Vous n'avez pas encore de notes !**\n\n"
            "Participez aux quiz pour voir vos résultats ici ! 🎯",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )
        return

    await display_user_notes(query.edit_message_text, user, stats, is_callback=True)

async def display_user_notes(reply_func, user, stats, is_callback=False):
    """Fonction utilitaire pour afficher les notes utilisateur."""
    try:
        score = stats['basic']
        grades = stats['grades']
        percentage = stats['percentage']

        notes_text = f"📝 **Vos Notes Personnelles** - {user.first_name}\n\n"
        notes_text += f"🌟 **Total étoiles :** {score['stars']}\n"
        notes_text += f"✅ **Réussies :** {score['correct']}\n"
        notes_text += f"❌ **Ratées :** {score['total'] - score['correct']}\n"
        notes_text += f"📊 **Pourcentage :** {percentage:.1f}%\n\n"

        if grades['correct']:
            notes_text += "✅ **Dernières bonnes réponses :**\n"
            for correct in grades['correct'][-3:]:
                notes_text += f"• {correct['question']} (+5🌟)\n"
            notes_text += "\n"

        if grades['incorrect']:
            notes_text += "❌ **Dernières réponses ratées :**\n"
            for incorrect in grades['incorrect'][-3:]:
                notes_text += f"• {incorrect['question']} (0🌟)\n"

        kwargs = {'parse_mode': ParseMode.MARKDOWN}
        if is_callback:
            kwargs['reply_markup'] = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])

        await reply_func(notes_text, **kwargs)

    except Exception as e:
        logger.error(f"Erreur affichage notes personnelles : {e}")
        await reply_func(MESSAGES["error_general"])

@rate_limit('ranking')
async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Afficher le classement TOP 20."""
    await ranking_display(update, context, is_message=True)

@retry_on_network_error(max_retries=3, delay=1.0)
@safe_telegram_call(network_manager)
async def ranking_display(update_or_query, context: ContextTypes.DEFAULT_TYPE, is_message=False) -> None:
    """Affiche le classement."""
    try:
        # Pour les groupes, afficher uniquement le classement du groupe
        chat_type = None
        if is_message:
            chat_type = update_or_query.message.chat.type
        else:
            chat_type = update_or_query.message.chat.type

        group_only = chat_type != 'private'
        ranking = user_manager.get_ranking(20, group_only=group_only)
        global_stats = user_manager.get_global_stats()

        if not ranking:
            if group_only:
                text = (
                    "📊 **Aucun score enregistré dans ce groupe pour le moment !**\n\n"
                    "Participez aux quiz quotidiens à 21h00 pour apparaître dans le classement du groupe ! 🎯"
                )
            else:
                text = (
                    "📊 **Aucun score enregistré pour le moment !**\n\n"
                    "Participez aux quiz pour apparaître dans le classement ! 🎯"
                )
            kwargs = {}
            if not is_message:
                kwargs['reply_markup'] = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])

            if is_message:
                await update_or_query.message.reply_text(text, **kwargs)
            else:
                await update_or_query.edit_message_text(text, **kwargs)
            return

        if group_only:
            ranking_text = "🏆 **TOP 20 - CLASSEMENT DU GROUPE** 🏆\n\n"
        else:
            ranking_text = "🏆 **TOP 20 - CLASSEMENT GÉNÉRAL** 🏆\n\n"
        medals = ["🥇", "🥈", "🥉"]

        for i, (user_id, score) in enumerate(ranking):
            rank = i + 1
            percentage = (score['correct'] / max(score['total'], 1)) * 100
            stars_display = "🌟" * min(score['stars'] // 5, 10)

            if rank <= 3:
                medal = medals[rank - 1]
                ranking_text += f"{medal} **{rank}.** {score['name']}\n"
            else:
                ranking_text += f"🏅 **{rank}.** {score['name']}\n"

            correct_count = score['correct']
            failed_count = score['total'] - score['correct']
            total_stars = score['stars']

            ranking_text += f"   ✅ Réussies: {correct_count} | ❌ Ratées: {failed_count}\n"
            ranking_text += f"   🌟 {total_stars} étoiles ({percentage:.1f}%)\n"
            if stars_display:
                ranking_text += f"   {stars_display}\n"
            ranking_text += "\n"

        # Statistiques globales
        if group_only:
            ranking_text += "📈 **STATISTIQUES DU GROUPE**\n"
        else:
            ranking_text += "📈 **STATISTIQUES GLOBALES**\n"
        ranking_text += f"👥 Participants : {global_stats.get('total_participants', 0)}\n"
        ranking_text += f"❓ Questions répondues : {global_stats.get('total_questions', 0)}\n"
        ranking_text += f"✅ Bonnes réponses : {global_stats.get('total_correct', 0)}\n"
        ranking_text += f"🌟 Total étoiles gagnées : {global_stats.get('total_stars', 0)}\n"

        if global_stats.get('total_questions', 0) > 0:
            global_percentage = global_stats.get('global_percentage', 0)
            ranking_text += f"📊 Taux de réussite général : {global_percentage:.1f}%"

        kwargs = {'parse_mode': ParseMode.MARKDOWN}
        if not is_message:
            kwargs['reply_markup'] = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])

        if is_message:
            await update_or_query.message.reply_text(ranking_text, **kwargs)
        else:
            await update_or_query.edit_message_text(ranking_text, **kwargs)

    except Exception as e:
        logger.error(f"Erreur classement : {e}")
        error_text = MESSAGES["error_general"]
        if is_message:
            await update_or_query.message.reply_text(error_text)
        else:
            await update_or_query.edit_message_text(error_text)


async def leaderboards_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu des classements."""
    query = update.callback_query

    leaderboards_text = (
        "🏆 **CLASSEMENTS PAR PÉRIODE** 🏆\n\n"
        "📅 Choisissez la période qui vous intéresse :\n\n"
        "🌅 **Aujourd'hui** : Performances d'aujourd'hui\n"
        "📅 **Cette semaine** : 7 derniers jours\n"
        "🗓️ **Ce mois** : 30 derniers jours\n\n"
        "💡 Les classements sont mis à jour en temps réel !"
    )

    keyboard = [
        [InlineKeyboardButton("🌅 Aujourd'hui", callback_data="leaderboard_daily")],
        [InlineKeyboardButton("📅 Cette Semaine", callback_data="leaderboard_weekly")],
        [InlineKeyboardButton("🗓️ Ce Mois", callback_data="leaderboard_monthly")],
        [InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]
    ]

    await query.edit_message_text(
        leaderboards_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def leaderboard_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche un classement spécifique par période."""
    query = update.callback_query
    period = query.data.replace("leaderboard_", "")

    try:
        from leaderboard_manager import LeaderboardManager
        leaderboard_manager = LeaderboardManager(db_manager)

        leaderboard_text = leaderboard_manager.get_leaderboard_text(period, 10)

        keyboard = [
            [InlineKeyboardButton("🔄 Actualiser", callback_data=f"leaderboard_{period}")],
            [InlineKeyboardButton("🔙 Classements", callback_data="menu_leaderboards")]
        ]

        await query.edit_message_text(
            leaderboard_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Erreur affichage classement {period}: {e}")
        await query.edit_message_text(
            "❌ Erreur lors du chargement du classement.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )

async def streaks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les streaks de l'utilisateur."""
    query = update.callback_query
    user = query.from_user

    try:
        from streak_manager import StreakManager
        streak_manager = StreakManager(db_manager)

        streak_text = streak_manager.get_streak_display_text(user.id)

        # Ajouter le classement des streaks
        streak_leaderboard = streak_manager.get_streak_leaderboard(5)
        if streak_leaderboard:
            streak_text += "\n\n🔥 **TOP 5 STREAKS ACTUELS** 🔥\n"
            for i, user_streak in enumerate(streak_leaderboard):
                rank = i + 1
                medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
                medal = medals[min(rank-1, 4)]
                streak_text += f"{medal} {user_streak['name']}: {user_streak['current_streak']} jours\n"

        await query.edit_message_text(
            streak_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )

    except Exception as e:
        logger.error(f"Erreur affichage streaks: {e}")
        await query.edit_message_text(
            "❌ Erreur lors du chargement des streaks.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )

async def challenges_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les défis de l'utilisateur."""
    query = update.callback_query
    user = query.from_user

    try:
        from challenge_manager import ChallengeManager
        challenge_manager = ChallengeManager(db_manager)

        challenge_text = challenge_manager.get_challenge_display_text(user.id)

        keyboard = [
            [InlineKeyboardButton("🎯 Créer un Défi", callback_data="menu_create_challenge")],
            [InlineKeyboardButton("🔄 Actualiser", callback_data="menu_challenges")],
            [InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]
        ]

        await query.edit_message_text(
            challenge_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Erreur affichage défis: {e}")
        await query.edit_message_text(
            "❌ Erreur lors du chargement des défis.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )

async def create_challenge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Interface de création de défi."""
    query = update.callback_query

    create_text = (
        "🎯 **CRÉER UN DÉFI** ⚔️\n\n"
        "💡 **Comment créer un défi :**\n"
        "1. Utilisez la commande `/challenge @utilisateur`\n"
        "2. L'utilisateur recevra une notification\n"
        "3. S'il accepte, le défi commence !\n\n"
        "🏁 **Types de défis disponibles :**\n"
        "• **Course aux questions** : Premier à 10 bonnes réponses\n"
        "• **Plus d'étoiles** : Qui gagne le plus d'étoiles en 24h\n"
        "• **Streak battle** : Meilleur streak sur 7 jours\n\n"
        "⏰ **Durée** : 24h pour accepter, 7 jours pour terminer\n\n"
        "**Exemple :** `/challenge @alice course 10`"
    )

    await query.edit_message_text(
        create_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
    )

async def analytics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les analytics avancés (admins seulement)."""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    # Vérifier les permissions admin
    if chat.type != 'private' and not await is_admin(chat.id, user.id, context):
        await query.edit_message_text("❌ Fonction réservée aux administrateurs.")
        return

    try:
        analytics_text = analytics_manager.get_advanced_analytics_text()

        keyboard = [
            [InlineKeyboardButton("📊 Questions Difficiles", callback_data="analytics_hard_questions")],
            [InlineKeyboardButton("🎯 Tendances", callback_data="analytics_trends")],
            [InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]
        ]

        await query.edit_message_text(
            analytics_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Erreur affichage analytics: {e}")
        await query.edit_message_text(
            "❌ Erreur lors du chargement des analytics.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )


        ranking_text += f"🌟 Total étoiles gagnées : {global_stats.get('total_stars', 0)}\n"

        if global_stats.get('total_questions', 0) > 0:
            global_percentage = global_stats.get('global_percentage', 0)
            ranking_text += f"📊 Taux de réussite général : {global_percentage:.1f}%"

        kwargs = {'parse_mode': ParseMode.MARKDOWN}
        if not is_message:
            kwargs['reply_markup'] = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])

        if is_message:
            await update_or_query.message.reply_text(ranking_text, **kwargs)
        else:
            await update_or_query.edit_message_text(ranking_text, **kwargs)

    except Exception as e:
        logger.error(f"Erreur classement : {e}")
        try:
            error_text = MESSAGES["error_general"]
            if is_message:
                await update_or_query.message.reply_text(error_text)
            else:
                await update_or_query.edit_message_text(error_text)
        except Exception as e2:
            logger.error(f"Erreur lors de l'envoi du message d'erreur : {e2}")


async def database_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les statistiques de la base de données (admins seulement)."""
    user = update.effective_user
    chat = update.effective_chat

    # Vérifier les permissions admin
    if chat.type != 'private' and not await is_admin(chat.id, user.id, context):
        await update.message.reply_text("❌ Commande réservée aux administrateurs.")
        return

    try:
        db_stats = db_manager.get_database_stats()

        stats_text = (
            "📊 **STATISTIQUES BASE DE DONNÉES**\n\n"
            f"💾 **Taille :** {db_stats.get('db_size_mb', 0)} MB\n"
            f"👥 **Utilisateurs :** {db_stats.get('user_scores_count', 0)}\n"
            f"📝 **Notes totales :** {db_stats.get('user_grades_count', 0)}\n"
            f"⚠️ **Avertissements :** {db_stats.get('user_warnings_count', 0)}\n"
            f"🏆 **Badges :** {db_stats.get('user_badges_count', 0)}\n"
            f"🎯 **Polls actifs :** {db_stats.get('active_polls_count', 0)}\n"
            f"📅 **Sessions quiz :** {db_stats.get('daily_quiz_sessions_count', 0)}\n"
            f"🗄️ **Données archivées :** {db_stats.get('archived_data_count', 0)}\n\n"
            f"⚡ **Optimisation :** Base indexée pour performances\n"
            f"🔄 **Buffer réseau :** {len(network_manager.message_buffer)} messages en attente"
        )

        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Erreur affichage stats DB : {e}")
        await update.message.reply_text("❌ Erreur récupération des statistiques.")
    except Exception as e:
        logger.error(f"Erreur affichage stats DB : {e}")
        await update.message.reply_text("❌ Erreur récupération des statistiques.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande d'aide."""
    help_text = (
        "ℹ️ **AIDE - BOT ÉDUCATIF**\n\n"
        "🎯 **Quiz Automatiques :**\n"
        "• 3 questions consécutives chaque jour à 21h00\n"
        "• Format Poll interactif\n"
        "• 5🌟 par bonne réponse\n\n"
        "📊 **Système de Points :**\n"
        "• Bonne réponse = +5 étoiles\n"
        "• Mauvaise réponse = 0 étoile\n"
        "• Classement basé sur les étoiles totales\n\n"
        "🏆 **Classement :**\n"
        "• TOP 20 visible\n"
        "• Notes détaillées par utilisateur\n"
        "• Pourcentage de réussite\n\n"
        "📝 **Commandes disponibles :**\n"
        "• /menu - Menu principal\n"
        "• /ranking - Classement du groupe\n"
        "• /stats - Statistiques\n"
        "• /my_notes - Vos notes personnelles\n"
        "• /quiz_now - Lancer un quiz (admins)\n"
        "• /warn - Avertir un utilisateur (admins)\n\n"
        "💡 **Utilisez /menu pour accéder facilement à toutes les fonctions !**"
    )

    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

@rate_limit('stats')
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Afficher les statistiques."""
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != 'private' and not await is_admin(chat.id, user.id, context):
        await update.message.reply_text(MESSAGES["admin_only"])
        return

    try:
        if chat.type == 'private':
            stats_text = (
                f"📊 **Vos Statistiques Personnelles**\n\n"
                f"👤 Utilisateur : {user.first_name}\n"
                f"🎯 Quiz disponibles : Histoire-Géographie\n"
                f"🤖 Bot actif et prêt pour vos quiz !\n"
                f"💡 Utilisez /menu pour accéder à toutes les fonctions"
            )
        else:
            chat_member_count = await context.bot.get_chat_member_count(chat.id)
            all_warnings = db_manager.get_all_warnings()
            warnings_count = len(all_warnings)

            stats_text = (
                f"📊 **Statistiques du Groupe**\n\n"
                f"👥 Membres : {chat_member_count}\n"
                f"⚠️ Utilisateurs avec avertissements : {warnings_count}\n"
                f"🤖 Bot actif avec persistance des données\n"
                f"📅 Quiz quotidiens : 3 questions consécutives à 21h00"
            )

        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Erreur stats : {e}")
        await update.message.reply_text(MESSAGES["error_general"])

# --- GESTION DES POLLS ---

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les réponses aux polls."""
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    user = poll_answer.user

    poll_data = quiz_manager.get_active_poll(poll_id)
    if not poll_data:
        return

    try:
        question_data = poll_data['question_data']
        session_id = poll_data.get('session_id')

        # Créer ou récupérer l'utilisateur
        user_name = user.first_name or user.username or f"User{user.id}"

        # Ajouter à la session si c'est un quiz quotidien
        if session_id:
            quiz_manager.update_daily_session_participant(session_id, user.id)

        # Vérifier si la réponse est correcte
        selected_options = poll_answer.option_ids
        is_correct = (selected_options and 
                     selected_options[0] == question_data['correct_option_id'])

        # Mettre à jour les scores de l'utilisateur
        user_manager.update_user_answer(
            user.id, user_name, poll_data['question'], is_correct
        )

        logger.info(f"Réponse poll enregistrée pour {user_name}: {'correcte' if is_correct else 'incorrecte'}")

    except Exception as e:
        logger.error(f"Erreur gestion réponse poll : {e}")

def schedule_daily_quiz(job_queue: JobQueue, chat_id: int) -> None:
    """Programme le quiz quotidien."""
    quiz_time = time(hour=QUIZ_HOUR, minute=QUIZ_MINUTE)
    job_queue.run_daily(
        callback=lambda ctx: quiz_manager.send_daily_quiz_sequence(ctx),
        time=quiz_time,
        name=f"daily_quiz_sequence_{chat_id}"
    )

    logger.info(f"Quiz quotidien programmé à {QUIZ_HOUR:02d}h{QUIZ_MINUTE:02d} pour le groupe {chat_id}")

def schedule_cleanup(job_queue: JobQueue) -> None:
    """Programme le nettoyage automatique des anciennes données."""
    # Nettoyage quotidien à 2h00
    cleanup_time = time(hour=2, minute=0)
    job_queue.run_daily(
        callback=lambda ctx: db_manager.cleanup_old_data(CLEANUP_OLD_DATA_DAYS),
        time=cleanup_time,
        name="daily_cleanup"
    )

    # Archivage hebdomadaire le dimanche à 3h00
    archive_time = time(hour=3, minute=0)
    job_queue.run_weekly(
        callback=lambda ctx: db_manager.archive_old_data(90),
        time=archive_time,
        days=(6,),  # Dimanche
        name="weekly_archive"
    )

    # Optimisation mensuelle le 1er à 4h00
    optimize_time = time(hour=4, minute=0)
    job_queue.run_monthly(
        callback=lambda ctx: db_manager.optimize_database(),
        time=optimize_time,
        day=1,
        name="monthly_optimize"
    )

    # Traitement du buffer toutes les 5 minutes
    job_queue.run_repeating(
        callback=lambda ctx: network_manager.process_buffer(ctx),
        interval=300,  # 5 minutes
        name="process_message_buffer"
    )

    # Nettoyage des caches et rate limiter toutes les 2 minutes
    def cleanup_performance_systems(context):
        rate_limiter.cleanup_expired()
        global_cache.cleanup_expired()
        logger.info("Nettoyage des systèmes de performance effectué")

    job_queue.run_repeating(
        callback=cleanup_performance_systems,
        interval=120,  # 2 minutes
        name="cleanup_performance"
    )

    logger.info(f"Tâches programmées : nettoyage quotidien, archivage hebdomadaire, optimisation mensuelle")

# --- FONCTION PRINCIPALE ---

def main() -> None:
    """Démarre le bot."""
    if not TELEGRAM_TOKEN:
        logger.error("❌ Veuillez configurer votre TOKEN Telegram !")
        print("❌ Veuillez configurer votre TOKEN Telegram dans les variables d'environnement !")
        return

    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Commandes essentielles
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("warn", warn_member))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("ranking", ranking))
        application.add_handler(CommandHandler("stats", stats))
        application.add_handler(CommandHandler("my_notes", my_notes))
        application.add_handler(CommandHandler("quiz_now", quiz_now))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("commandes", commands_list))
        application.add_handler(CommandHandler("db_stats", database_stats))

        # Gestionnaires d'événements
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

        # Gestionnaire pour les boutons du menu physique (priorité haute)
        menu_button_filters = filters.Regex("^🔵 Menu$|^🎯 Quiz Maintenant$|^🏆 Classement$|^📊 Mes Stats$|^📝 Mes Notes$|^💡 Commandes$")
        application.add_handler(MessageHandler(menu_button_filters, handle_menu_buttons), group=0)

        # Gestionnaire anti-spam (priorité basse)
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_spam), group=1)

        # Gestionnaires de callbacks pour le menu
        application.add_handler(CallbackQueryHandler(handle_menu_callback, pattern="^menu_"))
        application.add_handler(CallbackQueryHandler(back_menu_callback, pattern="^back_menu$"))

        # Gestionnaire de réponses aux polls
        application.add_handler(PollAnswerHandler(handle_poll_answer))

        # Programmer les tâches périodiques
        if application.job_queue:
            schedule_daily_quiz(application.job_queue, GROUP_CHAT_ID)
            schedule_cleanup(application.job_queue)
        else:
            logger.warning("JobQueue non disponible - Quiz quotidien et nettoyage désactivés")

        logger.info("🚀 Bot éducatif démarré avec persistance des données !")
        print("🚀 Bot éducatif démarré avec améliorations !")
        print(f"📊 Base de données : {db_manager.db_path}")
        print(f"📅 Quiz quotidien : {QUIZ_HOUR:02d}h{QUIZ_MINUTE:02d}")
        print(f"🧹 Nettoyage auto : données > {CLEANUP_OLD_DATA_DAYS} jours")

        application.run_polling()

    except Exception as e:
        logger.error(f"Erreur critique au démarrage : {e}")
        print(f"❌ Erreur au démarrage : {e}")

if __name__ == "__main__":
    main()