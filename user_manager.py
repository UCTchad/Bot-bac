
import logging
from typing import Dict, Optional
from database import DatabaseManager
from config import POINTS_PER_CORRECT_ANSWER
from cache_manager import global_cache, cache_result

logger = logging.getLogger(__name__)

class UserManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def get_or_create_user(self, user_id: int, name: str) -> Dict:
        """Récupère ou crée un utilisateur."""
        try:
            user_score = self.db.get_user_score(user_id)
            if user_score is None:
                # Créer un nouvel utilisateur
                self.db.update_user_score(user_id, name, 0, 0, 0)
                user_score = {'correct': 0, 'total': 0, 'name': name, 'stars': 0}
                logger.info(f"Nouvel utilisateur créé : {name} (ID: {user_id})")
            else:
                # Mettre à jour le nom si nécessaire
                if user_score['name'] != name and name:
                    user_score['name'] = name
                    self.db.update_user_score(
                        user_id, name, user_score['correct'], 
                        user_score['total'], user_score['stars']
                    )
            
            return user_score
        except Exception as e:
            logger.error(f"Erreur récupération/création utilisateur {user_id}: {e}")
            return {'correct': 0, 'total': 0, 'name': name, 'stars': 0}
    
    def update_user_answer(self, user_id: int, name: str, question: str, is_correct: bool):
        """Met à jour les scores après une réponse."""
        try:
            user_score = self.get_or_create_user(user_id, name)
            
            # Calculer les nouveaux scores
            new_correct = user_score['correct'] + (1 if is_correct else 0)
            new_total = user_score['total'] + 1
            stars_earned = POINTS_PER_CORRECT_ANSWER if is_correct else 0
            new_stars = user_score['stars'] + stars_earned
            
            # Mettre à jour en base
            self.db.update_user_score(user_id, name, new_correct, new_total, new_stars)
            self.db.add_user_grade(user_id, question, is_correct, stars_earned)
            
            # Invalider les caches liés aux classements et stats
            self._invalidate_ranking_caches()
            global_cache.delete("global_stats")
            
            # Incrémenter le compteur d'activité récente
            activity_key = "recent_activity"
            current_activity = global_cache.get(activity_key) or 0
            global_cache.set(activity_key, current_activity + 1, ttl=300)  # 5 minutes
            
            # Mettre à jour le streak
            try:
                from streak_manager import StreakManager
                streak_manager = StreakManager(self.db)
                streak_result = streak_manager.update_user_streak(user_id, is_correct)
                if streak_result and streak_result['is_new_record']:
                    logger.info(f"NOUVEAU RECORD DE STREAK pour {name}: {streak_result['current_streak']} jours!")
            except Exception as e:
                logger.error(f"Erreur mise à jour streak: {e}")
            
            # Vérifier les nouveaux badges
            try:
                from badge_manager import BadgeManager
                badge_manager = BadgeManager(self.db)
                updated_stats = self.get_user_stats(user_id)
                if updated_stats:
                    new_badges = badge_manager.check_user_badges(user_id, updated_stats)
                    if new_badges:
                        logger.info(f"Nouveaux badges pour {name}: {[b['name'] for b in new_badges]}")
            except Exception as e:
                logger.error(f"Erreur vérification badges: {e}")
            
            logger.info(f"Score mis à jour pour {name}: {'correct' if is_correct else 'incorrect'} (+{stars_earned} étoiles)")
            
            return {
                'correct': new_correct,
                'total': new_total,
                'name': name,
                'stars': new_stars
            }
        except Exception as e:
            logger.error(f"Erreur mise à jour réponse utilisateur {user_id}: {e}")
            return None
    
    def _invalidate_ranking_caches(self):
        """Invalide tous les caches de classement."""
        keys_to_delete = []
        for key in global_cache.cache.keys():
            if key.startswith('ranking:'):
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            global_cache.delete(key)
    
    def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """Récupère les statistiques détaillées d'un utilisateur."""
        try:
            user_score = self.db.get_user_score(user_id)
            if not user_score:
                return None
            
            user_grades = self.db.get_user_grades(user_id)
            percentage = (user_score['correct'] / max(user_score['total'], 1)) * 100
            
            return {
                'basic': user_score,
                'grades': user_grades,
                'percentage': percentage
            }
        except Exception as e:
            logger.error(f"Erreur récupération stats utilisateur {user_id}: {e}")
            return None
    
    def get_ranking(self, limit: int = 20, group_only: bool = False) -> list:
        """Récupère le classement des utilisateurs avec cache (version legacy)."""
        return self.get_ranking_paginated(page=1, per_page=limit, group_only=group_only)['ranking']
    
    def get_ranking_paginated(self, page: int = 1, per_page: int = 20, group_only: bool = False) -> Dict:
        """Récupère le classement paginé avec cache optimisé."""
        cache_key = f"ranking_page:{page}:{per_page}:{group_only}"
        
        # Vérifier le cache
        cached_ranking = global_cache.get(cache_key)
        if cached_ranking is not None:
            return cached_ranking
        
        try:
            # Utiliser la méthode optimisée de la base de données
            result = self.db.get_ranking_paginated(page, per_page, group_only)
            
            # TTL adaptatif basé sur l'activité
            activity_key = "recent_activity"
            recent_activity = global_cache.get(activity_key) or 0
            
            # Plus d'activité = cache plus court
            if recent_activity > 10:  # Beaucoup d'activité
                ttl = 30  # 30 secondes
            elif recent_activity > 5:  # Activité modérée
                ttl = 60  # 1 minute
            else:  # Peu d'activité
                ttl = 180  # 3 minutes
            
            global_cache.set(cache_key, result, ttl=ttl)
            
            return result
        except Exception as e:
            logger.error(f"Erreur récupération classement paginé: {e}")
            return {'ranking': [], 'pagination': {}}
    
    def get_global_stats(self) -> Dict:
        """Récupère les statistiques globales avec cache."""
        cache_key = "global_stats"
        
        # Vérifier le cache
        cached_stats = global_cache.get(cache_key)
        if cached_stats is not None:
            return cached_stats
        
        try:
            all_scores = self.db.get_all_user_scores()
            
            if not all_scores:
                empty_stats = {
                    'total_participants': 0,
                    'total_questions': 0,
                    'total_correct': 0,
                    'total_stars': 0,
                    'global_percentage': 0
                }
                global_cache.set(cache_key, empty_stats, ttl=120)
                return empty_stats
            
            total_participants = len(all_scores)
            total_questions = sum(score['total'] for score in all_scores.values())
            total_correct = sum(score['correct'] for score in all_scores.values())
            total_stars = sum(score['stars'] for score in all_scores.values())
            global_percentage = (total_correct / max(total_questions, 1)) * 100
            
            stats = {
                'total_participants': total_participants,
                'total_questions': total_questions,
                'total_correct': total_correct,
                'total_stars': total_stars,
                'global_percentage': global_percentage
            }
            
            # Mettre en cache pour 2 minutes
            global_cache.set(cache_key, stats, ttl=120)
            
            return stats
        except Exception as e:
            logger.error(f"Erreur récupération stats globales: {e}")
            return {}
    
    def get_user_warnings(self, user_id: int) -> int:
        """Récupère le nombre d'avertissements d'un utilisateur."""
        return self.db.get_user_warnings(user_id)
    
    def add_user_warning(self, user_id: int) -> int:
        """Ajoute un avertissement à un utilisateur et retourne le nouveau total."""
        current_warnings = self.db.get_user_warnings(user_id)
        new_warnings = current_warnings + 1
        self.db.update_user_warnings(user_id, new_warnings)
        return new_warnings
    
    def clear_user_warnings(self, user_id: int):
        """Supprime tous les avertissements d'un utilisateur."""
        self.db.delete_user_warnings(user_id)
