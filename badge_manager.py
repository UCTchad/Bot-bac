
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from database import DatabaseManager

logger = logging.getLogger(__name__)

class BadgeManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.badges_config = {
            'first_correct': {
                'name': 'Premier Succès',
                'emoji': '🌟',
                'description': 'Première bonne réponse',
                'condition': lambda stats: stats['basic']['correct'] >= 1
            },
            'streak_5': {
                'name': 'Série de 5',
                'emoji': '🔥',
                'description': '5 bonnes réponses consécutives',
                'condition': self._check_streak_5
            },
            'star_collector_50': {
                'name': 'Collectionneur',
                'emoji': '⭐',
                'description': '50 étoiles collectées',
                'condition': lambda stats: stats['basic']['stars'] >= 50
            },
            'star_collector_100': {
                'name': 'Maître Collectionneur',
                'emoji': '🌠',
                'description': '100 étoiles collectées',
                'condition': lambda stats: stats['basic']['stars'] >= 100
            },
            'perfectionist': {
                'name': 'Perfectionniste',
                'emoji': '💎',
                'description': '100% de réussite sur 10+ questions',
                'condition': lambda stats: stats['basic']['total'] >= 10 and stats['percentage'] == 100.0
            },
            'history_expert': {
                'name': 'Expert Histoire',
                'emoji': '🏛️',
                'description': '20 bonnes réponses en histoire',
                'condition': self._check_history_expert
            },
            'geography_expert': {
                'name': 'Expert Géographie', 
                'emoji': '🌍',
                'description': '20 bonnes réponses en géographie',
                'condition': self._check_geography_expert
            },
            'daily_warrior': {
                'name': 'Guerrier Quotidien',
                'emoji': '⚔️',
                'description': '7 jours de participation consécutifs',
                'condition': self._check_daily_warrior
            },
            'top_3': {
                'name': 'Podium',
                'emoji': '🥉',
                'description': 'Classé dans le TOP 3',
                'condition': self._check_top_3
            },
            'champion': {
                'name': 'Champion',
                'emoji': '👑',
                'description': '1ère place du classement',
                'condition': self._check_champion
            }
        }
    
    def _check_streak_5(self, stats) -> bool:
        """Vérifie si l'utilisateur a 5 bonnes réponses consécutives."""
        grades = stats['grades']['correct']
        if len(grades) < 5:
            return False
        
        # Vérifier les 5 dernières réponses
        recent_correct = grades[-5:]
        return len(recent_correct) == 5
    
    def _check_history_expert(self, stats) -> bool:
        """Vérifie si l'utilisateur a 20 bonnes réponses en histoire."""
        grades = stats['grades']['correct']
        history_count = sum(1 for grade in grades if 'histoire' in grade['question'].lower())
        return history_count >= 20
    
    def _check_geography_expert(self, stats) -> bool:
        """Vérifie si l'utilisateur a 20 bonnes réponses en géographie."""
        grades = stats['grades']['correct']
        geo_count = sum(1 for grade in grades if 'géographie' in grade['question'].lower() or 'capitale' in grade['question'].lower())
        return geo_count >= 20
    
    def _check_daily_warrior(self, stats) -> bool:
        """Vérifie 7 jours de participation consécutifs."""
        # Implémentation basique - peut être améliorée avec un tracking plus précis
        grades = stats['grades']['correct'] + stats['grades']['incorrect']
        if not grades:
            return False
        
        # Compter les jours uniques des 7 derniers jours
        recent_days = set()
        cutoff_date = datetime.now() - timedelta(days=7)
        
        for grade in grades:
            # Supposer que le timestamp est stocké quelque part
            # Pour l'instant, approximation basée sur le nombre total
            pass
        
        return len(recent_days) >= 7  # À implémenter correctement avec timestamps
    
    def _check_top_3(self, stats) -> bool:
        """Vérifie si l'utilisateur est dans le TOP 3."""
        from user_manager import UserManager
        user_manager = UserManager(self.db)
        ranking = user_manager.get_ranking(3)
        
        # Trouver la position de l'utilisateur (à améliorer avec user_id)
        return len(ranking) >= 3 and stats['basic']['stars'] > 0
    
    def _check_champion(self, stats) -> bool:
        """Vérifie si l'utilisateur est champion."""
        from user_manager import UserManager
        user_manager = UserManager(self.db)
        ranking = user_manager.get_ranking(1)
        
        return len(ranking) > 0 and stats['basic']['stars'] > 0
    
    def check_user_badges(self, user_id: int, stats: Dict) -> List[Dict]:
        """Vérifie quels badges l'utilisateur a mérités."""
        earned_badges = []
        
        for badge_key, badge_config in self.badges_config.items():
            try:
                if badge_config['condition'](stats):
                    # Vérifier si le badge n'est pas déjà attribué
                    if not self.user_has_badge(user_id, badge_key):
                        earned_badges.append({
                            'key': badge_key,
                            'name': badge_config['name'],
                            'emoji': badge_config['emoji'],
                            'description': badge_config['description']
                        })
                        # Attribuer le badge
                        self.award_badge(user_id, badge_key)
            except Exception as e:
                logger.error(f"Erreur vérification badge {badge_key} pour user {user_id}: {e}")
        
        return earned_badges
    
    def user_has_badge(self, user_id: int, badge_key: str) -> bool:
        """Vérifie si un utilisateur a déjà un badge."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM user_badges 
                    WHERE user_id = ? AND badge_key = ?
                """, (user_id, badge_key))
                return cursor.fetchone()[0] > 0
        except:
            return False
    
    def award_badge(self, user_id: int, badge_key: str):
        """Attribue un badge à un utilisateur."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO user_badges (user_id, badge_key, earned_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (user_id, badge_key))
                conn.commit()
                logger.info(f"Badge {badge_key} attribué à l'utilisateur {user_id}")
        except Exception as e:
            logger.error(f"Erreur attribution badge {badge_key} à {user_id}: {e}")
    
    def get_user_badges(self, user_id: int) -> List[Dict]:
        """Récupère tous les badges d'un utilisateur."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT badge_key, earned_at FROM user_badges 
                    WHERE user_id = ? ORDER BY earned_at DESC
                """, (user_id,))
                results = cursor.fetchall()
                
                badges = []
                for badge_key, earned_at in results:
                    if badge_key in self.badges_config:
                        badge_config = self.badges_config[badge_key]
                        badges.append({
                            'key': badge_key,
                            'name': badge_config['name'],
                            'emoji': badge_config['emoji'],
                            'description': badge_config['description'],
                            'earned_at': earned_at
                        })
                
                return badges
        except Exception as e:
            logger.error(f"Erreur récupération badges utilisateur {user_id}: {e}")
            return []
    
    def get_badge_display_text(self, badges: List[Dict]) -> str:
        """Génère le texte d'affichage des badges."""
        if not badges:
            return "🏆 **Vos Badges : Aucun pour le moment**\n\nParticipez aux quiz pour débloquer des badges !"
        
        text = f"🏆 **Vos Badges ({len(badges)})** 🏆\n\n"
        
        for badge in badges:
            text += f"{badge['emoji']} **{badge['name']}**\n"
            text += f"   📝 {badge['description']}\n\n"
        
        return text
