#!/usr/bin/env python3
"""
OTT Manager Telegram Bot Service - Complete Fixed Version
Single instance enforcement, all commands forwarded to Flask API
"""
import os
import sys
import time
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-project-v2.onrender.com')

print(f"🔑 Bot Token: {'Found' if BOT_TOKEN else 'Missing'}")
print(f"🌐 API URL: {WEBHOOK_URL}")

def kill_existing_bot_processes():
    """Kill any existing telegram bot processes to prevent conflicts"""
    try:
        import psutil
        current_pid = os.getpid()
        killed_count = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] == current_pid:
                    continue
                    
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                
                # Kill processes running telegram bot service
                if ('telegram_bot_service.py' in cmdline or 
                    ('python' in proc.info['name'] and 'telegram' in cmdline)):
                    print(f"🔪 Killing existing bot process: PID {proc.info['pid']}")
                    proc.terminate()
                    killed_count += 1
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        if killed_count > 0:
            print(f"✅ Killed {killed_count} existing bot processes")
            time.sleep(2)  # Wait for processes to die
        else:
            print("✅ No existing bot processes found")
            
    except ImportError:
        print("⚠️ psutil not available, skipping process cleanup")
    except Exception as e:
        print(f"⚠️ Error during process cleanup: {e}")

async def handle_api_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward all commands to Flask API with comprehensive error handling"""
    try:
        command_text = update.message.text
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = (update.effective_user.username or 
                   update.effective_user.first_name or 
                   f'User_{chat_id}')
        
        print(f"📤 Forwarding: {command_text} from {username} (ID: {chat_id})")
        
        payload = {
            'chat_id': chat_id,
            'username': username,
            'message': command_text,
            'user_id': user_id
        }

        # Make API request with proper timeout and error handling
        response = requests.post(
            f'{WEBHOOK_URL}/api/telegram-command',
            json=payload,
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )

        print(f"📥 API Response: {response.status_code}")

        if response.status_code == 200:
            try:
                data = response.json()
                message = data.get('message', 'Command processed successfully.')
                print(f"✅ Sending response: {message[:50]}...")
                await update.message.reply_text(message, parse_mode='Markdown')
            except Exception as json_error:
                print(f"❌ JSON parse error: {json_error}")
                await update.message.reply_text('✅ Command processed successfully.')
                
        elif response.status_code == 404:
            await update.message.reply_text('❌ **Command not found**\n\nUse `/help` to see available commands.')
            
        elif response.status_code == 500:
            await update.message.reply_text('❌ **Internal Server Error**\n\nPlease try again in a few moments.')
            
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            await update.message.reply_text('❌ **Service temporarily unavailable**\n\nPlease try again later.')
            
    except requests.exceptions.Timeout:
        print("⏰ Request timeout")
        await update.message.reply_text('⏰ **Request timeout**\n\nThe service is taking too long to respond. Please try again.')
        
    except requests.exceptions.ConnectionError:
        print("🔌 Connection error to API")
        await update.message.reply_text('🔌 **Connection error**\n\nCannot reach the service. Please try again later.')
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        await update.message.reply_text(f'❌ **Error**: {str(e)[:100]}...')

async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands or non-command messages"""
    await update.message.reply_text(
        '❓ **Unknown command**\n\n'
        'Use `/help` to see all available commands.\n\n'
        '**Popular commands:**\n'
        '• `/start` - Get started\n'
        '• `/list` - View subscriptions\n'
        '• `/add` - Add subscription\n'
        '• `/help` - Show help'
    )

def main():
    """Main function - starts the Telegram bot with single instance enforcement"""
    
    # Validate environment
    if not BOT_TOKEN:
        print('❌ ERROR: BOT_TOKEN environment variable not found!')
        print('   Please set BOT_TOKEN in your Render dashboard.')
        return 1

    # Kill any existing bot processes
    print('🔍 Checking for existing bot processes...')
    kill_existing_bot_processes()

    # Initialize bot
    print(f'🤖 Initializing bot...')
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Register all command handlers
        all_commands = [
            'start', 'ping', 'list', 'add', 'search', 'delete', 
            'upgrade', 'help', 'stats', 'sendreminder', 'forcedreminder',
            'promote', 'makeadmin', 'removeadmin'
        ]
        
        print(f'📋 Registering {len(all_commands)} command handlers...')
        
        for cmd in all_commands:
            application.add_handler(CommandHandler(cmd, handle_api_command))
            
        # Handle unknown commands
        from telegram.ext import MessageHandler, filters
        application.add_handler(
            MessageHandler(filters.COMMAND, handle_unknown_command)
        )
        
        # Start polling
        print('🚀 Starting bot in polling mode...')
        print('✅ Bot is ready to receive commands!')
        print('🔗 All commands will be forwarded to Flask API')
        print(f'📡 Flask API: {WEBHOOK_URL}/api/telegram-command')
        
        # Run with error recovery
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,  # Clear any queued updates
            timeout=30,
            pool_timeout=30,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30
        )
        
    except Exception as e:
        print(f'❌ CRITICAL ERROR: {e}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    print('=' * 60)
    print('🎯 OTT Manager Telegram Bot Service Starting...')
    print('=' * 60)
    
    exit_code = main()
    sys.exit(exit_code or 0)
