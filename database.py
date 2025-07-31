
import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "bot_data.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialise la base de données avec les tables nécessaires."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Table des utilisateurs et leurs scores
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_scores (
                        user_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        correct INTEGER DEFAULT 0,
                        total INTEGER DEFAULT 0,
                        stars INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Table des avertissements
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_warnings (
                        user_id INTEGER PRIMARY KEY,
                        warning_count INTEGER DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Table des notes détaillées (bonnes/mauvaises réponses)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_grades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        question TEXT,
                        is_correct BOOLEAN,
                        stars_earned INTEGER,
                        answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES user_scores (user_id)
                    )
                """)
                
                # Table des polls actifs
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS active_polls (
                        poll_id TEXT PRIMARY KEY,
                        question_data TEXT,
                        chat_id INTEGER,
                        message_id INTEGER,
                        question TEXT,
                        session_id TEXT,
                        question_number INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Table des sessions de quiz quotidiens
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS daily_quiz_sessions (
                        session_id TEXT PRIMARY KEY,
                        chat_id INTEGER,
                        current_question INTEGER,
                        total_questions INTEGER,
                        participants TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Table des badges utilisateur
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_badges (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        badge_key TEXT,
                        earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, badge_key),
                        FOREIGN KEY (user_id) REFERENCES user_scores (user_id)
                    )
                """)
                
                # Table d'archivage pour les anciennes données
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS archived_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        table_name TEXT,
                        data_json TEXT,
                        archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Créer les index pour optimiser les performances
                self._create_indexes(cursor)
                
                conn.commit()
                logger.info("Base de données initialisée avec succès")
                
        except Exception as e:
            logger.error(f"Erreur initialisation base de données : {e}")
    
    # Méthodes pour user_scores
    def get_user_score(self, user_id: int) -> Optional[Dict]:
        """Récupère les scores d'un utilisateur."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, name, correct, total, stars 
                    FROM user_scores WHERE user_id = ?
                """, (user_id,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'correct': result[2],
                        'total': result[3],
                        'name': result[1],
                        'stars': result[4]
                    }
                return None
        except Exception as e:
            logger.error(f"Erreur récupération score utilisateur {user_id}: {e}")
            return None
    
    def update_user_score(self, user_id: int, name: str, correct: int, total: int, stars: int):
        """Met à jour ou insère les scores d'un utilisateur."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO user_scores (user_id, name, correct, total, stars, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, name, correct, total, stars))
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur mise à jour score utilisateur {user_id}: {e}")
    
    def get_all_user_scores(self) -> Dict[int, Dict]:
        """Récupère tous les scores des utilisateurs."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, name, correct, total, stars FROM user_scores")
                results = cursor.fetchall()
                
                scores = {}
                for result in results:
                    scores[result[0]] = {
                        'correct': result[2],
                        'total': result[3],
                        'name': result[1],
                        'stars': result[4]
                    }
                return scores
        except Exception as e:
            logger.error(f"Erreur récupération tous les scores: {e}")
            return {}
    
    # Méthodes pour user_warnings
    def get_user_warnings(self, user_id: int) -> int:
        """Récupère le nombre d'avertissements d'un utilisateur."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT warning_count FROM user_warnings WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Erreur récupération avertissements utilisateur {user_id}: {e}")
            return 0
    
    def update_user_warnings(self, user_id: int, warning_count: int):
        """Met à jour le nombre d'avertissements d'un utilisateur."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO user_warnings (user_id, warning_count, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (user_id, warning_count))
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur mise à jour avertissements utilisateur {user_id}: {e}")
    
    def delete_user_warnings(self, user_id: int):
        """Supprime les avertissements d'un utilisateur."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM user_warnings WHERE user_id = ?", (user_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur suppression avertissements utilisateur {user_id}: {e}")
    
    def get_all_warnings(self) -> Dict[int, int]:
        """Récupère tous les avertissements."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, warning_count FROM user_warnings")
                results = cursor.fetchall()
                return {result[0]: result[1] for result in results}
        except Exception as e:
            logger.error(f"Erreur récupération tous les avertissements: {e}")
            return {}
    
    # Méthodes pour user_grades
    def add_user_grade(self, user_id: int, question: str, is_correct: bool, stars_earned: int):
        """Ajoute une note pour un utilisateur."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_grades (user_id, question, is_correct, stars_earned)
                    VALUES (?, ?, ?, ?)
                """, (user_id, question, is_correct, stars_earned))
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur ajout note utilisateur {user_id}: {e}")
    
    def get_user_grades(self, user_id: int) -> Dict:
        """Récupère les notes détaillées d'un utilisateur."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT question, is_correct, stars_earned, answered_at
                    FROM user_grades WHERE user_id = ?
                    ORDER BY answered_at DESC
                """, (user_id,))
                results = cursor.fetchall()
                
                correct = []
                incorrect = []
                total_stars = 0
                
                for result in results:
                    question_data = {
                        'question': result[0],
                        'stars': result[2]
                    }
                    total_stars += result[2]
                    
                    if result[1]:  # is_correct
                        correct.append(question_data)
                    else:
                        incorrect.append(question_data)
                
                return {
                    'correct': correct,
                    'incorrect': incorrect,
                    'total_stars': total_stars
                }
        except Exception as e:
            logger.error(f"Erreur récupération notes utilisateur {user_id}: {e}")
            return {'correct': [], 'incorrect': [], 'total_stars': 0}
    
    # Méthodes pour active_polls
    def add_active_poll(self, poll_id: str, question_data: Dict, chat_id: int, 
                       message_id: int, question: str, session_id: str = None, 
                       question_number: int = None):
        """Ajoute un poll actif."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO active_polls 
                    (poll_id, question_data, chat_id, message_id, question, session_id, question_number)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (poll_id, json.dumps(question_data), chat_id, message_id, 
                     question, session_id, question_number))
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur ajout poll actif {poll_id}: {e}")
    
    def get_active_poll(self, poll_id: str) -> Optional[Dict]:
        """Récupère un poll actif."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT question_data, chat_id, message_id, question, session_id, question_number
                    FROM active_polls WHERE poll_id = ?
                """, (poll_id,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'question_data': json.loads(result[0]),
                        'chat_id': result[1],
                        'message_id': result[2],
                        'question': result[3],
                        'session_id': result[4],
                        'question_number': result[5]
                    }
                return None
        except Exception as e:
            logger.error(f"Erreur récupération poll actif {poll_id}: {e}")
            return None
    
    def remove_active_poll(self, poll_id: str):
        """Supprime un poll actif."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM active_polls WHERE poll_id = ?", (poll_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur suppression poll actif {poll_id}: {e}")
    
    # Méthodes pour daily_quiz_sessions
    def add_daily_quiz_session(self, session_id: str, chat_id: int, current_question: int, 
                              total_questions: int, participants: set):
        """Ajoute une session de quiz quotidien."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO daily_quiz_sessions 
                    (session_id, chat_id, current_question, total_questions, participants)
                    VALUES (?, ?, ?, ?, ?)
                """, (session_id, chat_id, current_question, total_questions, json.dumps(list(participants))))
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur ajout session quiz quotidien {session_id}: {e}")
    
    def get_daily_quiz_session(self, session_id: str) -> Optional[Dict]:
        """Récupère une session de quiz quotidien."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT chat_id, current_question, total_questions, participants
                    FROM daily_quiz_sessions WHERE session_id = ?
                """, (session_id,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'chat_id': result[0],
                        'current_question': result[1],
                        'total_questions': result[2],
                        'participants': set(json.loads(result[3]))
                    }
                return None
        except Exception as e:
            logger.error(f"Erreur récupération session quiz quotidien {session_id}: {e}")
            return None
    
    def update_daily_quiz_session_participants(self, session_id: str, participants: set):
        """Met à jour les participants d'une session de quiz quotidien."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE daily_quiz_sessions SET participants = ?
                    WHERE session_id = ?
                """, (json.dumps(list(participants)), session_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur mise à jour participants session {session_id}: {e}")
    
    def remove_daily_quiz_session(self, session_id: str):
        """Supprime une session de quiz quotidien."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM daily_quiz_sessions WHERE session_id = ?", (session_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur suppression session quiz quotidien {session_id}: {e}")
    
    def cleanup_old_data(self, days: int = 30):
        """Nettoie les anciennes données (polls actifs et sessions expirées)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Supprimer les polls actifs de plus de X jours
                cursor.execute("""
                    DELETE FROM active_polls 
                    WHERE created_at < datetime('now', '-{} days')
                """.format(days))
                
                # Supprimer les sessions de quiz de plus de X jours
                cursor.execute("""
                    DELETE FROM daily_quiz_sessions 
                    WHERE created_at < datetime('now', '-{} days')
                """.format(days))
                
                conn.commit()
                logger.info(f"Nettoyage des données anciennes de plus de {days} jours effectué")
                
        except Exception as e:
            logger.error(f"Erreur nettoyage données anciennes : {e}")
    
    def _create_indexes(self, cursor):
        """Crée les index pour optimiser les performances."""
        try:
            # Index sur user_scores pour le classement
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_scores_stars ON user_scores(stars DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_scores_correct ON user_scores(correct DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_scores_total ON user_scores(total)")
            
            # Index sur user_grades pour les requêtes par utilisateur
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_grades_user_id ON user_grades(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_grades_answered_at ON user_grades(answered_at DESC)")
            
            # Index sur active_polls pour les requêtes rapides
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_polls_chat_id ON active_polls(chat_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_polls_session_id ON active_polls(session_id)")
            
            # Index sur user_badges
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_badges_user_id ON user_badges(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_badges_earned_at ON user_badges(earned_at DESC)")
            
            logger.info("Index créés avec succès")
        except Exception as e:
            logger.error(f"Erreur création index : {e}")
    
    def get_ranking_paginated(self, page: int = 1, per_page: int = 20, group_only: bool = False) -> Dict:
        """Récupère le classement avec pagination."""
        try:
            offset = (page - 1) * per_page
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Requête pour compter le total
                if group_only:
                    cursor.execute("SELECT COUNT(*) FROM user_scores WHERE total > 0")
                else:
                    cursor.execute("SELECT COUNT(*) FROM user_scores")
                total_count = cursor.fetchone()[0]
                
                # Requête paginée optimisée avec index
                if group_only:
                    cursor.execute("""
                        SELECT user_id, name, correct, total, stars 
                        FROM user_scores 
                        WHERE total > 0
                        ORDER BY stars DESC, correct DESC 
                        LIMIT ? OFFSET ?
                    """, (per_page, offset))
                else:
                    cursor.execute("""
                        SELECT user_id, name, correct, total, stars 
                        FROM user_scores 
                        ORDER BY stars DESC, correct DESC 
                        LIMIT ? OFFSET ?
                    """, (per_page, offset))
                
                results = cursor.fetchall()
                
                ranking_data = []
                for result in results:
                    ranking_data.append((result[0], {
                        'correct': result[2],
                        'total': result[3],
                        'name': result[1],
                        'stars': result[4]
                    }))
                
                total_pages = (total_count + per_page - 1) // per_page
                
                return {
                    'ranking': ranking_data,
                    'pagination': {
                        'current_page': page,
                        'per_page': per_page,
                        'total_pages': total_pages,
                        'total_count': total_count,
                        'has_next': page < total_pages,
                        'has_prev': page > 1
                    }
                }
                
        except Exception as e:
            logger.error(f"Erreur récupération classement paginé : {e}")
            return {'ranking': [], 'pagination': {}}
    
    def archive_old_data(self, days: int = 90):
        """Archive les anciennes données avant suppression."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Archiver les anciennes notes (user_grades)
                cursor.execute("""
                    INSERT INTO archived_data (table_name, data_json)
                    SELECT 'user_grades', json_group_array(
                        json_object(
                            'user_id', user_id,
                            'question', question,
                            'is_correct', is_correct,
                            'stars_earned', stars_earned,
                            'answered_at', answered_at
                        )
                    )
                    FROM user_grades 
                    WHERE answered_at < datetime('now', '-{} days')
                """.format(days))
                
                # Supprimer après archivage
                cursor.execute("""
                    DELETE FROM user_grades 
                    WHERE answered_at < datetime('now', '-{} days')
                """.format(days))
                
                archived_count = cursor.rowcount
                
                # Nettoyer les polls et sessions expirés
                cursor.execute("""
                    DELETE FROM active_polls 
                    WHERE created_at < datetime('now', '-7 days')
                """)
                
                cursor.execute("""
                    DELETE FROM daily_quiz_sessions 
                    WHERE created_at < datetime('now', '-7 days')
                """)
                
                conn.commit()
                logger.info(f"Archivage terminé : {archived_count} entrées archivées")
                
        except Exception as e:
            logger.error(f"Erreur archivage données : {e}")
    
    def optimize_database(self):
        """Optimise la base de données (VACUUM, ANALYZE)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Analyser les statistiques pour l'optimiseur
                cursor.execute("ANALYZE")
                
                # Compacter la base de données
                cursor.execute("VACUUM")
                
                logger.info("Optimisation de la base de données terminée")
                
        except Exception as e:
            logger.error(f"Erreur optimisation base de données : {e}")
    
    def get_database_stats(self) -> Dict:
        """Récupère les statistiques de la base de données."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Taille des tables
                tables = ['user_scores', 'user_grades', 'user_warnings', 'active_polls', 
                         'daily_quiz_sessions', 'user_badges', 'archived_data']
                
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    stats[f"{table}_count"] = cursor.fetchone()[0]
                
                # Taille du fichier
                stats['db_size_bytes'] = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                stats['db_size_mb'] = round(stats['db_size_bytes'] / (1024 * 1024), 2)
                
                return stats
                
        except Exception as e:
            logger.error(f"Erreur récupération stats DB : {e}")
            return {}
    
    def connection(self):
        """Retourne une connexion à la base de données."""
        return sqlite3.connect(self.db_path)
