
import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from user_manager import UserManager
from config import SPAM_KEYWORDS, MAX_WARNINGS, MESSAGES

logger = logging.getLogger(__name__)

class SpamManager:
    def __init__(self, user_manager: UserManager):
        self.user_manager = user_manager
        self.spam_keywords = SPAM_KEYWORDS
    
    def is_spam(self, text: str) -> bool:
        """Vérifie si un texte contient des mots-clés de spam."""
        if not text:
            return False
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.spam_keywords)
    
    async def handle_spam_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gère un message de spam détecté. Retourne True si c'était du spam."""
        message = update.message
        if not message or not message.text:
            return False
        
        if not self.is_spam(message.text):
            return False
        
        user_id = message.from_user.id
        chat_id = message.chat.id
        username = message.from_user.mention_html()
        
        try:
            # Supprimer le message de spam
            await message.delete()
            logger.info(f"Message spam supprimé de {message.from_user.username}")
            
            # Ajouter un avertissement
            warning_count = self.user_manager.add_user_warning(user_id)
            
            if warning_count >= MAX_WARNINGS:
                # Bannir après le nombre max d'avertissements
                try:
                    await context.bot.ban_chat_member(chat_id, user_id)
                    await context.bot.send_message(
                        chat_id,
                        MESSAGES["user_banned"].format(username=username),
                        parse_mode=ParseMode.HTML
                    )
                    self.user_manager.clear_user_warnings(user_id)
                    logger.info(f"Utilisateur banni pour spam : {message.from_user.username}")
                except Exception as ban_error:
                    logger.error(f"Erreur bannissement : {ban_error}")
            else:
                # Envoyer un avertissement
                remaining = MAX_WARNINGS - warning_count
                warning_msg = await context.bot.send_message(
                    chat_id,
                    MESSAGES["warning_message"].format(
                        username=username,
                        warning_count=warning_count,
                        remaining=remaining
                    ),
                    parse_mode=ParseMode.HTML
                )
                
                # Supprimer le message d'avertissement après 10 secondes
                context.job_queue.run_once(
                    lambda ctx: self._delete_message_safe(ctx, chat_id, warning_msg.message_id),
                    when=10
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur gestion spam : {e}")
            return False
    
    async def _delete_message_safe(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
        """Supprime un message de manière sécurisée."""
        try:
            await context.bot.delete_message(chat_id, message_id)
        except Exception as e:
            logger.debug(f"N'a pas pu supprimer le message {message_id}: {e}")
    
    def add_spam_keyword(self, keyword: str):
        """Ajoute un mot-clé de spam."""
        if keyword.lower() not in [k.lower() for k in self.spam_keywords]:
            self.spam_keywords.append(keyword.lower())
            logger.info(f"Mot-clé spam ajouté : {keyword}")
    
    def remove_spam_keyword(self, keyword: str) -> bool:
        """Supprime un mot-clé de spam."""
        try:
            self.spam_keywords.remove(keyword.lower())
            logger.info(f"Mot-clé spam supprimé : {keyword}")
            return True
        except ValueError:
            return False
    
    def get_spam_keywords(self) -> list:
        """Retourne la liste des mots-clés de spam."""
        return self.spam_keywords.copy()
