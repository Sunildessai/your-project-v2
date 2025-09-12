#!/usr/bin/env python3
import os
import json
import logging
import uuid
import csv
import io
from datetime import datetime, timedelta
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file, Response
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import firebase_admin
from firebase_admin import credentials, firestore
from apscheduler.schedulers.background import BackgroundScheduler

# Import unified command system
from command_registry import get_command, get_all_commands, get_commands_for_role, CommandResponse
from command_processor import CommandProcessor

# ============ Flask App Setup ============
flask_app = Flask(__name__)
flask_app.secret_key = os.environ.get('SECRET_KEY', 'your-super-secret-key-change-this')
CORS(flask_app)

# Logging setup
logging.basicConfig(level=logging.INFO)
flask_app.logger.setLevel(logging.INFO)

# ============ Plans Configuration ============
SUBSCRIPTION_PLANS = {
    'free': {
        'name': 'Free Plan',
        'price': '₹0 (Lifetime)',
        'max_subscriptions': 5,
        'validity_days': None,
        'features': ['Up to 5 OTT subscriptions', 'Basic reminders', 'Telegram + Web access']
    },
    'basic': {
        'name': 'Basic Plan',
        'price': '₹299/month',
        'max_subscriptions': 15,
        'validity_days': 30,
        'features': ['Up to 15 OTT subscriptions', 'Email reminders', 'Priority support']
    },
    'premium': {
        'name': 'Premium Plan',
        'price': '₹599/month',
        'max_subscriptions': 30,
        'validity_days': 30,
        'features': ['Up to 30 OTT subscriptions', 'Email + SMS reminders', 'Data export', '24/7 support']
    },
    'enterprise': {
        'name': 'Enterprise Plan',
        'price': '₹999/month',
        'max_subscriptions': 100,
        'validity_days': 30,
        'features': ['Up to 100 subscriptions', 'All premium features', 'API access', 'Custom integration']
    },
    'monthly_unlimited': {
        'name': 'Monthly Unlimited',
        'price': '₹499 (30 Days)',
        'max_subscriptions': 999999,
        'validity_days': 30,
        'features': ['Unlimited OTT subscriptions', 'Manager role access', 'Email + SMS reminders', 'Priority support', 'Advanced analytics']
    },
    'yearly_unlimited': {
        'name': 'Yearly Unlimited',
        'price': '₹4999 (365 Days)',
        'max_subscriptions': 999999,
        'validity_days': 365,
        'features': ['Unlimited OTT subscriptions', 'Manager role access', 'Email + SMS reminders', 'Priority support', 'Advanced analytics', '17% discount vs monthly!']
    }
}

# ============ User Roles ============
USER_ROLES = {
    'owner': 5,
    'admin': 4,
    'manager': 3,
    'user': 2,
    'free': 1
}

# ============ Flask-Login Setup ============
login_manager = LoginManager()
login_manager.init_app(flask_app)
login_manager.login_view = 'login'

# ============ Flask-Mail Setup ============
flask_app.config['MAIL_SERVER'] = 'smtp.gmail.com'
flask_app.config['MAIL_PORT'] = 587
flask_app.config['MAIL_USE_TLS'] = True
flask_app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER', '')
flask_app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASSWORD', '')
flask_app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_USER', '')
mail = Mail(flask_app)

# ============ User Model ============
class User(UserMixin):
    def __init__(self, user_id, unique_id=None, telegram_chat_id=None, telegram_username=None, plan_type='free', role='user', max_subscriptions=5, is_active=True, expiry_date=None):
        self.id = user_id
        self.unique_id = unique_id or user_id
        self.telegram_chat_id = telegram_chat_id
        self.telegram_username = telegram_username
        self.plan_type = plan_type
        self.role = role
        self.max_subscriptions = max_subscriptions
        self._active = is_active
        self.expiry_date = expiry_date

    @property
    def is_active(self):
        return self._active

    @is_active.setter
    def is_active(self, value):
        self._active = value

    def get_id(self):
        return str(self.id)

    def has_role(self, required_role):
        return USER_ROLES.get(self.role, 0) >= USER_ROLES.get(required_role, 0)

    def is_plan_active(self):
        if not self.expiry_date or self.plan_type == 'free':
            return True
        return datetime.now() < self.expiry_date

