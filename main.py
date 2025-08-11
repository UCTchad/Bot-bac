
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    ContextTypes,
    JobQueue
)
import json
import random
from datetime import datetime, time
import pytz
import asyncio
from typing import Dict, Set, Tuple, Optional

from pdf_manager import PDFManager

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class BotState:
    """Classe pour gérer l'état global du bot."""
    def __init__(self):
        self.quiz_sessions: Dict = {}
        self.group_scores: Dict = {}
        self.active_polls: Dict = {}
        self.active_groups: Set = set()
        self.questions_data: list = []
        self.motivational_quotes: list = []
        
        # Configuration
        self.TELEGRAM_TOKEN = os.getenv("TOKEN")
        self.BOT_CREATOR_ID = int(os.getenv("BOT_CREATOR_ID", "6692408502"))
        
        # Canaux et groupes obligatoires
        self.REQUIRED_CHANNEL = "@kabro_edu"
        self.REQUIRED_GROUP = "@kabroedu"
        self.REQUIRED_CHANNEL_ID = -1002716550843
        self.REQUIRED_GROUP_ID = -1002391261450
        
        # Fichiers de sauvegarde
        self.SCORES_FILE = 'group_scores.json'
        self.ACTIVE_GROUPS_FILE = 'active_groups.json'
        
        # Initialiser le gestionnaire PDF
        self.pdf_manager = PDFManager()

