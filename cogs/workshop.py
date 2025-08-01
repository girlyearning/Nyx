import discord
from discord.ext import commands
from datetime import datetime
import os
import logging
import json
import aiofiles
import asyncio
import random

# ★ Channel and reward constants
WORKSHOP_CHANNEL_ID = 1392093043800412160
WORKSHOP_REWARD = 20
NYX_COLOR = 0x76b887  # Consistent with house embed color

# ★ File paths (match persistent storage expectations)
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
os.makedirs(STORAGE_PATH, exist_ok=True)
SUBMISSIONS_FILE = os.path.join(STORAGE_PATH, "workshop_submissions.json")
PROMPT_HISTORY_FILE = os.path.join(STORAGE_PATH, "weekend_prompt_history.json")

class Workshop(commands.Cog):
    """Cog for handling weekly workshop submissions and points."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("Workshop")
        self._lock = asyncio.Lock()  # Add lock for file operations
        
        # ★ Workshop prompt list for various activities
        self.prompt_prompts = [
            "What's something that made you smile today?",
            "Describe a challenge you overcame recently.",
            "What's a goal you're working towards?",
            "Share a memory that always makes you laugh.",
            "What's something you're grateful for right now?",
            "Describe your ideal day from start to finish.",
            "What's a skill you'd like to learn?",
            "Share something that's been on your mind lately.",
            "What's one thing you're proud of accomplishing recently?",
            "Describe a place where you feel most at peace.",
            "What advice would you give to your younger self?",
            "Share a moment when you felt truly connected to someone.",
            "What's a small act of kindness you've witnessed or experienced?",
            "Describe a time when you stepped out of your comfort zone.",
            "What were your childhood career dreams/goals? How do they compare to what you want to do now?",
            "Which year comes to mind when you think about the best nostalgia? Why did that year carry the best memories?",
            "Describe your childhood in one word, or a single phrase. If this inspires you to talk more about it, go ahead.",
            "What posters did you have on your wall growing up or want to have?",
            "What instance immediately comes to mind when you remember a meaningful display of kindness?",
            "Who are some people in history you admire?",
            "Who was your first best friend? Tell me about them. Why did you get along so well?",
            "Who was your first love? Tell me about them. Why did they stand out more than others?",
            "What was your first job and when did you get it? What do you wish it would've been?",
            "Describe the experience of your first kiss or first time.",
            "Describe the experience of your first time being drunk/high.",
            "Have you ever gotten in trouble with the law? If you were to, what would it most likely be for?",
            "What was the age you actually became an adult, if you feel you have.",
            "Who or what has had the greatest impact on your life, negatively or positively?",
            "What's one of the hardest things you've ever had to do? Do you regret it or did it need to be done?",
            "If I could do it all over again, I would change...",
            "The teacher that had the most influence on my life was...",
            "Describe your parents, how you feel about them, and how they've influenced you.",
            "The long-lost childhood possession that I would love to see again is...",
            "The one thing I regret most about my life or decisions is...",
            "Some things I've been addicted to include...",
            "I was most happy when...",
            "I will never forgive...",
            "Something I'm glad I tried but will never do again is...",
            "The 3-5 best things I've ever had or done in my life are...",
            "The 3-5 things I want to do but have never done are...",
            "I wish I never met...",
            "The one person I've been most jealous of is...",
            "Someone I miss is...",
            "The last time I said I love you was...",
            "Describe your greatest heartbreak or loss.",
            "Something I feel guilty about is...",
            "My life story in 3 sentences is...",
            "My top 3 favorite bands are...",
            "My top 3 favorite songs are...",
            "My top 3 favorite movies are...",
            "My top 3 favorite TV shows are...",
            "My top 3 favorite books are...",
            "My top 3 favorite games are...",
            "My top 3 favorite places I've been are...",
            "My top 3 favorite foods are...",
            "My top 3 favorite colors are...",
            "My top 3 favorite animals are...",
            "My top 3 favorite drinks are...",
            "My top 3 favorite desserts are...",
            "My top 3 favorite snacks are...",
            "My top 3 favorite celebrities are...",
            "What time period would you most like to live in and why?",
            "What would 16 year old you think of current you?",
            "How was it getting your license? If you don't have it, why not?",
            "What's the most embarrassing thing you've ever done?",
            "What's something you've gotten an award for?",
            "Do you regret any of your exes?",
            "What's your political affiliation and why?",
            "Have you ever been in a fight?",
            "Have you ever saved someone's life?",
            "Something you need to confess to someone who won't know is...",
            "First word you'd use to describe yourself is...",
            "First person you think to confide in and why is...",
            "When did you last cry and why?",
            "What's the first quality you look for in a person?",
            "When's the last time you felt in control of your life?",
            "When's a time you successfully stood your ground?",
            "When's the last time you felt proud of yourself?",
            "When's the last time you were scared for your life?",
            "When's the last time you wanted to end your life?",
            "Three signs of hope for your future are...",
            "Three things you forgive yourself for are..."
        ]

    async def cog_load(self):
        """Called when cog is loaded."""
        try:
            self.logger.info("Workshop cog loading...")
            # Ensure storage directory exists
            os.makedirs(STORAGE_PATH, exist_ok=True)
            self.logger.info("Workshop cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Error in Workshop cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded."""
        try:
            self.logger.info("Workshop cog unloading...")
            self.logger.info("Workshop cog unloaded successfully")
        except Exception as e:
            self.logger.error(f"Error during Workshop cog unload: {e}")

    async def get_prompt_history(self):
        """Load prompt history from file, similar to other cogs."""
        async with self._lock:
            if os.path.exists(PROMPT_HISTORY_FILE):
                try:
                    async with aiofiles.open(PROMPT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                        data = await f.read()
                        if data.strip():
                            return json.loads(data)
                except Exception as e:
                    self.logger.error(f"Error loading prompt history: {e}")
            return []

    async def set_prompt_history(self, history):
        """Save prompt history to file, with atomic operations like other cogs."""
        async with self._lock:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(PROMPT_HISTORY_FILE), exist_ok=True)
                
                # Save to temporary file first (atomic operation)
                temp_file = PROMPT_HISTORY_FILE + '.tmp'
                async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(history, indent=2, ensure_ascii=False))
                
                # Create backup of existing file if it exists
                backup_file = PROMPT_HISTORY_FILE + '.backup'
                if os.path.exists(PROMPT_HISTORY_FILE):
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(PROMPT_HISTORY_FILE, backup_file)
                
                # Move temp file to final location
                os.rename(temp_file, PROMPT_HISTORY_FILE)
                
                self.logger.debug(f"Prompt history saved successfully ({len(history)} prompts)")
                
            except Exception as e:
                self.logger.error(f"Error saving prompt history: {e}")
                # Try to restore backup if it exists
                backup_file = PROMPT_HISTORY_FILE + '.backup'
                if os.path.exists(backup_file) and not os.path.exists(PROMPT_HISTORY_FILE):
                    try:
                        os.rename(backup_file, PROMPT_HISTORY_FILE)
                        self.logger.info("Restored prompt history from backup")
                    except Exception as restore_error:
                        self.logger.error(f"Failed to restore backup: {restore_error}")

    async def save_submission(self, user_id, username, day, content):
        """Save workshop submission to dedicated file with atomic operations."""
        async with self._lock:
            try:
                # Ensure directory exists
                os.makedirs(STORAGE_PATH, exist_ok=True)
                
                submission_data = {
                    "user_id": user_id,
                    "username": username, 
                    "day": day,
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Load existing submissions
                all_subs = []
                if os.path.exists(SUBMISSIONS_FILE):
                    try:
                        async with aiofiles.open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
                            data = await f.read()
                            if data.strip():
                                all_subs = json.loads(data)
                    except Exception as e:
                        self.logger.error(f"Error loading existing submissions: {e}")
                
                all_subs.append(submission_data)
                
                # Save to temporary file first (atomic operation)
                temp_file = SUBMISSIONS_FILE + '.tmp'
                async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(all_subs, indent=2, ensure_ascii=False))
                
                # Create backup of existing file if it exists
                backup_file = SUBMISSIONS_FILE + '.backup'
                if os.path.exists(SUBMISSIONS_FILE):
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(SUBMISSIONS_FILE, backup_file)
                
                # Move temp file to final location
                os.rename(temp_file, SUBMISSIONS_FILE)
                
                self.logger.debug(f"Saved workshop submission for user {user_id}: {day}")
                
            except Exception as e:
                self.logger.error(f"Failed to save workshop submission: {e}")
                # Try to restore backup if it exists
                backup_file = SUBMISSIONS_FILE + '.backup'
                if os.path.exists(backup_file) and not os.path.exists(SUBMISSIONS_FILE):
                    try:
                        os.rename(backup_file, SUBMISSIONS_FILE)
                        self.logger.info("Restored submissions from backup")
                    except Exception as restore_error:
                        self.logger.error(f"Failed to restore backup: {restore_error}")
                raise

    async def add_points(self, user_id, amount):
        """Award points using Memory cog consistently with other cogs."""
        try:
            # Add enhanced rate limiting delay
            await asyncio.sleep(0.2)  # Increased delay
            
            memory_cog = self.bot.get_cog("Memory")
            if not memory_cog:
                self.logger.error("Memory cog not loaded - cannot award points")
                raise RuntimeError("Memory cog not loaded - cannot award points")
            
            return await memory_cog.add_nyx_notes(user_id, amount)
        except Exception as e:
            self.logger.error(f"Failed to award points to {user_id}: {e}")
            raise

    async def handle_submission(self, ctx, day: str, *, content: str = None):
        """Process the actual submission."""
        if ctx.channel.id != WORKSHOP_CHANNEL_ID:
            return  # Only allow in the designated workshop channel

        if not content or not content.strip():
            embed = discord.Embed(
                title="❌ Missing Content",
                description="Please provide your workshop submission text after the command. No points awarded.",
                color=discord.Color.red()
            )
            await self.bot.safe_send(ctx.channel, embed=embed)
            return

        try:
            # ★ Save submission
            await self.save_submission(ctx.author.id, ctx.author.display_name, day, content.strip())

            # ★ Award points
            total_points = await self.add_points(ctx.author.id, WORKSHOP_REWARD)

            # ★ Create embed (consistent with other cogs)
            embed = discord.Embed(
                title=f"✅ Workshop Submission Received: {day}",
                color=NYX_COLOR
            )
            embed.add_field(
                name="Submitted by",
                value=f"{ctx.author.display_name}",
                inline=True
            )
            embed.add_field(
                name="Day",
                value=day,
                inline=True
            )
            embed.add_field(
                name="Nyx Notes Earned",
                value=f"**{WORKSHOP_REWARD}** 🪙",
                inline=True
            )
            embed.add_field(
                name="Total Nyx Notes",
                value=f"**{total_points:,}** 🪙",
                inline=True
            )
            embed.add_field(
                name="Content",
                value=f"```{content.strip()[:500]}{'...' if len(content.strip()) > 500 else ''}```",
                inline=False
            )
            embed.set_footer(
                text=f"Thank you for contributing to the Weekly Workshop!",
                icon_url=ctx.author.display_avatar.url
            )

            # ★ Use safe send with fallback
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                fallback_text = (
                    f"✅ Workshop Submission Received: {day}\n"
                    f"Submitted by: {ctx.author.display_name}\n"
                    f"Nyx Notes Earned: {WORKSHOP_REWARD} 🪙\n"
                    f"Total Nyx Notes: {total_points:,} 🪙\n"
                    f"Content: {content.strip()[:200]}{'...' if len(content.strip()) > 200 else ''}"
                )
                await self.bot.safe_send(ctx.channel, fallback_text)

        except Exception as e:
            self.logger.error(f"Error handling workshop submission: {e}")
            embed = discord.Embed(
                title="❌ Submission Error",
                description=f"There was an error processing your submission: {str(e)}",
                color=discord.Color.red()
            )
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                await self.bot.safe_send(ctx.channel, f"❌ Submission Error: {str(e)}")

    @commands.command(name="monday")
    async def monday(self, ctx, *, content: str = None):
        """Submit a Monday Workshop entry."""
        try:
            await self.handle_submission(ctx, "Monday", content=content)
        except Exception as e:
            self.logger.error(f"Error in monday command: {e}")

    @commands.command(name="tuesday")
    async def tuesday(self, ctx, *, content: str = None):
        """Submit a Tuesday Workshop entry."""
        try:
            await self.handle_submission(ctx, "Tuesday", content=content)
        except Exception as e:
            self.logger.error(f"Error in tuesday command: {e}")

    @commands.command(name="thursday")
    async def thursday(self, ctx, *, content: str = None):
        """Submit a Thursday Workshop entry."""
        try:
            await self.handle_submission(ctx, "Thursday", content=content)
        except Exception as e:
            self.logger.error(f"Error in thursday command: {e}")

    @commands.command(name="friday")
    async def friday(self, ctx, *, content: str = None):
        """Submit a Friday Workshop entry."""
        try:
            await self.handle_submission(ctx, "Friday", content=content)
        except Exception as e:
            self.logger.error(f"Error in friday command: {e}")

    @commands.command(name="weekend")
    async def weekend(self, ctx):
        """Generate a weekend writing prompt."""
        if ctx.channel.id != WORKSHOP_CHANNEL_ID:
            return
        
        try:
            prompt_history = await self.get_prompt_history()
            available_prompts = [p for p in self.prompt_prompts if p not in prompt_history]
            
            if not available_prompts:
                # All prompts used, reset and reshuffle
                prompt_history = []
                available_prompts = self.prompt_prompts.copy()
                random.shuffle(available_prompts)
            
            # Select next prompt
            selected_prompt = available_prompts[0]
            prompt_history.append(selected_prompt)
            await self.set_prompt_history(prompt_history)
            
            embed = discord.Embed(
                title="📝 Weekend Writing Prompt",
                description=selected_prompt,
                color=NYX_COLOR
            )
            embed.add_field(
                name="How to Submit",
                value="Use `!weekendsubmit <your writing>` to submit your response",
                inline=False
            )
            embed.set_footer(text="Weekend Workshop • Atypical Asylum")
            
            # ★ Use safe send with fallback
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                fallback_text = (
                    f"📝 Weekend Writing Prompt\n"
                    f"{selected_prompt}\n\n"
                    f"Use !weekendsubmit <your writing> to submit your response"
                )
                await self.bot.safe_send(ctx.channel, fallback_text)
            
        except Exception as e:
            self.logger.error(f"Error generating weekend prompt: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to generate weekend prompt. Please try again.",
                color=discord.Color.red()
            )
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                await self.bot.safe_send(ctx.channel, "❌ Failed to generate weekend prompt. Please try again.")

    @commands.command(name="weekendsubmit")
    async def weekendsubmit(self, ctx, *, content: str = None):
        """Submit a weekend workshop entry."""
        try:
            await self.handle_submission(ctx, "Weekend", content=content)
        except Exception as e:
            self.logger.error(f"Error in weekendsubmit command: {e}")

# ★ Standard async setup function for bot loading (consistent with other cogs)
async def setup(bot):
    await bot.add_cog(Workshop(bot))