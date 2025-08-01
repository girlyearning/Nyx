# Nyx's storage and memory file
import os
import json
import discord
from discord.ext import commands
import logging
import aiofiles
import asyncio
from typing import Dict, Optional

# ★ Define color and environment key (keep consistent with nyxcore.py)
NYX_COLOR = 0x76b887
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
os.makedirs(STORAGE_PATH, exist_ok=True)

class Memory(commands.Cog):
    """
    Cog for saving/loading Nyx Notes (points) for users.
    Data is stored in {STORAGE_PATH}/nyxnotes.json with atomic operations.
    """
    def __init__(self, bot):
        self.bot = bot
        self.storage_path = STORAGE_PATH
        self.notes_file = os.path.join(self.storage_path, 'nyxnotes.json')
        self.backup_file = os.path.join(self.storage_path, 'nyxnotes_backup.json')
        self.nyx_color = NYX_COLOR
        self.logger = logging.getLogger("nyxmemory")
        self.local_logger = logging.getLogger("nyxmemory.local")
        self.notes: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    async def cog_load(self):
        """Called when cog is loaded - initialize data"""
        try:
            self.logger.info("Memory cog loading...")
            await self.load_notes()
            self.logger.info("Memory cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Error in Memory cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded - save data"""
        try:
            self.logger.info("Memory cog unloading...")
            await self.save_notes()
            self.logger.info("Memory cog unloaded successfully")
        except Exception as e:
            self.logger.error(f"Error during Memory cog unload: {e}")

    async def save_notes(self):
        """
        Saves current Nyx Notes data to persistent storage with atomic operations.
        Uses backup file to prevent data corruption.
        """
        async with self._lock:
            try:
                # REMOVED: Rate limiting delay that could cause issues
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.notes_file), exist_ok=True)
                
                # Write to temporary file first (atomic operation)
                temp_file = self.notes_file + '.tmp'
                async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(self.notes, indent=2, ensure_ascii=False))
                
                # Create backup of existing file if it exists
                if os.path.exists(self.notes_file):
                    if os.path.exists(self.backup_file):
                        os.remove(self.backup_file)
                    os.rename(self.notes_file, self.backup_file)
                
                # Move temp file to final location
                os.rename(temp_file, self.notes_file)
                
                self.local_logger.debug(f"Nyx Notes saved successfully ({len(self.notes)} users)")
                
            except Exception as e:
                self.logger.error(f"Failed to save Nyx Notes: {e}")
                # Try to restore backup if it exists
                if os.path.exists(self.backup_file) and not os.path.exists(self.notes_file):
                    try:
                        os.rename(self.backup_file, self.notes_file)
                        self.local_logger.debug("Restored from backup file")
                    except Exception as restore_error:
                        self.logger.error(f"Failed to restore backup: {restore_error}")

    async def load_notes(self):
        """
        Loads Nyx Notes data from persistent storage with error recovery.
        """
        async with self._lock:
            # Try to load from local files
            for file_path in [self.notes_file, self.backup_file]:
                if not os.path.exists(file_path):
                    continue
                
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        data = await f.read()
                        if data.strip():
                            loaded_notes = json.loads(data)
                            # Validate data structure
                            if isinstance(loaded_notes, dict):
                                # Ensure all keys are strings and values are integers
                                self.notes = {}
                                for user_id, points in loaded_notes.items():
                                    try:
                                        self.notes[str(user_id)] = int(points)
                                    except (ValueError, TypeError):
                                        self.logger.warning(f"Invalid data for user {user_id}: {points}")
                                        continue
                                
                                self.local_logger.debug(f"Nyx Notes loaded from local storage: {file_path} ({len(self.notes)} users)")
                                self._loaded = True
                                return
                            else:
                                self.logger.error(f"Invalid data structure in {file_path}")
                        else:
                            self.logger.warning(f"Empty file: {file_path}")
                            
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON decode error in {file_path}: {e}")
                except Exception as e:
                    self.logger.error(f"Failed to load from {file_path}: {e}")
            
            # If no valid file found, initialize empty
            self.notes = {}
            self._loaded = True
            self.local_logger.debug("Initialized new Nyx Notes storage")

    async def add_nyx_notes(self, user_id: int, amount: int) -> int:
        """
        Adds points (Nyx Notes) to a user's total.
        
        Args:
            user_id: Discord user ID
            amount: Points to add (can be negative)
            
        Returns:
            New total points for user
        """
        if not self._loaded:
            await self.load_notes()
            
        async with self._lock:
            user_id_str = str(user_id)
            old_total = self.notes.get(user_id_str, 0)
            new_total = max(0, old_total + amount)  # Prevent negative points
            self.notes[user_id_str] = new_total
            
            self.local_logger.debug(f"User {user_id}: {old_total} -> {new_total} ({amount:+d} points)")
            
        # Save after modification
        await self.save_notes()
        return new_total

    async def get_nyx_notes(self, user_id: int) -> int:
        """
        Retrieves current points for user.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Current points (0 if user not found)
        """
        if not self._loaded:
            await self.load_notes()
            
        return self.notes.get(str(user_id), 0)

    async def set_nyx_notes(self, user_id: int, amount: int) -> int:
        """
        Sets a user's Nyx Notes to a specific value.
        
        Args:
            user_id: Discord user ID
            amount: Points to set
            
        Returns:
            New total (same as amount, but clamped to 0+)
        """
        if not self._loaded:
            await self.load_notes()
            
        async with self._lock:
            user_id_str = str(user_id)
            amount = max(0, amount)  # Prevent negative points
            old_total = self.notes.get(user_id_str, 0)
            self.notes[user_id_str] = amount
            
            self.local_logger.debug(f"User {user_id}: {old_total} -> {amount} (set)")
            
        # Save after modification
        await self.save_notes()
        return amount

    async def get_leaderboard(self, limit: int = 10) -> list:
        """
        Get top users by Nyx Notes.
        
        Args:
            limit: Maximum number of users to return
            
        Returns:
            List of tuples (user_id, points) sorted by points descending
        """
        if not self._loaded:
            await self.load_notes()
            
        sorted_users = sorted(
            [(int(uid), points) for uid, points in self.notes.items()],
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_users[:limit]

    @commands.command(name='nyxnotes')
    async def show_nyx_notes(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Show Nyx Notes for yourself or another user."""
        try:
            member = member or ctx.author
            points = await self.get_nyx_notes(member.id)
            
            embed = discord.Embed(
                title=f"{member.display_name}'s Nyx Notes",
                description=f"**{points:,}** 🪙",
                color=self.nyx_color
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Use safe send method with rate limiting
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                await self.bot.safe_send(ctx.channel, f"{member.display_name}: {points:,} 🪙")
        except Exception as e:
            self.logger.error(f"Error in show_nyx_notes: {e}")
            await self.bot.safe_send(ctx.channel, "❌ Error retrieving Nyx Notes.")

    @commands.command(name='leaderboard')
    async def show_leaderboard(self, ctx: commands.Context, limit: int = 10):
        """Show the Nyx Notes leaderboard."""
        try:
            if limit > 20:
                limit = 20
            elif limit < 1:
                limit = 10
                
            leaderboard = await self.get_leaderboard(limit)
            
            if not leaderboard:
                embed = discord.Embed(
                    title="Nyx Notes Leaderboard",
                    description="No users found with Nyx Notes yet!",
                    color=self.nyx_color
                )
                result = await self.bot.safe_send(ctx.channel, embed=embed)
                if not result:
                    await self.bot.safe_send(ctx.channel, "No users found with Nyx Notes yet!")
                return
            
            embed = discord.Embed(
                title="🏆 Nyx Notes Leaderboard",
                color=self.nyx_color
            )
            
            description_lines = []
            for i, (user_id, points) in enumerate(leaderboard, 1):
                # Try to get display name with fallbacks, cache-only (no API calls)
                name = "Unknown User"
                try:
                    user = self.bot.get_user(user_id)  # This is cache-only, no API call
                    if user:
                        # Try to get guild member for display name first
                        member = None
                        if hasattr(ctx, 'guild') and ctx.guild:
                            member = ctx.guild.get_member(user_id)
                        if member:
                            name = member.display_name
                        else:
                            name = user.global_name or user.name
                except:
                    pass  # Fail silently, keep using "Unknown User"
                
                # RATE LIMITING: Add delay between processing users
                if i > 1:  # Don't delay for first user
                    await asyncio.sleep(0.1)  # Small delay between users
                
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                description_lines.append(f"{medal} **{name}** - {points:,} 🪙")
                
                # CRITICAL: Limit leaderboard size to prevent rate limiting
                if i >= 10:  # Cap at 10 users max
                    break
            
            embed.description = "\n".join(description_lines)
            
            # Use safe send method with fallback
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                text_leaderboard = "🏆 Nyx Notes Leaderboard\n" + "\n".join(description_lines)
                await self.bot.safe_send(ctx.channel, text_leaderboard)
                
        except Exception as e:
            self.logger.error(f"Error in show_leaderboard: {e}")
            await self.bot.safe_send(ctx.channel, "❌ Error retrieving leaderboard.")

    @commands.command(name='givepoints', hidden=True)
    @commands.has_permissions(administrator=True)
    async def give_points(self, ctx: commands.Context, member: discord.Member, amount: int):
        """Admin command to give Nyx Notes to a user."""
        try:
            new_total = await self.add_nyx_notes(member.id, amount)
            
            embed = discord.Embed(
                title="Nyx Notes Awarded",
                description=f"Gave **{amount:,}** Nyx Notes 🪙 to {member.display_name}\nNew total: **{new_total:,}** 🪙",
                color=self.nyx_color
            )
            
            # Use safe send method with fallback
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                await self.bot.safe_send(ctx.channel, f"Gave {amount:,} 🪙 to {member.display_name}. New total: {new_total:,} 🪙")
        except Exception as e:
            self.logger.error(f"Error in give_points: {e}")
            await self.bot.safe_send(ctx.channel, "❌ Error awarding points.")

# ★ Standard async setup function for bot loading
async def setup(bot):
    await bot.add_cog(Memory(bot))