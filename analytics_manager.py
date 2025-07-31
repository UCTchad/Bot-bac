
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from database import DatabaseManager
from cache_manager import global_cache

logger = logging.getLogger(__name__)

class AnalyticsManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def get_activity_stats(self, days: int = 7) -> Dict:
        """Statistiques d'activité des derniers jours."""
        cache_key = f"activity_stats_{days}"
        cached = global_cache.get(cache_key)
        if cached:
            return cached
        
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Questions répondues par jour
                cursor.execute("""
                    SELECT DATE(answered_at) as day, COUNT(*) as count
                    FROM user_grades
                    WHERE answered_at >= datetime('now', '-{} days')
                    GROUP BY DATE(answered_at)
                    ORDER BY day DESC
                """.format(days))
                daily_questions = dict(cursor.fetchall())
                
                # Utilisateurs actifs par jour
                cursor.execute("""
                    SELECT DATE(answered_at) as day, COUNT(DISTINCT user_id) as users
                    FROM user_grades
                    WHERE answered_at >= datetime('now', '-{} days')
                    GROUP BY DATE(answered_at)
                    ORDER BY day DESC
                """.format(days))
                daily_users = dict(cursor.fetchall())
                
                # Taux de réussite par jour
                cursor.execute("""
                    SELECT DATE(answered_at) as day, 
                           AVG(CASE WHEN is_correct THEN 1.0 ELSE 0.0 END) * 100 as success_rate
                    FROM user_grades
                    WHERE answered_at >= datetime('now', '-{} days')
                    GROUP BY DATE(answered_at)
                    ORDER BY day DESC
                """.format(days))
                daily_success = dict(cursor.fetchall())
                
                stats = {
                    'daily_questions': daily_questions,
                    'daily_users': daily_users,
                    'daily_success_rate': {k: round(v, 1) for k, v in daily_success.items()},
                    'total_questions_period': sum(daily_questions.values()),
                    'avg_questions_per_day': sum(daily_questions.values()) / max(len(daily_questions), 1),
                    'active_users_period': len(set().union(*[[] for _ in daily_users.values()])) if daily_users else 0
                }
                
                global_cache.set(cache_key, stats, ttl=300)  # 5 minutes
                return stats
                
        except Exception as e:
            logger.error(f"Erreur récupération stats activité: {e}")
            return {}
    
    def get_question_difficulty_stats(self) -> Dict:
        """Analyse de difficulté des questions."""
        cache_key = "question_difficulty"
        cached = global_cache.get(cache_key)
        if cached:
            return cached
        
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Questions les plus difficiles (taux d'échec élevé)
                cursor.execute("""
                    SELECT question, 
                           COUNT(*) as total_attempts,
                           SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct_attempts,
                           (1.0 - CAST(SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) * 100 as difficulty_score
                    FROM user_grades
                    GROUP BY question
                    HAVING COUNT(*) >= 3
                    ORDER BY difficulty_score DESC
                    LIMIT 10
                """)
                hardest_questions = cursor.fetchall()
                
                # Questions les plus faciles
                cursor.execute("""
                    SELECT question,
                           COUNT(*) as total_attempts,
                           SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct_attempts,
                           (CAST(SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) * 100 as success_rate
                    FROM user_grades
                    GROUP BY question
                    HAVING COUNT(*) >= 3
                    ORDER BY success_rate DESC
                    LIMIT 10
                """)
                easiest_questions = cursor.fetchall()
                
                stats = {
                    'hardest_questions': [
                        {
                            'question': q[0][:50] + '...' if len(q[0]) > 50 else q[0],
                            'attempts': q[1],
                            'difficulty': round(q[3], 1)
                        } for q in hardest_questions
                    ],
                    'easiest_questions': [
                        {
                            'question': q[0][:50] + '...' if len(q[0]) > 50 else q[0],
                            'attempts': q[1],
                            'success_rate': round(q[3], 1)
                        } for q in easiest_questions
                    ]
                }
                
                global_cache.set(cache_key, stats, ttl=600)  # 10 minutes
                return stats
                
        except Exception as e:
            logger.error(f"Erreur analyse difficulté questions: {e}")
            return {'hardest_questions': [], 'easiest_questions': []}
    
    def get_user_engagement_stats(self) -> Dict:
        """Statistiques d'engagement des utilisateurs."""
        cache_key = "user_engagement"
        cached = global_cache.get(cache_key)
        if cached:
            return cached
        
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Distribution des scores
                cursor.execute("""
                    SELECT 
                        CASE 
                            WHEN stars = 0 THEN '0 étoiles'
                            WHEN stars BETWEEN 1 AND 20 THEN '1-20 étoiles'
                            WHEN stars BETWEEN 21 AND 50 THEN '21-50 étoiles'
                            WHEN stars BETWEEN 51 AND 100 THEN '51-100 étoiles'
                            ELSE '100+ étoiles'
                        END as score_range,
                        COUNT(*) as user_count
                    FROM user_scores
                    GROUP BY score_range
                    ORDER BY MIN(stars)
                """)
                score_distribution = dict(cursor.fetchall())
                
                # Utilisateurs les plus actifs
                cursor.execute("""
                    SELECT name, total, correct, stars,
                           (CAST(correct AS FLOAT) / NULLIF(total, 0)) * 100 as success_rate
                    FROM user_scores
                    WHERE total > 0
                    ORDER BY total DESC
                    LIMIT 5
                """)
                most_active = cursor.fetchall()
                
                # Taux de rétention approximatif
                cursor.execute("""
                    SELECT COUNT(DISTINCT user_id) as total_users
                    FROM user_grades
                """)
                total_users = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT user_id) as active_users
                    FROM user_grades
                    WHERE answered_at >= datetime('now', '-7 days')
                """)
                active_users = cursor.fetchone()[0]
                
                retention_rate = (active_users / max(total_users, 1)) * 100
                
                stats = {
                    'score_distribution': score_distribution,
                    'most_active_users': [
                        {
                            'name': u[0],
                            'total_questions': u[1],
                            'correct': u[2],
                            'stars': u[3],
                            'success_rate': round(u[4], 1) if u[4] else 0
                        } for u in most_active
                    ],
                    'retention_rate': round(retention_rate, 1),
                    'total_registered_users': total_users,
                    'active_users_week': active_users
                }
                
                global_cache.set(cache_key, stats, ttl=600)  # 10 minutes
                return stats
                
        except Exception as e:
            logger.error(f"Erreur stats engagement: {e}")
            return {}
    
    def generate_analytics_report(self) -> str:
        """Génère un rapport d'analytics complet."""
        try:
            activity = self.get_activity_stats(7)
            difficulty = self.get_question_difficulty_stats()
            engagement = self.get_user_engagement_stats()
            
            report = "📊 **RAPPORT ANALYTICS - 7 DERNIERS JOURS** 📊\n\n"
            
            # Activité générale
            report += "🎯 **ACTIVITÉ GÉNÉRALE**\n"
            report += f"• Questions répondues : {activity.get('total_questions_period', 0)}\n"
            report += f"• Moyenne par jour : {activity.get('avg_questions_per_day', 0):.1f}\n"
            report += f"• Utilisateurs actifs : {engagement.get('active_users_week', 0)}\n"
            report += f"• Taux de rétention : {engagement.get('retention_rate', 0)}%\n\n"
            
            # Questions les plus difficiles
            if difficulty.get('hardest_questions'):
                report += "😰 **QUESTIONS LES PLUS DIFFICILES**\n"
                for i, q in enumerate(difficulty['hardest_questions'][:3], 1):
                    report += f"{i}. {q['question']} ({q['difficulty']}% d'échec)\n"
                report += "\n"
            
            # Distribution des scores
            if engagement.get('score_distribution'):
                report += "⭐ **RÉPARTITION DES SCORES**\n"
                for range_name, count in engagement['score_distribution'].items():
                    report += f"• {range_name} : {count} utilisateur(s)\n"
                report += "\n"
            
            # Top utilisateurs
            if engagement.get('most_active_users'):
                report += "🏆 **TOP UTILISATEURS ACTIFS**\n"
                for i, user in enumerate(engagement['most_active_users'][:3], 1):
                    report += f"{i}. {user['name']} : {user['total_questions']} questions ({user['success_rate']}%)\n"
            
            return report
            
        except Exception as e:
            logger.error(f"Erreur génération rapport analytics: {e}")
            return "❌ Erreur lors de la génération du rapport d'analytics."
