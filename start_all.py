#!/usr/bin/env python3
"""
OTT Manager Service Launcher - Fixed Version with Process Management
"""
import subprocess
import threading
import os
import sys
import time

def kill_existing_processes():
    """Kill any existing conflicting processes"""
    try:
        print("🔪 Killing existing processes...")
        
        # Kill any Python processes that might be running bots
        subprocess.run(['pkill', '-f', 'telegram_bot_service'], capture_output=True)
        subprocess.run(['pkill', '-f', 'python.*telegram'], capture_output=True)
        
        # Wait for processes to die
        time.sleep(2)
        print("✅ Existing processes killed")
        
    except Exception as e:
        print(f"Process cleanup error: {e}")

def run_flask():
    """Start Flask app with gunicorn"""
    port = os.getenv('PORT', '10000')
    print(f"🌐 Starting Flask on port {port}")
    
    subprocess.run([
        'gunicorn',
        'main:flask_app',
        '--bind', f'0.0.0.0:{port}',
        '--workers', '1',
        '--timeout', '120',
        '--access-logfile', '-',
        '--error-logfile', '-',
        '--preload'  # Prevents multiple worker conflicts
    ])

def run_bot():
    """Start Telegram bot after Flask is ready"""
    print("🤖 Starting Telegram Bot...")
    time.sleep(8)  # Give Flask more time to start
    
    subprocess.run([sys.executable, 'telegram_bot_service.py'])

def main():
    """Main launcher with proper process management"""
    print("🚀 Starting OTT Manager Services...")
    
    # Kill any existing processes that could conflict
    kill_existing_processes()
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Start bot in main thread (keeps process alive)
    run_bot()

if __name__ == "__main__":
    main()
