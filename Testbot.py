import os

# Set the environment variable to disable legacy support
os.environ['CRYPTOGRAPHY_OPENSSL_NO_LEGACY'] = '1'
import json
import random
import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Union
from telegram.ext import ContextTypes
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    BotCommand
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = "7654148686:AAFy1Ka6EHk2s_VU89D6DdS9hysEC5FdCIM"
ADMIN_ID = 6827304330
KEYS_FILE = "keys.json"
ADMINS_FILE = "admins.json"
USERS_FILE = "users.json"
DATABASE_FILES = ["/storage/emulated/0/Download/Telegram/database/dump.txt"]
SEARCHED_ACCOUNTS_FILE = "searched_accounts.txt"
LOG_FILE = "bot_activity.log"
LINES_TO_SEND = 500
MAX_RESULTS = 50
MAX_KEY_GENERATION = 50
MAX_SEARCH_ATTEMPTS = 5
SEARCH_COOLDOWN = 30  # seconds

# Ensure required files exist
for file in [SEARCHED_ACCOUNTS_FILE, KEYS_FILE, ADMINS_FILE, USERS_FILE, LOG_FILE]:
    if not os.path.exists(file):
        with open(file, "w") as f:
            if file.endswith('.json'):
                default_data = {
                    KEYS_FILE: {"keys": {}, "user_keys": {}, "logs": {}},
                    ADMINS_FILE: {"admins": [ADMIN_ID]},
                    USERS_FILE: {}
                }.get(file, {})
                json.dump(default_data, f)
            else:
                f.write("")

# Type aliases
UserDict = Dict[str, Union[str, int, float, None]]
LicenseCache = Dict[str, Dict[str, Union[Dict[str, Optional[float]], Dict[str, Optional[float]], Dict]]]
AdminsData = Dict[str, List[int]]

# Load initial data
def load_data(file_name: str, default: Union[dict, list, None] = None) -> Union[dict, list]:
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load {file_name}: {e}")
        return default if default is not None else {}

def save_data(file_name: str, data: Union[dict, list]) -> None:
    try:
        temp_file = f"{file_name}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(temp_file, file_name)
    except Exception as e:
        logger.error(f"Failed to save {file_name}: {e}")
        raise

def log_activity(user_id: int, action: str, details: str = "") -> None:
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} - User {user_id} - {action} - {details}\n")
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

license_cache: LicenseCache = load_data(KEYS_FILE, {"keys": {}, "user_keys": {}, "logs": {}})
admins_data: AdminsData = load_data(ADMINS_FILE, {"admins": [ADMIN_ID]})
users_data: Dict[str, UserDict] = load_data(USERS_FILE, {})

def fetch_searched_lines() -> Set[str]:
    try:
        with open(SEARCHED_ACCOUNTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()

def log_searched_lines(lines: List[str]) -> None:
    try:
        with open(SEARCHED_ACCOUNTS_FILE, "a", encoding="utf-8", errors="ignore") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        logger.error(f"Error logging searched lines: {e}")

def craft_random_license(length: int = 12) -> str:
    prefix = "ZIAADEV-PREMIUM-"
    charset = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return prefix + ''.join(random.choices(charset, k=length))

def compute_expiry(duration: str) -> Optional[float]:
    if duration == "lifetime":
        return None
    
    durations = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "6h": 21600, "12h": 43200,
        "1d": 86400, "3d": 259200, "7d": 604800,
        "14d": 1209600, "30d": 2592000
    }
    
    if duration not in durations:
        raise ValueError(f"Invalid duration: {duration}")
    
    return (datetime.now() + timedelta(seconds=durations[duration])).timestamp()

def sanitize_userpass_format(line: str) -> Optional[str]:
    match = re.search(r'([^:]+:[^:]+)(?::|$)', line.strip())
    return match.group(1).strip() if match else None

def is_admin(user_id: int) -> bool:
    return str(user_id) in [str(admin_id) for admin_id in admins_data.get("admins", [])]

