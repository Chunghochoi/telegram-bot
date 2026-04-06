import os
import asyncio
import logging
import json
from pathlib import Path
from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from langchain_openai import ChatOpenAI
from browser_use import Agent, Controller
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import BrowserContext
from browser_use.agent.views import ActionResult

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o")

EXT_DIR = Path(__file__).parent / "extensions" / "rektCaptcha"
PREFS_FILE = Path(__file__).parent / "user_prefs.json"

DEFAULT_TEMP_MAIL = "https://temp-mail.org"
DEFAULT_TEMP_SMS = "https://receive-smss.com"

captcha_queues: dict[int, asyncio.Queue] = {}
running_tasks: dict[int, bool] = {}


def load_prefs() -> dict:
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text())
        except Exception:
            pass
    return {}


def save_prefs(prefs: dict) -> None:
    PREFS_FILE.write_text(json.dumps(prefs, indent=2, ensure_ascii=False))


def get_user_pref(user_id: int, key: str, default: str) -> str:
    prefs = load_prefs()
    return prefs.get(str(user_id), {}).get(key, default)


def set_user_pref(user_id: int, key: str, value: str) -> None:
    prefs = load_prefs()
    uid = str(user_id)
    if uid not in prefs:
        prefs[uid] = {}
    prefs[uid][key] = value
    save_prefs(prefs)


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=OPENROUTER_MODEL,
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
    )


def build_browser() -> Browser:
    args = []
    if EXT_DIR.exists():
        ext_path = str(EXT_DIR.resolve())
        args += [
            f"--load-extension={ext_path}",
            f"--disable-extensions-except={ext_path}",
        ]
        logger.info("rektCaptcha extension loaded from %s", ext_path)
    else:
        logger.warning("Extension not found at %s, running without reCAPTCHA solver", EXT_DIR)
    return Browser(config=BrowserConfig(extra_chromium_args=args))


def build_controller(user_id: int, bot, chat_id: int) -> Controller:
    controller = Controller()

    @controller.action(
        "Take a screenshot of the current page and send it to the user on Telegram to manually solve a CAPTCHA or verification challenge. Wait for the user reply before continuing.",
    )
    async def ask_user_captcha(reason: str, browser: BrowserContext) -> ActionResult:
        page = await browser.get_current_page()
        screenshot = await page.screenshot(type="png")
        caption = (
            f"⚠️ Cần giải CAPTCHA thủ công!\n\n"
            f"Lý do: {reason}\n\n"
            f"Hãy nhìn vào ảnh và gõ đáp án (hoặc mô tả những gì bạn thấy) để bot tiếp tục."
        )
        await bot.send_photo(chat_id=chat_id, photo=screenshot, caption=caption)

        queue: asyncio.Queue = asyncio.Queue()
        captcha_queues[user_id] = queue
        try:
            answer = await asyncio.wait_for(queue.get(), timeout=300)
        except asyncio.TimeoutError:
            del captcha_queues[user_id]
            return ActionResult(
                extracted_content="User did not respond to CAPTCHA within 5 minutes. Skip this step or try another approach.",
                error="CAPTCHA timeout",
            )
        captcha_queues.pop(user_id, None)
        return ActionResult(extracted_content=f"User's CAPTCHA answer: {answer}")

    @controller.action(
        "Get the URL of the user's configured temporary email service to obtain a disposable email address.",
    )
    async def get_temp_mail_url() -> ActionResult:
        url = get_user_pref(user_id, "temp_mail_url", DEFAULT_TEMP_MAIL)
        return ActionResult(
            extracted_content=(
                f"Temporary email service URL: {url}\n"
                "Navigate there to get a disposable email address. "
                "Look for the generated email address shown on the page."
            )
        )

    @controller.action(
        "Get the URL of the user's configured temporary SMS service to obtain a disposable phone number for OTP verification.",
    )
    async def get_temp_sms_url() -> ActionResult:
        url = get_user_pref(user_id, "temp_sms_url", DEFAULT_TEMP_SMS)
        return ActionResult(
            extracted_content=(
                f"Temporary SMS service URL: {url}\n"
                "Navigate there to get a disposable phone number. "
                "Find an available number, use it for registration, then return here to read the incoming OTP."
            )
        )

    return controller


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Xin chào! Tôi là bot điều khiển trình duyệt tự động.\n\n"
        "Lệnh có thể dùng:\n"
        "/task <yêu cầu> — Giao việc cho trình duyệt\n"
        "/setmail <url> — Đặt trang email tạm thời\n"
        "/setsms <url>  — Đặt trang số điện thoại tạm thời\n"
        "/settings — Xem cài đặt hiện tại\n"
        "/help — Hướng dẫn chi tiết"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hướng dẫn sử dụng:\n\n"
        "/task <yêu cầu>\n"
        "  Bot sẽ mở trình duyệt và thực hiện yêu cầu.\n"
        "  Ví dụ:\n"
        "  • /task Đăng ký tài khoản GitHub với email tạm\n"
        "  • /task Tìm 5 tin tức AI mới nhất trên Google\n"
        "  • /task Điền form liên hệ tại example.com\n\n"
        "/setmail <url>\n"
        "  Đặt trang web cung cấp email tạm thời.\n"
        "  Mặc định: https://temp-mail.org\n"
        "  Ví dụ: /setmail https://guerrillamail.com\n\n"
        "/setsms <url>\n"
        "  Đặt trang web cung cấp số điện thoại tạm thời.\n"
        "  Mặc định: https://receive-smss.com\n"
        "  Ví dụ: /setsms https://sms24.me\n\n"
        "/settings — Xem cài đặt hiện tại\n\n"
        "Khi gặp CAPTCHA:\n"
        "  • reCAPTCHA → Tự giải tự động qua extension\n"
        "  • CAPTCHA khác → Bot gửi ảnh cho bạn giải\n"
        "  • Email xác minh → Bot tự vào trang email tạm\n"
        "  • OTP SMS → Bot tự vào trang số điện thoại tạm"
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    mail = get_user_pref(user_id, "temp_mail_url", DEFAULT_TEMP_MAIL)
    sms = get_user_pref(user_id, "temp_sms_url", DEFAULT_TEMP_SMS)
    await update.message.reply_text(
        f"Cài đặt của bạn:\n\n"
        f"Email tạm: {mail}\n"
        f"SMS tạm:   {sms}\n\n"
        f"Model AI:  {OPENROUTER_MODEL}"
    )


