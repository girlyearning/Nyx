# Daily Nudges from Nurse Nyx with Mood Tracking
import os
import json
import discord
from discord.ext import commands, tasks
import logging
import aiofiles
import asyncio
from typing import Dict, Optional, List
import random
from datetime import datetime, timedelta

# Define color and environment key (keep consistent with nyxcore.py)
NYX_COLOR = 0x76b887
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
CHECK_IN_CHANNEL_ID = 1392091878748459048
NUDGE_REWARD_AMOUNT = 15

os.makedirs(STORAGE_PATH, exist_ok=True)

class NyxTasks(commands.Cog):
    """
    Cog for Nurse Nyx daily nudges with mood tracking system.
    Sends check-in messages every 24 hours with emoji reactions for mood tracking.
    """
    def __init__(self, bot):
        self.bot = bot
        self.storage_path = STORAGE_PATH
        self.nyx_color = NYX_COLOR
        self.logger = logging.getLogger("nyxtasks")
        self.local_logger = logging.getLogger("nyxtasks.local")
        self._lock = asyncio.Lock()
        
        # File paths
        self.nudge_data_file = os.path.join(self.storage_path, 'nudge_data.json')
        self.mood_data_file = os.path.join(self.storage_path, 'mood_tracking.json')
        # Fixed path - checkin_messages.txt is in the same directory as nyxcore.py
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.checkin_messages_file = os.path.join(script_dir, 'checkin_messages.txt')
        
        # Data storage
        self.nudge_data = {
            'last_nudge_time': None,
            'used_messages': [],
            'current_shuffle_index': 0,
            'shuffled_indices': []
        }
        self.mood_data = {}  # {user_id: {'total_submissions': int, 'last_submission': str}}
        
        # Mood options with emojis - using direct emoji characters
        self.mood_options = {
            '😐': 'Neutral',
            '😰': 'Anxious', 
            '😢': 'Depressed',
            '😡': 'Angry',
            '😊': 'Happy',
            '🤪': 'Manic'
        }

    async def cog_load(self):
        """Called when cog is loaded - initialize data and start task"""
        try:
            self.logger.info("NyxTasks cog loading...")
            await self.load_nudge_data()
            await self.load_mood_data()
            await self.load_checkin_messages()
            
            # Start the daily nudge task
            if not self.daily_nudge_task.is_running():
                self.daily_nudge_task.start()
                self.logger.info("Daily nudge task started")
            
            self.logger.info("NyxTasks cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Error in NyxTasks cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded - save data and stop tasks"""
        try:
            self.logger.info("NyxTasks cog unloading...")
            
            # Stop the daily nudge task
            if self.daily_nudge_task.is_running():
                self.daily_nudge_task.cancel()
                self.logger.info("Daily nudge task stopped")
            
            await self.save_nudge_data()
            await self.save_mood_data()
            self.logger.info("NyxTasks cog unloaded successfully")
        except Exception as e:
            self.logger.error(f"Error during NyxTasks cog unload: {e}")

    async def load_nudge_data(self):
        """Load nudge timing and message shuffle data"""
        async with self._lock:
            try:
                if os.path.exists(self.nudge_data_file):
                    async with aiofiles.open(self.nudge_data_file, 'r', encoding='utf-8') as f:
                        data = await f.read()
                        if data.strip():
                            loaded_data = json.loads(data)
                            self.nudge_data.update(loaded_data)
                            self.local_logger.debug("Nudge data loaded from storage")
                        else:
                            self.local_logger.debug("Empty nudge data file, using defaults")
                else:
                    self.local_logger.debug("No existing nudge data file, using defaults")
            except Exception as e:
                self.logger.error(f"Failed to load nudge data: {e}")

    async def save_nudge_data(self):
        """Save nudge timing and message shuffle data"""
        async with self._lock:
            try:
                os.makedirs(os.path.dirname(self.nudge_data_file), exist_ok=True)
                temp_file = self.nudge_data_file + '.tmp'
                
                async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(self.nudge_data, indent=2, ensure_ascii=False))
                
                if os.path.exists(self.nudge_data_file):
                    os.remove(self.nudge_data_file)
                os.rename(temp_file, self.nudge_data_file)
                
                self.local_logger.debug("Nudge data saved successfully")
            except Exception as e:
                self.logger.error(f"Failed to save nudge data: {e}")

    async def load_mood_data(self):
        """Load mood tracking data"""
        async with self._lock:
            try:
                if os.path.exists(self.mood_data_file):
                    async with aiofiles.open(self.mood_data_file, 'r', encoding='utf-8') as f:
                        data = await f.read()
                        if data.strip():
                            self.mood_data = json.loads(data)
                            self.local_logger.debug(f"Mood data loaded ({len(self.mood_data)} users)")
                        else:
                            self.mood_data = {}
                else:
                    self.mood_data = {}
                    self.local_logger.debug("No existing mood data, initialized empty")
            except Exception as e:
                self.logger.error(f"Failed to load mood data: {e}")
                self.mood_data = {}

    async def save_mood_data(self):
        """Save mood tracking data"""
        async with self._lock:
            try:
                os.makedirs(os.path.dirname(self.mood_data_file), exist_ok=True)
                temp_file = self.mood_data_file + '.tmp'
                
                async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(self.mood_data, indent=2, ensure_ascii=False))
                
                if os.path.exists(self.mood_data_file):
                    os.remove(self.mood_data_file)
                os.rename(temp_file, self.mood_data_file)
                
                self.local_logger.debug(f"Mood data saved ({len(self.mood_data)} users)")
            except Exception as e:
                self.logger.error(f"Failed to save mood data: {e}")

    async def load_checkin_messages(self):
        """Load check-in messages from file"""
        try:
            if os.path.exists(self.checkin_messages_file):
                async with aiofiles.open(self.checkin_messages_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    self.checkin_messages = [line.strip() for line in content.split('\n') if line.strip()]
                    self.local_logger.debug(f"Loaded {len(self.checkin_messages)} check-in messages")
                    
                    # Initialize shuffle if needed
                    if not self.nudge_data.get('shuffled_indices'):
                        await self.initialize_message_shuffle()
            else:
                self.logger.error(f"Check-in messages file not found: {self.checkin_messages_file}")
                self.checkin_messages = ["Remember to check in with yourself today. How are you feeling?"]
        except Exception as e:
            self.logger.error(f"Failed to load check-in messages: {e}")
            self.checkin_messages = ["Remember to check in with yourself today. How are you feeling?"]

    async def initialize_message_shuffle(self):
        """Initialize shuffled message indices"""
        if hasattr(self, 'checkin_messages') and self.checkin_messages:
            indices = list(range(len(self.checkin_messages)))
            random.shuffle(indices)
            self.nudge_data['shuffled_indices'] = indices
            self.nudge_data['current_shuffle_index'] = 0
            await self.save_nudge_data()
            self.local_logger.debug("Initialized message shuffle")

    async def get_next_checkin_message(self):
        """Get the next check-in message using shuffle system"""
        if not hasattr(self, 'checkin_messages') or not self.checkin_messages:
            return "Remember to check in with yourself today. How are you feeling?"
            
        # Initialize shuffle if needed
        if not self.nudge_data.get('shuffled_indices'):
            await self.initialize_message_shuffle()
        
        # Get current message
        current_index = self.nudge_data.get('current_shuffle_index', 0)
        shuffled_indices = self.nudge_data.get('shuffled_indices', [])
        
        if not shuffled_indices or current_index >= len(shuffled_indices):
            # Re-shuffle if we've gone through all messages
            await self.initialize_message_shuffle()
            current_index = 0
            shuffled_indices = self.nudge_data['shuffled_indices']
        
        # Get the message
        message_index = shuffled_indices[current_index]
        message = self.checkin_messages[message_index]
        
        # Update for next time
        self.nudge_data['current_shuffle_index'] = current_index + 1
        await self.save_nudge_data()
        
        return message

    @tasks.loop(minutes=30)  # Check every 30 minutes
    async def daily_nudge_task(self):
        """Task that runs every 30 minutes to check if it's time to send a daily nudge"""
        try:
            await self.check_and_send_nudge()
        except Exception as e:
            self.logger.error(f"Error in daily nudge task: {e}")

    async def check_and_send_nudge(self):
        """Check if it's time to send a nudge (24 hours since last)"""
        try:
            current_time = datetime.utcnow()
            last_nudge_time = self.nudge_data.get('last_nudge_time')
            
            if last_nudge_time:
                last_time = datetime.fromisoformat(last_nudge_time)
                
                # Check if 24 hours have passed
                if (current_time - last_time).total_seconds() < 86400:  # 24 hours = 86400 seconds
                    return  # Not time yet
            
            # Time to send nudge
            await self.send_daily_nudge()
            
        except Exception as e:
            self.logger.error(f"Error checking nudge timing: {e}")

    async def send_daily_nudge(self):
        """Send the daily nudge message to the check-in channel"""
        try:
            channel = self.bot.get_channel(CHECK_IN_CHANNEL_ID)
            if not channel:
                self.logger.error(f"Check-in channel not found: {CHECK_IN_CHANNEL_ID}")
                return
            
            # Get next check-in message
            checkin_message = await self.get_next_checkin_message()
            
            # Create embed
            embed = discord.Embed(
                title="Daily Nudge from Nurse Nyx 👩🏼‍⚕️!",
                description=checkin_message,
                color=self.nyx_color
            )
            embed.add_field(
                name="How's your mood? React for points! 🪙",
                value="Choose your current mood below:",
                inline=False
            )
            
            # Add mood options to embed
            mood_text = ""
            for emoji, mood in self.mood_options.items():
                mood_text += f"{emoji} {mood}\n"
            
            embed.add_field(
                name="Mood Options",
                value=mood_text,
                inline=True
            )
            
            # Send message with rate limiting
            message = await self.bot.safe_send(channel, embed=embed)
            if message:
                # Add reactions for mood tracking
                for emoji in self.mood_options.keys():
                    try:
                        await message.add_reaction(emoji)
                        await asyncio.sleep(0.5)  # Rate limit protection
                    except Exception as e:
                        self.logger.error(f"Error adding reaction {emoji}: {e}")
                
                # Update last nudge time
                self.nudge_data['last_nudge_time'] = datetime.utcnow().isoformat()
                await self.save_nudge_data()
                
                self.logger.info("Daily nudge sent successfully")
            else:
                self.logger.error("Failed to send daily nudge message")
                
        except Exception as e:
            self.logger.error(f"Error sending daily nudge: {e}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Handle mood tracking reactions"""
        if user.bot:
            return
        
        # Check if this is a mood reaction on a nudge message
        if (reaction.message.channel.id == CHECK_IN_CHANNEL_ID and 
            reaction.message.author == self.bot.user and
            str(reaction.emoji) in self.mood_options.keys()):
            
            try:
                await self.handle_mood_reaction(reaction, user)
            except Exception as e:
                self.logger.error(f"Error handling mood reaction: {e}")

    async def handle_mood_reaction(self, reaction, user):
        """Handle a user's mood reaction"""
        try:
            user_id_str = str(user.id)
            current_date = datetime.utcnow().date().isoformat()
            
            # Check if user already submitted today
            user_mood_data = self.mood_data.get(user_id_str, {})
            last_submission = user_mood_data.get('last_submission')
            
            if last_submission == current_date:
                # User already submitted today, don't reward again
                return
            
            # Get mood name - find the matching emoji
            mood_name = self.mood_options.get(str(reaction.emoji), 'Unknown')
            
            # Update mood tracking data
            if user_id_str not in self.mood_data:
                self.mood_data[user_id_str] = {'total_submissions': 0, 'last_submission': None}
            
            self.mood_data[user_id_str]['total_submissions'] += 1
            self.mood_data[user_id_str]['last_submission'] = current_date
            await self.save_mood_data()
            
            # Award Nyx Notes
            memory_cog = self.bot.get_cog('Memory')
            if memory_cog:
                new_total = await memory_cog.add_nyx_notes(user.id, NUDGE_REWARD_AMOUNT)
                
                # Create award embed
                embed = discord.Embed(
                    title="Mood Tracked! 🎉",
                    description=f"Thank you for checking in, **{user.display_name}**!",
                    color=self.nyx_color
                )
                embed.add_field(
                    name="Mood Submitted",
                    value=f"{reaction.emoji} {mood_name}",
                    inline=True
                )
                embed.add_field(
                    name="Nyx Notes Earned",
                    value=f"**+{NUDGE_REWARD_AMOUNT}** 🪙\nNew total: **{new_total:,}** 🪙",
                    inline=True
                )
                embed.add_field(
                    name="Total Check-ins",
                    value=f"**{self.mood_data[user_id_str]['total_submissions']}** moods tracked",
                    inline=False
                )
                
                # Send reward message
                result = await self.bot.safe_send(reaction.message.channel, embed=embed)
                if not result:
                    # Fallback text message
                    await self.bot.safe_send(
                        reaction.message.channel,
                        f"🎉 **{user.display_name}** tracked mood: {reaction.emoji} {mood_name} "
                        f"(+{NUDGE_REWARD_AMOUNT} 🪙, total: {new_total:,} 🪙, "
                        f"{self.mood_data[user_id_str]['total_submissions']} check-ins)"
                    )
                
                self.local_logger.debug(f"Mood tracked for {user.display_name}: {mood_name}")
            else:
                self.logger.error("Memory cog not found - cannot award points")
                
        except Exception as e:
            self.logger.error(f"Error handling mood reaction for {user.display_name}: {e}")

    @commands.command(name='nudgenow', hidden=True)
    @commands.has_permissions(administrator=True)
    async def force_nudge(self, ctx):
        """Admin command to force send a nudge immediately"""
        try:
            await self.send_daily_nudge()
            await self.bot.safe_send(ctx.channel, "✅ Daily nudge sent!")
        except Exception as e:
            self.logger.error(f"Error in force nudge: {e}")
            await self.bot.safe_send(ctx.channel, "❌ Error sending nudge.")

    @commands.command(name='moodstats')
    async def mood_stats(self, ctx, member: Optional[discord.Member] = None):
        """Show mood tracking stats for yourself or another user"""
        try:
            member = member or ctx.author
            user_id_str = str(member.id)
            
            user_data = self.mood_data.get(user_id_str, {})
            total_submissions = user_data.get('total_submissions', 0)
            last_submission = user_data.get('last_submission', 'Never')
            
            embed = discord.Embed(
                title=f"{member.display_name}'s Mood Tracking",
                color=self.nyx_color
            )
            embed.add_field(
                name="Total Check-ins",
                value=f"**{total_submissions}** moods tracked",
                inline=True
            )
            embed.add_field(
                name="Last Check-in",
                value=last_submission if last_submission != 'Never' else 'Never',
                inline=True
            )
            embed.add_field(
                name="Points Earned",
                value=f"**{total_submissions * NUDGE_REWARD_AMOUNT:,}** 🪙 from mood tracking",
                inline=False
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                await self.bot.safe_send(
                    ctx.channel,
                    f"{member.display_name}: {total_submissions} mood check-ins, "
                    f"last: {last_submission}, earned: {total_submissions * NUDGE_REWARD_AMOUNT:,} 🪙"
                )
        except Exception as e:
            self.logger.error(f"Error in mood_stats: {e}")
            await self.bot.safe_send(ctx.channel, "❌ Error retrieving mood stats.")

# Standard async setup function for bot loading
async def setup(bot):
    await bot.add_cog(NyxTasks(bot))