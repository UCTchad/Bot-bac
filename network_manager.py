
import asyncio
import logging
from typing import Callable, Any, Optional
from functools import wraps
from telegram.error import NetworkError, TimedOut, RetryAfter, BadRequest
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)

class NetworkManager:
    def __init__(self):
        self.message_buffer = []
        self.max_buffer_size = 1000
        self.buffer_file = "message_buffer.json"
        self.load_buffer()
    
    def load_buffer(self):
        """Charge le buffer des messages depuis le fichier."""
        try:
            if os.path.exists(self.buffer_file):
                with open(self.buffer_file, 'r', encoding='utf-8') as f:
                    self.message_buffer = json.load(f)
                logger.info(f"Buffer chargé : {len(self.message_buffer)} messages en attente")
        except Exception as e:
            logger.error(f"Erreur chargement buffer : {e}")
            self.message_buffer = []
    
    def save_buffer(self):
        """Sauvegarde le buffer des messages."""
        try:
            with open(self.buffer_file, 'w', encoding='utf-8') as f:
                json.dump(self.message_buffer, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erreur sauvegarde buffer : {e}")
    
    def add_to_buffer(self, chat_id: int, text: str, parse_mode: str = None, reply_markup=None):
        """Ajoute un message au buffer en cas de panne."""
        if len(self.message_buffer) >= self.max_buffer_size:
            # Supprimer les anciens messages si le buffer est plein
            self.message_buffer.pop(0)
        
        message_data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode,
            'timestamp': datetime.now().isoformat(),
            'retry_count': 0
        }
        
        self.message_buffer.append(message_data)
        self.save_buffer()
        logger.info(f"Message ajouté au buffer pour chat {chat_id}")
    
    async def process_buffer(self, context):
        """Traite les messages en attente dans le buffer."""
        if not self.message_buffer:
            return
        
        logger.info(f"Traitement du buffer : {len(self.message_buffer)} messages")
        processed = []
        
        for message_data in self.message_buffer[:]:
            try:
                await context.bot.send_message(
                    chat_id=message_data['chat_id'],
                    text=message_data['text'],
                    parse_mode=message_data.get('parse_mode')
                )
                processed.append(message_data)
                logger.info(f"Message buffer envoyé à {message_data['chat_id']}")
                
            except Exception as e:
                # Incrémenter le compteur de retry
                message_data['retry_count'] = message_data.get('retry_count', 0) + 1
                
                # Supprimer après 5 tentatives ou si trop ancien (24h)
                message_time = datetime.fromisoformat(message_data['timestamp'])
                if (message_data['retry_count'] >= 5 or 
                    datetime.now() - message_time > timedelta(hours=24)):
                    processed.append(message_data)
                    logger.warning(f"Message buffer abandonné après {message_data['retry_count']} tentatives")
                
                logger.error(f"Erreur envoi message buffer : {e}")
        
        # Supprimer les messages traités
        for msg in processed:
            if msg in self.message_buffer:
                self.message_buffer.remove(msg)
        
        if processed:
            self.save_buffer()
            logger.info(f"{len(processed)} messages traités du buffer")

def retry_on_network_error(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Décorateur pour retry automatique sur erreurs réseau."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except RetryAfter as e:
                    # Respecter le délai demandé par Telegram
                    retry_delay = e.retry_after + 1
                    logger.warning(f"Rate limit atteint, attente {retry_delay}s")
                    await asyncio.sleep(retry_delay)
                    last_exception = e
                    
                except (NetworkError, TimedOut) as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"Erreur réseau tentative {attempt + 1}/{max_retries}: {e}")
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"Échec après {max_retries} tentatives : {e}")
                        
                except BadRequest as e:
                    # Ne pas retry sur les erreurs de requête
                    logger.error(f"Erreur de requête (pas de retry) : {e}")
                    raise e
                    
                except Exception as e:
                    # Autres erreurs - pas de retry
                    logger.error(f"Erreur non-réseau (pas de retry) : {e}")
                    raise e
            
            # Si on arrive ici, toutes les tentatives ont échoué
            raise last_exception
            
        return wrapper
    return decorator

def safe_telegram_call(network_manager: NetworkManager):
    """Décorateur pour sécuriser les appels Telegram avec buffer."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # En cas d'erreur, essayer de mettre en buffer
                if hasattr(args[0], 'message') and hasattr(args[0].message, 'chat'):
                    chat_id = args[0].message.chat.id
                    error_text = f"⚠️ Erreur temporaire du bot. Message en attente de traitement."
                    network_manager.add_to_buffer(chat_id, error_text)
                
                logger.error(f"Erreur dans {func.__name__}: {e}")
                raise e
        return wrapper
    return decorator

# Instance globale
network_manager = NetworkManager()
