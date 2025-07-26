import os
import logging
import random
import json
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll, ReplyKeyboardMarkup, KeyboardButton
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

# --- CONFIGURATION ---
TOKEN = os.getenv("TOKEN")

# Message de bienvenue
WELCOME_MESSAGE = "👋 Bienvenue {user_name} dans notre groupe d'études ! 📚\nN'hésitez pas à participer aux discussions et aux quiz quotidiens à 21h00."

# Mots-clés de spam
SPAM_KEYWORDS = ["crypto", "forex", "gagnez de l'argent", "investissement rapide", "http://", "https://"]

# Chargement des questions depuis le fichier JSON
def load_quiz_questions():
    try:
        with open('questions.json', 'r', encoding='utf-8') as file:
            data = json.load(file)
            return data['histoire_geographie']
    except FileNotFoundError:
        logger.error("Fichier questions.json non trouvé")
        return []
    except Exception as e:
        logger.error(f"Erreur lors du chargement des questions : {e}")
        return []

# Questions d'Histoire-Géographie pour Terminale
QUIZ_QUESTIONS = load_quiz_questions()

# Configuration du logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Dictionnaire pour stocker les avertissements des utilisateurs
user_warnings = {}

# Dictionnaire pour stocker les scores des utilisateurs
user_scores = {}

# Dictionnaire pour stocker les notes de chaque utilisateur
user_grades = {}  # Structure: {user_id: {'correct': [], 'incorrect': [], 'total_stars': int}}

# Dictionnaire pour stocker les polls actifs
active_polls = {}

# Dictionnaire pour stocker les sessions de quiz quotidiens
daily_quiz_sessions = {}

# --- FONCTIONS UTILITAIRES ---

