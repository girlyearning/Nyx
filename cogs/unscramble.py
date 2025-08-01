# Unscramble game for Nyx - Fixed with proper rounds and rate limiting
import discord
from discord.ext import commands
import random
import aiofiles
import os
import asyncio
import logging
from datetime import datetime, timezone

NYX_COLOR = 0x76b887
FONT = "monospace"
COMMON_WORDS_FILE = "./common_words.txt"  # Ensure path is correct for your project
ROUNDS_PER_GAME = 3
NYX_NOTES_PER_CORRECT = 5
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
os.makedirs(STORAGE_PATH, exist_ok=True)

class Unscramble(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # channel_id: game_data dict
        self.word_list = []
        self.memory = None  # Will be set in cog_load
        self.logger = logging.getLogger("Unscramble")

    async def cog_load(self):
        # Load words from common_words.txt on cog load
        try:
            self.logger.info("Unscramble cog loading...")
            self.word_list = await self.load_words()
            # Get Memory cog for points
            self.memory = self.bot.get_cog("Memory")
            if not self.memory:
                raise RuntimeError("Memory cog not loaded - Unscramble requires persistent storage.")
            self.logger.info("Unscramble cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Error in Unscramble cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded - cleanup active games sequentially."""
        try:
            self.logger.info("Unscramble cog unloading...")
            
            # End all active games gracefully with delays
            active_channels = list(self.active_games.keys())
            for channel_id in active_channels:
                try:
                    await asyncio.sleep(0.5)  # Delay between cleanups
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await self.bot.safe_send(channel, "🔤 Unscramble game ended due to bot restart.")
                    del self.active_games[channel_id]
                except Exception as e:
                    self.logger.error(f"Error ending unscramble game in channel {channel_id}: {e}")
            
            self.logger.info("Unscramble cog unloaded successfully")
        except Exception as e:
            self.logger.error(f"Error during Unscramble cog unload: {e}")

    async def load_words(self):
        words = []
        if not os.path.exists(COMMON_WORDS_FILE):
            # Fallback word list if file doesn't exist
            fallback_words = [
                "chair", "table", "house", "water", "light", "music", "paper", "phone",
                "computer", "keyboard", "elephant", "butterfly", "wonderful", "beautiful",
                "telephone", "basketball", "incredible", "extraordinary", "magnificent",
                "adhere", "bridge", "carpet", "dragon", "engine", "forest", "garden",
                "hammer", "island", "jungle", "kettle", "ladder", "margin", "needle",
                "orange", "planet", "quartz", "ribbon", "silver", "travel", "unique"
            ]
            return [w for w in fallback_words if 5 <= len(w) <= 9]
            
        async with aiofiles.open(COMMON_WORDS_FILE, "r", encoding="utf-8") as f:
            async for line in f:
                word = line.strip().lower()
                if 5 <= len(word) <= 9 and word.isalpha():
                    words.append(word)
        return words

    def pick_unused_word(self, used_words):
        """Pick a random unused word between 5 and 9 letters"""
        eligible = [w for w in self.word_list if 5 <= len(w) <= 9 and w not in used_words]
        if not eligible:
            return None
        return random.choice(eligible)

    def scramble_word(self, word):
        """Scramble a word ensuring it's different from original."""
        chars = list(word)
        attempts = 0
        while attempts < 20:  # Prevent infinite loop
            random.shuffle(chars)
            scrambled = ''.join(chars)
            if scrambled != word:
                return scrambled
            attempts += 1
        # If we can't scramble it differently, just reverse it
        return word[::-1]

    # ★ NEW: Award points in batches at the end of the game to prevent rate limiting
    async def award_game_points(self, channel, game):
        """Award all accumulated points to users at once (prevents rate limiting)"""
        try:
            if not game.get("user_scores"):
                return
                
            points_per_word = NYX_NOTES_PER_CORRECT
            
            # Award points to each user with delay between users
            for user_id, words_found in game["user_scores"].items():
                if words_found > 0:
                    total_points = words_found * points_per_word
                    try:
                        new_total = await self.memory.add_nyx_notes(user_id, total_points)
                        
                        # Get user display name safely (prefer guild member display name)
                        user = self.bot.get_user(user_id)
                        if user:
                            # Try to get guild member for display name
                            if hasattr(channel, 'guild') and channel.guild:
                                member = channel.guild.get_member(user_id)
                                if member:
                                    user_name = member.display_name
                                else:
                                    user_name = user.global_name or user.name
                            else:
                                user_name = user.global_name or user.name
                        else:
                            user_name = "Unknown User"
                        
                        # Points will be shown in final embed - no separate messages
                        
                        # Rate limiting delay between users
                        await asyncio.sleep(1.0)
                        
                    except Exception as e:
                        self.logger.error(f"Error awarding points to user {user_id}: {e}")
                        user = self.bot.get_user(user_id)
                        if user:
                            # Try to get guild member for display name
                            if hasattr(channel, 'guild') and channel.guild:
                                member = channel.guild.get_member(user_id)
                                if member:
                                    user_name = member.display_name
                                else:
                                    user_name = user.global_name or user.name
                            else:
                                user_name = user.global_name or user.name
                        else:
                            user_name = "Unknown User"
                        await self.bot.safe_send(channel, f"⚠️ Error awarding points to {user_name}")
                        
        except Exception as e:
            self.logger.error(f"Error in award_game_points: {e}")

    @commands.command(name="unscramble")
    async def start_unscramble(self, ctx):
        channel_id = ctx.channel.id
        if channel_id in self.active_games:
            await self.bot.safe_send(ctx.channel, "An unscramble game is already running in this channel. Use `!endunscramble` to end it.")
            return

        if len(self.word_list) < ROUNDS_PER_GAME:
            await self.bot.safe_send(ctx.channel, "Not enough words available to start the game.")
            return

        # Initialize game data with NEW user scoring system
        self.active_games[channel_id] = {
            "current_round": 0,
            "correct_count": 0,
            "total_rounds": ROUNDS_PER_GAME,
            "used_words": set(),
            "current_word": None,
            "current_scrambled": None,
            "hints_given": 0,
            "started_at": datetime.now(timezone.utc),
            "started_by": ctx.author.id,
            "active": True,
            "words_played": [],  # Track all words for summary
            "user_scores": {},   # NEW: Track points per user {user_id: word_count}
            "found_by": {}       # NEW: Track who found each word {word: user_id}
        }
        
        # Send game announcement
        embed = discord.Embed(
            title="🔤 Unscramble Word Game Started!",
            description=(
                f"**{ROUNDS_PER_GAME} rounds** of word unscrambling!\n"
                f"**{NYX_NOTES_PER_CORRECT} 🪙** per correct word\n"
                f"**Total possible: {ROUNDS_PER_GAME * NYX_NOTES_PER_CORRECT} 🪙**\n\n"
                "**Commands:**\n"
                "`!hint` - Get first/last letter hint\n"
                "`!reveal` - Reveal current word\n"
                "`!endunscramble` - End game early"
            ),
            color=NYX_COLOR
        )
        embed.set_footer(text="Starting first round...")
        
        result = await self.bot.safe_send(ctx.channel, embed=embed)
        if not result:
            await self.bot.safe_send(ctx.channel, f"🔤 Unscramble Game Started! {ROUNDS_PER_GAME} rounds, {NYX_NOTES_PER_CORRECT} points each!")
        
        # Start first round with delay
        await asyncio.sleep(2)
        await self.next_round(ctx)

    async def next_round(self, ctx):
        """Start the next round of the unscramble game"""
        channel_id = ctx.channel.id
        game = self.active_games[channel_id]
        
        # Check if game is complete
        if game["current_round"] >= game["total_rounds"]:
            await self.end_game(ctx)
            return

        # Pick new word
        word = self.pick_unused_word(game["used_words"])
        if not word:
            await self.bot.safe_send(ctx.channel, "No more eligible words to use. Ending game.")
            await self.end_game(ctx)
            return
            
        # Update game state
        game["used_words"].add(word)
        game["current_word"] = word
        game["current_scrambled"] = self.scramble_word(word)
        game["current_round"] += 1
        game["hints_given"] = 0  # Reset hints for new round
        game["words_played"].append({"word": word, "scrambled": game["current_scrambled"]})

        embed = discord.Embed(
            title=f"Round {game['current_round']}/{game['total_rounds']} - Unscramble This Word!",
            description=f"`{game['current_scrambled']}`\n\nType your guess in chat!",
            color=NYX_COLOR,
        )
        embed.add_field(
            name="📊 Progress",
            value=f"Round {game['current_round']}/{game['total_rounds']}\nCorrect: {game['correct_count']}",
            inline=True
        )
        
        result = await self.bot.safe_send(ctx.channel, embed=embed)
        if not result:
            await self.bot.safe_send(ctx.channel, f"Round {game['current_round']}/{game['total_rounds']}: {game['current_scrambled']} (Type your guess!)")

    @commands.command(name="endunscramble")
    async def end_unscramble(self, ctx):
        channel_id = ctx.channel.id
        if channel_id not in self.active_games:
            await self.bot.safe_send(ctx.channel, "No active unscramble game to end in this channel.")
            return
        await self.end_game(ctx, aborted=True)

    async def end_game(self, ctx, aborted=False):
        """End the current unscramble game"""
        channel_id = ctx.channel.id
        game = self.active_games[channel_id]
        game["active"] = False
        
        # Award all accumulated points silently (no separate messages)
        try:
            if game.get("user_scores"):
                points_per_word = NYX_NOTES_PER_CORRECT
                
                # Award points to each user with delay between users
                for user_id, words_found in game["user_scores"].items():
                    if words_found > 0:
                        total_points = words_found * points_per_word
                        try:
                            await self.memory.add_nyx_notes(user_id, total_points)
                            # Rate limiting delay between users
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            self.logger.error(f"Error awarding points to user {user_id}: {e}")
        except Exception as e:
            self.logger.error(f"Error in silent award_game_points: {e}")
        
        total_points_earned = game["correct_count"] * NYX_NOTES_PER_CORRECT
        
        msg = (
            f"🟢 Game ended by user. You solved {game['correct_count']} out of {game['current_round']} rounds."
            if aborted
            else f"🏁 Unscramble game complete! You solved {game['correct_count']} out of {game['total_rounds']} words."
        )
        
        embed = discord.Embed(
            title="Unscramble Game Over",
            description=msg + f"\n**Total Nyx Notes awarded:** {total_points_earned} 🪙",
            color=NYX_COLOR,
        )
        
        # Show user earned nyx notes
        if game["user_scores"]:
            user_summary = []
            for user_id, words_found in game["user_scores"].items():
                user = self.bot.get_user(user_id)
                if user:
                    # Try to get guild member for display name
                    if hasattr(ctx, 'guild') and ctx.guild:
                        member = ctx.guild.get_member(user_id)
                        if member:
                            user_name = member.display_name
                        else:
                            user_name = user.global_name or user.name
                    else:
                        user_name = user.global_name or user.name
                else:
                    user_name = "Unknown User"
                total_earned = words_found * NYX_NOTES_PER_CORRECT
                user_summary.append(f"**{user_name}**: {total_earned} 🪙")
            
            embed.add_field(
                name="Nyx Notes Earned",
                value="\n".join(user_summary),
                inline=False
            )
        
        embed.set_footer(text="Thanks for playing!")
        
        result = await self.bot.safe_send(ctx.channel, embed=embed)
        if not result:
            await self.bot.safe_send(ctx.channel, f"Game Over! Earned {total_points_earned} 🪙 total.")
        
        del self.active_games[channel_id]

    @commands.command(name="hint")
    async def hint(self, ctx):
        """Get a hint for the current unscramble word - shows first and last letter"""
        if ctx.channel.id not in self.active_games:
            await self.bot.safe_send(ctx.channel, "No active unscramble game in this channel.")
            return

        game = self.active_games[ctx.channel.id]
        if not game["active"] or not game["current_word"]:
            await self.bot.safe_send(ctx.channel, "No current word to give a hint for.")
            return

        word = game["current_word"]
        
        # Create hint with first letter, underscores, and last letter
        hint_display = word[0] + "_" * (len(word) - 2) + word[-1]
        
        game["hints_given"] += 1
        
        embed = discord.Embed(
            title="💡 Hint",
            description=f"**Pattern:** `{hint_display}`\n**Length:** {len(word)} letters",
            color=NYX_COLOR
        )
        embed.add_field(
            name="Round Info",
            value=f"Round {game['current_round']}/{game['total_rounds']}\nHints used: {game['hints_given']}",
            inline=True
        )
        embed.set_footer(text="You still get full points even after using hints!")
        
        result = await self.bot.safe_send(ctx.channel, embed=embed)
        if not result:
            await self.bot.safe_send(ctx.channel, f"💡 Hint: {hint_display} ({len(word)} letters)")

    @commands.command(name="reveal")
    async def reveal(self, ctx):
        """Reveal the current unscramble word and move to next round"""
        if ctx.channel.id not in self.active_games:
            await self.bot.safe_send(ctx.channel, "No active unscramble game in this channel.")
            return

        game = self.active_games[ctx.channel.id]
        if not game["active"] or not game["current_word"]:
            await self.bot.safe_send(ctx.channel, "No current word to reveal.")
            return

        embed = discord.Embed(
            title="🔤 Word Revealed",
            description=f"**Word:** `{game['current_word']}`\n`{game['current_scrambled']}`",
            color=NYX_COLOR
        )
        embed.add_field(
            name="Round Info",
            value=f"Round {game['current_round']}/{game['total_rounds']}\nNo points awarded for revealed word",
            inline=True
        )
        embed.set_footer(text="Moving to next round...")
        
        result = await self.bot.safe_send(ctx.channel, embed=embed)
        if not result:
            await self.bot.safe_send(ctx.channel, f"🔤 Word revealed: {game['current_word']}")
        
        # Move to next round after short delay
        await asyncio.sleep(2)
        await self.next_round(ctx)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Only process guesses if a game is active in the channel
        if message.author.bot or not message.guild:
            return

        channel_id = message.channel.id
        if channel_id not in self.active_games:
            return
        
        game = self.active_games[channel_id]
        if not game["active"] or not game["current_word"]:
            return

        # Add enhanced rate limiting delay
        await asyncio.sleep(0.1)

        guess = message.content.strip().lower()
        if guess == game["current_word"]:
            game["correct_count"] += 1
            user_id = message.author.id
            
            # NEW: Track user scoring instead of immediate points
            game["user_scores"][user_id] = game["user_scores"].get(user_id, 0) + 1
            game["found_by"][game["current_word"]] = user_id
            
            display_name = message.author.display_name
            
            embed = discord.Embed(
                title="✅ Correct, Nyx Notes: 5",
                color=NYX_COLOR,
            )
            embed.add_field(
                name="Progress",
                value=f"Round {game['current_round']}/{game['total_rounds']} complete\nCorrect answers: {game['correct_count']}",
                inline=True
            )
            embed.add_field(
                name="Nyx Notes Rewarded",
                value=f"+{NYX_NOTES_PER_CORRECT} 🪙 (awarded at game end)",
                inline=True
            )
            
            result = await self.bot.safe_send(message.channel, embed=embed)
            if not result:
                fallback_text = f"Correct! {display_name} unscrambled: {game['current_word']} (+{NYX_NOTES_PER_CORRECT} 🪙 pending)"
                await self.bot.safe_send(message.channel, fallback_text)
            
            # Proceed to next round after a brief pause
            await asyncio.sleep(3)
            ctx = await self.bot.get_context(message)
            await self.next_round(ctx)

    # Ensure Memory cog is referenced on reload
    async def cog_reload(self):
        self.memory = self.bot.get_cog("Memory")

async def setup(bot):
    await bot.add_cog(Unscramble(bot))