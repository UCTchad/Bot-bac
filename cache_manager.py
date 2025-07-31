
import time
import logging
from typing import Dict, List, Optional, Any
from functools import wraps

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, default_ttl: int = 300):  # 5 minutes par défaut
        self.cache = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Récupère une valeur du cache."""
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                logger.debug(f"Cache HIT pour {key}")
                return value
            else:
                # Expirer la clé
                del self.cache[key]
                logger.debug(f"Cache EXPIRED pour {key}")
        
        logger.debug(f"Cache MISS pour {key}")
        return None
    
    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """Stocke une valeur dans le cache."""
        if ttl is None:
            ttl = self.default_ttl
        
        expiry = time.time() + ttl
        self.cache[key] = (value, expiry)
        logger.debug(f"Cache SET pour {key} (TTL: {ttl}s)")
    
    def delete(self, key: str) -> None:
        """Supprime une clé du cache."""
        if key in self.cache:
            del self.cache[key]
            logger.debug(f"Cache DELETE pour {key}")
    
    def clear(self) -> None:
        """Vide tout le cache."""
        self.cache.clear()
        logger.info("Cache vidé complètement")
    
    def cleanup_expired(self) -> None:
        """Nettoie les clés expirées."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self.cache.items()
            if current_time >= expiry
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.info(f"Cache cleanup: {len(expired_keys)} clés expirées supprimées")
    
    def get_stats(self) -> Dict:
        """Retourne les statistiques du cache."""
        return {
            'total_keys': len(self.cache),
            'memory_usage_estimate': sum(len(str(v[0])) for v in self.cache.values())
        }

def cache_result(cache_manager: CacheManager, key_prefix: str = "", ttl: int = None):
    """Décorateur pour mettre en cache les résultats de fonctions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Créer une clé unique basée sur la fonction et ses arguments
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Vérifier le cache
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Exécuter la fonction et mettre en cache
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator

# Instance globale du cache
global_cache = CacheManager(default_ttl=300)  # 5 minutes
