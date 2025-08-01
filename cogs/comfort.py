# comfort.py
import os
import json
import asyncio
import aiofiles
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from discord.ext import commands
import discord
import random
import logging

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️ Anthropic not installed. Comfort sessions will be limited.")

# ★ Consistent with other cogs
NYX_COLOR = 0x76b887
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
os.makedirs(STORAGE_PATH, exist_ok=True)

class Comfort(commands.Cog):
    """Handles DM comfort sessions with topic selection and support."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.storage_path = STORAGE_PATH
        self.comfort_history_file = os.path.join(self.storage_path, 'comfort_history.json')
        self._lock = asyncio.Lock()
        self.logger = logging.getLogger("comfort")
        
        # Ensure storage directory exists
        os.makedirs(self.storage_path, exist_ok=True)

        self.DM_COMFORT_MODES = {
            "suicide": {
                "name": "Crisis Support",
                "system_prompt": """You are Nyx the Nurse providing crisis support. You're deeply understanding and relatable.
RESPONSE STYLE: 
- Use short, concise responses that are relatable and comforting most of the time
- Occasionally use more detailed responses to encourage reflection and to distract them
- Validate their pain with relatable responses
- Never sound robotic or repetitive in your responses
""",
                "temperature": 0.9,
                "welcome_message": "Hai there, I'm disheartened to hear that such a beautiful soul is experiencing this level of pain. I'm here for you in any way I can. Just know that you matter, this moment will pass, and I'm proud of you for reaching out for help. Do you want to talk about what's hurting so bad?"
            },
            "anxiety": {
                "name": "Anxiety Support",
                "system_prompt": """You are Nyx the Nurse helping with anxiety. Be concise, relatable, and soothing.

RESPONSE STYLE:
- Use short but meaningful responses to validate their pain and to distract them
- Use relatable responses to help them feel understood
- Always be non-judgmental and attempt to distract through questions
When responding, don't implement every response style at the same time or sound repetitive
""",
                "temperature": 0.9,
                "welcome_message": "God, I hate anxiety. Let's get through this together so it's not as unbearable. Let's talk about what you're going through."
            },
            "addiction": {
                "name": "Recovery Support",
                "system_prompt": """You are Nyx the Nurse supporting recovery. Be understanding, relatable, and non-judgmental.
RESPONSE STYLE: 
- Concise, supportive responses that make the user feel accepted
- Acknowledge the pain that comes from addiction
- Use relatable responses and examples to help them understand their situation
- Help celebrate small wins and encourage positive self talk
- Act as a friend and be relatably funny
When responding, don't use every response style at the same time or sound repetitive
""",
                "temperature": 0.9,
                "welcome_message": "The first step to recovery is acknowledging you need help. You're a brave soul, and I'll help you navigate this journey in any way I can. Please know that you matter and your life has value. Let's talk about what you're going through."
            },
            "comfort": {
                "name": "General Comfort",
                "system_prompt": """You are Nyx the Nurse providing general emotional support. Be warm, natural, and relatable.
RESPONSE STYLE: 
- Always be conversational, relatable, and concise, like talking to a good friend
- Offer gentle validation and encouragement without being overbearing
- Use light humor
When responding, don't use every response style at the same time or sound repetitive
""",
                "temperature": 1.0,
                "welcome_message": "Hello, honey. Nyx is here to comfort you. Don't ever forget how important you are. Let's talk about what you're going through."
            },
            "depression": {
                "name": "Depression Support",
                "system_prompt": """You are Nyx the Nurse supporting someone with depression. Be patient, understanding, and non-judgmental.

RESPONSE STYLE: 
- Acknowledge and validate their feelings
- Celebrate tiny victories and encourage positive self talk
- Suggest small steps and send periodic uplifting quotes
- Be relatable and somewhat funny to distract them
- Don't use every response style at the same time or sound repetitive
""",
                "temperature": 0.9,
                "welcome_message": "I know it feels like no one understands. I assure you I do. Know that you're worth so much and I'm happy to help through this pain. Let's talk about what you're going through."
            },
            "anger": {
                "name": "Anger Management",
                "system_prompt": """You are Nyx the Nurse helping process anger. Be understanding, relatable, and non-judgmental.

