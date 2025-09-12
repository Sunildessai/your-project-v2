#!/usr/bin/env python3
"""
Unified Command Processor with Telegram ID Tracking
Handles all commands from both Telegram and Web interfaces
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from command_registry import get_command, validate_command_args, CommandResponse, get_commands_for_role

class CommandProcessor:
    def __init__(self, db, mail, subscription_plans, user_roles):
        self.db = db
        self.mail = mail
        self.subscription_plans = subscription_plans
        self.user_roles = user_roles

    def process_command(self, command_name: str, args: List[str], user_data: Dict) -> CommandResponse:
        """Process any command from any source (Telegram/Web)"""
        try:
            # Get command definition
            cmd_def = get_command(command_name)
            if not cmd_def:
                return CommandResponse(
                    success=False,
                    message=f"❌ **Unknown command:** `{command_name}`\n\nUse `/help` to see available commands.\n\n**Popular commands:**\n• `/start` - Get started\n• `/list` - View subscriptions\n• `/add` - Add subscription\n• `/help` - Show help"
                )

            # Check permissions
            user_role = user_data.get('role', 'free')
            if user_role not in cmd_def.permissions:
                return CommandResponse(
                    success=False,
                    message="❌ **Permission denied**\n\nYou don't have permission to use this command.\n\nYour role: `" + user_role + "`\nRequired: `" + "`, `".join(cmd_def.permissions) + "`"
                )

            # Route to specific command handler
            handler_method = f"_handle_{command_name}"
            if hasattr(self, handler_method):
                return getattr(self, handler_method)(args, user_data)
            else:
                return CommandResponse(
                    success=False,
                    message=f"❌ Command handler not implemented: `{command_name}`\n\nThis command is recognized but not yet implemented. Please contact support."
                )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Error processing command:** {str(e)[:100]}\n\nPlease try again or contact support if the problem persists."
            )

    def _handle_start(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /start command"""
        plan_name = self.subscription_plans[user_data['plan_type']]['name']
        message = f"""🎉 **Welcome to OTT Reminder Bot!**

👤 **Your Account:**
🆔 ID: `{user_data['unique_id']}`
📦 Plan: {plan_name}
📋 Limit: {user_data['max_subscriptions']} subscriptions

**🌐 Web Dashboard:**
https://your-project-v2.onrender.com

**🚀 Quick Start:**
• `/add username email service expiry` - Add subscription
• `/add username email service expiry amount telegram_id` - Add with tracking
• `/list` - View all subscriptions  
• `/help` - Show all commands

Use `/help` for complete command list!"""

        return CommandResponse(
            success=True,
            message=message,
            data={'user_info': user_data},
            web_redirect='/dashboard'
        )

    def _handle_add(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /add command with optional telegram_id tracking"""
        if len(args) < 4:
            return CommandResponse(
                success=False,
                message='❌ **Missing required information!**\n\n**Usage:** `/add username email service expiry [amount] [telegram_id]`\n\n**Examples:**\n• `/add john_netflix john@gmail.com Netflix 2025-12-31`\n• `/add jane_spotify jane@gmail.com Spotify 2025-06-15 299`\n• `/add mike_disney mike@gmail.com Disney+ 2025-03-15 399 @mike_official`\n• `/add sara_prime sara@gmail.com Prime 2025-08-20 199 123456789`\n\n**Required:**\n• `username` - Account username for the service\n• `email` - Customer\'s email address\n• `service` - Service name (Netflix, Disney+, etc.)\n• `expiry` - Expiry date (YYYY-MM-DD format)\n\n**Optional:**\n• `amount` - Amount paid (₹)\n• `telegram_id` - Customer\'s @username or numeric ID (for tracking)'
            )

        try:
            username, email, service, expiry = args[:4]

            # Parse optional amount and telegram_id
            remaining_args = args[4:] if len(args) > 4 else []
            amount = "0"
            telegram_id = None

            # Smart parsing of remaining arguments
            if len(remaining_args) == 1:
                # Only one extra argument - could be amount or telegram_id
                arg = remaining_args[0]
                if arg.startswith('@') or (arg.isdigit() and len(arg) > 3):
                    # Looks like telegram_id
                    telegram_id = arg
                else:
                    # Probably amount
                    amount = arg
            elif len(remaining_args) >= 2:
                # Two or more arguments - first is amount, second is telegram_id
                amount = remaining_args[0]
                telegram_id = remaining_args[1]

            # Validate email format
            if '@' not in email or '.' not in email:
                return CommandResponse(
                    success=False,
                    message="❌ **Invalid email format!**\n\nPlease provide a valid email address.\n\n**Example:** `john@gmail.com`"
                )

            # Validate date format
            try:
                expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
                if expiry_date < datetime.now().date():
                    return CommandResponse(
                        success=False,
                        message="❌ **Expiry date is in the past!**\n\nPlease provide a future date.\n\n**Format:** YYYY-MM-DD\n**Example:** `2025-12-31`"
                    )
            except ValueError:
                return CommandResponse(
                    success=False,
                    message="❌ **Invalid date format!**\n\n**Required format:** YYYY-MM-DD\n\n**Examples:**\n• `2025-12-31` (Dec 31, 2025)\n• `2025-06-15` (Jun 15, 2025)\n• `2026-01-01` (Jan 1, 2026)"
                )

            # Check user limits
            chat_id = user_data.get('telegram_chat_id')
            current_count = len(list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream()))

            max_subs = user_data.get('max_subscriptions', 5)
            if max_subs != 999999 and current_count >= max_subs:
                plan_name = self.subscription_plans[user_data['plan_type']]['name']
                return CommandResponse(
                    success=False,
                    message=f"❌ **Subscription limit reached!**\n\n**Current plan:** {plan_name}\n**Limit:** {max_subs} subscriptions\n**Used:** {current_count}/{max_subs}\n\n**Solution:**\nUpgrade your plan to add more subscriptions.\nUse `/upgrade` to see available plans.",
                    web_redirect='/upgrade'
                )

            # Add subscription
            subscription_data = {
                'username': username,
                'email': email,
                'service': service,
                'expiry': expiry,
                'amount_received': amount,
                'telegram_chat_id': chat_id,
                'created_at': datetime.now(),
                'note': "Added via unified command processor"
            }

            # Add telegram_id if provided
            if telegram_id:
                subscription_data['customer_telegram_id'] = telegram_id

            doc_ref = self.db.collection('subscriptions').add(subscription_data)

            # Build success message
            success_message = f"✅ **Subscription Added Successfully!**\n\n🎬 **Service:** {service}\n👤 **Username:** {username}\n📧 **Email:** {email}\n💰 **Amount:** ₹{amount}\n📅 **Expires:** {expiry}\n🆔 **ID:** `{doc_ref[1].id[:8]}`"

            if telegram_id:
                success_message += f"\n📱 **Telegram ID:** `{telegram_id}`"

            success_message += "\n\n💡 Use `/list` to see all your subscriptions!"

            return CommandResponse(
                success=True,
                message=success_message,
                data={'subscription_id': doc_ref[1].id, 'subscription': subscription_data},
                web_redirect='/dashboard'
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Error adding subscription:** {str(e)}\n\nPlease check your information and try again."
            )

    def _handle_list(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /list command - now shows telegram_id"""
        try:
            chat_id = user_data.get('telegram_chat_id')
            subscriptions = list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream())

            if not subscriptions:
                return CommandResponse(
                    success=True,
                    message="📋 **No Subscriptions Found**\n\nGet started by adding your first subscription:\n\n**Examples:**\n`/add john_netflix john@gmail.com Netflix 2025-12-31`\n\n**With Telegram ID:**\n`/add john_netflix john@gmail.com Netflix 2025-12-31 499 @john_doe`",
                    data={'subscriptions': []}
                )

            message = "📋 **Your Subscriptions:**\n\n"
            today = datetime.now().date()
            subscription_data = []

            for i, sub in enumerate(subscriptions, 1):
                sub_data = sub.to_dict()
                sub_data['id'] = sub.id
                subscription_data.append(sub_data)

                try:
                    expiry_date = datetime.strptime(sub_data['expiry'], '%Y-%m-%d').date()
                    days_left = (expiry_date - today).days

                    if days_left < 0:
                        status = "🔴 EXPIRED"
                    elif days_left <= 3:
                        status = "🟡 EXPIRING SOON"
                    else:
                        status = "✅ ACTIVE"
                except:
                    status = "❓ UNKNOWN"
                    days_left = 0

                message += f"**{i}. {sub_data['service']}** {status}\n"
                message += f"🆔 ID: `{sub.id[:8]}`\n"
                message += f"👤 Username: `{sub_data['username']}`\n"
                message += f"📧 Email: `{sub_data['email']}`\n"
                message += f"💰 Amount: ₹{sub_data.get('amount_received', 'N/A')}\n"
                message += f"📅 Expires: `{sub_data['expiry']}` ({days_left} days)\n"

                # Show telegram_id if available
                if sub_data.get('customer_telegram_id'):
                    message += f"📱 Telegram: `{sub_data['customer_telegram_id']}`\n"

                message += "─────────────────────\n\n"

            message += "💡 **Tip:** Use `/delete ID` to remove a subscription (e.g., `/delete " + subscriptions[0].id[:8] + "`)"

            return CommandResponse(
                success=True,
                message=message,
                data={'subscriptions': subscription_data}
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Error fetching subscriptions:** {str(e)}\n\nPlease try again or contact support."
            )

    def _handle_search(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /search command - now includes telegram_id in search"""
        if not args:
            return CommandResponse(
                success=False,
                message='❌ **Search keyword required!**\n\n**Usage:** `/search keyword`\n\n**Examples:**\n• `/search Netflix` - Find Netflix subscriptions\n• `/search john@gmail.com` - Find by email\n• `/search john_netflix` - Find by username\n• `/search @john_doe` - Find by Telegram ID\n\n**💡 What you can search for:**\n• Service names (Netflix, Spotify, Disney+)\n• Email addresses\n• Usernames\n• Telegram IDs\n• Any part of subscription details'
            )

        try:
            search_query = args[0].lower()
            chat_id = user_data.get('telegram_chat_id')

            subscriptions = list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream())

            if not subscriptions:
                return CommandResponse(
                    success=True,
                    message="📋 **No subscriptions to search**\n\nYou don't have any subscriptions yet.\n\n**Get started:**\n`/add john_netflix john@gmail.com Netflix 2025-12-31`",
                    data={'results': []}
                )

            # Filter subscriptions
            matching_subs = []
            for sub in subscriptions:
                sub_data = sub.to_dict()
                username = sub_data.get('username', '').lower()
                email = sub_data.get('email', '').lower()
                service = sub_data.get('service', '').lower()
                telegram_id = sub_data.get('customer_telegram_id', '').lower()

                if (search_query in username or search_query in email or 
                    search_query in service or search_query in telegram_id):
                    sub_data['id'] = sub.id
                    matching_subs.append(sub_data)

            if not matching_subs:
                return CommandResponse(
                    success=True,
                    message=f"🔍 **No matches found for** `{args[0]}`\n\n**Search tips:**\n• Try partial matches (e.g., 'Net' for Netflix)\n• Search by service, email, username, or Telegram ID\n• Check spelling\n\n**Your subscriptions:**\nUse `/list` to see all {len(subscriptions)} subscription(s)",
                    data={'results': []}
                )

            # Format results
            message = f"🔍 **Found {len(matching_subs)} result(s) for** `{args[0]}`:\n\n"
            today = datetime.now().date()

            for i, sub_data in enumerate(matching_subs, 1):
                try:
                    expiry_date = datetime.strptime(sub_data['expiry'], '%Y-%m-%d').date()
                    days_left = (expiry_date - today).days
                    if days_left < 0:
                        status = "🔴 EXPIRED"
                    elif days_left <= 7:
                        status = "🟡 EXPIRING SOON"
                    else:
                        status = "✅ ACTIVE"
                except:
                    status = "❓ UNKNOWN"
                    days_left = 0

                message += f"**{i}. {sub_data['service']}** {status}\n"
                message += f"🆔 ID: `{sub_data['id'][:8]}`\n"
                message += f"👤 Username: `{sub_data['username']}`\n"
                message += f"📧 Email: `{sub_data['email']}`\n"
                message += f"📅 Expires: `{sub_data['expiry']}` ({days_left} days)\n"

                # Show telegram_id if available
                if sub_data.get('customer_telegram_id'):
                    message += f"📱 Telegram: `{sub_data['customer_telegram_id']}`\n"

                message += "─────────────────────\n\n"

            message += f"💡 **Tips:**\n• Use `/delete ID` to remove any subscription\n• Use `/list` to see all {len(subscriptions)} subscription(s)"

            return CommandResponse(
                success=True,
                message=message,
                data={'results': matching_subs}
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Search Error:** {str(e)}\n\nPlease try again with a different keyword."
            )

    def _handle_delete(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /delete command with improved error messages"""
        if not args:
            return CommandResponse(
                success=False,
                message='❌ **Subscription ID required!**\n\n**Usage:** `/delete subscription_id`\n\n**Examples:**\n• `/delete abc12345`\n• `/delete gRNNegwP`\n\n**📋 To get subscription IDs:**\n1. Use `/list` command\n2. Copy the 8-character ID shown\n3. Use that ID with `/delete`\n\n💡 **Tip:** You only need the first 8 characters of the ID!'
            )

        try:
            sub_id = args[0]
            chat_id = user_data.get('telegram_chat_id')

            # Find subscription
            all_subs = list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream())

            if not all_subs:
                return CommandResponse(
                    success=False,
                    message="📋 **No subscriptions found!**\n\nYou don't have any subscriptions to delete.\n\nUse `/add` to add your first subscription."
                )

            target_sub = None
            target_id = None

            for sub in all_subs:
                if sub.id == sub_id or sub.id.startswith(sub_id):
                    target_sub = sub.to_dict()
                    target_id = sub.id
                    break

            if not target_sub:
                available_subs = []
                for sub in all_subs[:3]:  # Show first 3 subscriptions
                    sub_data = sub.to_dict()
                    available_subs.append(f"• `{sub.id[:8]}` - {sub_data.get('service', 'Unknown')}")

                subs_text = '\n'.join(available_subs)
                if len(all_subs) > 3:
                    subs_text += f"\n• ... and {len(all_subs) - 3} more"

                return CommandResponse(
                    success=False,
                    message=f"❌ **Subscription not found!**\n\n🔍 **Searched for:** `{sub_id}`\n\n**Available subscriptions:**\n{subs_text}\n\n💡 **Tips:**\n• Use `/list` to see all subscriptions\n• Make sure to copy the ID exactly\n• You can use partial IDs (first 8 characters)"
                )

            # Delete subscription
            self.db.collection('subscriptions').document(target_id).delete()

            delete_message = f"✅ **Successfully Deleted!**\n\n🎬 **Service:** {target_sub.get('service', 'Unknown')}\n👤 **Username:** {target_sub.get('username', 'Unknown')}\n📧 **Email:** {target_sub.get('email', 'Unknown')}\n🗑️ **ID:** `{target_id[:8]}`"

            # Show telegram_id if it was there
            if target_sub.get('customer_telegram_id'):
                delete_message += f"\n📱 **Telegram ID:** `{target_sub['customer_telegram_id']}`"

            delete_message += "\n\n💡 Use `/list` to see your remaining subscriptions."

            return CommandResponse(
                success=True,
                message=delete_message,
                data={'deleted_subscription': target_sub},
                web_redirect='/dashboard'
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Delete Error:** {str(e)[:100]}\n\nPlease try again or contact support."
            )

    def _handle_help(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /help command with improved formatting"""
        try:
            user_role = user_data.get('role', 'free')
            available_commands = get_commands_for_role(user_role)

            if args and args[0]:
                # Help for specific command
                cmd_name = args[0].lower()
                cmd_def = get_command(cmd_name)

                if not cmd_def or cmd_name not in available_commands:
                    available_list = ', '.join([f'`{cmd}`' for cmd in list(available_commands.keys())[:5]])
                    return CommandResponse(
                        success=False,
                        message=f"❌ **Command not found:** `{args[0]}`\n\n**Available commands:**\n{available_list}\n\nUse `/help` to see all commands."
                    )

                message = f"📖 **Help for /{cmd_name}**\n\n"
                message += f"**Description:**\n{cmd_def.help_text}\n\n"
                message += f"**Examples:**\n"
                for example in cmd_def.examples:
                    message += f"• `{example}`\n"

                return CommandResponse(
                    success=True,
                    message=message,
                    data={'command_help': cmd_def.__dict__}
                )
            else:
                # General help
                message = f"📖 **OTT Manager Bot Help**\n\nYour role: `{user_role}`\n\n**📋 Available Commands:**\n\n"

                # Group commands by category
                basic_commands = ['start', 'help', 'stats']
                subscription_commands = ['add', 'list', 'delete', 'search']
                reminder_commands = ['sendreminder']
                plan_commands = ['upgrade']
                admin_commands = ['promote', 'makeadmin', 'removeadmin', 'forcedreminder']

                def add_command_group(title, cmd_list, emoji):
                    group_message = f"**{emoji} {title}:**\n"
                    for cmd_name in cmd_list:
                        if cmd_name in available_commands:
                            cmd_def = available_commands[cmd_name]
                            group_message += f"• `/{cmd_name}` - {cmd_def.description}\n"
                    return group_message + "\n"

                message += add_command_group("Basic Commands", basic_commands, "🏠")
                message += add_command_group("Subscription Management", subscription_commands, "🎬")

                if any(cmd in available_commands for cmd in reminder_commands):
                    message += add_command_group("Reminders", reminder_commands, "🔔")

                if any(cmd in available_commands for cmd in plan_commands):
                    message += add_command_group("Plan Management", plan_commands, "💎")

                if any(cmd in available_commands for cmd in admin_commands):
                    message += add_command_group("Admin Commands", admin_commands, "👑")

                message += "💡 **Tips:**\n"
                message += "• Use `/help command_name` for detailed help\n"
                message += "• Example: `/help add` for add command help\n"
                message += "• Add Telegram ID for better tracking: `/add user email service date amount @telegram_id`"

                return CommandResponse(
                    success=True,
                    message=message,
                    data={'available_commands': list(available_commands.keys())}
                )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Help Error:** {str(e)}\n\nUse basic commands: `/start`, `/list`, `/add`"
            )

    def _handle_stats(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /stats command with telegram_id info"""
        try:
            chat_id = user_data.get('telegram_chat_id')
            subscriptions = list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream())

            total_subs = len(subscriptions)
            active_subs = 0
            expiring_subs = 0
            expired_subs = 0
            total_amount = 0
            tracked_customers = 0

            today = datetime.now().date()

            for sub in subscriptions:
                sub_data = sub.to_dict()

                # Count telegram_id tracked subscriptions
                if sub_data.get('customer_telegram_id'):
                    tracked_customers += 1

                try:
                    expiry_date = datetime.strptime(sub_data['expiry'], '%Y-%m-%d').date()
                    days_left = (expiry_date - today).days

                    if days_left < 0:
                        expired_subs += 1
                    elif days_left <= 7:
                        expiring_subs += 1
                    else:
                        active_subs += 1

                    # Calculate total amount
                    amount_str = sub_data.get('amount_received', '0')
                    try:
                        amount = float(amount_str) if amount_str != 'N/A' else 0
                        total_amount += amount
                    except:
                        pass

                except:
                    continue

            plan_info = self.subscription_plans[user_data['plan_type']]

            message = f"""📊 **Account Statistics**

👤 **Account Details:**
🆔 **ID:** `{user_data['unique_id']}`
📦 **Plan:** {plan_info['name']}
🎭 **Role:** {user_data['role'].title()}
💰 **Plan Price:** {plan_info['price']}

📋 **Subscription Overview:**
📈 **Total:** {total_subs}/{user_data['max_subscriptions']}
✅ **Active:** {active_subs}
🟡 **Expiring (≤7 days):** {expiring_subs}
🔴 **Expired:** {expired_subs}
💵 **Total Spent:** ₹{total_amount:.0f}
📱 **With Telegram ID:** {tracked_customers}/{total_subs}

📅 **Plan Details:**
⏳ **Validity:** {'Lifetime' if not user_data.get('expiry_date') else user_data['expiry_date']}
🎯 **Usage:** {(total_subs/user_data['max_subscriptions']*100):.1f}% of limit used"""

            if expiring_subs > 0:
                message += f"\n\n🚨 **Action Required:**\n{expiring_subs} subscription(s) expiring soon!\nUse `/sendreminder` to get email notifications."

            if tracked_customers < total_subs:
                message += f"\n\n💡 **Tip:** Add Telegram IDs to {total_subs - tracked_customers} more subscriptions for better tracking!"

            return CommandResponse(
                success=True,
                message=message,
                data={
                    'stats': {
                        'total_subscriptions': total_subs,
                        'active_subscriptions': active_subs,
                        'expiring_subscriptions': expiring_subs,
                        'expired_subscriptions': expired_subs,
                        'tracked_customers': tracked_customers,
                        'total_amount': total_amount,
                        'plan_info': plan_info,
                        'user_info': user_data
                    }
                }
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Stats Error:** {str(e)}\n\nPlease try again later."
            )

    def _handle_sendreminder(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /sendreminder command"""
        try:
            from flask_mail import Message

            chat_id = user_data.get('telegram_chat_id')
            subscriptions = list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream())

            today = datetime.now().date()
            expiring_subs = []

            for sub in subscriptions:
                sub_data = sub.to_dict()
                try:
                    expiry_date = datetime.strptime(sub_data['expiry'], '%Y-%m-%d').date()
                    days_left = (expiry_date - today).days
                    if 0 <= days_left <= 7:
                        expiring_subs.append(sub_data)
                except:
                    continue

            if not expiring_subs:
                return CommandResponse(
                    success=True,
                    message="✅ **No urgent reminders needed!**\n\nNo subscriptions are expiring in the next 7 days.\n\n💡 **Tip:** Use `/list` to see all subscription expiry dates."
                )

            # Get the first email for sending
            recipient_email = expiring_subs[0]['email']

            # Build email content
            email_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #333;">Dear {user_data.get('telegram_username', 'User')},</h2>
                <p>You have {len(expiring_subs)} subscription(s) expiring soon:</p>
                <ul style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
            """

            for sub in expiring_subs:
                email_content += f"<li><strong>{sub['service']}</strong> ({sub['username']}) - Expires: {sub['expiry']}"
                if sub.get('customer_telegram_id'):
                    email_content += f" | Customer: {sub['customer_telegram_id']}"
                email_content += "</li>"

            email_content += """
                </ul>
                <p>Please renew these subscriptions to avoid service interruption.</p>
                <p style="margin-top: 30px;">Best regards,<br><strong>OTT Manager Team</strong></p>
                <hr>
                <small style="color: #666;">Manage your subscriptions: <a href="https://your-project-v2.onrender.com">OTT Manager Dashboard</a></small>
            </div>
            """

            # Send email reminder
            msg = Message(
                subject="🔔 OTT Subscription Expiry Reminder",
                recipients=[recipient_email],
                html=email_content
            )

            self.mail.send(msg)

            sub_list = "\n".join([
                f"• {sub['service']} ({sub['username']}) - {sub['expiry']}" + 
                (f" | {sub['customer_telegram_id']}" if sub.get('customer_telegram_id') else "")
                for sub in expiring_subs
            ])

            return CommandResponse(
                success=True,
                message=f"✅ **Reminder sent successfully!**\n\n📧 **Email sent to:** {recipient_email}\n\n**Expiring subscriptions ({len(expiring_subs)}):**\n{sub_list}\n\n💡 **Tip:** Check your email inbox (and spam folder) for the detailed reminder.",
                data={'expiring_subscriptions': expiring_subs}
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Reminder Error:** {str(e)}\n\nPlease check your email settings or try again later."
            )

    def _handle_upgrade(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /upgrade command"""
        try:
            current_plan = user_data['plan_type']

            if args and args[0]:
                plan_type = args[0].lower()
                if plan_type not in self.subscription_plans:
                    available_plans = list(self.subscription_plans.keys())
                    plans_text = ', '.join([f'`{plan}`' for plan in available_plans])
                    return CommandResponse(
                        success=False,
                        message=f"❌ **Invalid plan:** `{plan_type}`\n\n**Available plans:**\n{plans_text}\n\nUse `/upgrade` to see all plan details."
                    )

                plan_info = self.subscription_plans[plan_type]
                features_text = "\n".join([f"• {feature}" for feature in plan_info['features']])

                if plan_type == current_plan:
                    status_msg = "✅ **This is your current plan!**"
                else:
                    status_msg = "🔗 **Contact admin to upgrade to this plan**"

                return CommandResponse(
                    success=True,
                    message=f"💎 **{plan_info['name']}**\n\n💰 **Price:** {plan_info['price']}\n📋 **Subscriptions:** {plan_info['max_subscriptions']}\n\n**✨ Features:**\n{features_text}\n\n{status_msg}",
                    data={'plan_info': plan_info},
                    web_redirect='/upgrade'
                )
            else:
                # Show all plans
                message = f"💎 **Available Subscription Plans**\n\nYour current plan: **{self.subscription_plans[current_plan]['name']}** ✅\n\n"

                for plan_name, plan_info in self.subscription_plans.items():
                    if plan_name == current_plan:
                        message += f"**{plan_info['name']} (CURRENT)** ✅\n"
                    else:
                        message += f"**{plan_info['name']}**\n"
                    message += f"💰 {plan_info['price']}\n"
                    message += f"📋 {plan_info['max_subscriptions']} subscriptions\n"
                    message += "─────────────────\n"

                message += "\n💡 **Tips:**\n• Use `/upgrade plan_name` for details\n• Example: `/upgrade premium`\n• Contact admin for plan upgrades"

                return CommandResponse(
                    success=True,
                    message=message,
                    data={'all_plans': self.subscription_plans, 'current_plan': current_plan},
                    web_redirect='/upgrade'
                )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Upgrade Error:** {str(e)}\n\nPlease try again or contact support."
            )

    def _handle_testmail(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Test email delivery"""
        try:
            from flask_mail import Message

            sender = "sunildessa1001@gmail.com"
            recipient = "divyanshukumar6090@gmail.com"

            msg = Message(
                subject="🧪 OTT Manager Email Test",
                recipients=[recipient],
                body=f"SMTP test from {sender} to {recipient}\nTime: {datetime.now()}",
                sender=sender
            )

            self.mail.send(msg)

            return CommandResponse(
                success=True,
                message=f"✅ **SMTP Test Done**\n\n📧 **From:** {sender}\n📧 **To:** {recipient}\n\nCheck divyanshukumar6090@gmail.com inbox!"
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **SMTP Failed:** {str(e)}\n\n**Solution:** Check App Password for sunildessa1001@gmail.com"
            )
