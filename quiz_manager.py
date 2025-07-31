
import json
import random
import logging
from datetime import datetime
from typing import Dict, List, Optional
from telegram import Poll
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import DatabaseManager
from cache_manager import global_cache, cache_result
from config import (
    QUESTIONS_FILE, DAILY_QUIZ_QUESTIONS_COUNT, QUIZ_ANSWER_TIME_SECONDS,
    QUIZ_QUESTION_DELAY_SECONDS, GROUP_CHAT_ID
)

logger = logging.getLogger(__name__)

class QuizManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.questions = self.load_quiz_questions()
    
    def load_quiz_questions(self) -> Dict[str, List[Dict]]:
        """Charge les questions depuis le fichier JSON par thème."""
        try:
            with open(QUESTIONS_FILE, 'r', encoding='utf-8') as file:
                data = json.load(file)
                
                # Charger toutes les questions par thème
                themes_questions = {}
                
                # Questions mixtes (mode classique)
                if 'histoire_geographie' in data:
                    themes_questions['histoire_geographie'] = data['histoire_geographie']
                
                # Questions par thème spécifique
                if 'histoire' in data:
                    themes_questions['histoire'] = data['histoire']
                
                if 'geographie' in data:
                    themes_questions['geographie'] = data['geographie']
                
                # Si pas de thèmes séparés, utiliser le mix pour tous
                if not themes_questions.get('histoire') and not themes_questions.get('geographie'):
                    if themes_questions.get('histoire_geographie'):
                        themes_questions['histoire'] = themes_questions['histoire_geographie']
                        themes_questions['geographie'] = themes_questions['histoire_geographie']
                
                total_questions = sum(len(q) for q in themes_questions.values())
                logger.info(f"{total_questions} questions chargées depuis {QUESTIONS_FILE} ({len(themes_questions)} thèmes)")
                return themes_questions
                
        except FileNotFoundError:
            logger.error(f"Fichier {QUESTIONS_FILE} non trouvé")
            return {'histoire_geographie': []}
        except Exception as e:
            logger.error(f"Erreur lors du chargement des questions : {e}")
            return {'histoire_geographie': []}
    
    def reload_questions(self):
        """Recharge les questions depuis le fichier."""
        self.questions = self.load_quiz_questions()
    
    def get_random_question(self, theme: str = 'histoire_geographie', avoid_recent: bool = True) -> Optional[Dict]:
        """Récupère une question aléatoire du thème spécifié avec cache des questions récentes."""
        if theme not in self.questions or not self.questions[theme]:
            logger.warning(f"Aucune question disponible pour le thème {theme}")
            return None
        
        available_questions = self.questions[theme]
        
        # Éviter les questions récemment posées
        if avoid_recent and len(available_questions) > 5:
            recent_cache_key = f"recent_questions_{theme}"
            recent_questions = global_cache.get(recent_cache_key) or []
            
            # Filtrer les questions récentes
            filtered_questions = [q for q in available_questions 
                                if q.get('question') not in recent_questions]
            
            if filtered_questions:
                available_questions = filtered_questions
        
        selected_question = random.choice(available_questions)
        
        # Mettre à jour le cache des questions récentes
        if avoid_recent:
            recent_cache_key = f"recent_questions_{theme}"
            recent_questions = global_cache.get(recent_cache_key) or []
            recent_questions.append(selected_question.get('question'))
            
            # Garder seulement les 10 dernières questions
            if len(recent_questions) > 10:
                recent_questions = recent_questions[-10:]
            
            global_cache.set(recent_cache_key, recent_questions, ttl=1800)  # 30 minutes
        
        return selected_question
    
    def get_available_themes(self) -> List[str]:
        """Retourne la liste des thèmes disponibles."""
        return [theme for theme, questions in self.questions.items() if questions]
    
    def get_theme_stats(self) -> Dict[str, int]:
        """Retourne les statistiques des questions par thème."""
        return {theme: len(questions) for theme, questions in self.questions.items()}
    
    async def send_single_poll_quiz(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, theme: str = 'histoire_geographie') -> bool:
        """Envoie un seul quiz sous forme de poll."""
        try:
            # Vérifier rate limit global pour création de polls
            from rate_limiter import rate_limiter
            global_allowed, global_reset = rate_limiter.is_globally_allowed('poll_creation')
            if not global_allowed:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ Trop de quiz simultanés. Réessayez dans {global_reset} seconde(s)."
                )
                return False
            question_data = self.get_random_question(theme)
            if not question_data:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Aucune question disponible pour le moment."
                )
                return False
            
            # Import config pour les thèmes
            from config import QUIZ_THEMES
            theme_info = QUIZ_THEMES.get(theme, {'name': '📚 Quiz', 'emoji': '🎯'})
            
            # Créer le poll
            poll_message = await context.bot.send_poll(
                chat_id=chat_id,
                question=f"🎯 QUIZ {theme_info['name']} {theme_info['emoji']}\n\n{question_data['question']}",
                options=question_data['options'],
                type=Poll.QUIZ,
                correct_option_id=question_data['correct_option_id'],
                explanation=f"📖 {question_data['explanation']}",
                is_anonymous=False,
                open_period=QUIZ_ANSWER_TIME_SECONDS
            )
            
            # Stocker les données du poll
            poll_id = poll_message.poll.id
            self.db.add_active_poll(
                poll_id, question_data, chat_id,
                poll_message.message_id, question_data['question']
            )
            
            logger.info(f"Quiz poll envoyé au chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi quiz poll : {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Erreur lors de l'envoi du quiz."
            )
            return False
    
    async def send_daily_quiz_sequence(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Envoie une séquence de quiz quotidiens."""
        chat_id = GROUP_CHAT_ID
        
        try:
            # Initialiser la session de quiz quotidien
            session_id = f"daily_{chat_id}_{datetime.now().strftime('%Y%m%d')}"
            self.db.add_daily_quiz_session(
                session_id, chat_id, 0, DAILY_QUIZ_QUESTIONS_COUNT, set()
            )
            
            # Envoyer le message d'introduction
            intro_text = (
                "🎯 **QUIZ QUOTIDIEN - DÉBUT** 🎯\n\n"
                f"📚 **{DAILY_QUIZ_QUESTIONS_COUNT} questions d'Histoire-Géographie vous attendent !**\n"
                f"⏰ Chaque question dure {QUIZ_ANSWER_TIME_SECONDS} secondes\n"
                "🌟 5 étoiles par bonne réponse\n"
                "🏆 Résultats et classement à la fin\n\n"
                "**🚀 QUESTION 1/3 arrive dans 5 secondes...**"
            )
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=intro_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Programmer les questions avec des délais
            for i in range(DAILY_QUIZ_QUESTIONS_COUNT):
                delay = 5 + (i * (QUIZ_ANSWER_TIME_SECONDS + QUIZ_QUESTION_DELAY_SECONDS))
                context.job_queue.run_once(
                    lambda ctx, question_num=i+1: self.send_daily_question(ctx, chat_id, question_num, session_id),
                    when=delay
                )
            
            # Programmer l'affichage des résultats finaux
            results_delay = 5 + (DAILY_QUIZ_QUESTIONS_COUNT * (QUIZ_ANSWER_TIME_SECONDS + QUIZ_QUESTION_DELAY_SECONDS)) + 10
            context.job_queue.run_once(
                lambda ctx: self.send_daily_results(ctx, chat_id, session_id),
                when=results_delay
            )
            
            logger.info(f"Séquence de quiz quotidien programmée pour le groupe {chat_id}")
            
        except Exception as e:
            logger.error(f"Erreur programmation quiz quotidien : {e}")
    
    async def send_daily_question(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, 
                                 question_num: int, session_id: str) -> None:
        """Envoie une question spécifique de la séquence quotidienne."""
        try:
            question_data = self.get_random_question()
            if not question_data:
                logger.error("Aucune question disponible pour le quiz quotidien")
                return
            
            # Créer le poll
            poll_message = await context.bot.send_poll(
                chat_id=chat_id,
                question=f"🎯 QUIZ QUOTIDIEN - QUESTION {question_num}/{DAILY_QUIZ_QUESTIONS_COUNT} 📚\n\n{question_data['question']}",
                options=question_data['options'],
                type=Poll.QUIZ,
                correct_option_id=question_data['correct_option_id'],
                explanation=f"📖 {question_data['explanation']}",
                is_anonymous=False,
                open_period=QUIZ_ANSWER_TIME_SECONDS
            )
            
            # Stocker les données du poll
            poll_id = poll_message.poll.id
            self.db.add_active_poll(
                poll_id, question_data, chat_id,
                poll_message.message_id, question_data['question'],
                session_id, question_num
            )
            
            logger.info(f"Question {question_num}/{DAILY_QUIZ_QUESTIONS_COUNT} envoyée pour le quiz quotidien")
            
        except Exception as e:
            logger.error(f"Erreur envoi question quotidienne : {e}")
    
    async def send_daily_results(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, session_id: str) -> None:
        """Envoie les résultats finaux du quiz quotidien."""
        try:
            session = self.db.get_daily_quiz_session(session_id)
            if not session:
                logger.warning(f"Session {session_id} non trouvée pour les résultats")
                return
            
            participants = len(session['participants'])
            
            # Créer le message de résultats
            result_text = (
                "🏆 **QUIZ QUOTIDIEN TERMINÉ !** 🏆\n\n"
                f"📊 **Bilan de la session :**\n"
                f"👥 Participants : {participants}\n"
                f"❓ Questions posées : {DAILY_QUIZ_QUESTIONS_COUNT}\n"
                f"🌟 Étoiles distribuées : {participants * DAILY_QUIZ_QUESTIONS_COUNT * 5} maximum\n\n"
            )
            
            # Afficher le top 5 du jour si applicable
            from user_manager import UserManager
            user_manager = UserManager(self.db)
            ranking = user_manager.get_ranking(5)
            
            if ranking:
                result_text += "🥇 **TOP 5 DU CLASSEMENT GÉNÉRAL :**\n"
                for i, (user_id, score) in enumerate(ranking):
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
            self.db.remove_daily_quiz_session(session_id)
            
            logger.info(f"Résultats du quiz quotidien envoyés pour le groupe {chat_id}")
            
        except Exception as e:
            logger.error(f"Erreur envoi résultats quotidiens : {e}")
    
    def get_active_poll(self, poll_id: str) -> Optional[Dict]:
        """Récupère un poll actif."""
        return self.db.get_active_poll(poll_id)
    
    def update_daily_session_participant(self, session_id: str, user_id: int):
        """Ajoute un participant à une session de quiz quotidien."""
        try:
            session = self.db.get_daily_quiz_session(session_id)
            if session:
                session['participants'].add(user_id)
                self.db.update_daily_quiz_session_participants(session_id, session['participants'])
        except Exception as e:
            logger.error(f"Erreur ajout participant session {session_id}: {e}")
