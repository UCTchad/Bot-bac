
import logging
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

logger = logging.getLogger(__name__)

class PDFManager:
    def __init__(self):
        # Configuration du canal privé (remplacez par votre ID de canal)
        self.private_channel_id = --1002614940882  # Exemple - remplacez par votre canal
        
        # PDF organisés par série avec message_id et file_unique_id
        self.pdfs = {
            # Matières communes à toutes les séries (A4)
            "A4": {
                "name": "📚 Série A4 (Littéraire)",
                "emoji": "📚",
                "subjects": {
                    "Anglais": {
                        "emoji": "🇬🇧",
                        "message_id": 123,  # ID du message dans le canal
                        "file_unique_id": "AgACAgQAAxkBAAIBGmiPb-WXb0FwILVRtw-7hCBI_c4sAAIEGQACash5UAXlb1z4tTIcNgQ",
                        "file_id": "BQACAgQAAxkBAAIBGmiPb-WXb0FwILVRtw-7hCBI_c4sAAIEGQACash5UAXlb1z4tTIcNgQ"  # Backup
                    },
                    "Français": {
                        "emoji": "🇫🇷", 
                        "message_id": 124,
                        "file_unique_id": "AgACAgQAAxkBAAIBHGiPcAkzDBkvKu29rCoxMzoVqKF9AAIFGQACash5UKYm6RtdlfeVNgQ",
                        "file_id": "BQACAgQAAxkBAAIBHGiPcAkzDBkvKu29rCoxMzoVqKF9AAIFGQACash5UKYm6RtdlfeVNgQ"
                    },
                    "Géographie": {
                        "emoji": "🌍",
                        "message_id": 125,
                        "file_unique_id": "AgACAgQAAxkBAAIBHmiPcBPvMXRhpgHTmZ9UxnS-5OxNAAIGGQACash5UHyWRteq5IBKNgQ",
                        "file_id": "BQACAgQAAxkBAAIBHmiPcBPvMXRhpgHTmZ9UxnS-5OxNAAIGGQACash5UHyWRteq5IBKNgQ"
                    },
                    "Histoire": {
                        "emoji": "🏛️",
                        "message_id": 126,
                        "file_unique_id": "AgACAgQAAxkBAAIBIGiPcD3w2N9zt4XaAdcdV14PKbZSAAIHGQACash5UOcZijTbLN3tNgQ",
                        "file_id": "BQACAgQAAxkBAAIBIGiPcD3w2N9zt4XaAdcdV14PKbZSAAIHGQACash5UOcZijTbLN3tNgQ"
                    },
                    "Mathématiques": {
                        "emoji": "🔢",
                        "message_id": 127,
                        "file_unique_id": "AgACAgQAAxkBAAIBIWiPcD_c6aq32jmWxLk6-l-q9m1qAAIIGQACash5UGJLz3X_N7bwNgQ",
                        "file_id": "BQACAgQAAxkBAAIBIWiPcD_c6aq32jmWxLk6-l-q9m1qAAIIGQACash5UGJLz3X_N7bwNgQ"
                    },
                    "Philosophie": {
                        "emoji": "🤔",
                        "message_id": 128,
                        "file_unique_id": "AgACAgQAAxkBAAIBImiPcEBe2QJvSDVe-F9ABb5oD0h7AAIJGQACash5UGvpOcX8oaoZNgQ",
                        "file_id": "BQACAgQAAxkBAAIBImiPcEBe2QJvSDVe-F9ABb5oD0h7AAIJGQACash5UGvpOcX8oaoZNgQ"
                    }
                }
            },
            
            # Série D (Sciences)
            "D": {
                "name": "🔬 Série D (Scientifique)",
                "emoji": "🔬",
                "subjects": {
                    "Chimie": {
                        "emoji": "⚗️",
                        "message_id": 129,
                        "file_unique_id": "AgACAgQAAxkBAAIBJ2iPcVnWm-8iXszDGFI3W9cFOQazAAIKGQACash5ULb_gO5GGj-UNgQ",
                        "file_id": "BQACAgQAAxkBAAIBJ2iPcVnWm-8iXszDGFI3W9cFOQazAAIKGQACash5ULb_gO5GGj-UNgQ"
                    },
                    "Physique": {
                        "emoji": "⚡",
                        "message_id": 130,
                        "file_unique_id": "AgACAgQAAxkBAAIBK2iPcWO089qT7wek90c-3kXR1E1dAAIMGQACash5UG-2K3OxsxfDNgQ",
                        "file_id": "BQACAgQAAxkBAAIBK2iPcWO089qT7wek90c-3kXR1E1dAAIMGQACash5UG-2K3OxsxfDNgQ"
                    },
                    "Mathématiques": {
                        "emoji": "📐",
                        "message_id": 131,
                        "file_unique_id": "AgACAgQAAxkBAAIBKWiPcWB3eV2aCR0IscsOz8WqqPbVAAILGQACash5UN47hadSyqw6NgQ",
                        "file_id": "BQACAgQAAxkBAAIBKWiPcWB3eV2aCR0IscsOz8WqqPbVAAILGQACash5UN47hadSyqw6NgQ"
                    },
                    "SVT": {
                        "emoji": "🧬",
                        "message_id": 132,
                        "file_unique_id": "AgACAgQAAxkBAAIBM2iPeOkdmtFXiJAMBPgxhq0KNBC3AAIVGQACash5UD6RIMb9IcNINgQ",
                        "file_id": "BQACAgQAAxkBAAIBM2iPeOkdmtFXiJAMBPgxhq0KNBC3AAIVGQACash5UD6RIMb9IcNINgQ"
                    }
                }
            },
            
            # Série C (Mathématiques)
            "C": {
                "name": "📊 Série C (Scientifique)",
                "emoji": "📊",
                "subjects": {
                    "Chimie": {
                        "emoji": "⚗️",
                        "message_id": 133,
                        "file_unique_id": "AgACAgQAAxkBAAIBLWiPctavLyBC2erR8H172rfrUT39AAIPGQACash5UPnJ_tDqQb8UNgQ",
                        "file_id": "BQACAgQAAxkBAAIBLWiPctavLyBC2erR8H172rfrUT39AAIPGQACash5UPnJ_tDqQb8UNgQ"
                    },
                    "Mathématiques": {
                        "emoji": "∞",
                        "message_id": 134,
                        "file_unique_id": "AgACAgQAAxkBAAIBLmiPcti0IxKobuwdGeVW7q3XwvNhAAIQGQACash5UHEPlNrdeKlCNgQ",
                        "file_id": "BQACAgQAAxkBAAIBLmiPcti0IxKobuwdGeVW7q3XwvNhAAIQGQACash5UHEPlNrdeKlCNgQ"
                    },
                    "Physique": {
                        "emoji": "⚡",
                        "message_id": 135,
                        "file_unique_id": "AgACAgQAAxkBAAIBL2iPctn5rB72kIjs_y5fZnfB0LhqAAIRGQACash5UDJFPlefY3N_NgQ",
                        "file_id": "BQACAgQAAxkBAAIBL2iPctn5rB72kIjs_y5fZnfB0LhqAAIRGQACash5UDJFPlefY3N_NgQ"
                    },
                    "SVT": {
                        "emoji": "🧬",
                        "message_id": 136,
                        "file_unique_id": "AgACAgQAAxkBAAIBM2iPeOkdmtFXiJAMBPgxhq0KNBC3AAIVGQACash5UD6RIMb9IcNINgQ",
                        "file_id": "BQACAgQAAxkBAAIBM2iPeOkdmtFXiJAMBPgxhq0KNBC3AAIVGQACash5UD6RIMb9IcNINgQ"
                    }
                }
            }
        }

    def get_pdf_series_keyboard(self):
        """Retourne le clavier de sélection des séries."""
        keyboard = []
        for serie_key, serie_info in self.pdfs.items():
            keyboard.append([InlineKeyboardButton(
                f"{serie_info['emoji']} {serie_info['name']}", 
                callback_data=f"pdf_serie_{serie_key}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Retour Menu", callback_data="back_menu")])
        return InlineKeyboardMarkup(keyboard)

    def get_pdf_subjects_keyboard(self, serie: str):
        """Retourne le clavier des matières pour une série."""
        if serie not in self.pdfs:
            return None
            
        serie_info = self.pdfs[serie]
        keyboard = []
        
        # Ajouter les matières par rangées de 2
        subjects = list(serie_info['subjects'].items())
        for i in range(0, len(subjects), 2):
            row = []
            for j in range(2):
                if i + j < len(subjects):
                    subject_key, subject_info = subjects[i + j]
                    # Utiliser | comme séparateur au lieu de _
                    row.append(InlineKeyboardButton(
                        f"{subject_info['emoji']} {subject_key}",
                        callback_data=f"pdf_download|{serie}|{subject_key}"
                    ))
            keyboard.append(row)
        
        keyboard.append([
            InlineKeyboardButton("📥 Télécharger Tout", callback_data=f"pdf_download_all|{serie}"),
            InlineKeyboardButton("🔙 Retour Séries", callback_data="menu_pdfs")
        ])
        
        return InlineKeyboardMarkup(keyboard)

    async def send_pdf_menu(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le menu principal des PDF."""
        menu_text = (
            "📚 **BIBLIOTHÈQUE DE COURS PDF** 📚\n\n"
            "🎓 **Choisissez votre série d'étude :**\n\n"
            "📚 **Série A4** : Matières communes (Français, Anglais, etc.)\n"
            "🔬 **Série D** : Sciences expérimentales\n"
            "📊 **Série C** : Mathématiques et sciences\n\n"
            "💡 **Tous les PDF sont gratuits et accessibles 24h/24 !**"
        )
        
        await query.edit_message_text(
            menu_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.get_pdf_series_keyboard()
        )

    async def send_serie_subjects(self, query, context: ContextTypes.DEFAULT_TYPE, serie: str):
        """Affiche les matières d'une série."""
        if serie not in self.pdfs:
            await query.edit_message_text("❌ Série non trouvée.")
            return
            
        serie_info = self.pdfs[serie]
        
        subjects_text = (
            f"{serie_info['emoji']} **{serie_info['name']}**\n\n"
            f"📖 **Matières disponibles :**\n\n"
        )
        
        for subject, info in serie_info['subjects'].items():
            subjects_text += f"{info['emoji']} **{subject}** - PDF de cours complet\n"
        
        subjects_text += (
            f"\n💡 **Cliquez sur une matière pour télécharger**\n"
            f"📥 **Ou téléchargez tout d'un coup !**"
        )
        
        await query.edit_message_text(
            subjects_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.get_pdf_subjects_keyboard(serie)
        )

    

    async def send_pdf(self, query, context: ContextTypes.DEFAULT_TYPE, serie: str, subject: str):
        """Envoie un PDF spécifique."""
        try:
            if serie not in self.pdfs or subject not in self.pdfs[serie]['subjects']:
                await query.edit_message_text("❌ PDF non trouvé.")
                return
            
            pdf_info = self.pdfs[serie]['subjects'][subject]
            serie_info = self.pdfs[serie]
            
            # Message de confirmation
            await query.edit_message_text(
                f"📤 **Envoi en cours...**\n\n"
                f"{pdf_info['emoji']} **{subject}** - {serie_info['name']}\n"
                f"⏳ Récupération du fichier...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Récupérer le message_id et file_id
            message_id = pdf_info.get('message_id')
            file_id = pdf_info.get('file_id')
            
            # Essayer de copier le message depuis le canal
            if message_id:
                try:
                    await context.bot.copy_message(
                        chat_id=query.message.chat_id,
                        from_chat_id=self.private_channel_id,
                        message_id=message_id
                    )
                    
                    await self.send_serie_subjects(query, context, serie)
                    logger.info(f"PDF {subject} copié avec succès")
                    return
                    
                except Exception as copy_error:
                    logger.warning(f"Copie échouée pour {subject}: {copy_error}")
            
            # Si la copie échoue, utiliser le file_id
            if file_id:
                try:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=file_id,
                        caption=(
                            f"{pdf_info['emoji']} **Cours de {subject}**\n"
                            f"📚 {serie_info['name']}\n\n"
                            f"📖 Bon apprentissage ! 🎓"
                        ),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    await self.send_serie_subjects(query, context, serie)
                    logger.info(f"PDF {subject} envoyé par file_id")
                    return
                    
                except Exception as send_error:
                    logger.error(f"Erreur envoi PDF {subject}: {send_error}")
            
            # Si tout échoue
            await query.edit_message_text(
                f"❌ **Impossible d'envoyer le fichier**\n\n"
                f"{pdf_info['emoji']} **{subject}** - {serie_info['name']}\n\n"
                f"Réessayez dans quelques instants.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Réessayer", callback_data=f"pdf_download|{serie}|{subject}"),
                    InlineKeyboardButton("🔙 Retour", callback_data=f"pdf_serie_{serie}")
                ]])
            )
            
        except Exception as e:
            logger.error(f"Erreur envoi PDF {subject}: {e}")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Erreur lors de l'envoi du PDF."
            )

    async def send_all_pdfs(self, query, context: ContextTypes.DEFAULT_TYPE, serie: str):
        """Envoie tous les PDF d'une série."""
        try:
            if serie not in self.pdfs:
                await query.edit_message_text("❌ Série non trouvée.")
                return
            
            serie_info = self.pdfs[serie]
            
            await query.edit_message_text(
                f"📤 **Envoi de tous les PDF...**\n\n"
                f"{serie_info['emoji']} **{serie_info['name']}**\n"
                f"📚 {len(serie_info['subjects'])} cours en cours d'envoi...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            sent_count = 0
            
            # Envoyer chaque PDF
            for subject, pdf_info in serie_info['subjects'].items():
                try:
                    message_id = pdf_info.get('message_id')
                    file_id = pdf_info.get('file_id')
                    
                    # Essayer de copier depuis le canal
                    if message_id:
                        try:
                            await context.bot.copy_message(
                                chat_id=query.message.chat_id,
                                from_chat_id=self.private_channel_id,
                                message_id=message_id
                            )
                            sent_count += 1
                            continue
                        except:
                            pass
                    
                    # Utiliser le file_id
                    if file_id:
                        try:
                            await context.bot.send_document(
                                chat_id=query.message.chat_id,
                                document=file_id,
                                caption=f"{pdf_info['emoji']} **{subject}** - {serie_info['name']}",
                                parse_mode=ParseMode.MARKDOWN
                            )
                            sent_count += 1
                        except:
                            pass
                        
                except:
                    pass
            
            # Message de confirmation
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    f"✅ **{sent_count} fichiers envoyés**\n\n"
                    f"{serie_info['emoji']} **{serie_info['name']}**\n\n"
                    f"🎓 **Bon apprentissage !**"
                ),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Retourner au menu des matières
            await self.send_serie_subjects(query, context, serie)
            
        except Exception as e:
            logger.error(f"Erreur envoi groupé: {e}")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Erreur lors de l'envoi groupé."
            )

    def parse_callback_data(self, callback_data: str):
        """Parse les données callback avec le nouveau format utilisant |."""
        try:
            if callback_data.startswith("pdf_download_all|"):
                serie = callback_data.replace("pdf_download_all|", "")
                return "download_all", serie, None
            elif callback_data.startswith("pdf_download|"):
                parts = callback_data.replace("pdf_download|", "").split("|", 1)
                if len(parts) == 2:
                    serie, subject = parts
                    return "download", serie, subject
            elif callback_data.startswith("pdf_serie_"):
                serie = callback_data.replace("pdf_serie_", "")
                return "serie", serie, None
                
            return None, None, None
        except Exception as e:
            logger.error(f"Erreur parsing callback_data {callback_data}: {e}")
            return None, None, None
