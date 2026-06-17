import os
import logging
import tempfile
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from pypdf import PdfReader, PdfWriter

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation States
WAITING_FILE, WAITING_PASSWORD = range(2)

# -------------------- Helper --------------------
def unlock_pdf_in_memory(input_data: bytes, password: str):
    reader = PdfReader(BytesIO(input_data))
    if reader.is_encrypted:
        result = reader.decrypt(password)
        if result == 0:
            raise ValueError("❌ මුරපදය වැරදියි!")
    writer = PdfWriter()
    writer.append(reader)
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output

# -------------------- Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🔓 PDF එක Unlock කරන්න", callback_data="unlock")],
        [InlineKeyboardButton("❓ උපකාරය", callback_data="help")]
    ]
    await update.message.reply_text(
        f"👋 **හලෝ {user.first_name}!**\n\nමම ඔබගේ Password-Protected PDF ගොනු වලින් ආරක්ෂාව ඉවත් කරන බොට් එකයි.\n\n🔐 ඔබට මුරපදය දැනගෙන සිටිය යුතුයි.\n\n👉 පහළ බොත්තම ඔබලා පටන් ගන්න.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "help":
        await query.edit_message_text(
            "📖 **මෙහෙයුම් උපදෙස්:**\n\n1️⃣ 'PDF එක Unlock කරන්න' ඔබන්න.\n2️⃣ ඔබගේ ආරක්ෂිත PDF ගොනුව එවන්න.\n3️⃣ එම PDF එකේ මුරපදය ටයිප් කරන්න.\n4️⃣ බොට් එක Unlock කරපු ගොනුව ආපසු එවයි.\n\n⚠️ **අවවාදය:** අනවසර PDF සඳහා මෙය භාවිතා නොකරන්න.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ආපසු", callback_data="back_to_main")]])
        )
    elif data == "back_to_main":
        await query.edit_message_text(
            "🏠 ප්‍රධාන මෙනුව",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔓 PDF එක Unlock කරන්න", callback_data="unlock")]])
        )
    elif data == "unlock":
        await query.edit_message_text(
            "📤 **කරුණාකර ඔබගේ PDF ගොනුව මෙහි එවන්න.**\n\n_(ගොනු විශාලත්වය 20MB ට අඩු විය යුතුය)_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ අවලංගු කරන්න", callback_data="cancel")]])
        )
        return WAITING_FILE
    elif data == "cancel":
        await query.edit_message_text("✅ කාර්යය අවලංගු කරන ලදී. /start ඔබන්න.")
        return ConversationHandler.END
    return ConversationHandler.END

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or document.mime_type != "application/pdf":
        await update.message.reply_text("⚠️ කරුණාකර **PDF** ගොනුවක් පමණක් එවන්න.", parse_mode="Markdown")
        return WAITING_FILE

    file = await context.bot.get_file(document.file_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        await file.download_to_drive(tmp_file.name)
        context.user_data['file_path'] = tmp_file.name
        context.user_data['file_name'] = document.file_name or "unlocked.pdf"

    await update.message.reply_text(
        f"✅ ගොනුව ලැබුණා!\n\n📄 ගොනුව: `{document.file_name}`\n📦 ප්‍රමාණය: `{document.file_size / 1024:.2f} KB`\n\n🔑 **කරුණාකර මෙම PDF එකේ මුරපදය ටයිප් කරන්න.**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ අවලංගු කරන්න", callback_data="cancel")]])
    )
    return WAITING_PASSWORD

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    file_path = context.user_data.get('file_path')
    original_name = context.user_data.get('file_name', 'document.pdf')

    if not file_path or not os.path.exists(file_path):
        await update.message.reply_text("❌ දෝෂයක්! /start ඔබන්න.")
        return ConversationHandler.END

    processing_msg = await update.message.reply_text("⏳ **PDF එක Unlock වෙමින්...**", parse_mode="Markdown")

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        unlocked_pdf = unlock_pdf_in_memory(file_bytes, password)
        base, ext = os.path.splitext(original_name)
        new_filename = f"{base}_unlocked{ext}"

        await update.message.reply_document(
            document=unlocked_pdf,
            filename=new_filename,
            caption="🎉 **PDF එක සාර්ථකව Unlock කරන ලදී!**",
            parse_mode="Markdown"
        )
        await processing_msg.delete()
        await update.message.reply_text(
            "🔁 නැවත PDF එකක් Unlock කිරීමට පහළ බොත්තම ඔබන්න.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔓 තවත් PDF එකක්", callback_data="unlock")]])
        )
    except ValueError as e:
        await processing_msg.delete()
        await update.message.reply_text(
            f"⚠️ {str(e)}\n\n🔑 නැවත මුරපදය ඇතුලත් කරන්න:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔑 නැවත මුරපදය", callback_data="retry_password")], [InlineKeyboardButton("❌ අවලංගු", callback_data="cancel")]])
        )
        return WAITING_PASSWORD
    except Exception as e:
        await processing_msg.delete()
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ තාක්ෂණික දෝෂයක්: `{str(e)}`", parse_mode="Markdown")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            context.user_data.pop('file_path', None)
    return ConversationHandler.END

async def retry_password_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔑 **නැවත මුරපදය ටයිප් කරන්න:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ අවලංගු කරන්න", callback_data="cancel")]])
    )
    return WAITING_PASSWORD

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_path = context.user_data.get('file_path')
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
        context.user_data.pop('file_path', None)
    await update.message.reply_text("🚫 අවලංගු කරන ලදී. /start", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 මුල් පිටුව", callback_data="back_to_main")]]))
    return ConversationHandler.END

# -------------------- Main --------------------
def main():
    # ⚠️ ඔබගේ Bot Token එක මෙතනට දාන්න (ආරක්ෂාව සඳහා පසුව .env භාවිතා කරන්න)
    TOKEN = "8341743742:AAFxmu3i2bUhvSFNSElLn700djcXVoE-P6I"  # <-- මෙය ඔබගේ Token

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^unlock$")],
        states={
            WAITING_FILE: [
                MessageHandler(filters.Document.ALL, receive_file),
                CallbackQueryHandler(button_callback, pattern="^cancel$")
            ],
            WAITING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password),
                CallbackQueryHandler(retry_password_callback, pattern="^retry_password$"),
                CallbackQueryHandler(button_callback, pattern="^cancel$")
            ],
        },
        fallbacks=[CommandHandler("start", start), CallbackQueryHandler(button_callback, pattern="^cancel$")],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(help|back_to_main|cancel|unlock)$"))
    app.add_handler(conv_handler)

    print("✅ Bot එක ක්‍රියාත්මකයි! (Press Ctrl+C to stop)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
