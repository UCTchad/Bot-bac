
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from database import DatabaseManager
from cache_manager import global_cache

logger = logging.getLogger(__name__)

class LeaderboardManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def get_daily_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Classement du jour."""
        cache_key = f"leaderboard_daily_{limit}"
        cached = global_cache.get(cache_key)
        if cached:
            return cached
        
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT ug.user_id, us.name,
                           COUNT(*) as questions_today,
                           SUM(CASE WHEN ug.is_correct THEN 1 ELSE 0 END) as correct_today,
                           SUM(ug.stars_earned) as stars_today
                    FROM user_grades ug
                    JOIN user_scores us ON ug.user_id = us.user_id
                    WHERE DATE(ug.answered_at) = ?
                    GROUP BY ug.user_id, us.name
                    ORDER BY stars_today DESC, correct_today DESC
                    LIMIT ?
                """, (today, limit))
                
                results = cursor.fetchall()
                
                leaderboard = []
                for result in results:
                    percentage = (result[3] / result[2]) * 100 if result[2] > 0 else 0
                    leaderboard.append({
                        'user_id': result[0],
                        'name': result[1],
                        'questions': result[2],
                        'correct': result[3],
                        'stars': result[4],
                        'percentage': percentage
                    })
                
                global_cache.set(cache_key, leaderboard, ttl=300)  # 5 minutes
                return leaderboard
                
        except Exception as e:
            logger.error(f"Erreur classement quotidien: {e}")
            return []
    
    def get_weekly_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Classement de la semaine."""
        cache_key = f"leaderboard_weekly_{limit}"
        cached = global_cache.get(cache_key)
        if cached:
            return cached
        
        try:
            week_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT ug.user_id, us.name,
                           COUNT(*) as questions_week,
                           SUM(CASE WHEN ug.is_correct THEN 1 ELSE 0 END) as correct_week,
                           SUM(ug.stars_earned) as stars_week
                    FROM user_grades ug
                    JOIN user_scores us ON ug.user_id = us.user_id
                    WHERE ug.answered_at >= ?
                    GROUP BY ug.user_id, us.name
                    ORDER BY stars_week DESC, correct_week DESC
                    LIMIT ?
                """, (week_start, limit))
                
                results = cursor.fetchall()
                
                leaderboard = []
                for result in results:
                    percentage = (result[3] / result[2]) * 100 if result[2] > 0 else 0
                    leaderboard.append({
                        'user_id': result[0],
                        'name': result[1],
                        'questions': result[2],
                        'correct': result[3],
                        'stars': result[4],
                        'percentage': percentage
                    })
                
                global_cache.set(cache_key, leaderboard, ttl=600)  # 10 minutes
                return leaderboard
                
        except Exception as e:
            logger.error(f"Erreur classement hebdomadaire: {e}")
            return []
    
    def get_monthly_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Classement du mois."""
        cache_key = f"leaderboard_monthly_{limit}"
        cached = global_cache.get(cache_key)
        if cached:
            return cached
        
        try:
            month_start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT ug.user_id, us.name,
                           COUNT(*) as questions_month,
                           SUM(CASE WHEN ug.is_correct THEN 1 ELSE 0 END) as correct_month,
                           SUM(ug.stars_earned) as stars_month
                    FROM user_grades ug
                    JOIN user_scores us ON ug.user_id = us.user_id
                    WHERE ug.answered_at >= ?
                    GROUP BY ug.user_id, us.name
                    ORDER BY stars_month DESC, correct_month DESC
                    LIMIT ?
                """, (month_start, limit))
                
                results = cursor.fetchall()
                
                leaderboard = []
                for result in results:
                    percentage = (result[3] / result[2]) * 100 if result[2] > 0 else 0
                    leaderboard.append({
                        'user_id': result[0],
                        'name': result[1],
                        'questions': result[2],
                        'correct': result[3],
                        'stars': result[4],
                        'percentage': percentage
                    })
                
                global_cache.set(cache_key, leaderboard, ttl=1800)  # 30 minutes
                return leaderboard
                
        except Exception as e:
            logger.error(f"Erreur classement mensuel: {e}")
            return []
    
    def get_leaderboard_text(self, period: str, limit: int = 10) -> str:
        """Génère le texte d'affichage du classement."""
        if period == "daily":
            leaderboard = self.get_daily_leaderboard(limit)
            title = "🏆 **CLASSEMENT DU JOUR** 🏆"
            period_text = "aujourd'hui"
        elif period == "weekly":
            leaderboard = self.get_weekly_leaderboard(limit)
            title = "🏆 **CLASSEMENT DE LA SEMAINE** 🏆"
            period_text = "cette semaine"
        elif period == "monthly":
            leaderboard = self.get_monthly_leaderboard(limit)
            title = "🏆 **CLASSEMENT DU MOIS** 🏆"
            period_text = "ce mois"
        else:
            return "❌ Période invalide. Utilisez: daily, weekly, monthly"
        
        if not leaderboard:
            return f"📊 **Aucune activité {period_text}**\n\nParticipez aux quiz pour apparaître dans le classement !"
        
        text = f"{title}\n\n"
        medals = ["🥇", "🥈", "🥉"]
        
        for i, user in enumerate(leaderboard):
            rank = i + 1
            if rank <= 3:
                medal = medals[rank - 1]
                text += f"{medal} **{rank}.** {user['name']}\n"
            else:
                text += f"🏅 **{rank}.** {user['name']}\n"
            
            text += f"   ✅ {user['correct']}/{user['questions']} questions"
            text += f" | 🌟 {user['stars']} étoiles"
            text += f" | 📊 {user['percentage']:.1f}%\n\n"
        
        return text