@login_manager.user_loader
def load_user(user_id):
    if db:
        try:
            user_doc = db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return User(
                    user_id=user_id,
                    unique_id=user_data.get('unique_id'),
                    telegram_chat_id=user_data.get('telegram_chat_id'),
                    telegram_username=user_data.get('telegram_username'),
                    plan_type=user_data.get('plan_type'),
                    role=user_data.get('role', 'user'),
                    max_subscriptions=user_data.get('max_subscriptions'),
                    is_active=user_data.get('is_active', True),
                    expiry_date=user_data.get('expiry_date')
                )
        except Exception as e:
            print(f"Error loading user: {e}")
    return None

# ============ Firebase Setup ============
db = None
try:
    firebase_credentials_json = os.environ.get('FIREBASE_CREDENTIALS')
    if firebase_credentials_json:
        cred = credentials.Certificate(json.loads(firebase_credentials_json))
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase initialized successfully.")
    else:
        print("❌ FIREBASE_CREDENTIALS environment variable not found.")
except Exception as e:
    print(f"❌ Error initializing Firebase: {e}")

# ============ Initialize Command Processor ============
command_processor = None
if db:
    command_processor = CommandProcessor(db, mail, SUBSCRIPTION_PLANS, USER_ROLES)
    print("✅ Command processor initialized.")

# ============ Helper Functions ============
def get_or_create_user(chat_id, username):
    """Get existing user or create free user automatically"""
    if not db:
        return None
    try:
        users = db.collection('users').where('telegram_chat_id', '==', chat_id).get()
        if users:
            return users[0].id

        unique_id = f"FREE{str(uuid.uuid4())[:8].upper()}"
        plan_info = SUBSCRIPTION_PLANS['free']
        user_data = {
            'unique_id': unique_id,
            'telegram_username': username or f"User_{chat_id}",
            'telegram_chat_id': chat_id,
            'plan_type': 'free',
            'role': 'free',
            'max_subscriptions': plan_info['max_subscriptions'],
            'is_active': True,
            'created_at': datetime.now(),
            'expiry_date': None,
            'created_via': 'telegram_auto'
        }
        doc_ref = db.collection('users').add(user_data)
        return doc_ref[1].id
    except Exception as e:
        print(f"Error creating user: {e}")
        return None

def get_user_by_chat_id(chat_id):
    """Get user data by telegram chat ID"""
    if not db:
        return None
    try:
        users = db.collection('users').where('telegram_chat_id', '==', chat_id).get()
        if users:
            user_doc = users[0]
            user_data = user_doc.to_dict()
            user_data['id'] = user_doc.id
            return user_data
        return None
    except Exception as e:
        print(f"Error getting user: {e}")
        return None

def parse_telegram_command(message_text):
    """Parse Telegram command and arguments"""
    if not message_text.startswith('/'):
        return None, []

    parts = message_text[1:].split()
    command = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []
    return command, args

# ============ UNIFIED API ENDPOINT ============
@flask_app.route('/api/telegram-command', methods=['POST'])
def unified_command_api():
    """UNIFIED endpoint for both Telegram bot and Web interface"""
    try:
        data = request.get_json(force=True)

        # Extract data
        chat_id = data.get('chat_id')
        username = data.get('username', 'Unknown')
        message_text = data.get('message', '')
        source = data.get('source', 'telegram')  # 'telegram' or 'web'

        print(f"🔄 Processing command: {message_text} from {source}")

        # Get or create user
        user_id = get_or_create_user(chat_id, username)
        if not user_id:
            return jsonify({
                'success': False,
                'message': '❌ Error creating/finding user account.'
            }), 500

        # Get user data
        user_data = get_user_by_chat_id(chat_id)
        if not user_data:
            return jsonify({
                'success': False,
                'message': '❌ User data not found.'
            }), 404

        # Parse command
        command, args = parse_telegram_command(message_text)
        if not command:
            return jsonify({
                'success': False,
                'message': '❌ Invalid command format. Commands must start with /'
            }), 400

        # Process command using unified processor
        if not command_processor:
            return jsonify({
                'success': False,
                'message': '❌ Command processor not available.'
            }), 500

        response = command_processor.process_command(command, args, user_data)

        # Return standardized response
        return jsonify({
            'success': response.success,
            'message': response.message,
            'data': response.data,
            'web_redirect': response.web_redirect,
            'telegram_parse_mode': response.telegram_parse_mode
        })

    except Exception as e:
        flask_app.logger.error(f"Command API Error: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'❌ Internal Error: {str(e)[:100]}'
        }), 500