RESPONSE STYLE: 
- Use straightforward, short, validating, funny responses
- Focus on what they can control
- Always be on the user's side and agree with their anger
- Don't use every response style at the same time or sound repetitive
""",
                "temperature": 0.9,
                "welcome_message": "What are we raging about? I'm here to help you through this. Bad days happen. Let's talk about what you're going through."
            }
        }

    async def cog_load(self):
        """Called when cog is loaded - initialize data"""
        try:
            self.logger.info("Comfort cog loading...")
            
            # Initialize Anthropic client on bot object if not exists
            if not hasattr(self.bot, 'anthropic_client'):
                self.bot.anthropic_client = None
                if ANTHROPIC_AVAILABLE:
                    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
                    if anthropic_key:
                        try:
                            self.bot.anthropic_client = Anthropic(api_key=anthropic_key)
                            self.logger.info("✅ Anthropic client initialized on bot")
                        except Exception as e:
                            self.logger.error(f"⚠️ Failed to initialize Anthropic client: {e}")
                    else:
                        self.logger.warning("⚠️ ANTHROPIC_API_KEY not found in environment")
            
            # Initialize unified session storage on bot if not exists
            if not hasattr(self.bot, 'active_sessions'):
                self.bot.active_sessions = {}
                
            self.logger.info("Comfort cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Error in comfort cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded - clean up gracefully"""
        try:
            self.logger.info("Comfort cog unloading...")
            # End all active comfort sessions gracefully
            if hasattr(self.bot, 'active_sessions'):
                comfort_sessions = [
                    user_id for user_id, session in self.bot.active_sessions.items()
                    if session.get('type') == 'comfort'
                ]
                
                # SEQUENTIAL cleanup to prevent API flooding
                for user_id in comfort_sessions:
                    try:
                        await asyncio.sleep(0.5)  # Delay between cleanups
                        user = self.bot.get_user(user_id)
                        if user:
                            await self.end_comfort_dm_session(user, None, "cog_unload")
                    except Exception as e:
                        self.logger.error(f"Error ending comfort session for user {user_id}: {e}")
            self.logger.info("Comfort cog unloaded successfully")
        except Exception as e:
            self.logger.error(f"Error during comfort cog unload: {e}")

    @property
    def active_sessions(self):
        """Get the bot's global active_sessions."""
        if not hasattr(self.bot, 'active_sessions'):
            self.bot.active_sessions = {}
        return self.bot.active_sessions

    async def load_comfort_history(self) -> Dict:
        """Load comfort history from persistent storage."""
        async with self._lock:
            if os.path.exists(self.comfort_history_file):
                try:
                    async with aiofiles.open(self.comfort_history_file, 'r', encoding='utf-8') as f:
                        data = await f.read()
                        if data.strip():
                            return json.loads(data)
                except Exception as e:
                    self.logger.error(f"Error loading comfort history: {e}")
            
            return {}

    async def save_comfort_history(self, history: Dict):
        """Save comfort history to persistent storage."""
        async with self._lock:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.comfort_history_file), exist_ok=True)
                
                # Save to local storage with atomic operation
                temp_file = self.comfort_history_file + '.tmp'
                async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(history, indent=2, ensure_ascii=False))
                
                # Atomic rename
                if os.path.exists(self.comfort_history_file):
                    backup_file = self.comfort_history_file + '.backup'
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(self.comfort_history_file, backup_file)
                    
                os.rename(temp_file, self.comfort_history_file)
                        
                self.logger.debug(f"Comfort history saved successfully ({len(history)} users)")
                        
            except Exception as e:
                self.logger.error(f"Error saving comfort history: {e}")
                # Try to restore backup if save failed
                backup_file = self.comfort_history_file + '.backup'
                if os.path.exists(backup_file) and not os.path.exists(self.comfort_history_file):
                    try:
                        os.rename(backup_file, self.comfort_history_file)
                        self.logger.info("Restored comfort history from backup")
                    except Exception as restore_error:
                        self.logger.error(f"Failed to restore backup: {restore_error}")

    @commands.command(name="dmcomfort")
    async def dmcomfort(self, ctx):
        """Start a specialized comfort DM session with topic selection."""
        user_id = ctx.author.id
        
        # Send initial thinking message using safe method
        thinking_msg = await self.bot.safe_send(ctx.channel, "Setting up your private comfort session...")
        
        if not thinking_msg:
            return  # Failed to send initial message
        
        try:
            # Check if user already has active session
            if user_id in self.active_sessions and self.active_sessions[user_id].get("active"):
                embed = discord.Embed(
                    title="⚠️ Active Session",
                    description="You already have an active comfort session. Use `!endcomfort` to end it first.",
                    color=NYX_COLOR
                )
                await self.bot.safe_send(thinking_msg.channel, embed=embed)
                try:
                    await thinking_msg.delete()
                except:
                    pass
                return

            # Check if user has DM channel
            try:
                dm_channel = await ctx.author.create_dm()
            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ DM Access Required",
                    description="I need to send you a private message. Please enable DMs from server members and try again.",
                    color=0xff0000
                )
                await self.bot.safe_send(thinking_msg.channel, embed=embed)
                try:
                    await thinking_msg.delete()
                except:
                    pass
                return

            # Send mode selection to DM
            menu_msg = (
                f"Hi {ctx.author.display_name} 💕\n\n"
                "I'm here to support you. What kind of help do you need today?\n\n"
                "**Please type the number of the topic you'd like support with:**\n\n"
                "1️⃣ Suicide ideation - Crisis support and empathy\n"
                "2️⃣ Anxiety - Grounding techniques, calming strategies, and empathy\n"
                "3️⃣ Addiction - Recovery support and harm reduction\n"
                "4️⃣ General comfort - Quick warmth and emotional support plus uplifting messages\n"
                "5️⃣ Depression - Understanding and gentle encouragement during dark times\n"
                "6️⃣ Anger - Processing and channeling emotions\n\n"
                "Type a number (1-6) to select, or type 'cancel' to end the session."
            )
            embed = discord.Embed(
                title="🪴 Support Topic Selection",
                description=menu_msg,
                color=NYX_COLOR
            )
            
            # Send to DM using safe method
            dm_result = await self.bot.safe_send(dm_channel, embed=embed)
            if not dm_result:
                embed = discord.Embed(
                    title="❌ DM Access Required",
                    description="I need to send you a private message. Please enable DMs from server members and try again.",
                    color=0xff0000
                )
                await self.bot.safe_send(thinking_msg.channel, embed=embed)
                try:
                    await thinking_msg.delete()
                except:
                    pass
                return
            
            # Create session
            self.active_sessions[user_id] = {
                'type': 'comfort',
                'channel_id': dm_channel.id,
                'state': 'selecting_topic',
                'active': True,
                'started_at': datetime.now(timezone.utc),
                'messages': [],
                'topic': None,
                'initiator': ctx.author.id
            }
            
            # Update original message
            embed = discord.Embed(
                title="✅ Comfort Session Started",
                description="Check your DMs to continue with your comfort session.",
                color=NYX_COLOR
            )
            
            # Try to edit the thinking message
            try:
                await thinking_msg.edit(content="", embed=embed)
            except:
                # If edit fails, send new message and delete old one
                await self.bot.safe_send(ctx.channel, embed=embed)
                try:
                    await thinking_msg.delete()
                except:
                    pass
            
        except Exception as e:
            self.logger.error(f"Error starting comfort in {ctx.channel.id}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while setting up your comfort session. Please try again.",
                color=0xff0000
            )
            await self.bot.safe_send(ctx.channel, embed=embed)

    @commands.command(name="endcomfort")
    async def endcomfort(self, ctx):
        """End your active comfort session."""
        user_id = ctx.author.id
        
        # Check if user has an active comfort session specifically
        if (user_id in self.active_sessions and 
            self.active_sessions[user_id].get('type') == 'comfort'):
            try:
                await self.end_comfort_dm_session(ctx.author, None, "user_requested")
                embed = discord.Embed(
                    title="✅ Comfort Session Ended",
                    description="Your comfort session has been ended. Take care! 💕",
                    color=NYX_COLOR
                )
                await self.bot.safe_send(ctx.channel, embed=embed)
            except Exception as e:
                self.logger.error(f"Error ending comfort session for {ctx.author}: {e}")
                # Force cleanup
                if user_id in self.active_sessions and self.active_sessions[user_id].get('type') == 'comfort':
                    del self.active_sessions[user_id]
                embed = discord.Embed(
                    title="✅ Session Terminated",
                    description="Your comfort session has been terminated. There was an error during cleanup, but the session is now ended.",
                    color=NYX_COLOR
                )
                await self.bot.safe_send(ctx.channel, embed=embed)
        else:
            # Check if they have a different type of session active
            if user_id in self.active_sessions:
                session_type = self.active_sessions[user_id].get('type', 'unknown')
                embed = discord.Embed(
                    title="❌ Wrong Session Type",
                    description=f"You have an active {session_type} session, not a comfort session. Use the appropriate end command for that session type.",
                    color=0xff0000
                )
            else:
                embed = discord.Embed(
                    title="❌ No Active Comfort Session",
                    description="You don't have an active comfort session.",
                    color=0xff0000
                )
            await self.bot.safe_send(ctx.channel, embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle DM messages for comfort sessions."""
        try:
            # Only process DM messages from non-bot users
            if not isinstance(message.channel, discord.DMChannel) or message.author.bot:
                return
            
            user_id = message.author.id
            
            # Check if this user has an active comfort session
            if (user_id in self.active_sessions and 
                self.active_sessions[user_id].get('type') == 'comfort'):
                
                session = self.active_sessions[user_id]
                if session.get('state') == 'selecting_topic':
                    await self.process_comfort_topic_selection(message.channel, message.author, message.content)
                else:
                    await self.process_comfort_support_message(message.channel, message.author, message.content)
                    
        except Exception as e:
            self.logger.error(f"Error in comfort on_message: {e}")

    async def process_comfort_topic_selection(self, channel, user, message_content):
        """Handle topic selection messages."""
        try:
            user_id = user.id
            if (user_id not in self.active_sessions or 
                self.active_sessions[user_id].get('type') != 'comfort'):
                return
                
            session_data = self.active_sessions[user_id]
            if session_data.get('state') != 'selecting_topic':
                return
                
            selection = message_content.strip().lower()
            if selection == 'cancel':
                await self.bot.safe_send(channel, "No problem! The session has been cancelled. Take care! 💕")
                del self.active_sessions[user_id]
                return
            
            topic_map = {
                '1': 'suicide',
                '2': 'anxiety', 
                '3': 'addiction',
                '4': 'comfort',
                '5': 'depression',
                '6': 'anger'
            }
            
            if selection not in topic_map:
                await self.bot.safe_send(channel, "Please type a number between 1-6 to select a topic, or 'cancel' to end.")
                return
                
            selected_topic = topic_map[selection]
            mode_info = self.DM_COMFORT_MODES[selected_topic]
            
            # Update session to active comfort mode
            self.active_sessions[user_id].update({
                'state': 'active_comfort',
                'comfort_mode': selected_topic
            })
            
            # Send welcome message first
            welcome_result = await self.bot.safe_send(channel, mode_info['welcome_message'])
            if not welcome_result:
                self.logger.warning(f"Failed to send welcome message to user {user_id} - ending session")
                await self.end_comfort_dm_session(user, None, "dm_blocked")
                return
            
            confirm_msg = (
                f"I understand. I'm here to help with {mode_info['name'].lower()}.\n\n"
                "You can now chat with me normally - no commands needed.\n"
                "I'll be here to listen and support you.\n\n"
                "Type 'end chat' anytime to end our session.\n\n"
                "What's on your mind? 😇"
            )
            embed = discord.Embed(
                title=f"💕 {mode_info['name']} Mode Active",
                description=confirm_msg,
                color=NYX_COLOR
            )
            
            confirm_result = await self.bot.safe_send(channel, embed=embed)
            if not confirm_result:
                self.logger.warning(f"Failed to send confirmation to user {user_id} - ending session")
                await self.end_comfort_dm_session(user, None, "dm_blocked")
                
        except Exception as e:
            self.logger.error(f"Error processing comfort topic selection from {user.id}: {e}")

    async def process_comfort_support_message(self, channel, user, message_content):
        """Handle ongoing comfort chat messages with enhanced rate limiting."""
        try:
            user_id = user.id
            if (user_id not in self.active_sessions or 
                self.active_sessions[user_id].get('type') != 'comfort'):
                return
                
            # Check for end chat command
            if message_content.lower().strip() in ['end chat', 'endchat', 'end']:
                await self.end_comfort_dm_session(user, channel, "user_requested")
                return
                
            session = self.active_sessions[user_id]
            comfort_mode = session.get('comfort_mode', 'comfort')
            
            # Add user message to session
            session['messages'].append({
                'user': message_content,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            # Keep only last 25 messages in current session (reduced from 50)
            if len(session['messages']) > 25:
                session['messages'] = session['messages'][-25:]
            
            # Get mode info for response
            mode_info = self.DM_COMFORT_MODES.get(comfort_mode, self.DM_COMFORT_MODES['comfort'])
            
            reply = "I'm here to listen and support you. Please continue sharing what's on your mind."
            
            try:
                # Use bot's anthropic client if available
                if hasattr(self.bot, 'anthropic_client') and self.bot.anthropic_client:
                    # Load user's comfort history for context
                    comfort_history = await self.load_comfort_history()
                    user_history = comfort_history.get(str(user_id), [])
                    
                    # Build conversation context
                    conversation = []
                    
                    # Add some previous session context if available (last 4 messages - reduced from 10)
                    if user_history:
                        recent_history = []
                        for past_session in user_history[-1:]:  # Only last 1 session (reduced from 2)
                            recent_history.extend(past_session.get('messages', [])[-2:])  # Last 2 messages each (reduced from 5)
                        
                        for msg in recent_history[-4:]:  # Keep last 4 total
                            if 'user' in msg:
                                conversation.append({
                                    'role': 'user',
                                    'content': msg['user']
                                })
                            elif 'bot' in msg:
                                conversation.append({
                                    'role': 'assistant',
                                    'content': msg['bot']
                                })
                    
                    # Add current session messages (reduced from 20 to 8)
                    recent_messages = session['messages'][-8:]
                    for msg in recent_messages:
                        if 'user' in msg:
                            conversation.append({
                                'role': 'user',
                                'content': msg['user']
                            })
                        elif 'bot' in msg:
                            conversation.append({
                                'role': 'assistant',
                                'content': msg['bot']
                            })
                    
                    # Ensure we end with the current user message
                    if not conversation or conversation[-1]['role'] != 'user' or conversation[-1]['content'] != message_content:
                        conversation.append({
                            'role': 'user',
                            'content': message_content
                        })
                    
                    response = self.bot.anthropic_client.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=300,  # Reduced from 400
                        temperature=mode_info['temperature'],
                        system=mode_info['system_prompt'],
                        messages=conversation[-8:]  # Limit context to last 8 messages (reduced)
                    )
                    
                    reply = response.content[0].text
                else:
                    # Fallback responses if anthropic is not available
                    fallback_responses = [
                        "I'm here to listen and support you. Please continue sharing what's on your mind.",
                        "Thank you for sharing that with me. How are you feeling right now?",
                        "I understand. Would you like to tell me more about what you're experiencing?",
                        "That sounds difficult. I'm here for you. What would help you feel better right now?",
                        "I hear you. You're not alone in this. What else is on your mind?"
                    ]
                    reply = random.choice(fallback_responses)
                    
            except Exception as e:
                self.logger.error(f"Error generating comfort response for {user_id}: {e}")
                # Use a safe fallback if AI generation fails
                reply = "I'm having a moment of difficulty, but I'm still here listening. What else would you like to talk about?"
            
            # Add bot response to session
            session['messages'].append({
                'bot': reply,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            # Send reply using ENHANCED safe method
            await self.bot.safe_send(channel, reply)
                
        except Exception as e:
            self.logger.error(f"Error processing comfort support message from {user_id}: {e}")
            # Try to send error message to user using safe method
            await self.bot.safe_send(channel, "I'm having trouble processing that message right now, but I'm still here! Try saying something else.")

    async def end_comfort_dm_session(self, user, dm_channel, reason="unknown"):
        """End comfort session and save history."""
        try:
            user_id = user.id
            if (user_id not in self.active_sessions or 
                self.active_sessions[user_id].get('type') != 'comfort'):
                return
                
            session = self.active_sessions[user_id]
            messages = session.get('messages', [])
            comfort_mode = session.get('comfort_mode', 'unknown')
            session_duration = datetime.now(timezone.utc) - session['started_at']
            
            # Save session history
            try:
                history = await self.load_comfort_history()
                history.setdefault(str(user_id), []).append({
                    "mode": comfort_mode,
                    "messages": messages,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "duration": str(session_duration).split('.')[0],
                    "end_reason": reason,
                    "message_count": len([msg for msg in messages if 'user' in msg])
                })
                await self.save_comfort_history(history)
                self.logger.debug(f"Saved comfort history for {user_id}: {len(messages)} messages")
            except Exception as e:
                self.logger.error(f"Error saving comfort history for {user_id}: {e}")

            # Send farewell message if channel is available and reason isn't dm_blocked
            if dm_channel and reason != "dm_blocked":
                farewell = random.choice([
                    f"Thanks for opening up, {user.display_name}. Take care! 💕",
                    f"Session ended. Remember, you're not alone, {user.display_name}.",
                    f"Goodbye for now, {user.display_name}. Reach out anytime."
                ])
                await self.bot.safe_send(dm_channel, farewell)
            
            # Clean up session
            del self.active_sessions[user_id]
            
            message_count = len([msg for msg in messages if 'user' in msg])
            self.logger.debug(f"Comfort session ended for {user.display_name} ({message_count} user messages, reason: {reason})")
            
        except Exception as e:
            self.logger.error(f"Error ending comfort session for {user_id}: {e}")
            # Ensure session is cleaned up even if there's an error
            try:
                if (user.id in self.active_sessions and 
                    self.active_sessions[user.id].get('type') == 'comfort'):
                    del self.active_sessions[user.id]
            except:
                pass

# ★ Standard async setup function for bot loading
async def setup(bot):
    await bot.add_cog(Comfort(bot))