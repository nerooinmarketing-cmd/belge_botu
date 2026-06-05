import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import crud
from services import ocr as ocr_service
from config import STORAGE_PATH, MAX_PHOTOS_PER_BATCH

logger = logging.getLogger(__name__)

# Conversation states
(
    CHOOSING_DOC_TYPE,
    CHOOSING_PAYMENT,
    CHOOSING_ITEMS_MODE,
    COLLECTING_PHOTOS,
    CHOOSING_ACCOUNTANT,
) = range(10, 15)

DOC_TYPES = {
    "📥 Alış Fatura": "alis_fatura",
    "📥 Alış Fiş": "alis_fis",
    "📤 Satış Fatura": "satis_fatura",
    "📤 Satış Fiş": "satis_fis",
}

PAYMENT_TYPES = {
    "💵 Nakit": "Nakit",
    "💳 Kredi Kartı": "Kredi Kartı",
    "🏦 Havale": "Havale",
    "📋 Açık Hesap": "Açık Hesap",
}


async def start_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    client = await crud.get_client(user.id)
    if not client:
        await update.message.reply_text("❌ Kayıtlı mükellef değilsiniz.")
        return ConversationHandler.END

    accountants = await crud.get_client_accountants(client["id"])
    if not accountants:
        await update.message.reply_text("❌ Henüz bir muhasebeciye bağlı değilsiniz.")
        return ConversationHandler.END

    context.user_data["scan_client"] = client
    context.user_data["scan_photos"] = []

    keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("📥 Alış Fatura"), KeyboardButton("📥 Alış Fiş")],
            [KeyboardButton("📤 Satış Fatura"), KeyboardButton("📤 Satış Fiş")],
            [KeyboardButton("❌ İptal")],
        ],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "📋 Belge türünü seçin:",
        reply_markup=keyboard,
    )
    return CHOOSING_DOC_TYPE


async def doc_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text not in DOC_TYPES:
        await update.message.reply_text("❌ Lütfen listeden seçin.")
        return CHOOSING_DOC_TYPE

    context.user_data["doc_type"] = DOC_TYPES[text]
    context.user_data["doc_type_label"] = text

    # Fatura ise kalem seçeneği sor
    if "fatura" in DOC_TYPES[text]:
        keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton("📋 Tüm Kalemleri Ekle"), KeyboardButton("📊 Sadece Özet")],
                [KeyboardButton("❌ İptal")],
            ],
            resize_keyboard=True,
        )
        await update.message.reply_text(
            "Fatura kalemlerini nasıl ekleyelim?",
            reply_markup=keyboard,
        )
        return CHOOSING_ITEMS_MODE

    return await ask_payment(update, context)


async def items_mode_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["include_items"] = 1 if "Tüm" in text else 0
    return await ask_payment(update, context)


async def ask_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("💵 Nakit"), KeyboardButton("💳 Kredi Kartı")],
            [KeyboardButton("🏦 Havale"), KeyboardButton("📋 Açık Hesap")],
            [KeyboardButton("❌ İptal")],
        ],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "💰 Ödeme türünü seçin:",
        reply_markup=keyboard,
    )
    return CHOOSING_PAYMENT


async def payment_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text not in PAYMENT_TYPES:
        await update.message.reply_text("❌ Lütfen listeden seçin.")
        return CHOOSING_PAYMENT

    context.user_data["payment_type"] = PAYMENT_TYPES[text]

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("✅ Bitti"), KeyboardButton("❌ İptal")]],
        resize_keyboard=True,
    )
    doc_label = context.user_data.get("doc_type_label", "Belge")
    payment_label = text
    await update.message.reply_text(
        f"📸 *{doc_label}* — {payment_label}\n\n"
        f"Fotoğraf çekin veya galeriden seçin (max {MAX_PHOTOS_PER_BATCH} adet).\n"
        "Tümünü gönderdikten sonra ✅ *Bitti* tuşuna basın.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return COLLECTING_PHOTOS


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photos = context.user_data.get("scan_photos", [])
    if len(photos) >= MAX_PHOTOS_PER_BATCH:
        await update.message.reply_text(f"⚠️ Max {MAX_PHOTOS_PER_BATCH} belge.")
        return COLLECTING_PHOTOS

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{update.effective_user.id}_{timestamp}.jpg"
    file_path = os.path.join(STORAGE_PATH, filename)
    await file.download_to_drive(file_path)

    photos.append({"file_path": file_path, "telegram_file_id": photo.file_id})
    context.user_data["scan_photos"] = photos
    await update.message.reply_text(f"✅ Alındı ({len(photos)}/{MAX_PHOTOS_PER_BATCH})")
    return COLLECTING_PHOTOS


async def scan_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photos = context.user_data.get("scan_photos", [])
    if not photos:
        await update.message.reply_text("⚠️ Henüz fotoğraf göndermediniz.")
        return COLLECTING_PHOTOS

    client = context.user_data.get("scan_client")
    accountants = await crud.get_client_accountants(client["id"])

    if len(accountants) == 1:
        context.user_data["chosen_accountant"] = accountants[0]
        return await process_documents(update, context)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(a.get("full_name", f"Muhasebeci #{a['id']}"), callback_data=f"acc_pick:{a['id']}")]
        for a in accountants
    ])
    await update.message.reply_text("Bu belgeleri kime göndermek istiyorsunuz?", reply_markup=keyboard)
    context.user_data["scan_accountants_map"] = {str(a["id"]): a for a in accountants}
    return CHOOSING_ACCOUNTANT