def format_timedelta(seconds: float) -> str:
    delta = timedelta(seconds=seconds)
    parts = []
    
    if delta.days > 0:
        parts.append(f"{delta.days}d")
    
    hours, remainder = divmod(delta.seconds, 3600)
    if hours > 0:
        parts.append(f"{hours}h")
    
    minutes, seconds = divmod(remainder, 60)
    if minutes > 0:
        parts.append(f"{minutes}m")
    
    if seconds > 0 and len(parts) < 2:
        parts.append(f"{seconds}s")
    
    return " ".join(parts) if parts else "0s"

async def set_bot_commands(application: Application) -> None:
    commands = [
        BotCommand("start", "Start the bot and see welcome message"),
        BotCommand("search", "Search databases for accounts"),
        BotCommand("key", "Activate your premium key"),
        BotCommand("help", "Show help information"),
        BotCommand("stats", "View bot statistics (admin only)"),
        BotCommand("genkey", "Generate premium keys (admin only)"),
        BotCommand("addadmin", "Add new admin (admin only)")
    ]
    await application.bot.set_my_commands(commands)

async def welcome_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        welcome_text = (
            "✨ Welcome to ZiaaDev Premium Checker Bot ✨\n\n"
            "🔍 Features:\n"
            "- Fast database searching\n"
            "- Premium accounts checker\n"
            "- Multi-database support\n"
            "- Clean result formatting\n\n"
            "📌 Available Commands:\n"
            "/key - Activate your premium key\n"
            "/search - Search databases\n"
            "/help - Show help information\n\n"
            "💻 Developer: @ZiaaDev\n"
            "📢 Channel: @ZiaaDevChannel"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔑 Get Premium", url="t.me/ZiaaDev")],
            [InlineKeyboardButton("📢 Join Channel", url="t.me/ZiaaDevChannel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        log_activity(update.message.from_user.id, "started_bot")
    except Exception as e:
        logger.error(f"Error in welcome_user: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        help_text = (
            "🆘 Help Center 🆘\n\n"
            "🔍 How to search:\n"
            "/search <keyword> [max_results]\n"
            "Example: /search netflix 50\n\n"
            "🔑 How to activate premium:\n"
            "/key <your_key>\n"
            "Example: /key ZIAADEV-PREMIUM-ABC123\n\n"
            "📊 Admin commands:\n"
            "/genkey - Generate premium keys\n"
            "/addadmin - Add new admin\n"
            "/stats - View bot statistics\n\n"
            "💻 Support: @ZiaaDev"
        )
        await update.message.reply_text(help_text)
    except Exception as e:
        logger.error(f"Error in help_command: {e}")

async def deliver_file(bot, chat_id: int, file_path: str, caption: Optional[str] = None) -> None:
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File {file_path} not found")
                
            with open(file_path, "rb") as f:
                await bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(f, filename=os.path.basename(file_path)),
                    caption=caption
                )
            os.remove(file_path)
            return
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed to send file: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise

async def perform_search(update: Update, context: CallbackContext) -> None:
    try:
        user_id = update.message.from_user.id
        chat_id = str(update.message.chat_id)
        username = update.message.from_user.username or "UnknownUser"
        
        if chat_id not in license_cache.get("user_keys", {}):
            await update.message.reply_text(
                "🔒 Premium access required!\n\n"
                "To search our databases, you need an active premium key.\n"
                "Use /key <your_key> to activate your premium access."
            )
            return
            
        last_search_time = context.user_data.get("last_search_time", 0)
        current_time = datetime.now().timestamp()
        cooldown_remaining = SEARCH_COOLDOWN - (current_time - last_search_time)
        
        if cooldown_remaining > 0:
            await update.message.reply_text(
                f"⏳ Please wait {format_timedelta(cooldown_remaining)} "
                "before performing another search."
            )
            return
            
        if len(context.args) < 1:
            await update.message.reply_text(
                "⚠️ Usage: /search <keyword> [max_results]\n"
                "Example: /search netflix 50"
            )
            return
            
        keyword = context.args[0].lower()
        max_results = (
            int(context.args[1]) 
            if len(context.args) > 1 and context.args[1].isdigit() 
            else LINES_TO_SEND
        )
        max_results = min(max_results, MAX_RESULTS)
        
        notice_msg = await update.message.reply_text(
            f"🔍 Searching for '{keyword}'...\n"
            f"⏳ Please wait, this may take a moment..."
        )
        
        already_used = fetch_searched_lines()
        found_lines = set()
        fresh_lines = []
        
        skip_prefixes = ("unknown:", "MISSING-USER", "UNKOWN", "invalid", "expired")
        search_attempts = 0
        
        for db_file in DATABASE_FILES:
            if len(found_lines) >= max_results or search_attempts >= MAX_SEARCH_ATTEMPTS:
                break
                
            try:
                with open(db_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if len(found_lines) >= max_results:
                            break
                            
                        content = line.strip()
                        if not content or keyword not in content.lower():
                            continue
                            
                        if content in already_used:
                            continue
                            
                        if content.lower().startswith(skip_prefixes):
                            continue
                            
                        if content not in found_lines:
                            found_lines.add(content)
                            fresh_lines.append(content)
            except Exception as e:
                logger.error(f"Error reading {db_file}: {e}")
                search_attempts += 1
                continue
                
        if not found_lines:
            await notice_msg.edit_text(
                f"❌ No results found for '{keyword}'.\n\n"
                "Try different keywords or check back later as we update our databases regularly."
            )
            return
            
        log_searched_lines(fresh_lines)
        log_activity(user_id, "search", f"keyword: {keyword}, results: {len(found_lines)}")
        
        if str(user_id) not in users_data:
            users_data[str(user_id)] = {
                "username": username,
                "joined": datetime.now().strftime('%Y-%m-%d'),
                "searches": 0,
                "last_search": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        users_data[str(user_id)]["searches"] = users_data[str(user_id)].get("searches", 0) + 1
        users_data[str(user_id)]["last_search"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_data(USERS_FILE, users_data)
        
        raw_lines = list(found_lines)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        final_lines = [sanitize_userpass_format(line) for line in raw_lines]
        final_lines = [line for line in final_lines if line]
        
        if not final_lines:
            await notice_msg.edit_text("❌ No valid results after processing!")
            return
            
        output_file = f"ZiaaDev_{keyword}_{user_id}_Results.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("══════════════════════════\n")
            f.write(f"🔎 SEARCH RESULTS: {keyword.upper()}\n")
            f.write("══════════════════════════\n\n")
            f.write(f"📅 Date: {timestamp}\n")
            f.write(f"👤 User: @{username}\n")
            f.write(f"📊 Results: {len(final_lines)}\n")
            f.write("══════════════════════════\n\n")
            f.write("\n".join(final_lines))
            f.write("\n\n══════════════════════════\n")
            f.write("💻 Bot by @ZiaaDev\n")
            f.write("📢 Channel: @ZiaaDevChannel\n")
            
        await notice_msg.delete()
        
        try:
            await deliver_file(
                context.bot, 
                update.message.chat_id, 
                output_file,
                caption=(
                    f"✅ Search completed!\n"
                    f"🔍 Keyword: {keyword}\n"
                    f"📊 Results: {len(final_lines)}\n\n"
                    f"💻 @ZiaaDev Premium Checker\n"
                    f"📢 Channel: @ZiaaDevChannel"
                )
            )
        except Exception as e:
            logger.error(f"Failed to send file after retries: {e}")
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text="❌ Failed to send results file after multiple attempts. Please try again later."
            )
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except Exception as e:
                    logger.error(f"Failed to remove temp file: {e}")
        
        context.user_data["last_search_time"] = datetime.now().timestamp()
        
    except Exception as e:
        logger.error(f"Search error for user {user_id}: {e}")
        try:
            await update.message.reply_text(
                "❌ An error occurred during search. Please try again later.\n"
                "If the problem persists, contact @ZiaaDev."
            )
        except Exception:
            pass

async def issue_keys(update: Update, context: CallbackContext) -> None:
    try:
        user_id = update.message.from_user.id
        if not is_admin(user_id):
            await update.message.reply_text(
                "❌ Admin access required!\n\n"
                "This command is restricted to bot administrators only."
            )
            return
            
        if len(context.args) < 1 or context.args[0] not in [
            "1m", "5m", "15m", "30m", "1h", "6h", "12h", "1d", "3d", "7d", "14d", "30d", "lifetime"
        ]:
            await update.message.reply_text(
                "⚠️ Usage: /genkey <duration> [count]\n\n"
                "🕒 Available durations:\n"
                "Short: 1m, 5m, 15m, 30m, 1h, 6h, 12h\n"
                "Long: 1d, 3d, 7d, 14d, 30d\n"
                "Permanent: lifetime\n\n"
                "Example: /genkey 7d 5"
            )
            return
            
        duration = context.args[0]
        amount = (
            int(context.args[1]) 
            if len(context.args) > 1 and context.args[1].isdigit() 
            else 1
        )
        amount = min(amount, MAX_KEY_GENERATION)
        
        keys_generated = []
        for _ in range(amount):
            token = craft_random_license()
            expiry = compute_expiry(duration)
            
            license_cache["keys"][token] = expiry
            keys_generated.append(token)
            
        save_data(KEYS_FILE, license_cache)
        log_activity(user_id, "generate_keys", f"duration: {duration}, count: {amount}")
        
        issuer = update.message.from_user.username or "Admin"
        keys_block = "\n".join(f"• {k}" for k in keys_generated)
        expiry_info = "Never" if duration == "lifetime" else duration
        
        response = (
            f"🎉 {amount} Premium Key{'s' if amount > 1 else ''} Generated\n\n"
            f"⏳ Duration: {expiry_info}\n"
            f"👤 Admin: @{issuer}\n\n"
            f"🔑 Generated Keys:\n{keys_block}\n\n"
            "⚠️ These keys will be automatically removed after use"
        )
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Key generation error by {user_id}: {e}")
        await update.message.reply_text(
            "❌ Failed to generate keys. Please check the command format and try again."
        )

async def add_admin(update: Update, context: CallbackContext) -> None:
    try:
        user_id = update.message.from_user.id
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin access required!")
            return
            
        if len(context.args) < 1:
            await update.message.reply_text("⚠️ Usage: /addadmin <user_id>")
            return
            
        try:
            new_admin = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number")
            return
            
        if "admins" not in admins_data:
            admins_data["admins"] = []
            
        if new_admin in admins_data["admins"]:
            await update.message.reply_text("ℹ️ User is already an admin")
            return
            
        admins_data["admins"].append(new_admin)
        save_data(ADMINS_FILE, admins_data)
        log_activity(user_id, "add_admin", f"new_admin: {new_admin}")
        
        await update.message.reply_text(f"✅ Added {new_admin} as admin")
        
    except Exception as e:
        logger.error(f"Admin addition error by {user_id}: {e}")
        await update.message.reply_text("❌ Failed to add admin. Please try again.")

async def activate_key(update: Update, context: CallbackContext) -> None:
    try:
        chat_id = str(update.message.chat_id)
        user_id = update.message.from_user.id
        username = update.message.from_user.username or "Unknown"
        
        if len(context.args) != 1:
            await update.message.reply_text(
                "⚠️ Usage: /key <your_key>\n\n"
                "Example: /key ZIAADEV-PREMIUM-ABC123"
            )
            return
            
        user_key = context.args[0]
        
        if user_key not in license_cache.get("keys", {}):
            await update.message.reply_text(
                "❌ Invalid or expired key!\n\n"
                "Please make sure you entered the correct key. "
                "If you don't have one, contact @ZiaaDev."
            )            
            return
        expiry = license_cache["keys"][user_key]
        if expiry is not None and datetime.now().timestamp() > expiry:
            del license_cache["keys"][user_key]
            save_data(KEYS_FILE, license_cache)
            await update.message.reply_text(
                "⌛ This key has expired!\n\n"
                "Please contact @ZiaaDev for a new key."
            )
            return
            
        license_cache.setdefault("user_keys", {})[chat_id] = expiry
        del license_cache["keys"][user_key]
        save_data(KEYS_FILE, license_cache)
        
        if str(user_id) not in users_data:
            users_data[str(user_id)] = {
                "username": username,
                "joined": datetime.now().strftime('%Y-%m-%d'),
                "key": user_key,
                "searches": 0,
                "last_active": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        else:
            users_data[str(user_id)]["key"] = user_key
            users_data[str(user_id)]["last_active"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
        save_data(USERS_FILE, users_data)
        log_activity(user_id, "activate_key", f"key: {user_key}")
        
        expiry_date = (
            "Lifetime" if expiry is None 
            else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M:%S')
        )
        
        await update.message.reply_text(
            f"🎉 Premium Activated Successfully!\n\n"
            f"👤 Username: @{username}\n"
            f"🔑 Key: {user_key}\n"
            f"⏳ Expiry: {expiry_date}\n\n"
            "🔍 Now you can use /search <keyword> to start searching our databases!\n\n"
            "💻 Bot by @ZiaaDev"
        )
        
    except Exception as e:
        logger.error(f"Key activation error for user {user_id}: {e}")
        await update.message.reply_text(
            "❌ Failed to activate key. Please check the key and try again.\n"
            "If the problem persists, contact @ZiaaDev."
        )

async def stats_command(update: Update, context: CallbackContext) -> None:
    try:
        user_id = update.message.from_user.id
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin access required!")
            return
            
        total_users = len(users_data)
        active_keys = len(license_cache.get("user_keys", {}))
        available_keys = len(license_cache.get("keys", {}))
        
        active_users = sum(
            1 for user in users_data.values() 
            if "last_active" in user and 
            (datetime.now() - datetime.strptime(user["last_active"], '%Y-%m-%d %H:%M:%S')).days < 7
        )
        
        total_searches = sum(user.get("searches", 0) for user in users_data.values())
        
        response = (
            f"📊 Bot Statistics\n\n"
            f"👥 Total Users: {total_users}\n"
            f"🟢 Active Users: {active_users}\n"
            f"🔑 Active Keys: {active_keys}\n"
            f"🛑 Available Keys: {available_keys}\n"
            f"🔍 Total Searches: {total_searches}\n\n"
            f"💻 @ZiaaDev Premium Checker"
        )
        
        await update.message.reply_text(response)
        log_activity(user_id, "view_stats")
        
    except Exception as e:
        logger.error(f"Stats error by admin {user_id}: {e}")
        await update.message.reply_text("❌ Failed to fetch statistics. Please try again.")

async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error("Exception while handling update:", exc_info=context.error)
    
    if update and hasattr(update, 'message') and update.message:
        try:
            await update.message.reply_text(
                "❌ An unexpected error occurred. Please try again later.\n"
                "If the problem persists, contact @ZiaaDev."
            )
        except Exception:
            pass

def run_bot() -> None:
    try:
        application = Application.builder().token(TOKEN).build()
        
        application.add_handler(CommandHandler("start", welcome_user))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("search", perform_search))
        application.add_handler(CommandHandler("genkey", issue_keys))
        application.add_handler(CommandHandler("addadmin", add_admin))
        application.add_handler(CommandHandler("key", activate_key))
        application.add_handler(CommandHandler("stats", stats_command))
        
        application.add_error_handler(error_handler)
        
        application.post_init = set_bot_commands
        
        logger.info("🚀 ZiaaDev Premium Checker Bot is running...")
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    run_bot()
