
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from database import DatabaseManager

logger = logging.getLogger(__name__)

class StreakManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._init_streak_table()
    
    def _init_streak_table(self):
        """Initialise la table des streaks."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_streaks (
                        user_id INTEGER PRIMARY KEY,
                        current_streak INTEGER DEFAULT 0,
                        best_streak INTEGER DEFAULT 0,
                        last_correct_date DATE,
                        streak_broken_count INTEGER DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES user_scores (user_id)
                    )
                """)
                
                # Index pour optimiser les requêtes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_streaks_current ON user_streaks(current_streak DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_streaks_best ON user_streaks(best_streak DESC)")
                
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur initialisation table streaks: {e}")
    
    def update_user_streak(self, user_id: int, is_correct: bool):
        """Met à jour le streak d'un utilisateur après une réponse."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Récupérer le streak actuel
                cursor.execute("""
                    SELECT current_streak, best_streak, last_correct_date, streak_broken_count
                    FROM user_streaks WHERE user_id = ?
                """, (user_id,))
                
                result = cursor.fetchone()
                today = datetime.now().date()
                
                if result:
                    current_streak, best_streak, last_correct_date, broken_count = result
                    last_date = datetime.strptime(last_correct_date, '%Y-%m-%d').date() if last_correct_date else None
                else:
                    current_streak, best_streak, last_date, broken_count = 0, 0, None, 0
                
                if is_correct:
                    # Bonne réponse
                    if last_date == today:
                        # Déjà une bonne réponse aujourd'hui, pas de changement
                        pass
                    elif last_date == today - timedelta(days=1):
                        # Streak continue
                        current_streak += 1
                    else:
                        # Nouveau streak ou streak interrompu
                        current_streak = 1
                    
                    # Mettre à jour le meilleur streak
                    if current_streak > best_streak:
                        best_streak = current_streak
                    
                    last_correct_date = today.strftime('%Y-%m-%d')
                else:
                    # Mauvaise réponse - streak cassé
                    if current_streak > 0:
                        broken_count += 1
                        current_streak = 0
                    last_correct_date = None
                
                # Sauvegarder
                cursor.execute("""
                    INSERT OR REPLACE INTO user_streaks 
                    (user_id, current_streak, best_streak, last_correct_date, streak_broken_count, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, current_streak, best_streak, last_correct_date, broken_count))
                
                conn.commit()
                
                return {
                    'current_streak': current_streak,
                    'best_streak': best_streak,
                    'is_new_record': current_streak == best_streak and current_streak > 1
                }
                
        except Exception as e:
            logger.error(f"Erreur mise à jour streak utilisateur {user_id}: {e}")
            return None
    
    def get_user_streak(self, user_id: int) -> Optional[Dict]:
        """Récupère les informations de streak d'un utilisateur."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT current_streak, best_streak, last_correct_date, streak_broken_count
                    FROM user_streaks WHERE user_id = ?
                """, (user_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'current_streak': result[0],
                        'best_streak': result[1],
                        'last_correct_date': result[2],
                        'streak_broken_count': result[3]
                    }
                return None
        except Exception as e:
            logger.error(f"Erreur récupération streak utilisateur {user_id}: {e}")
            return None
    
    def get_streak_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Récupère le classement des meilleurs streaks actuels."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT us.name, st.current_streak, st.best_streak
                    FROM user_streaks st
                    JOIN user_scores us ON st.user_id = us.user_id
                    WHERE st.current_streak > 0
                    ORDER BY st.current_streak DESC, st.best_streak DESC
                    LIMIT ?
                """, (limit,))
                
                results = cursor.fetchall()
                return [
                    {
                        'name': result[0],
                        'current_streak': result[1],
                        'best_streak': result[2]
                    }
                    for result in results
                ]
        except Exception as e:
            logger.error(f"Erreur classement streaks: {e}")
            return []
    
    def get_streak_display_text(self, user_id: int) -> str:
        """Génère le texte d'affichage du streak pour un utilisateur."""
        streak_data = self.get_user_streak(user_id)
        
        if not streak_data:
            return "🔥 **Aucun streak en cours**\n\nRépondez correctement plusieurs jours de suite pour commencer un streak !"
        
        current = streak_data['current_streak']
        best = streak_data['best_streak']
        broken = streak_data['streak_broken_count']
        
        text = "🔥 **VOS STREAKS** 🔥\n\n"
        
        if current > 0:
            text += f"🔥 **Streak actuel :** {current} jour{'s' if current > 1 else ''}\n"
            text += f"⭐ **Meilleur streak :** {best} jour{'s' if best > 1 else ''}\n"
            
            if current == best and current >= 5:
                text += "👑 **NOUVEAU RECORD PERSONNEL !**\n"
        else:
            text += f"💔 **Streak interrompu**\n"
            text += f"⭐ **Meilleur streak :** {best} jour{'s' if best > 1 else ''}\n"
        
        text += f"📊 **Streaks cassés :** {broken}\n\n"
        
        if current >= 7:
            text += "🏆 **STREAK LÉGENDAIRE !**"
        elif current >= 3:
            text += "🌟 **Excellent streak !**"
        elif current == 0:
            text += "💪 **Continuez, le prochain streak vous attend !**"
        
        return text
