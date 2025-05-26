import os
import json
import random
import os

# Set the environment variable to disable legacy support
os.environ['CRYPTOGRAPHY_OPENSSL_NO_LEGACY'] = '1'

import re
import asyncio
from datetime import datetime, timedelta
from telegram.ext import ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler

TOKEN = "7654148686:AAFy1Ka6EHk2s_VU89D6DdS9hysEC5FdCIM"
ADMIN_ID = 6827304330
KEYS_FILE = "keys.json"
ADMINS_FILE = "admins.json"
DATABASE_FILES = ["/storage/emulated/0/Download/Telegram/database/dump.txt"]
SEARCHED_ACCOUNTS_FILE = "searched_accounts.txt"
LINES_TO_SEND = 500
MAX_RESULTS = 500

for file in [SEARCHED_ACCOUNTS_FILE, KEYS_FILE, ADMINS_FILE]:
    if not os.path.exists(file):
        with open(file, "w") as f:
            if file == KEYS_FILE:
                json.dump({"keys": {}, "user_keys": {}, "logs": {}}, f)
            elif file.endswith('.json'):
                json.dump({}, f)
            else:
                f.write("")

def load_data(file_name, default=None):
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

def save_data(file_name, data):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

license_cache = load_data(KEYS_FILE, {"keys": {}, "user_keys": {}, "logs": {}})
admins_data = load_data(ADMINS_FILE, {"admins": [ADMIN_ID]})
users_data = load_data("users.json", {})