async def accountant_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acc_id = query.data.split(":")[1]
    chosen = context.user_data.get("scan_accountants_map", {}).get(acc_id)
    if not chosen:
        await query.message.reply_text("❌ Seçim hatası.")
        return ConversationHandler.END
    context.user_data["chosen_accountant"] = chosen
    return await process_documents(update, context)


async def process_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.start import client_main_menu
    msg = update.message or (update.callback_query and update.callback_query.message)

    photos = context.user_data.get("scan_photos", [])
    client = context.user_data.get("scan_client")
    accountant = context.user_data.get("chosen_accountant")
    doc_type = context.user_data.get("doc_type", "alis_fis")
    payment_type = context.user_data.get("payment_type", "")
    include_items = context.user_data.get("include_items", 0)
    client_name = client.get("full_name") or "Mükellef"

    wait_msg = await msg.reply_text("⏳ Belgeler işleniyor...")

    batch_id = await crud.create_batch(client["id"], accountant["id"])
    await crud.update_batch_status(batch_id, "processing")

    for photo in photos:
        doc_id = await crud.add_document(
            batch_id, photo["file_path"], photo["telegram_file_id"],
            doc_type=doc_type, payment_type=payment_type, include_items=include_items
        )
        try:
            result = await ocr_service.analyze_document(photo["file_path"], doc_type)
            await crud.update_document_ocr(doc_id, result)

            # Cari kaydet
            firma = result.get("firma_adi")
            vergi_no = result.get("vergi_no")
            if firma:
                await crud.upsert_company(client["id"], accountant["id"], firma, vergi_no)
        except Exception as e:
            logger.error(f"OCR error: {e}")
            await crud.update_document_ocr(doc_id, {"notlar": f"OCR hatası: {str(e)}"})

    await crud.update_batch_status(batch_id, "done")

    try:
        doc_label = context.user_data.get("doc_type_label", "Belge")
        await context.bot.send_message(
            chat_id=accountant["telegram_id"],
            text=(
                f"📬 *Yeni Belge Geldi*\n\n"
                f"👤 Mükellef: {client_name}\n"
                f"📄 Tür: {doc_label}\n"
                f"💰 Ödeme: {payment_type}\n"
                f"📋 Adet: {len(photos)}\n\n"
                f"Panelden görüntülemek için /panel"
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Bildirim hatası: {e}")

    await wait_msg.edit_text(
        f"✅ {len(photos)} belge muhasebeciye iletildi.",
        reply_markup=client_main_menu(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.start import client_main_menu
    for p in context.user_data.get("scan_photos", []):
        try:
            if os.path.exists(p["file_path"]):
                os.remove(p["file_path"])
        except Exception:
            pass
    context.user_data.clear()
    await update.message.reply_text("❌ İptal edildi.", reply_markup=client_main_menu())
    return ConversationHandler.END


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    client = await crud.get_client(user.id)
    if not client:
        await update.message.reply_text("❌ Kayıtlı mükellef değilsiniz.")
        return

    history = await crud.get_client_history(client["id"], limit=10)
    if not history:
        await update.message.reply_text("Henüz belge göndermediniz.")
        return

    lines = []
    for batch in history:
        status_map = {"done": "✅", "processing": "⏳", "error": "❌", "pending": "🔄"}
        emoji = status_map.get(batch.get("status"), "❓")
        date = batch.get("created_at", "")[:16].replace("T", " ")
        count = batch.get("doc_count", 0)
        lines.append(f"{emoji} {date} — {count} belge")

    await update.message.reply_text(
        "📋 *Son 10 Gönderiminiz*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )
