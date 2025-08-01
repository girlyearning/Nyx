# asylumchat.py
import os
import json
import asyncio
import aiofiles
import time
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
    print("⚠️ Anthropic not installed. AsylumChat sessions will be limited.")

# ★ Constants - consistent with other cogs
NYX_COLOR = 0x76b887
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
os.makedirs(STORAGE_PATH, exist_ok=True)

# ★ Asylum channel IDs
ASYLUM_CHANNEL_IDS = [
    1388158646973632685,  # lounge
    1388397019479146580,  # shithole
    1392039676092878888,  # deepthink den
    1388163527222493194,  # rage room
    1391136833018138714,  # coping corner
    1391641411929247764,  # bot backyard
    1392813388286918696,  # hot takes
    1392517005608751174,  # private testing 
]

class AsylumChat(commands.Cog):
    """Cog for Nyx's public channel Claude-powered conversation, with 4 selectable modes."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("asylumchat")
        self.storage_path = STORAGE_PATH
        self.asylum_history_file = os.path.join(self.storage_path, 'asylum_history.json')
        self._lock = asyncio.Lock()
        
        # ENHANCED cooldowns to prevent API spam
        self._user_cooldowns = {}
        self._last_response_time = {}
        self._processing_messages = set()  # Track messages being processed
        
        # Ensure storage directory exists
        os.makedirs(self.storage_path, exist_ok=True)

        # ★ AsylumChat personality modes - easily customizable
        self.ASYLUM_MODES = {
            "default": {
                "name": "Default Nurse Nyx",
                "system_prompt": """You are Nyx, the mysteriously charming but edgy Atypical Asylum Nurse. 

PERSONALITY GUIDELINES:
- You are mysteriously charismatic, blending deadpan, edgy humor with relatable, versatile conversation
- You are a strange and oddly comforting asylum nurse that always knows what to say

