
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from database import DatabaseManager
from enum import Enum

logger = logging.getLogger(__name__)

class ChallengeStatus(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    EXPIRED = "expired"

class ChallengeManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._init_challenge_tables()
    
    def _init_challenge_tables(self):
        """Initialise les tables des défis."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Table des défis
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_challenges (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        challenger_id INTEGER,
                        challenged_id INTEGER,
                        challenge_type TEXT,
                        parameters TEXT,
                        status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        winner_id INTEGER,
                        FOREIGN KEY (challenger_id) REFERENCES user_scores (user_id),
                        FOREIGN KEY (challenged_id) REFERENCES user_scores (user_id),
                        FOREIGN KEY (winner_id) REFERENCES user_scores (user_id)
                    )
                """)
                
                # Table des résultats de défi
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        challenge_id INTEGER,
                        user_id INTEGER,
                        questions_answered INTEGER DEFAULT 0,
                        correct_answers INTEGER DEFAULT 0,
                        stars_earned INTEGER DEFAULT 0,
                        completion_time INTEGER,
                        FOREIGN KEY (challenge_id) REFERENCES user_challenges (id),
                        FOREIGN KEY (user_id) REFERENCES user_scores (user_id)
                    )
                """)
                
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur initialisation tables défis: {e}")
    
    def create_challenge(self, challenger_id: int, challenged_id: int, 
                        challenge_type: str, parameters: Dict) -> Optional[int]:
        """Crée un nouveau défi."""
        try:
            if challenger_id == challenged_id:
                return None
            
            expires_at = datetime.now() + timedelta(hours=24)  # Expire dans 24h
            
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_challenges 
                    (challenger_id, challenged_id, challenge_type, parameters, status, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (challenger_id, challenged_id, challenge_type, 
                     json.dumps(parameters), ChallengeStatus.PENDING.value, expires_at))
                
                challenge_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"Défi créé: {challenge_id} entre {challenger_id} et {challenged_id}")
                return challenge_id
                
        except Exception as e:
            logger.error(f"Erreur création défi: {e}")
            return None
    
    def accept_challenge(self, challenge_id: int, user_id: int) -> bool:
        """Accepte un défi."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Vérifier que l'utilisateur peut accepter ce défi
                cursor.execute("""
                    SELECT challenged_id, status, expires_at FROM user_challenges 
                    WHERE id = ? AND challenged_id = ? AND status = ?
                """, (challenge_id, user_id, ChallengeStatus.PENDING.value))
                
                result = cursor.fetchone()
                if not result:
                    return False
                
                expires_at = datetime.strptime(result[2], '%Y-%m-%d %H:%M:%S')
                if datetime.now() > expires_at:
                    # Défi expiré
                    cursor.execute("""
                        UPDATE user_challenges SET status = ? WHERE id = ?
                    """, (ChallengeStatus.EXPIRED.value, challenge_id))
                    conn.commit()
                    return False
                
                # Accepter le défi
                cursor.execute("""
                    UPDATE user_challenges SET status = ? WHERE id = ?
                """, (ChallengeStatus.ACCEPTED.value, challenge_id))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Erreur acceptation défi {challenge_id}: {e}")
            return False
    
    def update_challenge_progress(self, challenge_id: int, user_id: int, 
                                is_correct: bool, stars_earned: int):
        """Met à jour le progrès d'un utilisateur dans un défi."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Vérifier si l'entrée existe
                cursor.execute("""
                    SELECT questions_answered, correct_answers, stars_earned 
                    FROM challenge_results 
                    WHERE challenge_id = ? AND user_id = ?
                """, (challenge_id, user_id))
                
                result = cursor.fetchone()
                
                if result:
                    # Mettre à jour
                    new_questions = result[0] + 1
                    new_correct = result[1] + (1 if is_correct else 0)
                    new_stars = result[2] + stars_earned
                    
                    cursor.execute("""
                        UPDATE challenge_results 
                        SET questions_answered = ?, correct_answers = ?, stars_earned = ?
                        WHERE challenge_id = ? AND user_id = ?
                    """, (new_questions, new_correct, new_stars, challenge_id, user_id))
                else:
                    # Créer nouvelle entrée
                    cursor.execute("""
                        INSERT INTO challenge_results 
                        (challenge_id, user_id, questions_answered, correct_answers, stars_earned)
                        VALUES (?, ?, 1, ?, ?)
                    """, (challenge_id, user_id, 1 if is_correct else 0, stars_earned))
                
                conn.commit()
                
                # Vérifier si le défi est terminé
                self._check_challenge_completion(challenge_id)
                
        except Exception as e:
            logger.error(f"Erreur mise à jour progrès défi {challenge_id}: {e}")
    
    def _check_challenge_completion(self, challenge_id: int):
        """Vérifie si un défi est terminé et détermine le gagnant."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                # Récupérer les paramètres du défi
                cursor.execute("""
                    SELECT challenge_type, parameters, challenger_id, challenged_id, status
                    FROM user_challenges WHERE id = ?
                """, (challenge_id,))
                
                challenge_data = cursor.fetchone()
                if not challenge_data or challenge_data[4] != ChallengeStatus.ACCEPTED.value:
                    return
                
                challenge_type, params_json, challenger_id, challenged_id, status = challenge_data
                parameters = json.loads(params_json)
                
                # Récupérer les résultats des deux participants
                cursor.execute("""
                    SELECT user_id, questions_answered, correct_answers, stars_earned
                    FROM challenge_results WHERE challenge_id = ?
                """, (challenge_id,))
                
                results = cursor.fetchall()
                user_results = {result[0]: result[1:] for result in results}
                
                # Vérifier les conditions de fin selon le type de défi
                if challenge_type == "quiz_race":
                    target_questions = parameters.get('target_questions', 10)
                    
                    # Vérifier si les deux ont terminé
                    challenger_done = challenger_id in user_results and user_results[challenger_id][0] >= target_questions
                    challenged_done = challenged_id in user_results and user_results[challenged_id][0] >= target_questions
                    
                    if challenger_done and challenged_done:
                        # Déterminer le gagnant (plus d'étoiles)
                        challenger_stars = user_results.get(challenger_id, (0,0,0))[2]
                        challenged_stars = user_results.get(challenged_id, (0,0,0))[2]
                        
                        winner_id = challenger_id if challenger_stars > challenged_stars else challenged_id
                        if challenger_stars == challenged_stars:
                            winner_id = None  # Égalité
                        
                        # Marquer comme terminé
                        cursor.execute("""
                            UPDATE user_challenges 
                            SET status = ?, completed_at = CURRENT_TIMESTAMP, winner_id = ?
                            WHERE id = ?
                        """, (ChallengeStatus.COMPLETED.value, winner_id, challenge_id))
                        
                        conn.commit()
                        
                        logger.info(f"Défi {challenge_id} terminé, gagnant: {winner_id}")
                
        except Exception as e:
            logger.error(f"Erreur vérification fin défi {challenge_id}: {e}")
    
    def get_user_challenges(self, user_id: int, status_filter: str = None) -> List[Dict]:
        """Récupère les défis d'un utilisateur."""
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                
                query = """
                    SELECT c.id, c.challenger_id, c.challenged_id, c.challenge_type, 
                           c.parameters, c.status, c.created_at, c.expires_at, c.winner_id,
                           u1.name as challenger_name, u2.name as challenged_name
                    FROM user_challenges c
                    JOIN user_scores u1 ON c.challenger_id = u1.user_id
                    JOIN user_scores u2 ON c.challenged_id = u2.user_id
                    WHERE (c.challenger_id = ? OR c.challenged_id = ?)
                """
                
                params = [user_id, user_id]
                
                if status_filter:
                    query += " AND c.status = ?"
                    params.append(status_filter)
                
                query += " ORDER BY c.created_at DESC"
                
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                challenges = []
                for result in results:
                    challenges.append({
                        'id': result[0],
                        'challenger_id': result[1],
                        'challenged_id': result[2],
                        'challenge_type': result[3],
                        'parameters': json.loads(result[4]),
                        'status': result[5],
                        'created_at': result[6],
                        'expires_at': result[7],
                        'winner_id': result[8],
                        'challenger_name': result[9],
                        'challenged_name': result[10],
                        'is_challenger': user_id == result[1]
                    })
                
                return challenges
                
        except Exception as e:
            logger.error(f"Erreur récupération défis utilisateur {user_id}: {e}")
            return []
    
    def get_challenge_display_text(self, user_id: int) -> str:
        """Génère le texte d'affichage des défis pour un utilisateur."""
        pending_challenges = self.get_user_challenges(user_id, ChallengeStatus.PENDING.value)
        active_challenges = self.get_user_challenges(user_id, ChallengeStatus.ACCEPTED.value)
        completed_challenges = self.get_user_challenges(user_id, ChallengeStatus.COMPLETED.value)[-5:]  # 5 derniers
        
        text = "⚔️ **VOS DÉFIS** ⚔️\n\n"
        
        if pending_challenges:
            text += "⏳ **DÉFIS EN ATTENTE**\n"
            for challenge in pending_challenges[:3]:
                if challenge['is_challenger']:
                    text += f"• Défi envoyé à {challenge['challenged_name']}\n"
                else:
                    text += f"• Défi reçu de {challenge['challenger_name']}\n"
                text += f"  Type: {challenge['challenge_type']}\n\n"
        
        if active_challenges:
            text += "🔥 **DÉFIS ACTIFS**\n"
            for challenge in active_challenges[:3]:
                opponent = challenge['challenged_name'] if challenge['is_challenger'] else challenge['challenger_name']
                text += f"• Contre {opponent}\n"
                text += f"  Type: {challenge['challenge_type']}\n\n"
        
        if completed_challenges:
            text += "🏆 **DERNIERS RÉSULTATS**\n"
            for challenge in completed_challenges:
                opponent = challenge['challenged_name'] if challenge['is_challenger'] else challenge['challenger_name']
                
                if challenge['winner_id'] == user_id:
                    result = "🎉 VICTOIRE"
                elif challenge['winner_id'] is None:
                    result = "🤝 ÉGALITÉ"
                else:
                    result = "😔 DÉFAITE"
                
                text += f"• {result} contre {opponent}\n"
        
        if not any([pending_challenges, active_challenges, completed_challenges]):
            text += "Aucun défi en cours.\n\n"
            text += "💡 Créez un défi avec /challenge @utilisateur"
        
        return text