class SubscriptionManager:
    """Gestionnaire des vérifications d'abonnement."""
    
    def __init__(self, bot_state: BotState):
        self.bot_state = bot_state
    
    async def check_user_subscription(self, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Tuple[bool, str]:
        """Vérifie si l'utilisateur est abonné au canal et au groupe requis."""
        try:
            # Vérifier l'abonnement au canal
            try:
                channel_member = await context.bot.get_chat_member(self.bot_state.REQUIRED_CHANNEL_ID, user_id)
                channel_subscribed = channel_member.status in ['member', 'administrator', 'creator']
                logger.info(f"Utilisateur {user_id} - Canal: {channel_member.status}")
            except Exception as e:
                error_msg = str(e).lower()
                if "user not found" in error_msg:
                    logger.warning(f"Utilisateur {user_id} non trouvé dans le canal")
                    channel_subscribed = False
                elif any(keyword in error_msg for keyword in ["forbidden", "member list is inaccessible"]):
                    logger.warning(f"Canal {self.bot_state.REQUIRED_CHANNEL_ID} - Accès limité")
                    # Ne pas donner accès automatique en cas d'erreur
                    channel_subscribed = False
                else:
                    logger.error(f"Erreur vérification canal: {e}")
                    channel_subscribed = False

            # Vérifier l'abonnement au groupe
            try:
                group_member = await context.bot.get_chat_member(self.bot_state.REQUIRED_GROUP_ID, user_id)
                group_subscribed = group_member.status in ['member', 'administrator', 'creator']
                logger.info(f"Utilisateur {user_id} - Groupe: {group_member.status}")
            except Exception as e:
                error_msg = str(e).lower()
                if "user not found" in error_msg:
                    logger.warning(f"Utilisateur {user_id} non trouvé dans le groupe")
                    group_subscribed = False
                elif any(keyword in error_msg for keyword in ["forbidden", "member list is inaccessible"]):
                    logger.warning(f"Groupe {self.bot_state.REQUIRED_GROUP_ID} - Accès limité")
                    group_subscribed = False
                else:
                    logger.error(f"Erreur vérification groupe: {e}")
                    group_subscribed = False

            if channel_subscribed and group_subscribed:
                logger.info(f"Utilisateur {user_id} vérifié avec succès")
                return True, ""

            # Messages d'erreur selon ce qui manque
            if not channel_subscribed and not group_subscribed:
                message = (
                    "❌ ABONNEMENT REQUIS ❌\n\n"
                    "🚫 Pour utiliser ce bot, vous devez être abonné à :\n\n"
                    f"📢 Canal : {self.bot_state.REQUIRED_CHANNEL}\n"
                    f"👥 Groupe : {self.bot_state.REQUIRED_GROUP}\n\n"
                    "✅ Abonnez-vous puis réessayez !"
                )
            elif not channel_subscribed:
                message = (
                    "❌ ABONNEMENT AU CANAL REQUIS ❌\n\n"
                    f"📢 Veuillez vous abonner au canal : {self.bot_state.REQUIRED_CHANNEL}\n\n"
                    "✅ Abonnez-vous puis réessayez !"
                )
            else:
                message = (
                    "❌ ABONNEMENT AU GROUPE REQUIS ❌\n\n"
                    f"👥 Veuillez rejoindre le groupe : {self.bot_state.REQUIRED_GROUP}\n\n"
                    "✅ Rejoignez-nous puis réessayez !"
                )

            return False, message

        except Exception as e:
            logger.error(f"Erreur critique vérification abonnement: {e}")
            return False, "❌ Erreur de vérification. Réessayez plus tard."

class DataManager:
    """Gestionnaire des données (sauvegarde/chargement)."""
    
    def __init__(self, bot_state: BotState):
        self.bot_state = bot_state
    
    def load_motivational_quotes(self):
        """Charge les citations motivantes depuis citations_motivantes.json"""
        try:
            with open('citations_motivantes.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.bot_state.motivational_quotes = data.get('citations', [])
            logger.info(f"Chargé {len(self.bot_state.motivational_quotes)} citations motivantes")
        except FileNotFoundError:
            logger.warning("Fichier citations_motivantes.json introuvable")
            self._load_default_quotes()
        except json.JSONDecodeError as e:
            logger.error(f"Format JSON invalide dans citations_motivantes.json: {e}")
            self._load_default_quotes()
        except Exception as e:
            logger.error(f"Erreur chargement citations: {e}")
            self._load_default_quotes()
    
    def _load_default_quotes(self):
        """Charge des citations par défaut."""
        self.bot_state.motivational_quotes = [
            "💪 Le succès, c'est 1% d'inspiration et 99% de transpiration. - Thomas Edison",
            "🎯 Un objectif sans plan n'est qu'un souhait. - Antoine de Saint-Exupéry",
            "🌟 L'éducation est l'arme la plus puissante pour changer le monde. - Nelson Mandela",
            "📚 Celui qui ouvre une porte d'école ferme une prison. - Victor Hugo",
            "🚀 Il n'y a pas d'ascenseur vers le succès, il faut prendre les escaliers. - Zig Ziglar"
        ]
    
    def load_questions(self):
        """Charge les questions depuis questions.json"""
        try:
            with open('questions.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.bot_state.questions_data = data.get('histoire_geographie', [])
            logger.info(f"Chargé {len(self.bot_state.questions_data)} questions")
            
            if not self.bot_state.questions_data:
                logger.warning("Aucune question trouvée dans le fichier JSON")
        except FileNotFoundError:
            logger.error("Fichier questions.json introuvable")
            self.bot_state.questions_data = []
        except json.JSONDecodeError as e:
            logger.error(f"Format JSON invalide dans questions.json: {e}")
            self.bot_state.questions_data = []
        except Exception as e:
            logger.error(f"Erreur chargement questions: {e}")
            self.bot_state.questions_data = []
    
    def save_scores(self):
        """Sauvegarde les scores dans un fichier JSON."""
        try:
            scores_to_save = {}
            for group_id, users in self.bot_state.group_scores.items():
                scores_to_save[str(group_id)] = {str(user_id): score for user_id, score in users.items()}
            
            with open(self.bot_state.SCORES_FILE, 'w', encoding='utf-8') as f:
                json.dump(scores_to_save, f, indent=2)
            logger.info(f"Scores sauvegardés pour {len(self.bot_state.group_scores)} groupes")
        except Exception as e:
            logger.error(f"Erreur sauvegarde scores: {e}")
    
    def load_scores(self):
        """Charge les scores depuis le fichier JSON."""
        try:
            with open(self.bot_state.SCORES_FILE, 'r', encoding='utf-8') as f:
                scores_data = json.load(f)
            
            self.bot_state.group_scores = {}
            for group_id_str, users in scores_data.items():
                group_id = int(group_id_str)
                self.bot_state.group_scores[group_id] = {int(user_id_str): score for user_id_str, score in users.items()}
            
            logger.info(f"Scores chargés pour {len(self.bot_state.group_scores)} groupes")
        except FileNotFoundError:
            logger.info("Aucun fichier de scores trouvé, démarrage avec scores vides")
            self.bot_state.group_scores = {}
        except Exception as e:
            logger.error(f"Erreur chargement scores: {e}")
            self.bot_state.group_scores = {}
    
    def save_active_groups(self):
        """Sauvegarde la liste des groupes actifs."""
        try:
            with open(self.bot_state.ACTIVE_GROUPS_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(self.bot_state.active_groups), f)
            logger.info(f"Groupes actifs sauvegardés: {len(self.bot_state.active_groups)} groupes")
        except Exception as e:
            logger.error(f"Erreur sauvegarde groupes actifs: {e}")
    
    def load_active_groups(self):
        """Charge la liste des groupes actifs."""
        try:
            with open(self.bot_state.ACTIVE_GROUPS_FILE, 'r', encoding='utf-8') as f:
                active_groups_list = json.load(f)
            self.bot_state.active_groups = set(active_groups_list)
            logger.info(f"Groupes actifs chargés: {len(self.bot_state.active_groups)} groupes")
        except FileNotFoundError:
            logger.info("Aucun fichier de groupes actifs trouvé")
            self.bot_state.active_groups = set()
        except Exception as e:
            logger.error(f"Erreur chargement groupes actifs: {e}")
            self.bot_state.active_groups = set()
    
    async def periodic_save(self):
        """Sauvegarde périodique des données."""
        while True:
            try:
                self.save_scores()
                self.save_active_groups()
                await asyncio.sleep(300)  # Toutes les 5 minutes
            except Exception as e:
                logger.error(f"Erreur sauvegarde périodique: {e}")
                await asyncio.sleep(60)  # Réessayer dans 1 minute

class QuizManager:
    """Gestionnaire des quiz."""
    
    def __init__(self, bot_state: BotState):
        self.bot_state = bot_state
    
    def get_random_questions(self, count: int = 3) -> list:
        """Sélectionne des questions aléatoirement avec vérification."""
        if not self.bot_state.questions_data:
            logger.warning("Aucune question disponible pour le quiz")
            return []
        
        available_count = min(count, len(self.bot_state.questions_data))
        return random.sample(self.bot_state.questions_data, available_count)
    
    async def start_quiz_in_group(self, context: ContextTypes.DEFAULT_TYPE, group_id: int, 
                                  trigger_message=None, is_daily=False):
        """Démarre un quiz dans un groupe."""
        try:
            # Vérifier si un quiz est déjà actif
            if group_id in self.bot_state.quiz_sessions:
                if trigger_message:
                    await trigger_message.reply_text(
                        "⚠️ Quiz déjà en cours !\n\n"
                        "📝 Attendez la fin du quiz actuel avant d'en démarrer un nouveau."
                    )
                return

            if not self.bot_state.questions_data:
                if trigger_message:
                    await trigger_message.reply_text(
                        "❌ Aucune question disponible\n\n"
                        "🔧 Les questions sont en cours de chargement."
                    )
                return

            # Initialiser le groupe dans les scores si nécessaire
            if group_id not in self.bot_state.group_scores:
                self.bot_state.group_scores[group_id] = {}

            # Ajouter le groupe aux groupes actifs
            self.bot_state.active_groups.add(group_id)

            # Sélectionner 3 questions aléatoirement
            selected_questions = self.get_random_questions(3)
            
            if not selected_questions:
                if trigger_message:
                    await trigger_message.reply_text(
                        "❌ Aucune question disponible\n\n"
                        "🔧 Les questions sont en cours de chargement."
                    )
                return

            # Créer la session de quiz
            session_id = f"{'daily_' if is_daily else ''}quiz_{group_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.bot_state.quiz_sessions[group_id] = {
                'session_id': session_id,
                'questions': selected_questions,
                'current_question': 0,
                'total_questions': len(selected_questions),
                'participants': set(),
                'is_daily': is_daily
            }

            # Message d'introduction
            intro_text = (
                f"🎯 QUIZ {'QUOTIDIEN ' if is_daily else ''}D'HISTOIRE-GÉOGRAPHIE 🎯\n\n"
                f"📚 {len(selected_questions)} questions vous attendent !\n"
                "⏰ 30 secondes par question\n"
                "🌟 1 point par bonne réponse\n\n"
                "🚀 Première question :"
            )

            if trigger_message:
                await trigger_message.reply_text(intro_text)
            else:
                await context.bot.send_message(chat_id=group_id, text=intro_text)

            # Démarrer immédiatement la première question
            await self.send_quiz_question(context, group_id)

            logger.info(f"Quiz {'quotidien ' if is_daily else ''}démarré dans le groupe {group_id}")

        except Exception as e:
            logger.error(f"Erreur démarrage quiz: {e}")
    
    async def send_quiz_question(self, context: ContextTypes.DEFAULT_TYPE, group_id: int):
        """Envoie une question de quiz."""
        try:
            if group_id not in self.bot_state.quiz_sessions:
                return

            session = self.bot_state.quiz_sessions[group_id]
            current_q = session['current_question']

            if current_q >= session['total_questions']:
                await self.end_quiz(context, group_id)
                return

            question_data = session['questions'][current_q].copy()

            # Limiter la longueur de la question et de l'explication
            question_text = question_data['question']
            if len(question_text) > 200:
                question_text = question_data['question'][:200] + "..."

            explanation = question_data['explanation']
            if len(explanation) > 150:
                explanation = question_data['explanation'][:150] + "..."

            # Mélanger les options
            original_options = question_data['options'].copy()
            original_correct_id = question_data['correct_option_id']
            correct_answer = original_options[original_correct_id]

            options_with_indices = list(enumerate(original_options))
            random.shuffle(options_with_indices)

            shuffled_options = []
            new_correct_id = 0

            for new_index, (old_index, option) in enumerate(options_with_indices):
                shuffled_options.append(option)
                if old_index == original_correct_id:
                    new_correct_id = new_index

            # Envoyer le poll
            poll_message = await context.bot.send_poll(
                chat_id=group_id,
                question=f"❓ Q{current_q + 1}/{session['total_questions']} - {question_text}",
                options=shuffled_options,
                type=Poll.QUIZ,
                correct_option_id=new_correct_id,
                explanation=explanation,
                is_anonymous=False,
                allows_multiple_answers=False,
                open_period=30
            )

            # Sauvegarder le poll actif
            self.bot_state.active_polls[poll_message.poll.id] = {
                'group_id': group_id,
                'question_number': current_q + 1,
                'correct_option_id': new_correct_id
            }

            # Programmer la question suivante ou la fin
            if current_q + 1 < session['total_questions']:
                asyncio.create_task(self._delayed_next_question(context, group_id))
            else:
                asyncio.create_task(self._delayed_quiz_end(context, group_id))

            logger.info(f"Question {current_q + 1} envoyée au groupe {group_id}")

        except Exception as e:
            logger.error(f"Erreur envoi question: {e}")
    
    async def _delayed_next_question(self, context: ContextTypes.DEFAULT_TYPE, group_id: int):
        """Envoie la prochaine question après 32 secondes."""
        await asyncio.sleep(32)
        await self._send_next_question(context, group_id)
    
    async def _delayed_quiz_end(self, context: ContextTypes.DEFAULT_TYPE, group_id: int):
        """Termine le quiz après 32 secondes."""
        await asyncio.sleep(32)
        await self.end_quiz(context, group_id)
    
    async def _send_next_question(self, context: ContextTypes.DEFAULT_TYPE, group_id: int):
        """Passe à la question suivante."""
        if group_id in self.bot_state.quiz_sessions:
            self.bot_state.quiz_sessions[group_id]['current_question'] += 1
            await self.send_quiz_question(context, group_id)
    
    async def end_quiz(self, context: ContextTypes.DEFAULT_TYPE, group_id: int):
        """Termine le quiz et affiche les résultats."""
        try:
            if group_id not in self.bot_state.quiz_sessions:
                return

            session = self.bot_state.quiz_sessions[group_id]
            participants = session['participants']

            if not participants:
                await context.bot.send_message(
                    chat_id=group_id,
                    text="🎯 QUIZ TERMINÉ 🎯\n\n❌ Aucune participation enregistrée."
                )
            else:
                # Créer le classement pour ce quiz
                results = []
                for user_id in participants:
                    score = self.bot_state.group_scores[group_id].get(user_id, 0)
                    try:
                        user = await context.bot.get_chat_member(group_id, user_id)
                        name = user.user.first_name or "Utilisateur"
                    except:
                        name = "Utilisateur"

                    results.append((name, score))

                # Trier par score décroissant
                results.sort(key=lambda x: x[1], reverse=True)

                result_text = "🏆 RÉSULTATS DU QUIZ 🏆\n\n"

                for i, (name, score) in enumerate(results[:5]):  # Top 5
                    if i == 0:
                        emoji = "🥇"
                    elif i == 1:
                        emoji = "🥈" 
                    elif i == 2:
                        emoji = "🥉"
                    else:
                        emoji = f"{i+1}."

                    result_text += f"{emoji} {name} - {score} points\n"

                result_text += f"\n💫 {len(participants)} participants au total"

                await context.bot.send_message(chat_id=group_id, text=result_text)

            # Nettoyer la session
            del self.bot_state.quiz_sessions[group_id]

            logger.info(f"Quiz terminé pour le groupe {group_id}")

        except Exception as e:
            logger.error(f"Erreur fin de quiz: {e}")

class UITexts:
    """Classe contenant tous les textes et claviers de l'interface utilisateur."""
    
    @staticmethod
    def get_main_menu_text() -> str:
        """Retourne le texte du menu principal."""
        return (
            "🎓 BOT ÉDUCATIF - BACCALAURÉAT TCHAD 🇹🇩\n\n"
            "📚 Bienvenue ! Ce bot vous accompagne dans vos révisions :\n\n"
            "📥 Téléchargez des cours par série\n"
            "💡 Recevez des conseils d'études personnalisés\n"
            "🎯 Motivez-vous avec des citations inspirantes\n\n"
            "✨ Choisissez une option ci-dessous :"
        )
    
    @staticmethod
    def get_main_menu_keyboard() -> InlineKeyboardMarkup:
        """Retourne le clavier du menu principal."""
        keyboard = [
            [InlineKeyboardButton("📥 Télécharger cours", callback_data="menu_pdfs")],
            [InlineKeyboardButton("💡 Conseils d'études", callback_data="conseils_etudes")],
            [InlineKeyboardButton("🎯 Citation motivante", callback_data="citation_motivante")],
            [InlineKeyboardButton("👥 Ajouter le bot à votre groupe", url="https://t.me/Kabroedu_bot?startgroup=true")],
            [InlineKeyboardButton("❓ Aide", callback_data="help")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def get_subscription_keyboard(required_channel: str, required_group: str) -> InlineKeyboardMarkup:
        """Retourne le clavier de vérification d'abonnement."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Rejoindre le Canal", url=f"https://t.me/{required_channel[1:]}")],
            [InlineKeyboardButton("👥 Rejoindre le Groupe", url=f"https://t.me/{required_group[1:]}")],
            [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="check_subscription")]
        ])

class EducationalBot:
    """Classe principale du bot éducatif."""
    
    def __init__(self):
        self.state = BotState()
        self.subscription_manager = SubscriptionManager(self.state)
        self.data_manager = DataManager(self.state)
        self.quiz_manager = QuizManager(self.state)
        self.ui_texts = UITexts()
        
        # Tâche de sauvegarde périodique
        self.save_task = None
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /start."""
        chat_type = update.effective_chat.type
        user_id = update.effective_user.id

        if chat_type == ChatType.PRIVATE:
            # Vérifier l'abonnement en privé uniquement
            is_subscribed, subscription_message = await self.subscription_manager.check_user_subscription(context, user_id)
            if not is_subscribed:
                keyboard = self.ui_texts.get_subscription_keyboard(
                    self.state.REQUIRED_CHANNEL, 
                    self.state.REQUIRED_GROUP
                )
                await update.message.reply_text(subscription_message, reply_markup=keyboard)
                return

            # Mode privé - téléchargement de cours
            await update.message.reply_text(
                self.ui_texts.get_main_menu_text(),
                reply_markup=self.ui_texts.get_main_menu_keyboard()
            )

        else:
            # Mode groupe - pas de vérification d'abonnement nécessaire
            group_id = update.effective_chat.id
            if group_id not in self.state.group_scores:
                self.state.group_scores[group_id] = {}

            # Ajouter le groupe aux groupes actifs
            self.state.active_groups.add(group_id)
            self.data_manager.save_active_groups()

            start_text = (
                "🎯 QUIZ ÉDUCATIF ACTIVÉ DANS CE GROUPE 🎯\n\n"
                "📚 Quiz d'Histoire-Géographie avec options mélangées !\n"
                "🌟 Gagnez des points en répondant correctement\n"
                "🏆 Scores individuels dans ce groupe\n"
                "🕘 Quiz quotidien automatique à 21h00\n\n"
                "Commandes disponibles :\n"
                "• /quiz - Démarrer un quiz de 3 questions\n"  
                "• /scores - Voir le classement du groupe\n"
                "• /cours - Télécharger des cours PDF\n"
                "• /conseil - Recevoir un conseil d'étude\n"
                "• /motivation - Citation motivante\n"
                "• /planning - Suggestion de planning\n\n"
                "🎓 Bonne chance dans vos révisions !"
            )

            await update.message.reply_text(start_text)
    
    async def quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /quiz."""
        chat_type = update.effective_chat.type
        user_id = update.effective_user.id

        # Vérifier l'abonnement seulement en privé
        if chat_type == ChatType.PRIVATE:
            is_subscribed, subscription_message = await self.subscription_manager.check_user_subscription(context, user_id)
            if not is_subscribed:
                await update.message.reply_text(subscription_message)
                return

            await update.message.reply_text(
                "❌ Quiz non disponible en privé\n\n"
                "📥 Les quiz sont réservés aux groupes.\n"
                "💡 Utilisez les boutons ci-dessous pour télécharger des cours :",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Télécharger cours", callback_data="menu_pdfs")]
                ])
            )
            return

        # Démarrer le quiz dans le groupe
        group_id = update.effective_chat.id
        await self.quiz_manager.start_quiz_in_group(context, group_id, update.message)
    
    async def scores_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /scores."""
        chat_type = update.effective_chat.type

        if chat_type == ChatType.PRIVATE:
            await update.message.reply_text(
                "❌ Scores non disponibles en privé\n\n"
                "📊 Les scores sont spécifiques à chaque groupe."
            )
            return

        group_id = update.effective_chat.id

        if group_id not in self.state.group_scores or not self.state.group_scores[group_id]:
            await update.message.reply_text(
                "📊 AUCUN SCORE ENREGISTRÉ 📊\n\n"
                "🎯 Participez à un quiz avec /quiz pour apparaître dans le classement !"
            )
            return

        # Créer le classement
        results = []
        for user_id, score in self.state.group_scores[group_id].items():
            try:
                user = await context.bot.get_chat_member(group_id, user_id)
                name = user.user.first_name or "Utilisateur"
            except:
                name = "Utilisateur"

            results.append((name, score))

        # Trier par score décroissant
        results.sort(key=lambda x: x[1], reverse=True)

        scores_text = "🏆 CLASSEMENT DU GROUPE 🏆\n\n"

        for i, (name, score) in enumerate(results[:10]):  # Top 10
            if i == 0:
                emoji = "👑"
            elif i == 1:
                emoji = "🥈"
            elif i == 2:
                emoji = "🥉"
            else:
                emoji = f"{i+1}."

            scores_text += f"{emoji} {name} - {score} points\n"

        scores_text += f"\n📊 {len(results)} participants au total"

        await update.message.reply_text(scores_text)
    
    async def handle_poll_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gère les réponses aux polls de quiz."""
        poll_answer = update.poll_answer
        poll_id = poll_answer.poll_id
        user_id = poll_answer.user.id

        if poll_id not in self.state.active_polls:
            return

        poll_info = self.state.active_polls[poll_id]
        group_id = poll_info['group_id']
        correct_option_id = poll_info['correct_option_id']

        if group_id not in self.state.quiz_sessions:
            return

        # Ajouter le participant
        self.state.quiz_sessions[group_id]['participants'].add(user_id)

        # Initialiser le score de l'utilisateur pour ce groupe
        if user_id not in self.state.group_scores[group_id]:
            self.state.group_scores[group_id][user_id] = 0

        # Vérifier si la réponse est correcte
        if poll_answer.option_ids and poll_answer.option_ids[0] == correct_option_id:
            self.state.group_scores[group_id][user_id] += 1
            logger.info(f"Utilisateur {user_id} a répondu correctement dans le groupe {group_id}")
    
    async def daily_quiz_job(self, context: ContextTypes.DEFAULT_TYPE):
        """Job qui lance le quiz quotidien à 21h00."""
        try:
            await self._cleanup_inactive_groups(context)
            
            if not self.state.active_groups:
                logger.info("Aucun groupe actif pour le quiz quotidien")
                return

            quiz_message = (
                "🌙 QUIZ QUOTIDIEN - 21H00 🌙\n\n"
                "🎯 L'heure du quiz quotidien est arrivée !\n"
                "📚 3 questions d'Histoire-Géographie\n"
                "🌟 1 point par bonne réponse\n"
                "⏰ 30 secondes par question\n\n"
                "🚀 Le quiz commence dans 10 secondes..."
            )

            successful_groups = 0
            for group_id in self.state.active_groups.copy():
                try:
                    if group_id not in self.state.quiz_sessions:
                        await context.bot.send_message(chat_id=group_id, text=quiz_message)
                        await asyncio.sleep(10)
                        await self.quiz_manager.start_quiz_in_group(context, group_id, is_daily=True)
                        successful_groups += 1
                except Exception as e:
                    logger.error(f"Erreur envoi quiz quotidien groupe {group_id}: {e}")
                    self.state.active_groups.discard(group_id)

            logger.info(f"Quiz quotidien lancé dans {successful_groups}/{len(self.state.active_groups)} groupes")

        except Exception as e:
            logger.error(f"Erreur job quiz quotidien: {e}")
    
    async def _cleanup_inactive_groups(self, context: ContextTypes.DEFAULT_TYPE):
        """Nettoie la liste des groupes actifs."""
        inactive_groups = set()
        
        for group_id in self.state.active_groups.copy():
            try:
                await context.bot.get_chat(group_id)
            except Exception:
                logger.info(f"Groupe {group_id} inaccessible, suppression de la liste active")
                inactive_groups.add(group_id)
        
        self.state.active_groups -= inactive_groups
        
        if inactive_groups:
            logger.info(f"Nettoyage terminé : {len(inactive_groups)} groupes supprimés")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gère tous les callbacks du bot."""
        query = update.callback_query
        await query.answer()
        data = query.data

        # Gestion des PDF
        if data == "menu_pdfs":
            await self.state.pdf_manager.send_pdf_menu(query, context)
        elif data.startswith("pdf_serie_"):
            serie = data.replace("pdf_serie_", "")
            await self.state.pdf_manager.send_serie_subjects(query, context, serie)
        elif data.startswith("pdf_download"):
            action, serie, subject = self.state.pdf_manager.parse_callback_data(data)
            if action == "download_all":
                await self.state.pdf_manager.send_all_pdfs(query, context, serie)
            elif action == "download" and subject:
                await self.state.pdf_manager.send_pdf(query, context, serie, subject)

        # Autres callbacks
        elif data == "conseils_etudes":
            await self._conseils_etudes_callback(query)
        elif data == "citation_motivante":
            await self._citation_motivante_callback(query)
        elif data == "help":
            await self._help_callback(query)
        elif data == "back_menu":
            await self._back_menu_callback(query)
        elif data == "check_subscription":
            await self._check_subscription_callback(query, context)
    
    async def _conseils_etudes_callback(self, query):
        """Affiche des conseils d'études."""
        conseils = [
            "📚 Lisez activement en prenant des notes",
            "🕐 Révisez régulièrement, pas au dernier moment", 
            "🎯 Fixez-vous des objectifs réalisables",
            "💡 Expliquez à quelqu'un d'autre ce que vous apprenez",
            "⏰ Faites des pauses pour mieux mémoriser"
        ]

        conseil = random.choice(conseils)

        conseil_text = (
            "💡 CONSEIL D'ÉTUDE 💡\n\n"
            f"{conseil}\n\n"
            "🎯 Mettez ce conseil en pratique dès aujourd'hui !"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Autre conseil", callback_data="conseils_etudes")],
            [InlineKeyboardButton("📥 Télécharger cours", callback_data="menu_pdfs")]
        ]

        await query.edit_message_text(conseil_text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _citation_motivante_callback(self, query):
        """Affiche une citation motivante."""
        quote = random.choice(self.state.motivational_quotes)

        motivation_text = (
            "🌟 MOTIVATION DU JOUR 🌟\n\n"
            f"{quote}\n\n"
            "🎓 Continuez vos efforts, le succès vous attend !"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Autre citation", callback_data="citation_motivante")],
            [InlineKeyboardButton("📥 Télécharger cours", callback_data="menu_pdfs")]
        ]

        await query.edit_message_text(motivation_text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _help_callback(self, query):
        """Affiche l'aide depuis le callback."""
        help_text = (
            "ℹ️ AIDE - BOT ÉDUCATIF ℹ️\n\n"
            "📥 Cours gratuits :\n"
            "• Toutes matières des séries A4, C, D\n"
            "• PDF téléchargeables instantanément\n\n"
            "🎯 Quiz en groupe :\n"  
            "• Ajoutez-moi à votre groupe d'étude\n"
            "• Quiz d'Histoire-Géographie\n"
            "• Système de points par groupe\n\n"
            "✅ Tout est gratuit et sans limite !"
        )

        await query.edit_message_text(
            help_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 Télécharger cours", callback_data="menu_pdfs")]])
        )
    
    async def _back_menu_callback(self, query):
        """Retour au menu principal."""
        await query.edit_message_text(
            self.ui_texts.get_main_menu_text(),
            reply_markup=self.ui_texts.get_main_menu_keyboard()
        )
    
    async def _check_subscription_callback(self, query, context):
        """Callback pour re-vérifier l'abonnement."""
        user_id = query.from_user.id
        is_subscribed, subscription_message = await self.subscription_manager.check_user_subscription(context, user_id)

        if is_subscribed:
            start_text = "✅ ABONNEMENT VÉRIFIÉ ! ✅\n\n" + self.ui_texts.get_main_menu_text()
            try:
                await query.edit_message_text(start_text, reply_markup=self.ui_texts.get_main_menu_keyboard())
            except Exception as e:
                if "Message is not modified" in str(e):
                    await query.message.reply_text(start_text, reply_markup=self.ui_texts.get_main_menu_keyboard())
                    await query.answer("✅ Vérification réussie !")
                else:
                    logger.error(f"Erreur modification message: {e}")
        else:
            keyboard = self.ui_texts.get_subscription_keyboard(self.state.REQUIRED_CHANNEL, self.state.REQUIRED_GROUP)
            try:
                await query.edit_message_text(subscription_message, reply_markup=keyboard)
            except Exception as e:
                if "Message is not modified" in str(e):
                    await query.answer("⚠️ Veuillez d'abord vous abonner")
                else:
                    logger.error(f"Erreur modification message: {e}")
    
    async def conseil_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /conseil."""
        chat_type = update.effective_chat.type
        user_id = update.effective_user.id

        if chat_type == ChatType.PRIVATE:
            is_subscribed, subscription_message = await self.subscription_manager.check_user_subscription(context, user_id)
            if not is_subscribed:
                await update.message.reply_text(subscription_message)
                return
            
        conseils = [
            "📚 Conseil d'étude : Lisez activement en prenant des notes manuscrites",
            "🕐 Conseil d'étude : Révisez régulièrement, pas au dernier moment", 
            "🎯 Conseil d'étude : Fixez-vous des objectifs réalisables quotidiennement",
            "💡 Conseil d'étude : Expliquez à quelqu'un d'autre ce que vous apprenez",
            "⏰ Conseil d'étude : Faites des pauses de 10 min toutes les heures",
            "🧠 Conseil d'étude : Variez les matières pour stimuler votre cerveau",
            "📖 Conseil d'étude : Créez des fiches de révision colorées",
            "🌅 Conseil d'étude : Étudiez le matin quand votre esprit est frais"
        ]

        conseil = random.choice(conseils)
        await update.message.reply_text(conseil)
    
    async def motivation_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /motivation."""
        chat_type = update.effective_chat.type
        user_id = update.effective_user.id

        if chat_type == ChatType.PRIVATE:
            is_subscribed, subscription_message = await self.subscription_manager.check_user_subscription(context, user_id)
            if not is_subscribed:
                await update.message.reply_text(subscription_message)
                return
            
        quote = random.choice(self.state.motivational_quotes)

        motivation_text = (
            "🌟 MOTIVATION DU JOUR 🌟\n\n"
            f"{quote}\n\n"
            "🎓 Continuez vos efforts, le succès vous attend !"
        )

        await update.message.reply_text(motivation_text)
    
    async def planning_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /planning."""
        chat_type = update.effective_chat.type
        user_id = update.effective_user.id

        if chat_type == ChatType.PRIVATE:
            is_subscribed, subscription_message = await self.subscription_manager.check_user_subscription(context, user_id)
            if not is_subscribed:
                await update.message.reply_text(subscription_message)
                return
            
        plannings = [
            (
                "📅 PLANNING SEMAINE INTENSIVE 📅\n\n"
                "🌅 06h-08h : Mathématiques (esprit frais)\n"
                "🌞 09h-11h : Sciences (Physique/Chimie)\n"
                "☀️ 14h-16h : Français/Philosophie\n"
                "🌆 17h-19h : Histoire/Géographie\n"
                "🌙 20h-21h : Révisions générales"
            ),
            (
                "📅 PLANNING ÉQUILIBRÉ 📅\n\n"
                "📚 Lundi : Mathématiques + Français\n"
                "🔬 Mardi : Sciences + Anglais\n"
                "🏛️ Mercredi : Histoire + Géographie\n"
                "🤔 Jeudi : Philosophie + SVT\n"
                "📖 Vendredi : Révisions mixtes\n"
                "🎯 Weekend : Tests et exercices"
            ),
            (
                "📅 PLANNING EXPRESS (2h/jour) 📅\n\n"
                "⏰ 45 min : Matière principale\n"
                "⏰ 30 min : Matière secondaire\n"
                "⏰ 15 min : Révisions rapides\n"
                "⏰ 30 min : Exercices pratiques\n\n"
                "💡 Astuce : Alternez les matières chaque jour"
            )
        ]

        planning = random.choice(plannings)
        await update.message.reply_text(planning)
    
    async def cours_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /cours."""
        chat_type = update.effective_chat.type
        user_id = update.effective_user.id

        if chat_type == ChatType.PRIVATE:
            is_subscribed, subscription_message = await self.subscription_manager.check_user_subscription(context, user_id)
            if not is_subscribed:
                await update.message.reply_text(subscription_message)
                return

            await update.message.reply_text(
                self.ui_texts.get_main_menu_text(),
                reply_markup=self.ui_texts.get_main_menu_keyboard()
            )
        else:
            cours_text = (
                "📚 TÉLÉCHARGEMENT DE COURS 📚\n\n"
                "🚫 Les téléchargements ne sont pas autorisés dans les groupes\n\n"
                "✅ Pour télécharger vos cours :\n"
                "1️⃣ Contactez le bot en privé : @Kabroedu_bot\n"
                "2️⃣ Ou cliquez sur le bouton ci-dessous\n\n"
                "📖 Séries disponibles :\n"
                "📚 A4 : Français, Anglais, Histoire, Géographie, Maths, Philo\n"
                "🔬 D : Sciences + matières communes\n"
                "📊 C : Maths & Sciences + matières communes\n\n"
                "🎓 Tous les cours sont GRATUITS !"
            )

            keyboard = [
                [InlineKeyboardButton("📥 Télécharger en privé", url="https://t.me/Kabroedu_bot?start=cours")]
            ]

            await update.message.reply_text(cours_text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande d'aide."""
        chat_type = update.effective_chat.type

        if chat_type == ChatType.PRIVATE:
            help_text = (
                "ℹ️ AIDE - BOT ÉDUCATIF ℹ️\n\n"
                "📥 En privé :\n"
                "• Téléchargement de cours par série\n"
                "• Conseils d'études personnalisés\n"
                "• Citations motivantes\n\n"
                "🎯 Dans les groupes :\n"
                "• Quiz d'Histoire-Géographie\n"
                "• Système de points par groupe\n"
                "• Classements séparés\n\n"
                "✅ Ajoutez-moi dans votre groupe d'étude !"
            )
        else:
            help_text = (
                "ℹ️ AIDE - QUIZ DE GROUPE ℹ️\n\n"
                "🎯 Commandes disponibles :\n"
                "• /quiz - Démarrer un quiz de 3 questions\n"
                "• /scores - Voir le classement du groupe\n"
                "• /conseil - Recevoir un conseil d'étude\n"
                "• /motivation - Citation motivante\n"
                "• /planning - Suggestion de planning\n"
                "• /cours - Télécharger des cours PDF\n"
                "• /start - Informations sur le bot\n\n"
                "📚 Fonctionnement :\n"
                "• Questions d'Histoire-Géographie mélangées\n"
                "• 30 secondes par question\n"
                "• 1 point par bonne réponse\n"
                "• Quiz quotidien automatique à 21h00\n"
                "• Scores séparés par groupe\n\n"
                "💡 Astuce : Utilisez /cours pour télécharger des PDF directement !"
            )

        await update.message.reply_text(help_text)
    
    def setup_daily_quiz_job(self, application: Application):
        """Configure le job quotidien de quiz à 21h00."""
        try:
            chad_tz = pytz.timezone('Africa/Ndjamena')
            job_queue = application.job_queue
            
            if job_queue:
                job_queue.run_daily(
                    self.daily_quiz_job,
                    time=time(21, 0, 0, tzinfo=chad_tz),
                    days=(0, 1, 2, 3, 4, 5, 6),
                    data="daily_quiz",
                    name="daily_quiz_job"
                )
                logger.info("Job quotidien configuré pour 21h00 (heure du Tchad)")
            else:
                logger.warning("JobQueue non disponible - quiz quotidien désactivé")

        except Exception as e:
            logger.error(f"Erreur configuration job quotidien: {e}")
    
    async def run(self):
        """Démarre le bot."""
        if not self.state.TELEGRAM_TOKEN:
            logger.error("❌ Veuillez configurer votre TOKEN Telegram !")
            return

        # Charger les données
        self.data_manager.load_questions()
        self.data_manager.load_motivational_quotes()
        self.data_manager.load_scores()
        self.data_manager.load_active_groups()

        # Créer l'application
        application = Application.builder().token(self.state.TELEGRAM_TOKEN).build()

        try:
            # Commandes
            application.add_handler(CommandHandler("start", self.start_command))
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(CommandHandler("quiz", self.quiz_command))
            application.add_handler(CommandHandler("scores", self.scores_command))
            application.add_handler(CommandHandler("cours", self.cours_command))
            application.add_handler(CommandHandler("conseil", self.conseil_command))
            application.add_handler(CommandHandler("motivation", self.motivation_command))
            application.add_handler(CommandHandler("planning", self.planning_command))

            # Callbacks et polls
            application.add_handler(CallbackQueryHandler(self.handle_callback))
            application.add_handler(PollAnswerHandler(self.handle_poll_answer))

            # Configurer le quiz quotidien automatique
            self.setup_daily_quiz_job(application)

            logger.info("🚀 Bot éducatif démarré avec succès !")
            print("🚀 Bot éducatif démarré avec succès !")
            print("📚 Fonctionnalités disponibles :")
            print("   • Téléchargement de cours (privé + groupes)")
            print("   • Quiz d'Histoire-Géographie avec options mélangées")
            print("   • Quiz quotidien automatique à 21h00")
            print("   • Scores séparés par groupe avec sauvegarde périodique")
            print("   • Plus de 500 citations motivantes")
            print(f"📊 Scores chargés pour {len(self.state.group_scores)} groupes")
            print(f"👥 {len(self.state.active_groups)} groupes actifs")

            # Démarrer la tâche de sauvegarde périodique
            self.save_task = asyncio.create_task(self.data_manager.periodic_save())

            # Démarrer le bot avec run_polling (méthode recommandée)
            await application.run_polling(
                poll_interval=1.0,
                timeout=10,
                bootstrap_retries=5,
                read_timeout=2,
                write_timeout=2
            )
            
        except KeyboardInterrupt:
            logger.info("Arrêt du bot demandé par l'utilisateur")
        except Exception as e:
            logger.error(f"Erreur critique au démarrage : {e}")
            print(f"❌ Erreur au démarrage : {e}")
        finally:
            # Arrêter la tâche de sauvegarde et sauvegarder une dernière fois
            if self.save_task:
                self.save_task.cancel()
            logger.info("Sauvegarde finale des données...")
            self.data_manager.save_scores()
            self.data_manager.save_active_groups()
            logger.info("Données sauvegardées avec succès")

async def main():
    """Point d'entrée principal."""
    bot = EducationalBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