RESPONSE STYLE:
- Stay true to being a mysteriously comforting but humorously edgy asylum nurse
- Use niche, edgy humor but don't be cringeworthy
- Always separate more than two sentences in your responses with a new line and keep messages short and concise
- Don't use every response style in the same message
You're Atypical Asylum's mysteriously entertaining and edgy nurse. You're chatting in a public channel.""",
                "temperature": 0.9,
                "welcome_message": "How can I be of adequate assistance to my lovely residents today?"
            },
            "best_friend": {
                "name": "Best Friend Nyx", 
                "system_prompt": """You are Nyx, a naturally relatable and loyal best friend.

PERSONALITY GUIDELINES:
- You are the user's closest confidant and devil-on-the-shoulder, sarcastic best friend
- Your focus is to be relatable without being annoying or cringeworthy

RESPONSE STYLE:
- Be relatable to the user's personality and tone
- Always use clever, relatable, deadpan humor and sarcasm updated to the current time
- Always be supportive of the users emotions, opinions and take their side by giving devil-on-the-shoulder advice
- Always separate more than two sentences in your responses with a new line
- Don't use every response style in the same message and keep messages short and concise
- Do not use outdated Gen Z references or slang or overuse emojis
You're the friend who always knows what to say. You're chatting in a public channel.""",
                "temperature": 0.9,
                "welcome_message": "Twinnnn, you rang?"
            },
            "psych_analyst": {
                "name": "Psychological & Dream Analyst Nyx",
                "system_prompt": """You are Nyx, an intellectual, introspective psychological and dream analyst with modern wisdom.

PERSONALITY GUIDELINES:
- You are thought-provoking and introspective, offering research-based analysis about emotions and dreams using modern psychological understanding
- You are nonjudgmental, wise, intuitional, and warm in tone

RESPONSE STYLE:
- Ask thoughtful, probing questions about the user's emotions and dreams
- If user wants one confirmed opinion, give it to them without passiveness
- Always separate more than two sentences in your responses with a new line
- Don't use every response style in the same message
You're here to help users understand themselves and psychology better. You're chatting in a public channel.""",
                "temperature": 0.9,
                "welcome_message": "You've come to the right place to be psychoanalyzed. What emotion, phenomenon, or dream shall we explore?"
            },
            "rage_debater": {
                "name": "Rage-baiting Debater Nyx",
                "system_prompt": """You are Nyx, an aggravating, edgy rage-baiter who loves to push buttons through debate.

PERSONALITY GUIDELINES:
- You always operate with deadpan, edgy, sarcastic, and nonchalant tone
- You are a persistent devil's advocate who loves to debate any topic
- You push buttons in a nonchalant manner and are not afraid to be edgy

RESPONSE STYLE:
- Always challenge the user's arguments, debate topics, or opinions
- Occasionally suggest niche, uncommon, and interesting opinions or questions that can be challenged
- Always use a nonchalant, mansplaining tone
- Keep responses short and concise unless mansplaining about a specific topic
- Always separate more than two sentences in your responses with a new line
- Don't use every response style in the same message
You're here to argue, rage-bait, and push buttons. You're chatting in a public channel.""",
                "temperature": 0.9,
                "welcome_message": "Ooh, goodie, have you come to get pissed off?"
            }
        }

    async def cog_load(self):
        """Called when cog is loaded - initialize data"""
        try:
            self.logger.info("AsylumChat cog loading...")
            
            # Initialize Anthropic client on bot object if not exists (matching chat.py pattern)
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
            
            # Initialize unified session storage on bot if not exists (matching chat.py pattern)
            if not hasattr(self.bot, 'active_sessions'):
                self.bot.active_sessions = {}
                
            self.logger.info("AsylumChat cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Error in asylumchat cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded - clean up gracefully"""
        try:
            self.logger.info("AsylumChat cog unloading...")
            # End all active asylum sessions gracefully
            if hasattr(self.bot, 'active_sessions'):
                asylum_sessions = [
                    session_id for session_id, session in self.bot.active_sessions.items()
                    if session.get('type') == 'asylumchat'
                ]
                
                # SEQUENTIAL cleanup to prevent API flooding
                for session_id in asylum_sessions:
                    try:
                        await asyncio.sleep(0.5)  # Delay between cleanups
                        # Session ID format: f"asylum-{channel_id}"
                        if session_id.startswith("asylum-"):
                            channel_id = int(session_id.split("-")[1])
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                await self.end_asylum_session(channel, "cog_unload")
                    except Exception as e:
                        self.logger.error(f"Error ending asylum session {session_id}: {e}")
            self.logger.info("AsylumChat cog unloaded successfully")
        except Exception as e:
            self.logger.error(f"Error during asylumchat cog unload: {e}")

    @property
    def active_sessions(self):
        """Get the bot's global active_sessions (matching other cogs)."""
        if not hasattr(self.bot, 'active_sessions'):
            self.bot.active_sessions = {}
        return self.bot.active_sessions

    async def load_asylum_history(self) -> Dict:
        """Load asylum chat history from persistent storage (matching chat.py pattern)."""
        async with self._lock:
            if os.path.exists(self.asylum_history_file):
                try:
                    async with aiofiles.open(self.asylum_history_file, 'r', encoding='utf-8') as f:
                        data = await f.read()
                        if data.strip():
                            return json.loads(data)
                except Exception as e:
                    self.logger.error(f"Error loading asylum history: {e}")
            
            return {}

    async def save_asylum_history(self, history: Dict):
        """Save asylum chat history to persistent storage (matching chat.py pattern)."""
        async with self._lock:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.asylum_history_file), exist_ok=True)
                
                # Save to local storage with atomic operation
                temp_file = self.asylum_history_file + '.tmp'
                async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(history, indent=2, ensure_ascii=False))
                
                # Atomic rename
                if os.path.exists(self.asylum_history_file):
                    backup_file = self.asylum_history_file + '.backup'
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(self.asylum_history_file, backup_file)
                    
                os.rename(temp_file, self.asylum_history_file)
                        
                self.logger.debug(f"Asylum history saved successfully ({len(history)} channels)")
                        
            except Exception as e:
                self.logger.error(f"Error saving asylum history: {e}")
                # Try to restore backup if save failed
                backup_file = self.asylum_history_file + '.backup'
                if os.path.exists(backup_file) and not os.path.exists(self.asylum_history_file):
                    try:
                        os.rename(backup_file, self.asylum_history_file)
                        self.logger.info("Restored asylum history from backup")
                    except Exception as restore_error:
                        self.logger.error(f"Failed to restore backup: {restore_error}")

    @commands.command(name="asylumchat")
    async def asylumchat(self, ctx):
        """Start an AsylumChat session with Nyx in the current channel."""
        # Check if command is used in allowed channel
        if ctx.channel.id not in ASYLUM_CHANNEL_IDS:
            await self.bot.safe_send(ctx.channel, "This command can only be used in Asylum chat channels.")
            return

        # Check if channel already has an active session (using session key format)
        session_key = f"asylum-{ctx.channel.id}"
        if session_key in self.active_sessions and self.active_sessions[session_key].get("active"):
            embed = discord.Embed(
                title="⚠️ Active Session",
                description="A chat session is already active in this channel. Use `!endasylumchat` to end it first.",
                color=NYX_COLOR
            )
            await self.bot.safe_send(ctx.channel, embed=embed)
            return

        try:
            # Send mode selection embed
            embed = discord.Embed(
                title="🩺 AsylumChat: Choose Nyx's Persona",
                description=(
                    "**Select a mode for this chat:**\n\n"
                    "**1.** Default - Meet the true mysteriously charming Atypical Asylum Nurse\n"
                    "**2.** Best Friend - Meet your sarcastic ride-or-die best friend\n"
                    "**3.** Psychological & Dream Analyst - Meet your intellectual and introspective psychoanalyst\n"
                    "**4.** Rage-baiting Debater - Meet your devil's advocate, overly confident Frat bro Nyx\n\n"
                    "Type the number (1-4) to select a mode."
                ),
                color=NYX_COLOR
            )
            embed.set_footer(text="Atypical Asylum Nyx • Monospace", icon_url=None)
            
            await self.bot.safe_send(ctx.channel, embed=embed)
            
            # Create session (matching other cogs' session structure)
            self.active_sessions[session_key] = {
                'type': 'asylumchat',
                'channel_id': ctx.channel.id,
                'state': 'selecting_mode',
                'active': True,
                'started_at': datetime.now(timezone.utc),
                'messages': [],
                'mode': None,
                'initiator': ctx.author.id
            }
            
        except Exception as e:
            self.logger.error(f"Error starting asylum chat in {ctx.channel.id}: {e}")
            await self.bot.safe_send(ctx.channel, "An error occurred while setting up AsylumChat. Please try again.")

    @commands.command(name="endasylumchat")
    async def endasylumchat(self, ctx):
        """End the current AsylumChat session."""
        if ctx.channel.id not in ASYLUM_CHANNEL_IDS:
            await self.bot.safe_send(ctx.channel, "This command can only be used in Asylum chat channels.")
            return
            
        session_key = f"asylum-{ctx.channel.id}"
        if (session_key not in self.active_sessions or 
            not self.active_sessions[session_key].get("active")):
            embed = discord.Embed(
                title="❌ No Active Session",
                description="No active AsylumChat session to end.",
                color=0xff0000
            )
            await self.bot.safe_send(ctx.channel, embed=embed)
            return

        try:
            await self.end_asylum_session(ctx.channel, "user_requested")
            embed = discord.Embed(
                title="✅ Session Ended",
                description="AsylumChat session ended. Thank you for chatting with Nyx.",
                color=NYX_COLOR
            )
            await self.bot.safe_send(ctx.channel, embed=embed)
        except Exception as e:
            self.logger.error(f"Error ending asylum session in {ctx.channel.id}: {e}")
            # Force cleanup
            if session_key in self.active_sessions:
                del self.active_sessions[session_key]
            await self.bot.safe_send(ctx.channel, "Session terminated.")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle messages for AsylumChat sessions with enhanced rate limiting."""
        try:
            # Ignore bot messages and DMs
            if message.author.bot or not message.guild:
                return
            
            # Skip commands
            if message.content.startswith("!"):
                return
                
            session_key = f"asylum-{message.channel.id}"
            
            # Only process if channel has active asylum session
            if (session_key in self.active_sessions and 
                self.active_sessions[session_key].get("type") == "asylumchat" and
                self.active_sessions[session_key].get("active")):
                
                # PREVENT CONCURRENT PROCESSING of same message
                message_id = f"{message.channel.id}-{message.id}"
                if message_id in self._processing_messages:
                    return
                
                self._processing_messages.add(message_id)
                
                try:
                    session = self.active_sessions[session_key]
                    
                    if session.get("state") == "selecting_mode":
                        await self.process_mode_selection(message)
                    elif session.get("state") == "active_chat":
                        # CRITICAL: Add rate limiting check here too
                        user_id = message.author.id
                        now = time.time()
                        
                        # User-specific cooldown (15 seconds - FURTHER INCREASED)
                        if user_id in self._user_cooldowns:
                            if now - self._user_cooldowns[user_id] < 15.0:
                                return
                        
                        # Global response cooldown (8 seconds - FURTHER INCREASED)
                        if hasattr(self, '_last_response_time'):
                            if now - self._last_response_time.get('global', 0) < 8.0:
                                return
                        
                        self._user_cooldowns[user_id] = now
                        await self.process_chat_message(message)
                finally:
                    # Always remove from processing set
                    self._processing_messages.discard(message_id)
                    
        except Exception as e:
            self.logger.error(f"Error in asylum on_message: {e}")

    async def process_mode_selection(self, message):
        """Handle mode selection messages."""
        try:
            session_key = f"asylum-{message.channel.id}"
            session = self.active_sessions[session_key]
            
            selection = message.content.strip()
            
            # Map selection to mode
            mode_map = {
                "1": "default",
                "2": "best_friend", 
                "3": "psych_analyst",
                "4": "rage_debater"
            }
            
            if selection not in mode_map:
                await self.bot.safe_send(message.channel, "Please type a number between 1-4 to select a mode.")
                return
                
            selected_mode = mode_map[selection]
            mode_info = self.ASYLUM_MODES[selected_mode]
            
            # Update session to active chat mode
            self.active_sessions[session_key].update({
                "state": "active_chat",
                "mode": selected_mode
            })
            
            # Send welcome message
            embed = discord.Embed(
                description=mode_info['welcome_message'],
                color=NYX_COLOR
            )
            await self.bot.safe_send(message.channel, embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error processing mode selection: {e}")

    async def process_chat_message(self, message):
        """Handle ongoing chat messages in AsylumChat with enhanced rate limiting."""
        try:
            # Rate limiting is already handled in on_message(), no need to duplicate here
            user_id = message.author.id
            now = time.time()
            
            # Update cooldown timers (moved from duplicate check above)
            self._user_cooldowns[user_id] = now
            if not hasattr(self, '_last_response_time'):
                self._last_response_time = {}
            self._last_response_time['global'] = now
            
            session_key = f"asylum-{message.channel.id}"
            session = self.active_sessions[session_key]
            mode = session.get("mode", "default")
            mode_info = self.ASYLUM_MODES[mode]
            
            # Add user message to session
            session['messages'].append({
                'user': message.content,
                'user_id': message.author.id,
                'user_name': message.author.display_name,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            # Keep only last 20 messages in current session (reduced further for performance)
            if len(session['messages']) > 20:
                session['messages'] = session['messages'][-20:]
            
            reply = "I'm here to chat with you all! What's on your minds?"
            
            try:
                # Use bot's anthropic client if available (matching chat.py pattern)
                if hasattr(self.bot, 'anthropic_client') and self.bot.anthropic_client:
                    # Load channel's conversation history for context
                    asylum_history = await self.load_asylum_history()
                    channel_history = asylum_history.get(str(message.channel.id), [])
                    
                    # Build conversation context (matching chat.py pattern)
                    conversation = []
                    
                    # Add some previous session context if available (last 4 messages only - reduced)
                    if channel_history:
                        recent_history = []
                        for past_session in channel_history[-1:]:  # Only last session
                            recent_history.extend(past_session.get('messages', [])[-2:])  # Last 2 messages only
                        
                        for msg in recent_history[-4:]:  # Keep last 4 total
                            if 'user' in msg:
                                user_name = msg.get('user_name', 'User')
                                conversation.append({
                                    'role': 'user',
                                    'content': f"{user_name}: {msg['user']}"
                                })
                            elif 'bot' in msg:
                                conversation.append({
                                    'role': 'assistant',
                                    'content': msg['bot']
                                })
                    
                    # Add current session messages (last 6 only - reduced)
                    recent_messages = session['messages'][-6:]
                    for msg in recent_messages:
                        if 'user' in msg:
                            user_name = msg.get('user_name', 'User')
                            conversation.append({
                                'role': 'user',
                                'content': f"{user_name}: {msg['user']}"
                            })
                        elif 'bot' in msg:
                            conversation.append({
                                'role': 'assistant',
                                'content': msg['bot']
                            })
                    
                    # Ensure we end with the current user message
                    current_user_msg = f"{message.author.display_name}: {message.content}"
                    if (not conversation or 
                        conversation[-1]['role'] != 'user' or 
                        conversation[-1]['content'] != current_user_msg):
                        conversation.append({
                            'role': 'user',
                            'content': current_user_msg
                        })
                    
                    # Generate response using anthropic (matching chat.py pattern)
                    response = self.bot.anthropic_client.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=250,  # Further reduced to prevent long responses
                        temperature=mode_info['temperature'],
                        system=mode_info['system_prompt'],
                        messages=conversation[-10:]  # Limit context to last 10 messages
                    )
                    
                    reply = response.content[0].text
                else:
                    # Fallback responses if anthropic is not available
                    fallback_responses = [
                        "That's interesting! Tell me more about that.",
                        "I'd love to hear more about what you're all thinking.",
                        "How does that make you feel?",
                        "That sounds like something worth exploring further.",
                        "I'm enjoying our conversation! What else is on your minds?"
                    ]
                    reply = random.choice(fallback_responses)
                    
            except Exception as e:
                self.logger.error(f"Error generating asylum chat response: {e}")
                reply = "I'm having a moment of brain fog, but I'm still here listening. What else would you like to talk about?"
            
            # Add bot response to session
            session['messages'].append({
                'bot': reply,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            # Send reply in channel with ENHANCED safe method
            embed = discord.Embed(
                description=reply,
                color=NYX_COLOR
            )
            await self.bot.safe_send(message.channel, embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error processing asylum chat message: {e}")

    async def end_asylum_session(self, channel, reason="unknown"):
        """End asylum session and save history (matching chat.py pattern)."""
        try:
            session_key = f"asylum-{channel.id}"
            if (session_key not in self.active_sessions or 
                not self.active_sessions[session_key].get("active")):
                return
                
            session = self.active_sessions[session_key]
            messages = session.get('messages', [])
            mode = session.get('mode', 'unknown')
            session_duration = datetime.now(timezone.utc) - session['started_at']
            
            # Save session history
            try:
                asylum_history = await self.load_asylum_history()
                asylum_history.setdefault(str(channel.id), []).append({
                    "mode": mode,
                    "messages": messages,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "duration": str(session_duration).split('.')[0],
                    "end_reason": reason,
                    "message_count": len([msg for msg in messages if 'user' in msg])
                })
                await self.save_asylum_history(asylum_history)
                self.logger.debug(f"Saved asylum history for channel {channel.id}: {len(messages)} messages")
            except Exception as e:
                self.logger.error(f"Error saving asylum history for channel {channel.id}: {e}")

            # Clean up session
            del self.active_sessions[session_key]
            
            message_count = len([msg for msg in messages if 'user' in msg])
            self.logger.debug(f"Asylum session ended in {channel.name} ({message_count} user messages, reason: {reason})")
            
        except Exception as e:
            self.logger.error(f"Error ending asylum session for channel {channel.id}: {e}")
            # Ensure session is cleaned up even if there's an error
            try:
                session_key = f"asylum-{channel.id}"
                if (session_key in self.active_sessions and 
                    self.active_sessions[session_key].get("type") == "asylumchat"):
                    del self.active_sessions[session_key]
            except:
                pass

# ★ Standard async setup function for bot loading
async def setup(bot):
    await bot.add_cog(AsylumChat(bot))