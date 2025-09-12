#!/usr/bin/env python3
"""
Unified Command Registry
Single source of truth for all bot/web commands
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime

@dataclass
class CommandResponse:
    """Standardized response format for all commands"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    web_redirect: Optional[str] = None
    telegram_parse_mode: str = 'Markdown'

@dataclass
class CommandDefinition:
    """Command metadata and validation"""
    name: str
    description: str
    args: List[str]
    permissions: List[str]
    web_ui_component: str
    help_text: str
    examples: List[str]

# Command definitions - SINGLE SOURCE OF TRUTH
COMMANDS = {
    'start': CommandDefinition(
        name='start',
        description='Welcome message and account information',
        args=[],
        permissions=['free', 'user', 'manager', 'admin', 'owner'],
        web_ui_component='dashboard_welcome',
        help_text='Shows welcome message and account details',
        examples=['/start']
    ),

    'list': CommandDefinition(
        name='list',
        description='List all subscriptions with expiry status',
        args=[],
        permissions=['free', 'user', 'manager', 'admin', 'owner'],
        web_ui_component='subscriptions_table',
        help_text='Display all your subscriptions with expiry dates and status',
        examples=['/list']
    ),

    'add': CommandDefinition(
        name='add',
        description='Add new subscription',
        args=['username', 'email', 'service', 'expiry', 'amount?'],
        permissions=['free', 'user', 'manager', 'admin', 'owner'],
        web_ui_component='add_subscription_form',
        help_text='Add a new subscription with username, email, service, expiry date, and optional amount',
        examples=[
            '/add john_netflix john@gmail.com Netflix 2025-12-31',
            '/add jane_spotify jane@gmail.com Spotify 2025-06-15 299'
        ]
    ),

    'delete': CommandDefinition(
        name='delete',
        description='Delete subscription by ID',
        args=['subscription_id'],
        permissions=['free', 'user', 'manager', 'admin', 'owner'],
        web_ui_component='delete_button',
        help_text='Delete a subscription using its ID (get ID from /list command)',
        examples=['/delete abc12345', '/delete gRNNegwP']
    ),

    'search': CommandDefinition(
        name='search',
        description='Search subscriptions by keyword',
        args=['keyword'],
        permissions=['free', 'user', 'manager', 'admin', 'owner'],
        web_ui_component='search_form',
        help_text='Search subscriptions by service name, username, or email',
        examples=['/search Netflix', '/search john@gmail.com', '/search john_netflix']
    ),

    'sendreminder': CommandDefinition(
        name='sendreminder',
        description='Send email reminders for expiring subscriptions',
        args=[],
        permissions=['user', 'manager', 'admin', 'owner'],
        web_ui_component='reminder_button',
        help_text='Send email notifications for subscriptions expiring in the next 7 days',
        examples=['/sendreminder']
    ),

    'upgrade': CommandDefinition(
        name='upgrade',
        description='Upgrade subscription plan',
        args=['plan_type?'],
        permissions=['free', 'user', 'manager', 'admin', 'owner'],
        web_ui_component='upgrade_form',
        help_text='Upgrade to a higher plan or view available plans',
        examples=['/upgrade', '/upgrade premium', '/upgrade yearly_unlimited']
    ),

    'stats': CommandDefinition(
        name='stats',
        description='Show account statistics',
        args=[],
        permissions=['user', 'manager', 'admin', 'owner'],
        web_ui_component='stats_dashboard',
        help_text='Display account statistics including subscription count, expiring subscriptions, and plan details',
        examples=['/stats']
    ),

    'help': CommandDefinition(
        name='help',
        description='Show available commands and help',
        args=['command?'],
        permissions=['free', 'user', 'manager', 'admin', 'owner'],
        web_ui_component='help_modal',
        help_text='Show all available commands or detailed help for a specific command',
        examples=['/help', '/help add', '/help search']
    ),

    'forcedreminder': CommandDefinition(
        name='forcedreminder',
        description='Force send reminders to all users (Admin only)',
        args=[],
        permissions=['admin', 'owner'],
        web_ui_component='admin_reminder_button',
        help_text='Send reminders to all users regardless of expiry dates (Admin only)',
        examples=['/forcedreminder']
    ),

    'promote': CommandDefinition(
        name='promote',
        description='Promote user to manager role (Admin only)',
        args=['user_id', 'role'],
        permissions=['admin', 'owner'],
        web_ui_component='admin_user_management',
        help_text='Promote a user to manager or admin role',
        examples=['/promote FREE12345678 manager', '/promote USER87654321 admin']
    )
}

def get_command(name: str) -> Optional[CommandDefinition]:
    """Get command definition by name"""
    return COMMANDS.get(name.lower())

def get_all_commands() -> Dict[str, CommandDefinition]:
    """Get all command definitions"""
    return COMMANDS

def get_commands_for_role(role: str) -> Dict[str, CommandDefinition]:
    """Get commands available for a specific role"""
    return {name: cmd for name, cmd in COMMANDS.items() if role in cmd.permissions}

def validate_command_args(command_name: str, args: List[str]) -> tuple[bool, str]:
    """Validate command arguments"""
    cmd = get_command(command_name)
    if not cmd:
        return False, f"Unknown command: {command_name}"

    required_args = [arg for arg in cmd.args if not arg.endswith('?')]
    optional_args = [arg for arg in cmd.args if arg.endswith('?')]

    if len(args) < len(required_args):
        return False, f"Missing required arguments. Expected: {', '.join(required_args)}"

    max_args = len(required_args) + len(optional_args)
    if len(args) > max_args and max_args > 0:
        return False, f"Too many arguments. Maximum: {max_args}"

    return True, "Valid"
