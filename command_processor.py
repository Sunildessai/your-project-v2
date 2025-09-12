#!/usr/bin/env python3
"""
Unified Command Processor
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
                    message=f"❌ **Unknown command:** `{command_name}`\n\nUse `/help` to see available commands."
                )

            # Check permissions
            user_role = user_data.get('role', 'free')
            if user_role not in cmd_def.permissions:
                return CommandResponse(
                    success=False,
                    message="❌ **Permission denied**\n\nYou don't have permission to use this command."
                )

            # Validate arguments
            is_valid, validation_msg = validate_command_args(command_name, args)
            if not is_valid:
                return CommandResponse(
                    success=False,
                    message=f"❌ **Invalid arguments:** {validation_msg}\n\n**Usage:** {cmd_def.help_text}\n\n**Examples:**\n" + "\n".join([f"• `{ex}`" for ex in cmd_def.examples])
                )

            # Route to specific command handler
            handler_method = f"_handle_{command_name}"
            if hasattr(self, handler_method):
                return getattr(self, handler_method)(args, user_data)
            else:
                return CommandResponse(
                    success=False,
                    message=f"❌ Command handler not implemented: {command_name}"
                )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Error processing command:** {str(e)[:100]}"
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

Use `/help` for all commands!"""

        return CommandResponse(
            success=True,
            message=message,
            data={'user_info': user_data},
            web_redirect='/dashboard'
        )

    def _handle_list(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /list command"""
        try:
            chat_id = user_data.get('telegram_chat_id')
            subscriptions = list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream())

            if not subscriptions:
                return CommandResponse(
                    success=True,
                    message="📋 **No Subscriptions Found**\n\nUse `/add username email service expiry` to add your first subscription!",
                    data={'subscriptions': []}
                )

            message = "📋 **Your Subscriptions:**\n\n"
            today = datetime.now().date()
            subscription_data = []

            for i, sub in enumerate(subscriptions, 1):
                sub_data = sub.to_dict()
                sub_data['id'] = sub.id
                subscription_data.append(sub_data)

                expiry_date = datetime.strptime(sub_data['expiry'], '%Y-%m-%d').date()
                days_left = (expiry_date - today).days

                if days_left < 0:
                    status = "🔴 EXPIRED"
                elif days_left <= 3:
                    status = "🟡 EXPIRING SOON"
                else:
                    status = "✅ ACTIVE"

                message += f"**{i}. {sub_data['service']}** {status}\n"
                message += f"🆔 ID: `{sub.id[:8]}`\n"
                message += f"👤 Username: `{sub_data['username']}`\n"
                message += f"📧 Email: `{sub_data['email']}`\n"
                message += f"💰 Amount: ₹{sub_data.get('amount_received', 'N/A')}\n"
                message += f"📅 Expires: `{sub_data['expiry']}` ({days_left} days)\n"
                message += "─────────────────────\n\n"

            return CommandResponse(
                success=True,
                message=message,
                data={'subscriptions': subscription_data}
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Error fetching subscriptions:** {str(e)}"
            )

    def _handle_add(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /add command"""
        try:
            username, email, service, expiry = args[:4]
            amount = ' '.join(args[4:]) if len(args) > 4 else "0"

            # Validate date
            try:
                datetime.strptime(expiry, '%Y-%m-%d')
            except ValueError:
                return CommandResponse(
                    success=False,
                    message="❌ **Invalid date format!** Use YYYY-MM-DD (e.g., 2025-12-31)"
                )

            # Check user limits
            chat_id = user_data.get('telegram_chat_id')
            current_count = len(list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream()))

            max_subs = user_data.get('max_subscriptions', 5)
            if max_subs != 999999 and current_count >= max_subs:
                return CommandResponse(
                    success=False,
                    message="❌ **Subscription limit reached!**\n\nUpgrade your plan to add more subscriptions.",
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

            doc_ref = self.db.collection('subscriptions').add(subscription_data)

            return CommandResponse(
                success=True,
                message=f"✅ **Subscription Added!**\n\n🎬 Service: {service}\n👤 Username: {username}\n📧 Email: {email}\n💰 Amount: ₹{amount}\n📅 Expiry: {expiry}",
                data={'subscription_id': doc_ref[1].id, 'subscription': subscription_data},
                web_redirect='/dashboard'
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Error adding subscription:** {str(e)}"
            )

    def _handle_delete(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /delete command"""
        try:
            sub_id = args[0]
            chat_id = user_data.get('telegram_chat_id')

            # Find subscription
            all_subs = list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream())
            target_sub = None
            target_id = None

            for sub in all_subs:
                if sub.id == sub_id or sub.id.startswith(sub_id):
                    target_sub = sub.to_dict()
                    target_id = sub.id
                    break

            if not target_sub:
                available_ids = [sub.id[:8] for sub in all_subs[:5]]
                ids_text = '\n'.join([f"• `{sub_id}`" for sub_id in available_ids]) if available_ids else "• No subscriptions found"

                return CommandResponse(
                    success=False,
                    message=f"❌ **Subscription not found!**\n\n🔍 **Searched for:** `{sub_id}`\n\n**Available IDs:**\n{ids_text}\n\nUse `/list` to see all subscriptions."
                )

            # Delete subscription
            self.db.collection('subscriptions').document(target_id).delete()

            return CommandResponse(
                success=True,
                message=f"✅ **Successfully Deleted!**\n\n🎬 **Service:** {target_sub.get('service', 'Unknown')}\n👤 **Username:** {target_sub.get('username', 'Unknown')}\n📧 **Email:** {target_sub.get('email', 'Unknown')}\n🗑️ **ID:** `{target_id[:8]}`",
                data={'deleted_subscription': target_sub},
                web_redirect='/dashboard'
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Delete Error:** {str(e)[:100]}"
            )

    def _handle_search(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /search command"""
        try:
            search_query = args[0].lower()
            chat_id = user_data.get('telegram_chat_id')

            subscriptions = list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream())

            if not subscriptions:
                return CommandResponse(
                    success=True,
                    message="📋 **No subscriptions found**\n\nAdd subscriptions first using `/add`",
                    data={'results': []}
                )

            # Filter subscriptions
            matching_subs = []
            for sub in subscriptions:
                sub_data = sub.to_dict()
                username = sub_data.get('username', '').lower()
                email = sub_data.get('email', '').lower()
                service = sub_data.get('service', '').lower()

                if (search_query in username or search_query in email or search_query in service):
                    sub_data['id'] = sub.id
                    matching_subs.append(sub_data)

            if not matching_subs:
                return CommandResponse(
                    success=True,
                    message=f"🔍 **No subscriptions found** for `{args[0]}`\n\nTry searching for:\n• Service name (e.g., Netflix)\n• Username (e.g., john_netflix)\n• Email (e.g., john@gmail.com)",
                    data={'results': []}
                )

            # Format results
            message = f"🔍 **Search Results for** `{args[0]}`:\n\n"
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
                message += "─────────────────────\n\n"

            return CommandResponse(
                success=True,
                message=message,
                data={'results': matching_subs}
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Search Error:** {str(e)}"
            )

    def _handle_help(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /help command"""
        try:
            user_role = user_data.get('role', 'free')
            available_commands = get_commands_for_role(user_role)

            if args and args[0]:
                # Help for specific command
                cmd_name = args[0].lower()
                cmd_def = get_command(cmd_name)

                if not cmd_def or cmd_name not in available_commands:
                    return CommandResponse(
                        success=False,
                        message=f"❌ **Command not found or not available:** `{cmd_name}`"
                    )

                message = f"📖 **Help for /{cmd_name}**\n\n"
                message += f"**Description:** {cmd_def.help_text}\n\n"
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
                message = "📖 **Available Commands:**\n\n"

                for cmd_name, cmd_def in available_commands.items():
                    message += f"**/{cmd_name}** - {cmd_def.description}\n"

                message += "\n💡 Use `/help command_name` for detailed help on any command!"

                return CommandResponse(
                    success=True,
                    message=message,
                    data={'available_commands': list(available_commands.keys())}
                )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Help Error:** {str(e)}"
            )

    def _handle_stats(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /stats command"""
        try:
            chat_id = user_data.get('telegram_chat_id')
            subscriptions = list(self.db.collection('subscriptions').where('telegram_chat_id', '==', chat_id).stream())

            total_subs = len(subscriptions)
            active_subs = 0
            expiring_subs = 0
            expired_subs = 0

            today = datetime.now().date()

            for sub in subscriptions:
                sub_data = sub.to_dict()
                try:
                    expiry_date = datetime.strptime(sub_data['expiry'], '%Y-%m-%d').date()
                    days_left = (expiry_date - today).days

                    if days_left < 0:
                        expired_subs += 1
                    elif days_left <= 7:
                        expiring_subs += 1
                    else:
                        active_subs += 1
                except:
                    continue

            plan_info = self.subscription_plans[user_data['plan_type']]

            message = f"""📊 **Account Statistics**

👤 **Account Info:**
🆔 ID: `{user_data['unique_id']}`
📦 Plan: {plan_info['name']}
🎭 Role: {user_data['role'].title()}

📋 **Subscriptions:**
📈 Total: {total_subs}/{user_data['max_subscriptions']}
✅ Active: {active_subs}
🟡 Expiring (≤7 days): {expiring_subs}
🔴 Expired: {expired_subs}

📅 **Plan Details:**
💰 Price: {plan_info['price']}
⏳ Validity: {'Lifetime' if not user_data.get('expiry_date') else user_data['expiry_date']}"""

            return CommandResponse(
                success=True,
                message=message,
                data={
                    'stats': {
                        'total_subscriptions': total_subs,
                        'active_subscriptions': active_subs,
                        'expiring_subscriptions': expiring_subs,
                        'expired_subscriptions': expired_subs,
                        'plan_info': plan_info,
                        'user_info': user_data
                    }
                }
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Stats Error:** {str(e)}"
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
                    message="✅ **No subscriptions expiring** in the next 7 days!"
                )

            # Send email reminder
            msg = Message(
                subject="🔔 OTT Subscription Expiry Reminder",
                recipients=[expiring_subs[0]['email']],
                html=f"""
                <h2>Dear {user_data['telegram_username']},</h2>
                <p>You have {len(expiring_subs)} subscription(s) expiring soon:</p>
                <ul>
                {"".join([f"<li>{sub['service']} - Expires: {sub['expiry']}</li>" for sub in expiring_subs])}
                </ul>
                <p>Please renew to avoid service interruption.</p>
                <p>Best regards,<br>OTT Manager Team</p>
                """
            )

            self.mail.send(msg)

            return CommandResponse(
                success=True,
                message=f"✅ **Reminder sent!** Email notification sent for {len(expiring_subs)} expiring subscription(s).",
                data={'expiring_subscriptions': expiring_subs}
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Reminder Error:** {str(e)}"
            )

    def _handle_upgrade(self, args: List[str], user_data: Dict) -> CommandResponse:
        """Handle /upgrade command"""
        try:
            if args and args[0]:
                plan_type = args[0].lower()
                if plan_type not in self.subscription_plans:
                    available_plans = list(self.subscription_plans.keys())
                    return CommandResponse(
                        success=False,
                        message=f"❌ **Invalid plan:** `{plan_type}`\n\n**Available plans:** {', '.join(available_plans)}"
                    )

                plan_info = self.subscription_plans[plan_type]
                return CommandResponse(
                    success=True,
                    message=f"💎 **{plan_info['name']}**\n\n💰 **Price:** {plan_info['price']}\n📋 **Subscriptions:** {plan_info['max_subscriptions']}\n\n**Features:**\n" + "\n".join([f"• {feature}" for feature in plan_info['features']]) + "\n\n🔗 Contact admin to upgrade!",
                    data={'plan_info': plan_info},
                    web_redirect='/upgrade'
                )
            else:
                # Show all plans
                message = "💎 **Available Plans:**\n\n"
                for plan_name, plan_info in self.subscription_plans.items():
                    if plan_name == user_data['plan_type']:
                        message += f"**{plan_info['name']} (Current)** ✅\n"
                    else:
                        message += f"**{plan_info['name']}**\n"
                    message += f"💰 {plan_info['price']}\n"
                    message += f"📋 {plan_info['max_subscriptions']} subscriptions\n"
                    message += "─────────────────\n\n"

                message += "Use `/upgrade plan_name` for details!"

                return CommandResponse(
                    success=True,
                    message=message,
                    data={'all_plans': self.subscription_plans, 'current_plan': user_data['plan_type']},
                    web_redirect='/upgrade'
                )

        except Exception as e:
            return CommandResponse(
                success=False,
                message=f"❌ **Upgrade Error:** {str(e)}"
            )
