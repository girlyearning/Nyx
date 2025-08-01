import os
import random
import asyncio
import discord
from discord.ext import commands
import aiofiles
import re
import logging
from typing import Dict, Set, Optional

# ★ Consistent color (matches nyxcore.py and memory.py)
NYX_COLOR = 0x76b887
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
os.makedirs(STORAGE_PATH, exist_ok=True)

# ★ File configuration - separate files for different purposes
PREFIXES_FILE = "common_words.txt"  # For generating common prefixes
VALIDATION_FILE = "words_alpha.txt"  # For validating submitted words

class PrefixGame(commands.Cog):
    """
    Cog for the Prefix Word Game in Nyx.
    Players submit words starting with given 3-letter prefixes to earn NyxNotes.
    """
    def __init__(self, bot):
        self.bot = bot
        self.nyx_color = NYX_COLOR
        self.prefix_words_cache: Optional[Set[str]] = None  # Cache for prefix generation
        self.validation_words_cache: Optional[Set[str]] = None  # Cache for word validation
        self.logger = logging.getLogger("PrefixGame")
        self.prefix_file_available = False  # Track if prefix file exists
        self.validation_file_available = False  # Track if validation file exists
        
    async def cog_load(self):
        """Called when cog is loaded - initialize data"""
        try:
            self.logger.info("PrefixGame cog loading...")
            
            # Check if prefix file exists
            if not os.path.exists(PREFIXES_FILE):
                self.logger.warning(f"⚠️ {PREFIXES_FILE} not found")
                self.logger.info("Will use fallback prefixes")
                self.prefix_file_available = False
            else:
                self.logger.info(f"✅ Found prefix file: {PREFIXES_FILE}")
                self.prefix_file_available = True
            
            # Check if validation file exists
            if not os.path.exists(VALIDATION_FILE):
                self.logger.warning(f"⚠️ {VALIDATION_FILE} not found")
                self.logger.info("Will use basic word validation")
                self.validation_file_available = False
            else:
                self.logger.info(f"✅ Found validation file: {VALIDATION_FILE}")
                self.validation_file_available = True
            
            # Create fallback word lists if needed
            if not self.prefix_file_available:
                self.prefix_words_cache = {
                    'the', 'and', 'cat', 'dog', 'run', 'car', 'tree', 'book', 'game', 'play',
                    'house', 'water', 'light', 'music', 'paper', 'phone', 'table', 'chair',
                    'computer', 'keyboard', 'elephant', 'butterfly', 'wonderful', 'beautiful',
                    'telephone', 'basketball', 'incredible', 'extraordinary', 'magnificent'
                }
                
            self.logger.info("PrefixGame cog loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error in PrefixGame cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded - cleanup"""
        try:
            self.logger.info("PrefixGame cog unloading...")
            self.logger.info("PrefixGame cog unloaded successfully")
        except Exception as e:
            self.logger.error(f"Error during PrefixGame cog unload: {e}")

    async def load_prefix_words(self) -> Set[str]:
        """
        Load and cache words for prefix generation.
        
        Returns:
            Set of words to use for generating prefixes
        """
        if self.prefix_words_cache is not None:
            return self.prefix_words_cache
            
        # If prefix file is not available, return the fallback word list
        if not self.prefix_file_available:
            return self.prefix_words_cache or set()
            
        try:
            async with aiofiles.open(PREFIXES_FILE, "r", encoding="utf-8") as f:
                content = await f.read()
                
            # Extract valid words (alphabetic, 3+ characters)
            words = set()
            for line in content.split('\n'):
                word = line.strip().lower()
                if len(word) >= 3 and word.isalpha():
                    words.add(word)
                    
            self.prefix_words_cache = words
            self.logger.debug(f"Loaded {len(words)} prefix words from {PREFIXES_FILE}")
            return words
            
        except Exception as e:
            self.logger.error(f"Error loading prefix words: {e}")
            # Return fallback word list on error
            fallback_words = {
                'the', 'and', 'cat', 'dog', 'run', 'car', 'tree', 'book', 'game', 'play',
                'house', 'water', 'light', 'music', 'paper', 'phone', 'table', 'chair',
                'computer', 'keyboard', 'elephant', 'butterfly', 'wonderful', 'beautiful',
                'telephone', 'basketball', 'incredible', 'extraordinary', 'magnificent'
            }
            self.prefix_words_cache = fallback_words
            return fallback_words

    async def load_validation_words(self) -> Set[str]:
        """
        Load and cache words for validation.
        
        Returns:
            Set of valid English words for validation
        """
        if self.validation_words_cache is not None:
            return self.validation_words_cache
            
        # If validation file is not available, return None (will use basic validation)
        if not self.validation_file_available:
            return set()
            
        try:
            async with aiofiles.open(VALIDATION_FILE, "r", encoding="utf-8") as f:
                content = await f.read()
                
            # Extract valid words (alphabetic, 3+ characters)
            words = set()
            for line in content.split('\n'):
                word = line.strip().lower()
                if len(word) >= 3 and word.isalpha():
                    words.add(word)
                    
            self.validation_words_cache = words
            self.logger.debug(f"Loaded {len(words)} validation words from {VALIDATION_FILE}")
            return words
            
        except Exception as e:
            self.logger.error(f"Error loading validation words: {e}")
            # Return empty set on error (will use basic validation)
            self.validation_words_cache = set()
            return set()

    async def get_prefixes(self, count: int = 50) -> list:
        """
        Get unique 3-letter prefixes from the prefix word list.
        
        Args:
            count: Number of prefixes to return
            
        Returns:
            List of 3-letter prefixes
        """
        words = await self.load_prefix_words()
        
        # Extract 3-letter prefixes
        prefixes = set()
        for word in words:
            if len(word) >= 3:
                prefix = word[:3]
                if prefix.isalpha():
                    prefixes.add(prefix)
                    
        prefix_list = list(prefixes)
        random.shuffle(prefix_list)
        return prefix_list[:count]

    def is_valid_word(self, word: str, prefix: str) -> bool:
        """
        Check if a word is valid for the game.
        
        Args:
            word: Word to validate
            prefix: Required prefix
            
        Returns:
            True if valid, False otherwise
        """
        if not word or not isinstance(word, str):
            return False
            
        word = word.lower().strip()
        
        # Basic validation
        if len(word) < 3 or not word.isalpha():
            return False
            
        # Must start with prefix
        if not word.startswith(prefix.lower()):
            return False
            
        # Check against validation word list if available
        if self.validation_words_cache is not None and len(self.validation_words_cache) > 0:
            if word not in self.validation_words_cache:
                return False
        # If no validation file, accept any word that passes basic checks
            
        return True

    def calculate_points(self, word: str, is_longest: bool = False) -> int:
        """
        Calculate NyxNotes points for a word based on length and longest status.
        
        Args:
            word: The submitted word
            is_longest: Whether this is the longest word in the game
            
        Returns:
            Points to award
        """
        base_points = 10 if len(word) >= 8 else 5
        longest_bonus = 10 if is_longest else 0
        return base_points + longest_bonus

    async def start_prefix_game(self, ctx: commands.Context):
        """
        Start the prefix word game in a channel.
        
        Args:
            ctx: Discord command context
        """
        
        try:
            # ★ Load words and get prefixes
            try:
                await self.load_prefix_words()  # Load prefix words
                await self.load_validation_words()  # Load validation words
                prefixes = await self.get_prefixes(10)
            except Exception as e:
                embed = discord.Embed(
                    title="Error",
                    description=f"Failed to load word lists: {str(e)}",
                    color=discord.Color.red()
                )
                await self.bot.safe_send(ctx.channel, embed=embed)
                return

            if len(prefixes) < 3:
                embed = discord.Embed(
                    title="Error",
                    description="Not enough prefixes available for the game.",
                    color=discord.Color.red()
                )
                await self.bot.safe_send(ctx.channel, embed=embed)
                return

            # ★ Choose random prefix
            prefix = random.choice(prefixes)
            
            # ★ Combined game announcement and round start
            game_embed = discord.Embed(
                title="🎮 Prefix Word Game Started!",
                description=(
                    "**How to play:**\n"
                    "• I'll give you a 3-letter prefix\n"
                    "• Submit valid English words starting with that prefix\n"
                    "• **ALL valid words get points:**\n"
                    "  - Words 3-7 letters = **5 🪙**\n"
                    "  - Words 8+ letters = **10 🪙**\n"
                    "  - **Longest word gets +10 🪙 bonus!**\n"
                    "• Game ends after 20 seconds!\n\n"
                    f"**Prefix:** `{prefix.upper()}`"
                ),
                color=self.nyx_color
            )
            game_embed.set_footer(text="You have 20 seconds to submit as many words as possible!")
            result = await self.bot.safe_send(ctx.channel, embed=game_embed)
            if not result:
                await self.bot.safe_send(ctx.channel, f"🎮 Prefix Word Game started! Submit words starting with: {prefix.upper()}\nYou have 20 seconds!")

            # ★ Collect responses - FIXED SCORING SYSTEM
            user_words: Dict[int, Set[str]] = {}  # Changed to set to avoid duplicates per user
            user_display_names: Dict[int, str] = {}  # Store display names during game
            longest_word = ""
            longest_user_id = None
            
            def check(msg):
                # Only messages in same channel, from real users, not bots
                if (msg.channel != ctx.channel or 
                    msg.author.bot):
                    return False
                
                word = msg.content.strip().lower()
                return self.is_valid_word(word, prefix)

            # ★ Game loop - collect words for exactly 20 seconds
            timeout_duration = 20  # 20 seconds to submit words
            reaction_cooldown = {}  # Track reaction cooldowns per user
            
            try:
                # Wait for the full 20 seconds, collecting all valid submissions
                end_time = asyncio.get_event_loop().time() + timeout_duration
                
                while asyncio.get_event_loop().time() < end_time:
                    remaining_time = end_time - asyncio.get_event_loop().time()
                    if remaining_time <= 0:
                        break
                        
                    try:
                        # Wait for next valid word (but only for remaining time)
                        msg = await self.bot.wait_for('message', timeout=remaining_time, check=check)
                        word = msg.content.strip().lower()
                        user_id = msg.author.id
                        
                        # Initialize user's word set if not exists
                        if user_id not in user_words:
                            user_words[user_id] = set()
                        
                        # Store display name during game (when we have access to message author)
                        user_display_names[user_id] = msg.author.display_name
                        
                        # Add word to user's set (automatically handles duplicates)
                        user_words[user_id].add(word)
                        
                        # Update longest word tracking
                        if len(word) > len(longest_word):
                            longest_word = word
                            longest_user_id = user_id
                        
                        # CHECKMARK ALL VALID WORDS with cooldown per user
                        try:
                            current_time = asyncio.get_event_loop().time()
                            if (user_id not in reaction_cooldown or 
                                current_time - reaction_cooldown[user_id] > 1.0):  # 1 second cooldown per user
                                await msg.add_reaction("✅")
                                reaction_cooldown[user_id] = current_time
                        except discord.HTTPException:
                            # Skip reactions if rate limited
                            pass
                                
                    except asyncio.TimeoutError:
                        # Time ran out, exit the loop
                        break
                        
            except Exception as e:
                # Handle any errors during word collection
                self.logger.error(f"Error during word collection: {e}")
                    
            # ★ Game ended - process results
            if not user_words or not longest_word:
                embed = discord.Embed(
                    title="Game Ended",
                    description="No valid words were submitted. Better luck next time!",
                    color=self.nyx_color
                )
                await self.bot.safe_send(ctx.channel, embed=embed)
                return

            # ★ CALCULATE AND AWARD POINTS - BATCH PROCESSING TO AVOID RATE LIMITS
            memory_cog = self.bot.get_cog("Memory")
            total_points_awarded = 0
            user_scores = {}  # Track each user's total points
            
            if memory_cog:
                try:
                    # Process each user's words in batches to avoid rate limiting
                    for user_id, words in user_words.items():
                        user_total = 0
                        
                        # Calculate total points for this user first
                        for word in words:
                            is_longest = (word == longest_word and user_id == longest_user_id)
                            points = self.calculate_points(word, is_longest)
                            user_total += points
                        
                        # Award all points to user in ONE API call instead of per-word
                        if user_total > 0:
                            await memory_cog.add_nyx_notes(user_id, user_total)
                            total_points_awarded += user_total
                            
                            # INCREASED delay between users to prevent rate limiting
                            await asyncio.sleep(0.5)  # Reduced to 0.5 seconds between users
                        
                        user_scores[user_id] = user_total
                        
                except Exception as e:
                    self.logger.error(f"Error awarding points: {e}")

            # ★ Get winner name - Use stored display name from game
            winner_name = user_display_names.get(longest_user_id, "Unknown User")

            # ★ Create results embed
            results_embed = discord.Embed(
                title="🏆 Game Complete!",
                color=self.nyx_color
            )
            
            results_embed.add_field(
                name="Longest Word Winner",
                value=f"**{winner_name}**",
                inline=True
            )
            
            results_embed.add_field(
                name="Winning Word",
                value=f"`{longest_word.upper()}` ({len(longest_word)} letters)",
                inline=True
            )
            
            # Show winner's total points
            winner_total = user_scores.get(longest_user_id, 0)
            longest_word_points = self.calculate_points(longest_word, True)
            results_embed.add_field(
                name="Winner's Score",
                value=f"**{winner_total} 🪙** total\n(Longest word: {longest_word_points} 🪙)",
                inline=True
            )
            
            # Show total game statistics
            total_words = sum(len(words) for words in user_words.values())
            results_embed.add_field(
                name="Game Statistics",
                value=(
                    f"**{total_points_awarded} 🪙** total awarded\n"
                    f"**{total_words}** valid words submitted\n"
                    f"**{len(user_words)}** players participated"
                ),
                inline=False
            )
            
            # Show top scoring players (limit to top 3 to avoid embed size issues)
            if len(user_scores) > 1:
                top_players = sorted(user_scores.items(), key=lambda x: x[1], reverse=True)[:3]
                player_list = []
                
                for i, (uid, score) in enumerate(top_players):
                    # Use stored display name from game
                    user_name = user_display_names.get(uid, "Unknown User")
                    
                    medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉"
                    word_count = len(user_words[uid])
                    player_list.append(f"{medal} **{user_name}:** {score} 🪙 ({word_count} words)")
                
                results_embed.add_field(
                    name="Top Players",
                    value="\n".join(player_list),
                    inline=False
                )
            
            results_embed.set_footer(text=f"Prefix: {prefix.upper()} • All valid words earned points!")
            
            # ★ Use safe send with fallback
            result = await self.bot.safe_send(ctx.channel, embed=results_embed)
            if not result:
                fallback_text = (
                    f"🏆 Game Complete!\n"
                    f"Longest Word: {winner_name} - {longest_word.upper()} ({len(longest_word)} letters)\n"
                    f"Total Points Awarded: {total_points_awarded} 🪙"
                )
                await self.bot.safe_send(ctx.channel, fallback_text)
            
        except Exception as e:
            # Handle any unexpected errors
            self.logger.error(f"Error in start_prefix_game: {e}")
            error_embed = discord.Embed(
                title="Game Error",
                description=f"An error occurred during the game: {str(e)}",
                color=discord.Color.red()
            )
            result = await self.bot.safe_send(ctx.channel, embed=error_embed)
            if not result:
                await self.bot.safe_send(ctx.channel, f"❌ Game error: {str(e)}")

    # ★ Command to start the game
    @commands.command(name='prefixgame', aliases=['pg', 'wordgame'])
    async def prefixgame_command(self, ctx: commands.Context):
        """Start the Prefix Word Game - submit as many valid words as possible with the given prefix!"""
        try:
            await self.start_prefix_game(ctx)
        except Exception as e:
            self.logger.error(f"Error in prefixgame_command: {e}")
            await self.bot.safe_send(ctx.channel, "❌ Error starting prefix game.")

    @commands.command(name='wordcheck', hidden=True)
    async def word_check(self, ctx: commands.Context, word: str, prefix: str = None):
        """Check if a word is valid (for testing purposes)"""
        try:
            if not prefix:
                if len(word) >= 3:
                    prefix = word[:3]
                else:
                    await self.bot.safe_send(ctx.channel, "Word too short or no prefix provided.")
                    return
            
            # Ensure word lists are loaded
            await self.load_prefix_words()
            await self.load_validation_words()
                
            word_lower = word.lower()
            is_valid = self.is_valid_word(word, prefix)
            base_points = self.calculate_points(word, False)  # Without longest bonus
            longest_points = self.calculate_points(word, True)  # With longest bonus
            
            embed = discord.Embed(
                title="Word Check",
                color=self.nyx_color if is_valid else discord.Color.red()
            )
            embed.add_field(name="Word", value=word, inline=True)
            embed.add_field(name="Prefix", value=prefix, inline=True)
            embed.add_field(name="Valid", value="✅ Yes" if is_valid else "❌ No", inline=True)
            embed.add_field(name="Length", value=f"{len(word)} letters", inline=True)
            
            if is_valid:
                embed.add_field(
                    name="Points", 
                    value=f"Normal: **{base_points} 🪙**\nIf longest: **{longest_points} 🪙**", 
                    inline=True
                )
            else:
                embed.add_field(name="Points", value="0 🪙", inline=True)
            
            # Show which dictionary was used
            if self.validation_words_cache and len(self.validation_words_cache) > 0:
                in_dict = word_lower in self.validation_words_cache
                embed.add_field(name="In Validation Dictionary", value="✅ Yes" if in_dict else "❌ No", inline=True)
                embed.add_field(name="Dictionary Info", value=f"Using {VALIDATION_FILE} ({len(self.validation_words_cache):,} words)", inline=False)
            else:
                embed.add_field(name="Validation Mode", value="Basic validation (no dictionary)", inline=False)
            
            # ★ Use safe send with fallback
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                fallback_text = f"Word: {word} | Valid: {'Yes' if is_valid else 'No'} | Points: {base_points if is_valid else 0} 🪙"
                await self.bot.safe_send(ctx.channel, fallback_text)
        except Exception as e:
            self.logger.error(f"Error in word_check: {e}")
            await self.bot.safe_send(ctx.channel, f"Error checking word: {e}")


# ★ Standard async setup for cog loader
async def setup(bot):
    await bot.add_cog(PrefixGame(bot))