# ============ Web Interface Routes ============
@flask_app.route('/')
def home():
    """Home page with command interface"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    return render_template('home.html', 
                         commands=get_all_commands(),
                         subscription_plans=SUBSCRIPTION_PLANS)

@flask_app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard with all commands available as UI elements"""
    try:
        user_data = {
            'telegram_chat_id': current_user.telegram_chat_id,
            'unique_id': current_user.unique_id,
            'telegram_username': current_user.telegram_username,
            'plan_type': current_user.plan_type,
            'role': current_user.role,
            'max_subscriptions': current_user.max_subscriptions
        }

        # Get user's available commands
        available_commands = get_commands_for_role(current_user.role)

        # Get user's subscriptions
        subscriptions = []
        if db and current_user.telegram_chat_id:
            subs = db.collection('subscriptions').where('telegram_chat_id', '==', current_user.telegram_chat_id).stream()
            for sub in subs:
                sub_data = sub.to_dict()
                sub_data['id'] = sub.id
                subscriptions.append(sub_data)

        return render_template('dashboard.html',
                             user_data=user_data,
                             commands=available_commands,
                             subscriptions=subscriptions,
                             subscription_plans=SUBSCRIPTION_PLANS)

    except Exception as e:
        flask_app.logger.error(f"Dashboard error: {e}")
        flash('Error loading dashboard', 'error')
        return redirect(url_for('home'))

@flask_app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        unique_id = request.form.get('unique_id')

        if not unique_id:
            flash('Please enter your User ID', 'error')
            return render_template('login.html')

        # Find user by unique_id
        if db:
            try:
                users = db.collection('users').where('unique_id', '==', unique_id).get()
                if users:
                    user_doc = users[0]
                    user_data = user_doc.to_dict()

                    user = User(
                        user_id=user_doc.id,
                        unique_id=user_data.get('unique_id'),
                        telegram_chat_id=user_data.get('telegram_chat_id'),
                        telegram_username=user_data.get('telegram_username'),
                        plan_type=user_data.get('plan_type', 'free'),
                        role=user_data.get('role', 'user'),
                        max_subscriptions=user_data.get('max_subscriptions', 5),
                        is_active=user_data.get('is_active', True),
                        expiry_date=user_data.get('expiry_date')
                    )

                    login_user(user)
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid User ID', 'error')
            except Exception as e:
                flask_app.logger.error(f"Login error: {e}")
                flash('Login failed', 'error')
        else:
            flash('Database not available', 'error')

    return render_template('login.html')

@flask_app.route('/logout')
@login_required
def logout():
    """Logout"""
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('home'))

# ============ Legacy webhook (keep for compatibility) ============
@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """Legacy webhook - redirects to unified API"""
    return unified_command_api()

# ============ Error Handlers ============
@flask_app.errorhandler(404)
def not_found_error(error):
    return """
    <h1>404 - Page Not Found</h1>
    <p>The page you're looking for doesn't exist.</p>
    <a href="/">← Go Home</a>
    """, 404

@flask_app.errorhandler(500)
def internal_error(error):
    return """
    <h1>500 - Internal Server Error</h1>
    <p>Something went wrong. Please try again later.</p>
    <a href="/">← Go Home</a>
    """, 500

# ============ Main Application ============
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f"🚀 Starting Flask app on {host}:{port}")
    flask_app.run(host=host, port=port, debug=False)
