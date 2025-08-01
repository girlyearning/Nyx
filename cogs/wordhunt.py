import os
import random
import discord
from discord.ext import commands
import aiofiles
from typing import List
import asyncio
from datetime import datetime, timezone
import logging

# ★ Constants – align with Nyx bot style
NYX_COLOR = 0x76b887
FONT = "monospace"
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
os.makedirs(STORAGE_PATH, exist_ok=True)
WORD_LIST_FILE = os.path.join("common_words.txt")
WORDHUNT_SAVE_FILE = os.path.join(STORAGE_PATH, "wordhunt_results.json")

class WordHunt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # {guild_id: {channel_id: game_data}}
        self.memory = None
        self.logger = logging.getLogger("WordHunt")

    async def cog_load(self):
        try:
            self.logger.info("WordHunt cog loading...")
            self.memory = self.bot.get_cog("Memory")
            if not self.memory:
                raise RuntimeError("Memory cog not loaded for WordHunt.")
            self.logger.info("WordHunt cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Error in WordHunt cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded - cleanup active games sequentially."""
        try:
            self.logger.info("WordHunt cog unloading...")
            
            # End all active games gracefully with delays
            for guild_id in list(self.active_games.keys()):
                for channel_id in list(self.active_games[guild_id].keys()):
                    try:
                        await asyncio.sleep(0.5)  # Delay between cleanups
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await self.bot.safe_send(channel, "🔍 Word Hunt game ended due to bot restart.")
                        del self.active_games[guild_id][channel_id]
                    except Exception as e:
                        self.logger.error(f"Error ending word hunt game in channel {channel_id}: {e}")
                        
            self.logger.info("WordHunt cog unloaded successfully")
        except Exception as e:
            self.logger.error(f"Error during WordHunt cog unload: {e}")

    # ★ Utility: Load word list (min_len/max_len inclusive)
    async def load_words(self, min_len: int, max_len: int) -> List[str]:
        try:
            async with aiofiles.open(WORD_LIST_FILE, "r") as f:
                lines = await f.readlines()
            return [w.strip().lower() for w in lines if min_len <= len(w.strip()) <= max_len]
        except FileNotFoundError:
            # Fallback word list if file doesn't exist
            fallback_words = [
                "cats", "dogs", "bird", "fish", "tree", "book", "desk", "lamp", "door", "wind",
                "house", "phone", "water", "paper", "chair", "table", "green", "happy", "small",
                "large", "quick", "quiet", "bright", "light", "heavy", "clean", "dirty", "space",
                "music", "heart", "sweet", "night", "ocean", "river", "stone", "smile", "dream",
                "peace", "magic", "power", "trust", "brave", "dance", "laugh", "shine", "grace",
                "storm", "cloud", "frost", "field", "mount", "beach", "craft", "pride", "teach",
                "learn", "build", "paint", "write", "climb", "brave", "flame", "horse", "eagle",
                "butterfly", "computer", "rainbow", "mountain", "adventure", "elephant", "keyboard"
            ]
            return [w for w in fallback_words if min_len <= len(w) <= max_len]

    # ★ Utility: Build an empty grid
    def build_grid(self, size: int) -> List[List[str]]:
        return [["." for _ in range(size)] for _ in range(size)]

    # ★ Utility: Directions
    @staticmethod
    def get_directions():
        # (dx, dy)
        return [
            (1, 0),   # right
            (0, 1),   # down
            (1, 1),   # down-right
            (-1, 0),  # left
            (0, -1),  # up
            (-1, -1), # up-left
            (1, -1),  # up-right
            (-1, 1),  # down-left
        ]

    # ★ Utility: Place word into the grid
    def place_word(self, grid, word, used_positions):
        size = len(grid)
        attempts = 60
        directions = self.get_directions()
        for _ in range(attempts):
            dx, dy = random.choice(directions)
            x = random.randint(0, size - 1)
            y = random.randint(0, size - 1)
            end_x = x + dx * (len(word) - 1)
            end_y = y + dy * (len(word) - 1)
            # Bounds check
            if not (0 <= end_x < size and 0 <= end_y < size):
                continue
            # Overlap/fit check
            fits = True
            positions = []
            for i in range(len(word)):
                nx = x + dx * i
                ny = y + dy * i
                c = grid[ny][nx]
                if c != "." and c != word[i]:
                    fits = False
                    break
                positions.append((ny, nx))
            if fits:
                for idx, (ny, nx) in enumerate(positions):
                    grid[ny][nx] = word[idx]
                used_positions[word] = positions
                return True
        return False

    # ★ Utility: Fill grid with random letters
    def fill_grid_randomly(self, grid):
        alphabet = "abcdefghijklmnopqrstuvwxyz"
        for y in range(len(grid)):
            for x in range(len(grid[y])):
                if grid[y][x] == ".":
                    grid[y][x] = random.choice(alphabet)

    # ★ Utility: Format grid for embed
    def format_grid(self, grid):
        # Use monospace, grid lines joined by spaces
        return "```\n" + "\n".join(" ".join(row) for row in grid) + "\n```"

    # ★ Utility: Save finished games to disk
    async def save_wordhunt_result(self, user_id, mode, found_words, success):
        try:
            # Save to disk with append mode (basic log, not a database)
            async with aiofiles.open(WORDHUNT_SAVE_FILE, "a") as f:
                line = f"{user_id},{mode},{'|'.join(found_words)},{success}\n"
                await f.write(line)
        except Exception as e:
            self.logger.error(f"Error saving wordhunt result: {e}")

    # ★ NEW: Award points in batches at the end of the game and return award summary
    async def award_game_points(self, game, guild=None):
        """Award all accumulated points to users at once and return summary for embed"""
        award_summary = []
        try:
            if not game.get("user_scores"):
                return award_summary
                
            points_per_word = 10 if game["mode"] == "easy" else 15
            
            # Award points to each user
            for user_id, words_found in game["user_scores"].items():
                if words_found > 0:
                    total_points = words_found * points_per_word
                    try:
                        new_total = await self.memory.add_nyx_notes(user_id, total_points)
                        
                        # Get user display name safely (prefer guild member display name)
                        user = self.bot.get_user(user_id)
                        if user:
                            # Try to get guild member for display name (use provided guild first)
                            member = None
                            if guild:
                                member = guild.get_member(user_id)
                            
                            # If no member found and no guild provided, search all guilds
                            if not member:
                                for g in self.bot.guilds:
                                    member = g.get_member(user_id)
                                    if member:
                                        break
                            
                            if member:
                                user_name = member.display_name
                            else:
                                user_name = user.global_name or user.name
                        else:
                            user_name = "Unknown User"
                        
                        award_summary.append(f"🪙 **{user_name}**: +{total_points:,} Nyx Notes ({words_found} words) → **{new_total:,}** total")
                        
                        # Small delay between awards
                        await asyncio.sleep(0.2)
                        
                    except Exception as e:
                        self.logger.error(f"Error awarding points to user {user_id}: {e}")
                        user = self.bot.get_user(user_id)
                        if user:
                            # Try to get guild member for display name (use provided guild first)
                            member = None
                            if guild:
                                member = guild.get_member(user_id)
                            
                            # If no member found and no guild provided, search all guilds
                            if not member:
                                for g in self.bot.guilds:
                                    member = g.get_member(user_id)
                                    if member:
                                        break
                            
                            if member:
                                user_name = member.display_name
                            else:
                                user_name = user.global_name or user.name
                        else:
                            user_name = "Unknown User"
                        award_summary.append(f"⚠️ **{user_name}**: Error awarding points")
                        
        except Exception as e:
            self.logger.error(f"Error in award_game_points: {e}")
            
        return award_summary

    # ★ Command: !easywordhunt
    @commands.command(name="easywordhunt")
    async def easy_wordhunt(self, ctx):
        """Start an easy word hunt (5x5, 3 hidden 4-letter words)"""
        # Only allow one active game per channel
        if ctx.channel.id in self.active_games.get(ctx.guild.id, {}):
            await self.bot.safe_send(ctx.channel, "An Easy Word Hunt is already active in this channel.")
            return

        try:
            # Load 4-letter words for easy mode
            words = await self.load_words(4, 4)
            if len(words) < 3:
                await self.bot.safe_send(ctx.channel, "Not enough 4-letter words available. Please try again.")
                return
                
            selected = random.sample(words, 3)
            grid_size = 5
            grid = self.build_grid(grid_size)
            used_positions = {}

            # Place words
            placed_count = 0
            for word in selected:
                if self.place_word(grid, word, used_positions):
                    placed_count += 1
                    
            if placed_count < 3:
                await self.bot.safe_send(ctx.channel, "Failed to place all words in the grid. Please try again.")
                return

            self.fill_grid_randomly(grid)
            formatted = self.format_grid(grid)
            
            # Initialize game state with NEW user scoring system
            if ctx.guild.id not in self.active_games:
                self.active_games[ctx.guild.id] = {}
                
            self.active_games[ctx.guild.id][ctx.channel.id] = {
                "mode": "easy",
                "words": selected,
                "found": set(),
                "grid": grid,
                "positions": used_positions,
                "started_at": datetime.now(timezone.utc),
                "started_by": ctx.author.id,
                "user_scores": {},  # NEW: Track points per user {user_id: word_count}
                "found_by": {}      # NEW: Track who found each word {word: user_id}
            }

            # Create embed - DON'T SHOW THE WORDS!
            embed = discord.Embed(
                title="🟩 Easy Word Hunt",
                description=f"Find all **3 hidden 4-letter words** in the 5x5 grid!\n\n{formatted}",
                color=NYX_COLOR
            )
            embed.add_field(
                name="📝 How to Play",
                value="Type the words you find in chat!\nEach correct word = **10 Nyx Notes** 🪙",
                inline=False
            )
            embed.set_footer(text="Use !easyhint for hints | !easyreveal to give up")
            
            # ★ Use safe send with fallback
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                fallback_text = (
                    f"🟩 Easy Word Hunt\n"
                    f"Find 3 hidden 4-letter words in the grid!\n"
                    f"{formatted}\n"
                    f"Type the words you find! Each = 10 Nyx Notes"
                )
                await self.bot.safe_send(ctx.channel, fallback_text)

        except Exception as e:
            self.logger.error(f"Error starting easy word hunt: {e}")
            await self.bot.safe_send(ctx.channel, "Failed to generate a valid board. Please try again.")

    @commands.command(name="easyhint")
    async def easy_hint(self, ctx):
        """Get hints for the easy word hunt (first letters of unfound words)"""
        game = self.active_games.get(ctx.guild.id, {}).get(ctx.channel.id)
        if not game or game["mode"] != "easy":
            await self.bot.safe_send(ctx.channel, "No active Easy Word Hunt in this channel.")
            return
        
        unfound_words = [word for word in game["words"] if word not in game["found"]]
        if not unfound_words:
            await self.bot.safe_send(ctx.channel, "All words have been found! No hints needed.")
            return
        
        hints = [word[0].upper() for word in unfound_words]
        embed = discord.Embed(
            title="🟩 Easy Word Hunt Hints",
            description=f"First letters of remaining words:\n**{', '.join(hints)}**",
            color=NYX_COLOR
        )
        embed.add_field(
            name="Progress",
            value=f"Found: {len(game['found'])}/3 words",
            inline=True
        )
        
        # ★ Use safe send with fallback
        result = await self.bot.safe_send(ctx.channel, embed=embed)
        if not result:
            await self.bot.safe_send(ctx.channel, f"💡 Hints: {', '.join(hints)} (Found: {len(game['found'])}/3)")

    @commands.command(name="easyreveal")
    async def easy_reveal(self, ctx):
        """Reveal all words in the easy word hunt"""
        game = self.active_games.get(ctx.guild.id, {}).get(ctx.channel.id)
        if not game or game["mode"] != "easy":
            await self.bot.safe_send(ctx.channel, "No active Easy Word Hunt in this channel.")
            return

        found_words = ', '.join(game['found']) if game['found'] else 'None'
        missing_words = ', '.join([w for w in game['words'] if w not in game['found']]) if set(game['words']) - game['found'] else 'None'
        
        embed = discord.Embed(
            title="🟩 Easy Word Hunt - All Words Revealed",
            description=f"**All words:** {', '.join(game['words'])}\n\n**Found:** {found_words}\n**Missing:** {missing_words}",
            color=NYX_COLOR
        )
        
        # Award accumulated points and get summary
        award_summary = await self.award_game_points(game, ctx.guild)
        
        # Add point awards to embed if any were made
        if award_summary:
            embed.add_field(
                name="🪙 Nyx Notes Awarded",
                value="\n".join(award_summary),
                inline=False
            )
        
        # Save result and clean up
        await self.save_wordhunt_result(ctx.author.id, "easy", list(game["found"]), len(game["found"]) == 3)
        
        # ★ Use safe send with fallback
        result = await self.bot.safe_send(ctx.channel, embed=embed)
        if not result:
            fallback_text = (
                f"🟩 Easy Word Hunt Complete!\n"
                f"All words: {', '.join(game['words'])}\n"
                f"Found: {found_words}\n"
                f"Missing: {missing_words}"
            )
            if award_summary:
                fallback_text += "\n\n" + "\n".join(award_summary)
            await self.bot.safe_send(ctx.channel, fallback_text)

        # Clean up game
        if ctx.guild.id in self.active_games and ctx.channel.id in self.active_games[ctx.guild.id]:
            del self.active_games[ctx.guild.id][ctx.channel.id]

    @commands.command(name="hardwordhunt")
    async def hard_word_hunt(self, ctx):
        """Start a hard word hunt game (8x8, 4 hidden 4-7 letter words)"""
        # Only allow one active game per channel
        if ctx.channel.id in self.active_games.get(ctx.guild.id, {}):
            await self.bot.safe_send(ctx.channel, "A Word Hunt is already active in this channel.")
            return

        try:
            # Load 4-7 letter words for hard mode
            words = await self.load_words(4, 7)
            if len(words) < 4:
                await self.bot.safe_send(ctx.channel, "Not enough words available. Please try again.")
                return
                
            selected = random.sample(words, 4)
            grid_size = 8
            grid = self.build_grid(grid_size)
            used_positions = {}

            # Place words
            placed_count = 0
            for word in selected:
                if self.place_word(grid, word, used_positions):
                    placed_count += 1
                    
            if placed_count < 4:
                await self.bot.safe_send(ctx.channel, "Failed to place all words in the grid. Please try again.")
                return

            self.fill_grid_randomly(grid)
            formatted = self.format_grid(grid)
            
            # Initialize game state with NEW user scoring system
            if ctx.guild.id not in self.active_games:
                self.active_games[ctx.guild.id] = {}
                
            self.active_games[ctx.guild.id][ctx.channel.id] = {
                "mode": "hard",
                "words": selected,
                "found": set(),
                "grid": grid,
                "positions": used_positions,
                "started_at": datetime.now(timezone.utc),
                "started_by": ctx.author.id,
                "user_scores": {},  # NEW: Track points per user {user_id: word_count}
                "found_by": {}      # NEW: Track who found each word {word: user_id}
            }

            # Create embed - DON'T SHOW THE WORDS!
            embed = discord.Embed(
                title="🟥 Hard Word Hunt",
                description=f"Find all **4 hidden words (4-7 letters)** in the 8x8 grid!\n\n{formatted}",
                color=NYX_COLOR
            )
            embed.add_field(
                name="📝 How to Play",
                value="Type the words you find in chat!\nEach correct word = **15 Nyx Notes** 🪙",
                inline=False
            )
            embed.set_footer(text="Use !hardhint for hints | !hardreveal to give up")
            
            # ★ Use safe send with fallback
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                fallback_text = (
                    f"🟥 Hard Word Hunt\n"
                    f"Find 4 hidden words (4-7 letters) in the grid!\n"
                    f"{formatted}\n"
                    f"Type the words you find! Each = 15 Nyx Notes"
                )
                await self.bot.safe_send(ctx.channel, fallback_text)

        except Exception as e:
            self.logger.error(f"Error starting hard word hunt: {e}")
            await self.bot.safe_send(ctx.channel, "Failed to generate a valid board. Please try again.")

    @commands.command(name="hardhint")
    async def hard_hint(self, ctx):
        """Get hints for the hard word hunt (first letters of unfound words)"""
        game = self.active_games.get(ctx.guild.id, {}).get(ctx.channel.id)
        if not game or game["mode"] != "hard":
            await self.bot.safe_send(ctx.channel, "No active Hard Word Hunt in this channel.")
            return
        
        unfound_words = [word for word in game["words"] if word not in game["found"]]
        if not unfound_words:
            await self.bot.safe_send(ctx.channel, "All words have been found! No hints needed.")
            return
        
        hints = [word[0].upper() for word in unfound_words]
        embed = discord.Embed(
            title="🟥 Hard Word Hunt Hints",
            description=f"First letters of remaining words:\n**{', '.join(hints)}**",
            color=NYX_COLOR
        )
        embed.add_field(
            name="Progress",
            value=f"Found: {len(game['found'])}/4 words",
            inline=True
        )
        
        # ★ Use safe send with fallback
        result = await self.bot.safe_send(ctx.channel, embed=embed)
        if not result:
            await self.bot.safe_send(ctx.channel, f"💡 Hints: {', '.join(hints)} (Found: {len(game['found'])}/4)")

    @commands.command(name="hardreveal")
    async def hard_reveal(self, ctx):
        """Reveal all words in the hard word hunt"""
        game = self.active_games.get(ctx.guild.id, {}).get(ctx.channel.id)
        if not game or game["mode"] != "hard":
            await self.bot.safe_send(ctx.channel, "No active Hard Word Hunt in this channel.")
            return

        found_words = ', '.join(game['found']) if game['found'] else 'None'
        missing_words = ', '.join([w for w in game['words'] if w not in game['found']]) if set(game['words']) - game['found'] else 'None'
        
        embed = discord.Embed(
            title="🟥 Hard Word Hunt - All Words Revealed",
            description=f"**All words:** {', '.join(game['words'])}\n\n**Found:** {found_words}\n**Missing:** {missing_words}",
            color=NYX_COLOR
        )
        
        # Award accumulated points and get summary
        award_summary = await self.award_game_points(game, ctx.guild)
        
        # Add point awards to embed if any were made
        if award_summary:
            embed.add_field(
                name="🪙 Nyx Notes Awarded",
                value="\n".join(award_summary),
                inline=False
            )
        
        # Save result and clean up
        await self.save_wordhunt_result(ctx.author.id, "hard", list(game["found"]), len(game["found"]) == 4)
        
        # ★ Use safe send with fallback
        result = await self.bot.safe_send(ctx.channel, embed=embed)
        if not result:
            fallback_text = (
                f"🟥 Hard Word Hunt Complete!\n"
                f"All words: {', '.join(game['words'])}\n"
                f"Found: {found_words}\n"
                f"Missing: {missing_words}"
            )
            if award_summary:
                fallback_text += "\n\n" + "\n".join(award_summary)
            await self.bot.safe_send(ctx.channel, fallback_text)

        # Clean up game
        if ctx.guild.id in self.active_games and ctx.channel.id in self.active_games[ctx.guild.id]:
            del self.active_games[ctx.guild.id][ctx.channel.id]

    # ★ Event: Message listener for guesses - COMPLETELY REWRITTEN for batched scoring
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bot/self
        if message.author.bot or not message.guild:
            return
        
        channel = message.channel
        game = self.active_games.get(message.guild.id, {}).get(channel.id)
        if not game:
            return
        
        # Skip commands
        if message.content.startswith("!"):
            return
        
        # Add enhanced rate limiting delay
        await asyncio.sleep(0.1)  # Increased delay
        
        guess = message.content.strip().lower()
        
        # Check if word is already found
        if guess in game["found"]:
            await self.bot.safe_send(channel, f"Already found **{guess}**.")
            return

        # Check if word is correct
        if guess in game["words"]:
            game["found"].add(guess)
            
            # NEW: Track user scoring instead of immediate points
            user_id = message.author.id
            game["user_scores"][user_id] = game["user_scores"].get(user_id, 0) + 1
            game["found_by"][guess] = user_id
            
            points = 10 if game["mode"] == "easy" else 15
            
            # Show immediate feedback WITHOUT awarding points yet
            embed = discord.Embed(
                title="✅ Correct Word Found!",
                description=f"**{guess.upper()}** found by {message.author.display_name}!",
                color=NYX_COLOR
            )
            embed.add_field(
                name="Reward",
                value=f"+{points} Nyx Notes 🪙 (pending)",
                inline=True
            )
            embed.add_field(
                name="Progress",
                value=f"Found: {len(game['found'])}/{len(game['words'])} words",
                inline=True
            )
            
            result = await self.bot.safe_send(channel, embed=embed)
            if not result:
                await self.bot.safe_send(channel, f"✅ Correct! **{guess.upper()}** found by {message.author.display_name}! (+{points} Nyx Notes pending)")

            # Check if all words found - AWARD ALL POINTS AT ONCE
            if len(game["found"]) == len(game["words"]):
                
                # Award all accumulated points and get summary
                award_summary = await self.award_game_points(game, message.guild)
                
                embed = discord.Embed(
                    title=f"🎉 {'Easy' if game['mode'] == 'easy' else 'Hard'} Word Hunt Complete!",
                    description=f"All {len(game['words'])} words found! Great job everyone!",
                    color=NYX_COLOR
                )
                embed.add_field(
                    name="Final Words",
                    value=", ".join([w.upper() for w in game["words"]]),
                    inline=False
                )
                
                # Add point awards to embed if any were made
                if award_summary:
                    embed.add_field(
                        name="🪙 Nyx Notes Awarded",
                        value="\n".join(award_summary),
                        inline=False
                    )
                
                # Save successful completion
                await self.save_wordhunt_result(message.author.id, game["mode"], list(game["found"]), True)
                
                # ★ Use safe send with fallback
                result = await self.bot.safe_send(channel, embed=embed)
                if not result:
                    await self.bot.safe_send(channel, f"🎉 {'Easy' if game['mode'] == 'easy' else 'Hard'} Word Hunt Complete! All words found!")
                
                # Clean up game
                if message.guild.id in self.active_games and channel.id in self.active_games[message.guild.id]:
                    del self.active_games[message.guild.id][channel.id]

# ★ Cog setup (async for compatibility with your main file)
async def setup(bot):
    await bot.add_cog(WordHunt(bot))