async def is_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Vérifie si un utilisateur est administrateur du groupe."""
    try:
        # Obtenir les informations du membre spécifique
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        
        # Vérifier le statut (creator = fondateur, administrator = admin)
        if chat_member.status in ['creator', 'administrator']:
            logger.info(f"Utilisateur {user_id} est {chat_member.status} du groupe {chat_id}")
            return True
        
        logger.info(f"Utilisateur {user_id} n'est pas admin (statut: {chat_member.status})")
        return False
        
    except Exception as e:
        logger.error(f"Erreur vérification admin pour user {user_id} dans chat {chat_id}: {e}")
        
        # Fallback : essayer avec get_chat_administrators
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
        # Menu complet pour conversation privée avec style bleu
        keyboard = [
            [InlineKeyboardButton("🔵 Lancer Quiz", callback_data="menu_quiz")],
            [InlineKeyboardButton("🔵 Mes Statistiques", callback_data="menu_stats")],
            [InlineKeyboardButton("🔵 Classement TOP 20", callback_data="menu_ranking")],
            [InlineKeyboardButton("🔵 Mes Notes", callback_data="menu_notes")],
            [InlineKeyboardButton("🔵 Aide", callback_data="menu_help")]
        ]
    else:
        # Menu pour groupe avec restrictions et style bleu
        if is_admin:
            keyboard = [
                [InlineKeyboardButton("🔵 Lancer Quiz (Admin)", callback_data="menu_quiz")],
                [InlineKeyboardButton("🔵 Classement TOP 20", callback_data="menu_ranking")],
                [InlineKeyboardButton("🔵 Mes Statistiques", callback_data="menu_stats")],
                [InlineKeyboardButton("🔵 Mes Notes", callback_data="menu_notes")],
                [InlineKeyboardButton("🔵 Aide", callback_data="menu_help")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("🔵 Classement TOP 20", callback_data="menu_ranking")],
                [InlineKeyboardButton("🔵 Mes Statistiques", callback_data="menu_stats")],
                [InlineKeyboardButton("🔵 Mes Notes", callback_data="menu_notes")],
                [InlineKeyboardButton("🔵 Aide", callback_data="menu_help")]
            ]
    return InlineKeyboardMarkup(keyboard)

def get_main_reply_keyboard():
    """Retourne le clavier de menu principal physique (comme dans l'image)."""
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
    user = update.effective_user
    chat = update.effective_chat
    
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
    message = update.message
    if not message or not message.text:
        return
        
    text = message.text.lower()
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Vérification des mots-clés de spam
    if any(keyword in text for keyword in SPAM_KEYWORDS):
        try:
            await message.delete()
            
            # Ajouter un avertissement
            if user_id not in user_warnings:
                user_warnings[user_id] = 0
            user_warnings[user_id] += 1
            
            username = message.from_user.mention_html()
            
            if user_warnings[user_id] >= 3:
                # Bannir après 3 avertissements
                try:
                    await context.bot.ban_chat_member(chat_id, user_id)
                    await context.bot.send_message(
                        chat_id,
                        f"🚫 {username} a été banni pour spam répété.",
                        parse_mode=ParseMode.HTML
                    )
                    del user_warnings[user_id]
                    logger.info(f"Utilisateur banni : {message.from_user.username}")
                except Exception as e:
                    logger.error(f"Erreur bannissement : {e}")
            else:
                # Avertissement
                remaining = 3 - user_warnings[user_id]
                warning_msg = await context.bot.send_message(
                    chat_id,
                    f"⚠️ {username}, message supprimé pour spam.\n"
                    f"Avertissement {user_warnings[user_id]}/3. "
                    f"Encore {remaining} avant bannissement.",
                    parse_mode=ParseMode.HTML
                )
                # Supprimer le message d'avertissement après 10 secondes
                context.job_queue.run_once(
                    lambda ctx: ctx.bot.delete_message(chat_id, warning_msg.message_id),
                    when=10
                )
            
            logger.info(f"Message spam supprimé de {message.from_user.username}")
        except Exception as e:
            logger.error(f"Erreur suppression spam : {e}")

# --- COMMANDES ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande de démarrage avec menu."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == 'private':
        # Message pour conversation privée avec menu
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
        # Envoyer le menu physique ET le menu inline
        await update.message.reply_text(
            menu_text,
            reply_markup=get_main_reply_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        # Puis le menu inline
        await update.message.reply_text(
            "📱 **Menu Interactif :**",
            reply_markup=get_main_menu_keyboard(is_admin=False, is_private=True),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Vérifier si l'utilisateur est admin
        user_is_admin = await is_admin(chat.id, user.id, context)
        
        # Message pour groupe avec menu
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
    """Affiche le message sans liste de commandes."""
    commands_text = (
        "🎓 **Bot Éducatif Actif !**\n\n"
        "📚 Utilisez le menu bleu pour naviguer facilement :\n"
        "• Quiz Histoire-Géographie\n"
        "• Système d'étoiles : 5🌟 par bonne réponse\n"
        "• Classement TOP 20\n"
        "• Suivi de vos performances\n\n"
        "🎯 **Quiz quotidien automatique à 21h00 !**"
    )
    
    await update.message.reply_text(
        commands_text,
        parse_mode=ParseMode.MARKDOWN
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu principal."""
    chat = update.effective_chat
    user = update.effective_user
    
    menu_text = (
        "🎓 **MENU PRINCIPAL - BOT ÉDUCATIF**\n\n"
        "📚 Choisissez une option ci-dessous :"
    )
    
    if chat.type == 'private':
        keyboard = get_main_menu_keyboard(is_admin=False, is_private=True)
    else:
        user_is_admin = await is_admin(chat.id, user.id, context)
        keyboard = get_main_menu_keyboard(is_admin=user_is_admin, is_private=False)
    
    await update.message.reply_text(
        menu_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les callbacks du menu."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "menu_quiz":
        await quiz_now_callback(update, context)
    elif query.data == "menu_stats":
        await stats_callback(update, context)
    elif query.data == "menu_ranking":
        await ranking_callback(update, context)
    elif query.data == "menu_notes":
        await my_notes_callback(update, context)
    elif query.data == "menu_help":
        await help_callback(update, context)

async def quiz_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance un quiz depuis le menu."""
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user

    # En privé, tout le monde peut utiliser
    # En groupe, seuls les admins peuvent
    if chat.type != 'private' and not await is_admin(chat.id, user.id, context):
        await query.edit_message_text("❌ Cette fonction est réservée aux administrateurs en groupe.")
        return
    
    await send_single_poll_quiz(context, chat.id)
    await query.edit_message_text("🎯 Quiz lancé !")

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les stats depuis le menu."""
    query = update.callback_query
    user = query.from_user
    
    if user.id not in user_scores:
        await query.edit_message_text(
            "📊 **Vos Statistiques**\n\n"
            "Aucune donnée disponible. Participez aux quiz pour voir vos stats !",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )
        return
    
    score = user_scores[user.id]
    percentage = (score['correct'] / max(score['total'], 1)) * 100
    
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
    
    menu_text = (
        "🎓 **MENU PRINCIPAL - BOT ÉDUCATIF**\n\n"
        "📚 Choisissez une option ci-dessous :"
    )
    
    if chat.type == 'private':
        keyboard = get_main_menu_keyboard(is_admin=False, is_private=True)
    else:
        user_is_admin = await is_admin(chat.id, user.id, context)
        keyboard = get_main_menu_keyboard(is_admin=user_is_admin, is_private=False)
    
    await query.edit_message_text(
        menu_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

async def warn_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande pour avertir un membre."""
    user = update.effective_user
    chat = update.effective_chat

    # Log pour débogage
    logger.info(f"Commande /warn utilisée par {user.first_name} (ID: {user.id}) dans le chat {chat.id}")
    
    # Vérifier que la commande est utilisée dans un groupe
    if chat.type == 'private':
        await update.message.reply_text(
            "❌ La commande `/warn` ne peut être utilisée qu'en groupe.\n"
            "💡 Allez dans votre groupe d'études pour utiliser cette commande."
        )
        return
    
    # Vérifier les permissions admin dans le groupe
    is_user_admin = await is_admin(chat.id, user.id, context)
    logger.info(f"Résultat vérification admin pour {user.first_name} dans le groupe {chat.id}: {is_user_admin}")
    
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
    
    # Ajouter l'avertissement
    if user_to_warn.id not in user_warnings:
        user_warnings[user_to_warn.id] = 0
    user_warnings[user_to_warn.id] += 1
    
    warning_text = (
        f"⚠️ **AVERTISSEMENT OFFICIEL** ⚠️\n\n"
        f"👤 Utilisateur : {user_to_warn.mention_html()}\n"
        f"📝 Motif : {reason}\n"
        f"🔢 Avertissement : {user_warnings[user_to_warn.id]}/3\n\n"
        f"⚡ Bannissement automatique au 3ème avertissement."
    )
    
    await update.message.reply_to_message.reply_text(warning_text, parse_mode=ParseMode.HTML)
    logger.info(f"Avertissement donné à {user_to_warn.username} par {user.username}")

async def quiz_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lancer un quiz immédiatement."""
    user = update.effective_user
    chat = update.effective_chat

    # En privé, tout le monde peut utiliser la commande
    # En groupe, seuls les admins peuvent l'utiliser
    if chat.type != 'private' and not await is_admin(chat.id, user.id, context):
        await update.message.reply_text("❌ Cette commande est réservée aux administrateurs en groupe.")
        return
    
    await send_single_poll_quiz(context, chat.id)

async def my_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Afficher les notes personnelles de l'utilisateur."""
    user = update.effective_user
    user_id = user.id
    
    if user_id not in user_scores:
        await update.message.reply_text(
            "📝 **Vous n'avez pas encore de notes !**\n\n"
            "Participez aux quiz pour voir vos résultats ici ! 🎯"
        )
        return
    
    try:
        score = user_scores[user_id]
        grades = user_grades.get(user_id, {'correct': [], 'incorrect': [], 'total_stars': 0})
        
        notes_text = f"📝 **Vos Notes Personnelles** - {user.first_name}\n\n"
        notes_text += f"🌟 **Total étoiles :** {score['stars']}\n"
        notes_text += f"✅ **Réussies :** {score['correct']}\n"
        notes_text += f"❌ **Ratées :** {score['total'] - score['correct']}\n"
        notes_text += f"📊 **Pourcentage :** {(score['correct']/max(score['total'], 1)*100):.1f}%\n\n"
        
        # Afficher les dernières réponses correctes
        if grades['correct']:
            notes_text += "✅ **Dernières bonnes réponses :**\n"
            for correct in grades['correct'][-5:]:  # 5 dernières
                notes_text += f"• {correct['question']} (+5🌟)\n"
            notes_text += "\n"
        
        # Afficher les dernières réponses incorrectes  
        if grades['incorrect']:
            notes_text += "❌ **Dernières réponses ratées :**\n"
            for incorrect in grades['incorrect'][-5:]:  # 5 dernières
                notes_text += f"• {incorrect['question']} (0🌟)\n"
        
        await update.message.reply_text(notes_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Erreur notes personnelles : {e}")
        await update.message.reply_text("❌ Erreur lors de l'affichage de vos notes.")

async def my_notes_display(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Afficher les notes depuis le callback."""
    user = query.from_user
    user_id = user.id
    
    if user_id not in user_scores:
        await query.edit_message_text(
            "📝 **Vous n'avez pas encore de notes !**\n\n"
            "Participez aux quiz pour voir vos résultats ici ! 🎯",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )
        return
    
    try:
        score = user_scores[user_id]
        grades = user_grades.get(user_id, {'correct': [], 'incorrect': [], 'total_stars': 0})
        
        notes_text = f"📝 **Vos Notes Personnelles** - {user.first_name}\n\n"
        notes_text += f"🌟 **Total étoiles :** {score['stars']}\n"
        notes_text += f"✅ **Réussies :** {score['correct']}\n"
        notes_text += f"❌ **Ratées :** {score['total'] - score['correct']}\n"
        notes_text += f"📊 **Pourcentage :** {(score['correct']/max(score['total'], 1)*100):.1f}%\n\n"
        
        # Afficher les dernières réponses correctes
        if grades['correct']:
            notes_text += "✅ **Dernières bonnes réponses :**\n"
            for correct in grades['correct'][-3:]:  # 3 dernières
                notes_text += f"• {correct['question']} (+5🌟)\n"
            notes_text += "\n"
        
        # Afficher les dernières réponses incorrectes  
        if grades['incorrect']:
            notes_text += "❌ **Dernières réponses ratées :**\n"
            for incorrect in grades['incorrect'][-3:]:  # 3 dernières
                notes_text += f"• {incorrect['question']} (0🌟)\n"
        
        await query.edit_message_text(
            notes_text, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
        )
        
    except Exception as e:
        logger.error(f"Erreur notes personnelles : {e}")
        await query.edit_message_text("❌ Erreur lors de l'affichage de vos notes.")

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Afficher le classement TOP 20 avec notes détaillées."""
    await ranking_display(update, context, is_message=True)

async def ranking_display(update_or_query, context: ContextTypes.DEFAULT_TYPE, is_message=False) -> None:
    """Affiche le classement - utilisable pour message ou callback."""
    try:
        if not user_scores:
            text = (
                "📊 **Aucun score enregistré pour le moment !**\n\n"
                "Participez aux quiz pour apparaître dans le classement ! 🎯"
            )
            if is_message:
                await update_or_query.message.reply_text(text)
            else:
                await update_or_query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
                )
            return
        
        # Trier les utilisateurs par étoiles totales, puis par pourcentage
        sorted_users = sorted(user_scores.items(), 
                            key=lambda x: (x[1]['stars'], x[1]['correct']/max(x[1]['total'], 1)), 
                            reverse=True)
        
        ranking_text = "🏆 **TOP 20 - CLASSEMENT GÉNÉRAL** 🏆\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        
        # Afficher les 20 premiers seulement
        top_20 = sorted_users[:20]
        
        for i, (user_id, score) in enumerate(top_20):
            rank = i + 1
            percentage = (score['correct'] / max(score['total'], 1)) * 100
            stars_display = "🌟" * min(score['stars'] // 5, 10)  # Max 10 étoiles affichées
            
            if rank <= 3:
                medal = medals[rank - 1]
                ranking_text += f"{medal} **{rank}.** {score['name']}\n"
            else:
                ranking_text += f"🏅 **{rank}.** {score['name']}\n"
            
            # Afficher réussites et échecs avec étoiles
            correct_count = score['correct']
            failed_count = score['total'] - score['correct']
            total_stars = score['stars']
            
            ranking_text += f"   ✅ Réussies: {correct_count} | ❌ Ratées: {failed_count}\n"
            ranking_text += f"   🌟 {total_stars} étoiles ({percentage:.1f}%)\n"
            if stars_display:
                ranking_text += f"   {stars_display}\n"
            ranking_text += "\n"
        
        # Ajouter statistiques globales
        total_participants = len(user_scores)
        total_questions_answered = sum(score['total'] for score in user_scores.values())
        total_correct_answers = sum(score['correct'] for score in user_scores.values())
        total_stars_earned = sum(score['stars'] for score in user_scores.values())
        
        ranking_text += "📈 **STATISTIQUES GLOBALES**\n"
        ranking_text += f"👥 Participants : {total_participants}\n"
        ranking_text += f"❓ Questions répondues : {total_questions_answered}\n"
        ranking_text += f"✅ Bonnes réponses : {total_correct_answers}\n"
        ranking_text += f"🌟 Total étoiles gagnées : {total_stars_earned}\n"
        
        if total_questions_answered > 0:
            global_percentage = (total_correct_answers / total_questions_answered) * 100
            ranking_text += f"📊 Taux de réussite général : {global_percentage:.1f}%"
        
        if is_message:
            await update_or_query.message.reply_text(ranking_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update_or_query.edit_message_text(
                ranking_text, 
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")]])
            )
        
    except Exception as e:
        logger.error(f"Erreur classement : {e}")
        error_text = "❌ Erreur lors de l'affichage du classement."
        if is_message:
            await update_or_query.message.reply_text(error_text)
        else:
            await update_or_query.edit_message_text(error_text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Afficher les statistiques."""
    user = update.effective_user
    chat = update.effective_chat

    # En groupe, seuls les admins peuvent voir les stats du groupe
    if chat.type != 'private' and not await is_admin(chat.id, user.id, context):
        await update.message.reply_text("❌ Cette commande est réservée aux administrateurs en groupe.")
        return

    try:
        if chat.type == 'private':
            # Stats personnelles en privé
            stats_text = (
                f"📊 **Vos Statistiques Personnelles**\n\n"
                f"👤 Utilisateur : {user.first_name}\n"
                f"🎯 Quiz disponibles : Histoire-Géographie\n"
                f"🤖 Bot actif et prêt pour vos quiz !\n"
                f"💡 Utilisez /menu pour accéder à toutes les fonctions"
            )
        else:
            # Stats du groupe
            chat_member_count = await context.bot.get_chat_member_count(chat.id)
            warnings_count = len(user_warnings)
            
            stats_text = (
                f"📊 **Statistiques du Groupe**\n\n"
                f"👥 Membres : {chat_member_count}\n"
                f"⚠️ Utilisateurs avec avertissements : {warnings_count}\n"
                f"🤖 Bot actif depuis le dernier redémarrage\n"
                f"📅 Quiz quotidiens : 3 questions consécutives à 21h00"
            )
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Erreur stats : {e}")
        await update.message.reply_text("❌ Erreur lors de la récupération des statistiques.")

# --- QUIZ AUTOMATIQUE AVEC POLLS ---

async def send_single_poll_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Envoie un seul quiz sous forme de poll."""
    try:
        # Choisir une question aléatoire
        question_data = random.choice(QUIZ_QUESTIONS)
        
        # Créer le poll
        poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"🎯 QUIZ HISTOIRE-GÉOGRAPHIE 📚\n\n{question_data['question']}",
            options=question_data['options'],
            type=Poll.QUIZ,
            correct_option_id=question_data['correct_option_id'],
            explanation=f"📖 {question_data['explanation']}",
            is_anonymous=False,
            open_period=60  # 60 secondes pour répondre
        )
        
        # Stocker les données du poll
        poll_id = poll_message.poll.id
        active_polls[poll_id] = {
            'question_data': question_data,
            'chat_id': chat_id,
            'message_id': poll_message.message_id,
            'question': question_data['question']
        }
        
        logger.info(f"Quiz poll envoyé au groupe {chat_id}")
        
    except Exception as e:
        logger.error(f"Erreur envoi quiz poll : {e}")

async def send_daily_quiz_sequence(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie une séquence de 3 quiz consécutifs à 21h00."""
    chat_id = -1002391261450  # ID de votre groupe
    
    try:
        # Initialiser la session de quiz quotidien
        session_id = f"daily_{chat_id}_{datetime.now().strftime('%Y%m%d')}"
        daily_quiz_sessions[session_id] = {
            'chat_id': chat_id,
            'current_question': 0,
            'total_questions': 3,
            'participants': set()
        }
        
        # Envoyer le message d'introduction
        intro_text = (
            "🎯 **QUIZ QUOTIDIEN - DÉBUT** 🎯\n\n"
            "📚 **3 questions d'Histoire-Géographie vous attendent !**\n"
            "⏰ Chaque question dure 60 secondes\n"
            "🌟 5 étoiles par bonne réponse\n"
            "🏆 Résultats et classement à la fin\n\n"
            "**🚀 QUESTION 1/3 arrive dans 5 secondes...**"
        )
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=intro_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Programmer les 3 questions avec des délais
        for i in range(3):
            delay = 5 + (i * 70)  # 5s + (question_number * 70s) - 60s pour répondre + 10s entre questions
            context.job_queue.run_once(
                lambda ctx, question_num=i+1: send_daily_question(ctx, chat_id, question_num, session_id),
                when=delay
            )
        
        # Programmer l'affichage des résultats finaux
        context.job_queue.run_once(
            lambda ctx: send_daily_results(ctx, chat_id, session_id),
            when=5 + (3 * 70) + 10  # Après toutes les questions
        )
        
        logger.info(f"Séquence de quiz quotidien programmée pour le groupe {chat_id}")
        
    except Exception as e:
        logger.error(f"Erreur programmation quiz quotidien : {e}")

async def send_daily_question(context: ContextTypes.DEFAULT_TYPE, chat_id: int, question_num: int, session_id: str) -> None:
    """Envoie une question spécifique de la séquence quotidienne."""
    try:
        # Choisir une question aléatoire
        question_data = random.choice(QUIZ_QUESTIONS)
        
        # Créer le poll
        poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"🎯 QUIZ QUOTIDIEN - QUESTION {question_num}/3 📚\n\n{question_data['question']}",
            options=question_data['options'],
            type=Poll.QUIZ,
            correct_option_id=question_data['correct_option_id'],
            explanation=f"📖 {question_data['explanation']}",
            is_anonymous=False,
            open_period=60  # 60 secondes pour répondre
        )
        
        # Stocker les données du poll
        poll_id = poll_message.poll.id
        active_polls[poll_id] = {
            'question_data': question_data,
            'chat_id': chat_id,
            'message_id': poll_message.message_id,
            'question': question_data['question'],
            'session_id': session_id,
            'question_number': question_num
        }
        
        logger.info(f"Question {question_num}/3 envoyée pour le quiz quotidien")
        
    except Exception as e:
        logger.error(f"Erreur envoi question quotidienne : {e}")

async def send_daily_results(context: ContextTypes.DEFAULT_TYPE, chat_id: int, session_id: str) -> None:
    """Envoie les résultats finaux du quiz quotidien."""
    try:
        if session_id not in daily_quiz_sessions:
            return
        
        session = daily_quiz_sessions[session_id]
        participants = len(session['participants'])
        
        # Créer le message de résultats
        result_text = (
            "🏆 **QUIZ QUOTIDIEN TERMINÉ !** 🏆\n\n"
            f"📊 **Bilan de la session :**\n"
            f"👥 Participants : {participants}\n"
            f"❓ Questions posées : 3\n"
            f"🌟 Étoiles distribuées : {participants * 3 * 5} maximum\n\n"
        )
        
        # Afficher le top 5 du jour si applicable
        if user_scores:
            sorted_users = sorted(user_scores.items(), 
                                key=lambda x: (x[1]['stars'], x[1]['correct']/max(x[1]['total'], 1)), 
                                reverse=True)
            
            result_text += "🥇 **TOP 5 DU CLASSEMENT GÉNÉRAL :**\n"
            for i, (user_id, score) in enumerate(sorted_users[:5]):
                percentage = (score['correct'] / max(score['total'], 1)) * 100
                stars_count = score['stars']
                result_text += f"{i+1}. {score['name']}: 🌟{stars_count} ({percentage:.1f}%)\n"
        
        result_text += "\n🔄 **Prochain quiz quotidien : Demain à 21h00 !**"
        result_text += "\n💡 Utilisez /menu pour accéder à toutes les fonctions"
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=result_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Nettoyer la session
        del daily_quiz_sessions[session_id]
        
        logger.info(f"Résultats du quiz quotidien envoyés pour le groupe {chat_id}")
        
    except Exception as e:
        logger.error(f"Erreur envoi résultats quotidiens : {e}")

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les réponses aux polls."""
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    user = poll_answer.user
    
    if poll_id not in active_polls:
        return
    
    poll_data = active_polls[poll_id]
    question_data = poll_data['question_data']
    
    try:
        # Initialiser l'utilisateur s'il n'existe pas
        if user.id not in user_scores:
            user_scores[user.id] = {'correct': 0, 'total': 0, 'name': '', 'stars': 0}
            user_grades[user.id] = {'correct': [], 'incorrect': [], 'total_stars': 0}
        
        # Mettre à jour le nom de l'utilisateur
        if user_scores[user.id]['name'] == '':
            user_scores[user.id]['name'] = user.first_name or user.username or f"User{user.id}"
        
        # Ajouter à la session si c'est un quiz quotidien
        session_id = poll_data.get('session_id')
        if session_id and session_id in daily_quiz_sessions:
            daily_quiz_sessions[session_id]['participants'].add(user.id)
        
        # Vérifier si la réponse est correcte
        selected_options = poll_answer.option_ids
        if selected_options and selected_options[0] == question_data['correct_option_id']:
            # Bonne réponse
            user_scores[user.id]['correct'] += 1
            user_scores[user.id]['total'] += 1
            user_scores[user.id]['stars'] += 5
            user_grades[user.id]['correct'].append({
                'question': poll_data['question'][:50] + '...', 
                'stars': 5
            })
            user_grades[user.id]['total_stars'] += 5
        else:
            # Mauvaise réponse
            user_scores[user.id]['total'] += 1
            user_grades[user.id]['incorrect'].append({
                'question': poll_data['question'][:50] + '...', 
                'stars': 0
            })
        
        logger.info(f"Réponse poll enregistrée pour {user.first_name}")
        
    except Exception as e:
        logger.error(f"Erreur gestion réponse poll : {e}")

def schedule_daily_quiz(job_queue: JobQueue, chat_id: int) -> None:
    """Programme le quiz quotidien à 21h00."""
    
    quiz_time = time(hour=21, minute=0)
    job_queue.run_daily(
        callback=send_daily_quiz_sequence,
        time=quiz_time,
        name=f"daily_quiz_sequence_{chat_id}"
    )
    
    logger.info(f"Quiz quotidien (3 questions consécutives) programmé à 21h00 pour le groupe {chat_id}")

# --- FONCTION PRINCIPALE ---

def main() -> None:
    """Démarre le bot."""
    if TOKEN == "VOTRE_TOKEN_ICI":
        print("❌ Veuillez configurer votre TOKEN Telegram dans le code !")
        return
    
    application = Application.builder().token(TOKEN).build()
    
    # Commandes essentielles seulement
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("warn", warn_member))
    
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
    
    # Pour programmer le quiz quotidien
    if application.job_queue:
        # ID de votre groupe configuré
        schedule_daily_quiz(application.job_queue, -1002391261450)  
        logger.info("Quiz quotidien programmé pour le groupe -1002391261450")
    else:
        logger.warning("JobQueue non disponible - Quiz quotidien désactivé")
    
    logger.info("🚀 Bot éducatif démarré avec format Poll Quiz et menu !")
    print("🚀 Bot éducatif démarré ! Quiz en format Poll avec 3 questions consécutives à 21h00.")
    
    application.run_polling()

if __name__ == "__main__":
    main()
