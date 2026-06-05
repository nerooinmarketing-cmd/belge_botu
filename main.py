import logging
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, API_PORT
from database.models import init_db
from handlers import start as start_handler
from handlers import accountant as accountant_handler
from handlers import documents as documents_handler
from api.panel import router as panel_router

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── TELEGRAM BOT ─────────────────────────────────────────────

def build_bot() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    registration_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start_handler.start)],
        states={
            start_handler.ASK_ROLE: [
                CallbackQueryHandler(start_handler.role_chosen, pattern="^role_")
            ],
            start_handler.ACC_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, start_handler.acc_name)
            ],
            start_handler.ACC_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, start_handler.acc_phone)
            ],
            start_handler.CLIENT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, start_handler.client_name)
            ],
        },
        fallbacks=[CommandHandler("start", start_handler.start)],
        per_message=False,
    )

    scan_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📄 Belge Tara$"), documents_handler.start_scan)
        ],
        states={
            documents_handler.CHOOSING_DOC_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, documents_handler.doc_type_chosen),
            ],
            documents_handler.CHOOSING_ITEMS_MODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, documents_handler.items_mode_chosen),
            ],
            documents_handler.CHOOSING_PAYMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, documents_handler.payment_chosen),
            ],
            documents_handler.COLLECTING_PHOTOS: [
                MessageHandler(filters.PHOTO, documents_handler.receive_photo),
                MessageHandler(filters.Regex("^✅ Bitti$"), documents_handler.scan_done),
                MessageHandler(filters.Regex("^❌ İptal$"), documents_handler.cancel_scan),
            ],
            documents_handler.CHOOSING_ACCOUNTANT: [
                CallbackQueryHandler(documents_handler.accountant_chosen, pattern="^acc_pick:")
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ İptal$"), documents_handler.cancel_scan),
            CommandHandler("start", start_handler.start),
        ],
        per_message=False,
    )

    # Accountant commands
    app.add_handler(CommandHandler("panel", accountant_handler.open_panel))
    app.add_handler(MessageHandler(filters.Regex("^🔗 Davet Linki Oluştur$"), accountant_handler.create_invite_link))
    app.add_handler(MessageHandler(filters.Regex("^📋 Linklerim$"), accountant_handler.list_links))
    app.add_handler(MessageHandler(filters.Regex("^👥 Mükelleflerim$"), accountant_handler.list_clients))
    app.add_handler(CallbackQueryHandler(accountant_handler.deactivate_link_callback, pattern="^deactivate:"))

    # Client commands
    app.add_handler(MessageHandler(filters.Regex("^📋 Geçmişim$"), documents_handler.show_history))

    # Conversations
    app.add_handler(registration_conv)
    app.add_handler(scan_conv)

    return app


# ─── FASTAPI ──────────────────────────────────────────────────

bot_app: Application = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_app
    await init_db()
    logger.info("Veritabanı hazır.")

    bot_app = build_bot()
    await bot_app.initialize()
    await bot_app.start()

    # Start polling in background
    asyncio.create_task(_run_polling())
    logger.info("Telegram bot başlatıldı.")

    yield

    await bot_app.stop()
    await bot_app.shutdown()


async def _run_polling():
    await bot_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)


api = FastAPI(title="Belge Botu API", lifespan=lifespan)

# Static files (panel.html)
api.mount("/static", StaticFiles(directory="static"), name="static")

# Panel route
@api.get("/panel")
async def panel_page():
    return FileResponse("static/panel.html")

# API routes
api.include_router(panel_router)


# ─── ENTRY POINT ──────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:api",
        host="0.0.0.0",
        port=API_PORT,
        log_level="info",
    )