def fetch_searched_lines():
    try:
        with open(SEARCHED_ACCOUNTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()

def log_searched_lines(lines):
    try:
        with open(SEARCHED_ACCOUNTS_FILE, "a", encoding="utf-8", errors="ignore") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        print(f"Error logging searched lines: {e}")

def craft_random_license(length=12):
    return "ZIAADEV-PREMIUM-" + ''.join(random.choices("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=length))

def compute_expiry(duration):
    now = datetime.now()
    durations = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "6h": 21600, "12h": 43200,
        "1d": 86400, "3d": 259200, "7d": 604800,
        "14d": 1209600, "30d": 2592000
    }
    return None if duration == "lifetime" else (now + timedelta(seconds=durations.get(duration, 0))).timestamp()

def sanitize_userpass_format(line):
    match = re.search(r'([^:]+:[^:]+)$', line.strip())
    return match.group(1).strip() if match else None
    
    return line.split(":")[0] + ":" + line.split(":")[1]

def is_admin(user_id):
    return str(user_id) in [str(admin_id) for admin_id in admins_data.get("admins", [])]

async def welcome_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        welcome_text = (
            "✨ Welcome to ZiaaDev Premium Checker Bot ✨\n\n"
            "🔍 Features:\n"
            "- Fast database searching\n"
            "- Premium accounts checker\n"
            "- Multi-database support\n\n"
            "📌 Use /key <your_key> to activate\n"
            "🔎 Use /search <keyword> to start\n\n"
            "💻 Developer: @ZiaaDev"
        )
        await update.message.reply_text(welcome_text)
    except Exception as e:
        print(f"Error in welcome_user: {e}")

async def deliver_file(bot, chat_id, file_path, caption=None):
    try:
        with open(file_path, "rb") as f:
            await bot.send_document(
                chat_id=chat_id,
                document=InputFile(f, filename=os.path.basename(file_path)),
                caption=caption
            )
        os.remove(file_path)
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Error sending file: {str(e)}")

async def perform_search(update: Update, context: CallbackContext):
    try:
        if len(context.args) < 1:
            return await update.message.reply_text("⚠️ Usage: /search <keyword> [max_results]")

        keyword = context.args[0].lower()
        max_results = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else LINES_TO_SEND
        max_results = min(max_results, MAX_RESULTS)
        chat_id = str(update.message.chat_id)

        if chat_id not in license_cache.get("user_keys", {}):
            return await update.message.reply_text("🔒 Please activate your key first using /key")

        notice_msg = await update.message.reply_text("🔍 Searching databases... Please wait")

        already_used = fetch_searched_lines()
        found_lines = set()
        fresh_lines = []

        skip_prefixes = ("unknown:", "MISSING-USER", "UNKOWN", "invalid", "expired")

        for db_file in DATABASE_FILES:
            if len(found_lines) >= max_results:
                break
            try:
                with open(db_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if len(found_lines) >= max_results:
                            break
                        content = line.strip()
                        if keyword not in content.lower():
                            continue
                        if content in already_used:
                            continue
                        if content.lower().startswith(skip_prefixes):
                            continue
                        if content not in found_lines:
                            found_lines.add(content)
                            fresh_lines.append(content)
            except Exception as e:
                print(f"Error reading {db_file}: {e}")
                continue

        if not found_lines:
            return await notice_msg.edit_text("❌ No results found for your keyword.")

        log_searched_lines(fresh_lines)

        context.user_data["search_results"] = list(found_lines)
        context.user_data["keyword"] = keyword
        context.user_data["username"] = update.message.from_user.username or "UnknownUser"

        # Automatically process with clean format (remove URLs)
        raw_lines = context.user_data.get("search_results", [])
        keyword = context.user_data.get("keyword", "")
        username = context.user_data.get("username", "UnknownUser")
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        final_lines = [sanitize_userpass_format(line) for line in raw_lines]
        final_lines = [line for line in final_lines if line]

        if not final_lines:
            return await notice_msg.edit_text("❌ No valid results after processing!")

        output_file = f"ZiaaDev_{keyword}_Results.txt"
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

        await notice_msg.delete()
        await deliver_file(
            context.bot, 
            update.message.chat_id, 
            output_file,
            caption=(
                f"✅ Search completed!\n"
                f"🔍 Keyword: {keyword}\n"
                f"📊 Results: {len(final_lines)}\n\n"
                f"💻 @ZiaaDev Premium Checker"
            )
        )
        context.user_data.clear()
    except Exception as e:
        await update.message.reply_text(f"❌ Search error: {str(e)}")

async def issue_keys(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.message.from_user.id):
            return await update.message.reply_text("❌ Admin access required!")

        if len(context.args) < 1 or context.args[0] not in ["1m", "5m", "15m", "30m", "1h", "6h", "12h", "1d", "3d", "7d", "14d", "30d", "lifetime"]:
            return await update.message.reply_text(
                "⚠️ Usage: /genkey <duration> [count]\n"
                "Available durations: 1m, 5m, 15m, 30m, 1h, 6h, 12h, 1d, 3d, 7d, 14d, 30d, lifetime"
            )

        duration = context.args[0]
        amount = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
        amount = min(amount, 50)

        keys_generated = []
        for _ in range(amount):
            token = craft_random_license()
            expiry = compute_expiry(duration)
            
            license_cache["keys"][token] = expiry
            keys_generated.append(token)

        save_data(KEYS_FILE, license_cache)
        issuer = update.message.from_user.username or "Admin"
        keys_block = "\n".join(f"{k}" for k in keys_generated)

        response = (
            f"🎉 {amount} Premium Key{'s' if amount > 1 else ''} Generated\n\n"
            f"⏳ Duration: {duration}\n"
            f"👤 Admin: @{issuer}\n\n"
            f"🔑 Keys:\n{keys_block}\n\n"
            "⚠️ These keys will be automatically removed after use"
        )

        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ Key generation error: {str(e)}")

async def add_admin(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.message.from_user.id):
            return await update.message.reply_text("❌ Admin access required!")

        if len(context.args) < 1:
            return await update.message.reply_text("⚠️ Usage: /addadmin <user_id>")

        new_admin = int(context.args[0])
        if "admins" not in admins_data:
            admins_data["admins"] = []
            
        if new_admin not in admins_data["admins"]:
            admins_data["admins"].append(new_admin)
            save_data(ADMINS_FILE, admins_data)
            await update.message.reply_text(f"✅ Added {new_admin} as admin")
        else:
            await update.message.reply_text("ℹ️ User is already an admin")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID format")
    except Exception as e:
        await update.message.reply_text(f"❌ Admin addition error: {str(e)}")

async def activate_key(update: Update, context: CallbackContext):
    try:
        chat_id = str(update.message.chat_id)
        user_id = update.message.from_user.id
        username = update.message.from_user.username or "Unknown"

        if len(context.args) != 1:
            return await update.message.reply_text("⚠️ Usage: /key <your_key>")

        user_key = context.args[0]

        if user_key not in license_cache.get("keys", {}):
            return await update.message.reply_text("❌ Invalid or expired key!")

        expiry = license_cache["keys"][user_key]
        if expiry is not None and datetime.now().timestamp() > expiry:
            del license_cache["keys"][user_key]
            save_data(KEYS_FILE, license_cache)
            return await update.message.reply_text("⌛ This key has expired!")

        license_cache.setdefault("user_keys", {})[chat_id] = expiry
        del license_cache["keys"][user_key]
        save_data(KEYS_FILE, license_cache)

        if str(user_id) not in users_data:
            users_data[str(user_id)] = {
                "username": username,
                "joined": datetime.now().strftime('%Y-%m-%d'),
                "key": user_key,
                "searches": 0
            }
        else:
            users_data[str(user_id)]["key"] = user_key

        save_data("users.json", users_data)

        expiry_date = "Lifetime" if expiry is None else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M:%S')
        
        await update.message.reply_text(
            f"🎉 Premium Activated!\n\n"
            f"👤 Username: @{username}\n"
            f"🔑 Key: {user_key}\n"
            f"⏳ Expiry: {expiry_date}\n\n"
            "🔍 Use /search <keyword> to start"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Activation error: {str(e)}")

async def stats_command(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.message.from_user.id):
            return await update.message.reply_text("❌ Admin access required!")
        
        total_users = len(users_data)
        active_keys = len(license_cache.get("user_keys", {}))
        available_keys = len(license_cache.get("keys", {}))
        
        response = (
            f"📊 Bot Statistics\n\n"
            f"👥 Total Users: {total_users}\n"
            f"🔑 Active Keys: {active_keys}\n"
            f"🛑 Available Keys: {available_keys}\n\n"
            f"💻 @ZiaaDev Premium Checker"
        )
        
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ Stats error: {str(e)}")

def run_bot():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", welcome_user))
    app.add_handler(CommandHandler("search", perform_search))
    app.add_handler(CommandHandler("genkey", issue_keys))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("key", activate_key))
    app.add_handler(CommandHandler("stats", stats_command))

    print("🚀 ZiaaDev Premium Checker Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    run_bot()