async def setmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Vui lòng cung cấp URL.\n"
            "Ví dụ: /setmail https://temp-mail.org"
        )
        return
    url = context.args[0]
    if not url.startswith("http"):
        await update.message.reply_text("URL không hợp lệ. Phải bắt đầu bằng http:// hoặc https://")
        return
    set_user_pref(update.effective_user.id, "temp_mail_url", url)
    await update.message.reply_text(f"Đã lưu trang email tạm: {url}")


async def setsms_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Vui lòng cung cấp URL.\n"
            "Ví dụ: /setsms https://receive-smss.com"
        )
        return
    url = context.args[0]
    if not url.startswith("http"):
        await update.message.reply_text("URL không hợp lệ. Phải bắt đầu bằng http:// hoặc https://")
        return
    set_user_pref(update.effective_user.id, "temp_sms_url", url)
    await update.message.reply_text(f"Đã lưu trang SMS tạm: {url}")


async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Vui lòng cung cấp yêu cầu sau lệnh /task.\n"
            "Ví dụ: /task Đăng ký tài khoản tại github.com"
        )
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if running_tasks.get(user_id):
        await update.message.reply_text(
            "Bạn đang có một tác vụ đang chạy. Vui lòng chờ nó hoàn thành."
        )
        return

    user_task = " ".join(context.args)
    user_name = update.effective_user.first_name or "bạn"

    await update.message.reply_text(
        f"Bắt đầu xử lý yêu cầu của {user_name}:\n{user_task}\n\n"
        "Bot đang điều khiển trình duyệt. Nếu gặp CAPTCHA, tôi sẽ gửi ảnh cho bạn giải."
    )

    running_tasks[user_id] = True
    try:
        llm = build_llm()
        browser = build_browser()
        controller = build_controller(user_id, context.bot, chat_id)

        agent = Agent(
            task=user_task,
            llm=llm,
            browser=browser,
            controller=controller,
        )

        result = await agent.run()

        await browser.close()

        result_text = str(result) if result else "Hoàn thành nhưng không có kết quả trả về."
        if len(result_text) > 4000:
            result_text = result_text[:4000] + "\n...(kết quả bị cắt bớt)"

        await update.message.reply_text(f"Kết quả:\n{result_text}")

    except Exception as e:
        logger.error("Lỗi agent user %s: %s", user_id, e, exc_info=True)
        await update.message.reply_text(f"Đã xảy ra lỗi:\n{e}")
    finally:
        running_tasks.pop(user_id, None)
        captcha_queues.pop(user_id, None)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if user_id in captcha_queues:
        answer = update.message.text or update.message.caption or ""
        await captcha_queues[user_id].put(answer)
        await update.message.reply_text("Đã nhận đáp án. Bot đang tiếp tục xử lý...")
        return

    await update.message.reply_text(
        "Dùng /task <yêu cầu> để giao việc cho bot.\nGõ /help để xem hướng dẫn."
    )


def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("setmail", setmail_command))
    app.add_handler(CommandHandler("setsms", setsms_command))
    app.add_handler(CommandHandler("task", task_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Bot đang chạy (model: %s) với chế độ polling...", OPENROUTER_MODEL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
