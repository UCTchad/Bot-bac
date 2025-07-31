
import time
import logging
from typing import Dict, Tuple
from functools import wraps

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        # user_id -> (last_request_time, request_count, window_start)
        self.user_requests: Dict[int, Tuple[float, int, float]] = {}
        self.global_requests: Dict[str, Tuple[float, int]] = {}
        
        # Limites par utilisateur (requêtes par minute)
        self.user_limits = {
            'quiz_now': (5, 60),      # 5 quiz par minute max
            'ranking': (10, 60),      # 10 classements par minute
            'stats': (15, 60),        # 15 stats par minute
            'menu': (20, 60),         # 20 menus par minute
            'badges': (10, 60),       # 10 badges par minute
        }
        
        # Limites globales (requêtes par seconde)
        self.global_limits = {
            'quiz_now': (2, 1),       # 2 quiz par seconde max globalement
            'poll_creation': (3, 1),  # 3 polls par seconde max
        }
    
    def is_user_allowed(self, user_id: int, command: str) -> Tuple[bool, int]:
        """Vérifie si l'utilisateur peut exécuter la commande."""
        if command not in self.user_limits:
            return True, 0
        
        max_requests, window = self.user_limits[command]
        current_time = time.time()
        
        if user_id not in self.user_requests:
            self.user_requests[user_id] = (current_time, 1, current_time)
            return True, 0
        
        last_time, count, window_start = self.user_requests[user_id]
        
        # Nouvelle fenêtre de temps
        if current_time - window_start >= window:
            self.user_requests[user_id] = (current_time, 1, current_time)
            return True, 0
        
        # Dans la même fenêtre
        if count >= max_requests:
            reset_time = int(window_start + window - current_time)
            return False, reset_time
        
        # Incrémenter le compteur
        self.user_requests[user_id] = (current_time, count + 1, window_start)
        return True, 0
    
    def is_globally_allowed(self, command: str) -> Tuple[bool, int]:
        """Vérifie les limites globales."""
        if command not in self.global_limits:
            return True, 0
        
        max_requests, window = self.global_limits[command]
        current_time = time.time()
        
        if command not in self.global_requests:
            self.global_requests[command] = (current_time, 1)
            return True, 0
        
        last_time, count = self.global_requests[command]
        
        # Nouvelle fenêtre
        if current_time - last_time >= window:
            self.global_requests[command] = (current_time, 1)
            return True, 0
        
        # Trop de requêtes
        if count >= max_requests:
            reset_time = int(last_time + window - current_time)
            return False, reset_time
        
        # Incrémenter
        self.global_requests[command] = (last_time, count + 1)
        return True, 0
    
    def cleanup_expired(self):
        """Nettoie les entrées expirées."""
        current_time = time.time()
        
        # Nettoyer les requêtes utilisateur
        expired_users = []
        for user_id, (last_time, count, window_start) in self.user_requests.items():
            if current_time - window_start > 300:  # 5 minutes
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del self.user_requests[user_id]
        
        # Nettoyer les requêtes globales
        expired_commands = []
        for command, (last_time, count) in self.global_requests.items():
            if current_time - last_time > 60:  # 1 minute
                expired_commands.append(command)
        
        for command in expired_commands:
            del self.global_requests[command]

def rate_limit(command: str):
    """Décorateur pour limiter le taux de requêtes."""
    def decorator(func):
        @wraps(func)
        async def wrapper(update_or_query, context, *args, **kwargs):
            # Déterminer l'utilisateur
            if hasattr(update_or_query, 'effective_user'):
                user = update_or_query.effective_user
            elif hasattr(update_or_query, 'from_user'):
                user = update_or_query.from_user
            else:
                # Fallback si pas d'utilisateur identifiable
                return await func(update_or_query, context, *args, **kwargs)
            
            user_id = user.id
            
            # Vérifier les limites utilisateur
            user_allowed, user_reset = rate_limiter.is_user_allowed(user_id, command)
            if not user_allowed:
                warning_text = (
                    f"⚠️ **Limite de requêtes atteinte !**\n\n"
                    f"Vous faites trop de requêtes `/{command}`.\n"
                    f"⏰ Réessayez dans {user_reset} seconde(s).\n\n"
                    f"💡 Cette limite protège le bot contre la surcharge."
                )
                
                if hasattr(update_or_query, 'message'):
                    await update_or_query.message.reply_text(warning_text, parse_mode='MARKDOWN')
                elif hasattr(update_or_query, 'edit_message_text'):
                    await update_or_query.edit_message_text(warning_text, parse_mode='MARKDOWN')
                
                logger.warning(f"Rate limit atteint pour user {user_id} sur command {command}")
                return
            
            # Vérifier les limites globales
            global_allowed, global_reset = rate_limiter.is_globally_allowed(command)
            if not global_allowed:
                warning_text = (
                    f"⚠️ **Bot temporairement surchargé !**\n\n"
                    f"Trop de requêtes simultanées.\n"
                    f"⏰ Réessayez dans {global_reset} seconde(s)."
                )
                
                if hasattr(update_or_query, 'message'):
                    await update_or_query.message.reply_text(warning_text)
                elif hasattr(update_or_query, 'edit_message_text'):
                    await update_or_query.edit_message_text(warning_text)
                
                logger.warning(f"Rate limit global atteint pour command {command}")
                return
            
            # Exécuter la fonction
            return await func(update_or_query, context, *args, **kwargs)
        
        return wrapper
    return decorator

# Instance globale
rate_limiter = RateLimiter()
