
import logging
from typing import Dict, List, Optional
from database import DatabaseManager
from enum import Enum

logger = logging.getLogger(__name__)

class DifficultyLevel(Enum):
    FACILE = "facile"
    MOYEN = "moyen"
    DIFFICILE = "difficile"

class DifficultyManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.difficulty_thresholds = {
            DifficultyLevel.FACILE: {'min_success_rate': 70, 'max_success_rate': 100},
            DifficultyLevel.MOYEN: {'min_success_rate': 40, 'max_success_rate': 69},
            DifficultyLevel.DIFFICILE: {'min_success_rate': 0, 'max_success_rate': 39}
        }
    
    def get_user_recommended_difficulty(self, user_id: int) -> DifficultyLevel:
        """Recommande un niveau de difficulté basé sur les performances de l'utilisateur."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Calculer le taux de réussite des 10 dernières questions
                cursor.execute("""
                    SELECT is_correct FROM user_grades 
                    WHERE user_id = ? 
                    ORDER BY answered_at DESC 
                    LIMIT 10
                """, (user_id,))
                
                recent_answers = cursor.fetchall()
                
                if len(recent_answers) < 3:
                    return DifficultyLevel.FACILE
                
                success_rate = (sum(1 for answer in recent_answers if answer[0]) / len(recent_answers)) * 100
                
                if success_rate >= 80:
                    return DifficultyLevel.DIFFICILE
                elif success_rate >= 60:
                    return DifficultyLevel.MOYEN
                else:
                    return DifficultyLevel.FACILE
                    
        except Exception as e:
            logger.error(f"Erreur calcul difficulté recommandée pour {user_id}: {e}")
            return DifficultyLevel.FACILE
    
    def classify_question_difficulty(self, question: str) -> DifficultyLevel:
        """Classifie automatiquement la difficulté d'une question selon les statistiques."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct
                    FROM user_grades 
                    WHERE question = ?
                """, (question,))
                
                result = cursor.fetchone()
                total, correct = result[0], result[1] or 0
                
                if total < 5:  # Pas assez de données
                    return DifficultyLevel.MOYEN
                
                success_rate = (correct / total) * 100
                
                for level, thresholds in self.difficulty_thresholds.items():
                    if thresholds['min_success_rate'] <= success_rate <= thresholds['max_success_rate']:
                        return level
                
                return DifficultyLevel.MOYEN
                
        except Exception as e:
            logger.error(f"Erreur classification difficulté question: {e}")
            return DifficultyLevel.MOYEN
    
    def get_difficulty_stats(self) -> Dict:
        """Retourne les statistiques des questions par niveau de difficulté."""
        try:
            stats = {}
            
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Récupérer toutes les questions avec leurs stats
                cursor.execute("""
                    SELECT question,
                           COUNT(*) as total_attempts,
                           SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct_attempts
                    FROM user_grades
                    GROUP BY question
                    HAVING COUNT(*) >= 3
                """)
                
                questions_stats = cursor.fetchall()
                
                for level in DifficultyLevel:
                    stats[level.value] = {'count': 0, 'avg_success_rate': 0}
                
                level_questions = {level: [] for level in DifficultyLevel}
                
                for question, total, correct in questions_stats:
                    success_rate = (correct / total) * 100 if total > 0 else 0
                    
                    for level, thresholds in self.difficulty_thresholds.items():
                        if thresholds['min_success_rate'] <= success_rate <= thresholds['max_success_rate']:
                            level_questions[level].append(success_rate)
                            break
                
                for level, success_rates in level_questions.items():
                    stats[level.value] = {
                        'count': len(success_rates),
                        'avg_success_rate': sum(success_rates) / len(success_rates) if success_rates else 0
                    }
                
                return stats
                
        except Exception as e:
            logger.error(f"Erreur récupération stats difficulté: {e}")
            return {}
