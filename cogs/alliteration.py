# alliteration.py
import os
import random
import asyncio
import discord
from discord.ext import commands
import aiofiles
import logging
from typing import Dict, Set, Optional, List
from datetime import datetime, timezone
import json

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️ Anthropic not installed. Alliteration validation will be limited.")

# ★ Consistent color (matches nyxcore.py and other cogs)
NYX_COLOR = 0x76b887
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
os.makedirs(STORAGE_PATH, exist_ok=True)

class AlliterationGame(commands.Cog):
    """
    Cog for the Alliteration Game in Nyx.
    Players submit valid alliterative phrases on given topics to earn NyxNotes.
    """
    def __init__(self, bot):
        self.bot = bot
        self.nyx_color = NYX_COLOR
        self.memory = None  # Will be set in cog_load
        self.logger = logging.getLogger("AlliterationGame")
        self.active_games = {}  # channel_id: game_data
        self.topic_shuffle_file = os.path.join(STORAGE_PATH, 'alliteration_topics.json')
        
        # Define all available topics with categories
        self.all_topics = [
            # Names
            {"category": "names", "topic": "people names", "description": "alliterative names like 'Peter Parker' or 'Susan Smith'"},
            {"category": "names", "topic": "superhero names", "description": "alliterative superhero names like 'Bruce Banner' or 'Clark Kent'"},
            {"category": "names", "topic": "character names", "description": "alliterative character names from movies, books, or shows"},
            
            # Normal Topics
            {"category": "normal", "topic": "animals", "description": "alliterative animal phrases like 'busy bee' or 'clever cat'"},
            {"category": "normal", "topic": "food items", "description": "alliterative food phrases like 'perfect pizza' or 'tasty tacos'"},
            {"category": "normal", "topic": "colors and objects", "description": "alliterative color-object pairs like 'blue balloon' or 'red rose'"},
            {"category": "normal", "topic": "weather descriptions", "description": "alliterative weather phrases like 'sunny skies' or 'windy winter'"},
            {"category": "normal", "topic": "hobbies and activities", "description": "alliterative hobby phrases like 'dancing dolphins' or 'swimming swans'"},
            
            # Quirky Topics
            {"category": "quirky", "topic": "silly situations", "description": "alliterative silly phrases like 'giggling goats' or 'bouncing balloons'"},
            {"category": "quirky", "topic": "magical creatures", "description": "alliterative fantasy phrases like 'dancing dragons' or 'mystical mermaids'"},
            {"category": "quirky", "topic": "space adventures", "description": "alliterative space phrases like 'stellar spaceships' or 'cosmic creatures'"},
            {"category": "quirky", "topic": "time travel", "description": "alliterative time phrases like 'temporal travelers' or 'future fantasies'"},
            
            # Mental Health Topics
            {"category": "mental_health", "topic": "positive emotions", "description": "alliterative positive feeling phrases like 'happy hearts' or 'joyful journeys'"},
            {"category": "mental_health", "topic": "self-care activities", "description": "alliterative self-care phrases like 'mindful meditation' or 'peaceful practices'"},
            {"category": "mental_health", "topic": "supportive words", "description": "alliterative supportive phrases like 'caring community' or 'wonderful wellness'"},
            {"category": "mental_health", "topic": "growth and healing", "description": "alliterative growth phrases like 'brave beginnings' or 'healing hearts'"},
            
            # Random Topics
            {"category": "random", "topic": "office supplies", "description": "alliterative office phrases like 'perfect pens' or 'sturdy staplers'"},
            {"category": "random", "topic": "transportation", "description": "alliterative transport phrases like 'speedy spaceships' or 'bouncing buses'"},
            {"category": "random", "topic": "musical instruments", "description": "alliterative music phrases like 'gorgeous guitars' or 'terrific trumpets'"},
            {"category": "random", "topic": "kitchen items", "description": "alliterative kitchen phrases like 'shiny spoons' or 'perfect pots'"},
            {"category": "random", "topic": "school subjects", "description": "alliterative subject phrases like 'marvelous math' or 'super science'"},
        ]
        
    async def cog_load(self):
        """Called when cog is loaded - initialize dependencies"""
        try:
            self.logger.info("AlliterationGame cog loading...")
            
            # Get Memory cog (required for points system)
            self.memory = self.bot.get_cog("Memory")
            if not self.memory:
                raise RuntimeError("Memory cog not loaded - required for AlliterationGame")
            
            # Initialize Anthropic client on bot object if not exists (matching other cogs pattern)
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
                else:
                    self.logger.warning("⚠️ Anthropic not available - using basic validation")
            
            # Initialize topic shuffle system
            await self.initialize_topic_shuffle()
            
            self.logger.info("AlliterationGame cog loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error in AlliterationGame cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded - cleanup active games"""
        try:
            self.logger.info("AlliterationGame cog unloading...")
            
            # End any active games with delays for rate limiting
            for channel_id in list(self.active_games.keys()):
                try:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        embed = discord.Embed(
                            title="Game Ended",
                            description="Alliteration game ended due to bot restart.",
                            color=self.nyx_color
                        )
                        await self.bot.safe_send(channel, embed=embed)
                    
                    # Rate limiting delay
                    await asyncio.sleep(0.5)
                except Exception as e:
                    self.logger.error(f"Error ending game in channel {channel_id}: {e}")
                finally:
                    # Always remove from active games
                    self.active_games.pop(channel_id, None)
            
            self.logger.info("AlliterationGame cog unloaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error during AlliterationGame cog unload: {e}")

    async def initialize_topic_shuffle(self):
        """Initialize the topic shuffling system"""
        try:
            # Try to load existing shuffle state
            if os.path.exists(self.topic_shuffle_file):
                try:
                    async with aiofiles.open(self.topic_shuffle_file, 'r') as f:
                        content = await f.read()
                        data = json.loads(content)
                        self.used_topics = set(data.get('used_topics', []))
                        self.logger.info(f"Loaded topic shuffle state: {len(self.used_topics)} topics used")
                except Exception as e:
                    self.logger.warning(f"Error loading topic shuffle file: {e}")
                    self.used_topics = set()
            else:
                self.used_topics = set()
                
        except Exception as e:
            self.logger.error(f"Error initializing topic shuffle: {e}")
            self.used_topics = set()

    async def save_topic_shuffle_state(self):
        """Save the current topic shuffle state"""
        try:
            data = {
                'used_topics': list(self.used_topics),
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            async with aiofiles.open(self.topic_shuffle_file, 'w') as f:
                await f.write(json.dumps(data, indent=2))
        except Exception as e:
            self.logger.error(f"Error saving topic shuffle state: {e}")

    async def get_next_topic(self):
        """Get the next topic, ensuring variety through shuffling"""
        try:
            # If we've used all topics, reset the shuffle
            if len(self.used_topics) >= len(self.all_topics):
                self.used_topics.clear()
                self.logger.info("Topic shuffle completed - resetting for new cycle")
            
            # Get unused topics
            unused_topics = [t for i, t in enumerate(self.all_topics) if i not in self.used_topics]
            
            # Pick a random unused topic
            selected_topic = random.choice(unused_topics)
            selected_index = self.all_topics.index(selected_topic)
            
            # Mark this topic as used
            self.used_topics.add(selected_index)
            
            # Save state
            await self.save_topic_shuffle_state()
            
            return selected_topic
            
        except Exception as e:
            self.logger.error(f"Error getting next topic: {e}")
            # Fallback to a simple random choice
            return random.choice(self.all_topics)

    async def validate_alliteration_with_ai(self, submission: str, topic_info: dict) -> bool:
        """Use Claude AI to validate alliteration submissions intelligently"""
        try:
            if not hasattr(self.bot, 'anthropic_client') or not self.bot.anthropic_client:
                # Fallback to basic validation if no AI available
                return await self.basic_alliteration_validation(submission, topic_info)
            
            # Create validation prompt for Claude
            validation_prompt = f"""You are validating submissions for an alliteration game. 

TOPIC: {topic_info['topic']}
DESCRIPTION: Submit {topic_info['description']}
SUBMISSION: "{submission}"

Rules for valid submissions:
1. Must be 2-3 words that start with the same letter/sound
2. Must be relevant to the topic "{topic_info['topic']}"
3. Must be appropriate and family-friendly
4. Must make logical sense (not complete nonsense)
5. For names: should sound like plausible names (can be playful)

Examples of VALID submissions for "people names": "Peter Parker", "Susan Smith", "Silly Sally", "Stupid Steve", "Dumb Dave"
Examples of INVALID submissions for "people names": "Poopy Pants", "Fart Face", "Butt Brain"

Respond with only "VALID" or "INVALID" followed by a brief reason."""

            response = self.bot.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                temperature=0.3,  # Low temperature for consistent validation
                messages=[{
                    'role': 'user',
                    'content': validation_prompt
                }]
            )
            
            ai_response = response.content[0].text.strip().upper()
            is_valid = ai_response.startswith("VALID")
            
            self.logger.debug(f"AI validation for '{submission}': {ai_response}")
            return is_valid
            
        except Exception as e:
            self.logger.error(f"Error in AI validation: {e}")
            # Fallback to basic validation on error
            return await self.basic_alliteration_validation(submission, topic_info)

    async def basic_alliteration_validation(self, submission: str, topic_info: dict) -> bool:
        """Basic fallback validation when AI is not available"""
        try:
            if not submission or not isinstance(submission, str):
                return False
                
            submission = submission.strip().lower()
            words = submission.split()
            
            # Must be 2-3 words
            if not (2 <= len(words) <= 3):
                return False
            
            # All words must be alphabetic and reasonable length
            for word in words:
                if not word.isalpha() or not (2 <= len(word) <= 15):
                    return False
            
            # Must start with same letter (alliteration check)
            first_letters = [word[0].lower() for word in words]
            if len(set(first_letters)) != 1:
                return False
            
            # Basic quality filter - reject only extremely inappropriate content
            inappropriate_patterns = [
                "poopy", "poop", "fart", "butt"
            ]
            
            full_submission = " ".join(words)
            for pattern in inappropriate_patterns:
                if pattern in full_submission:
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error in basic validation: {e}")
            return False

    async def start_alliteration_game(self, ctx: commands.Context):
        """Start the alliteration game in a channel"""
        try:
            # Check for existing active game in this channel
            if ctx.channel.id in self.active_games:
                embed = discord.Embed(
                    title="Game Already Active",
                    description="An alliteration game is already running in this channel!",
                    color=discord.Color.orange()
                )
                await self.bot.safe_send(ctx.channel, embed=embed)
                return

            # Get next topic
            topic_info = await self.get_next_topic()
            
            # Create game state
            self.active_games[ctx.channel.id] = {
                "started_at": datetime.now(timezone.utc),
                "started_by": ctx.author.id,
                "topic": topic_info,
                "user_submissions": {},  # {user_id: set of valid submissions}
                "user_display_names": {},  # Store display names during game
                "active": True
            }
            
            # Create game announcement embed
            game_embed = discord.Embed(
                title="🎭 Alliteration Game Started!",
                description=(
                    f"**Topic:** {topic_info['topic'].title()}\n"
                    f"Submit {topic_info['description']}!\n\n"
                    "**How to play:**\n"
                    "• Submit valid alliterative phrases for the topic\n"
                    "• Each valid submission earns **5 🪙**\n"
                    "• You have **30 seconds** to submit as many as you can!\n"
                    "• Be creative and appropriate!"
                ),
                color=self.nyx_color
            )
            game_embed.set_footer(text="Timer starts now! Submit your alliterations!")
            
            result = await self.bot.safe_send(ctx.channel, embed=game_embed)
            if not result:
                await self.bot.safe_send(ctx.channel, f"🎭 Alliteration Game: Submit {topic_info['description']} - 30 seconds starting now!")

            # Collect submissions for 30 seconds
            timeout_duration = 30
            end_time = asyncio.get_event_loop().time() + timeout_duration
            
            def check(msg):
                # Only messages in same channel, from real users, not bots
                if (msg.channel != ctx.channel or msg.author.bot):
                    return False
                
                # Don't process if game was cancelled
                if ctx.channel.id not in self.active_games:
                    return False
                
                return True  # Let all messages through for validation

            # Game collection loop
            while asyncio.get_event_loop().time() < end_time and ctx.channel.id in self.active_games:
                remaining_time = end_time - asyncio.get_event_loop().time()
                if remaining_time <= 0:
                    break
                
                try:
                    msg = await self.bot.wait_for('message', timeout=remaining_time, check=check)
                    
                    # Skip if game was ended
                    if ctx.channel.id not in self.active_games:
                        break
                    
                    submission = msg.content.strip()
                    user_id = msg.author.id
                    
                    # Validate submission using AI or basic validation
                    is_valid = await self.validate_alliteration_with_ai(submission, topic_info)
                    
                    if is_valid:
                        # Double-check game still exists (race condition protection)
                        if ctx.channel.id not in self.active_games:
                            break
                        
                        game = self.active_games[ctx.channel.id]
                        
                        # Initialize user data if needed
                        if user_id not in game["user_submissions"]:
                            game["user_submissions"][user_id] = set()
                        
                        # Store display name and add submission
                        game["user_display_names"][user_id] = msg.author.display_name
                        game["user_submissions"][user_id].add(submission.lower())  # Normalize for deduplication
                        
                        # Silent checkmark for valid submissions (with rate limiting)
                        try:
                            await msg.add_reaction("✅")
                        except discord.HTTPException:
                            pass  # Skip if rate limited
                    
                except asyncio.TimeoutError:
                    break  # Time's up
                except Exception as e:
                    self.logger.error(f"Error during game collection: {e}")
                    break

            # Game ended - process results
            if ctx.channel.id not in self.active_games:
                return  # Game was cancelled
            
            game = self.active_games.pop(ctx.channel.id)
            await self.award_points_and_show_results(ctx, game)
            
        except Exception as e:
            self.logger.error(f"Error in start_alliteration_game: {e}")
            # Clean up active game on error
            self.active_games.pop(ctx.channel.id, None)
            
            error_embed = discord.Embed(
                title="Game Error",
                description=f"An error occurred during the game: {str(e)}",
                color=discord.Color.red()
            )
            result = await self.bot.safe_send(ctx.channel, embed=error_embed)
            if not result:
                await self.bot.safe_send(ctx.channel, f"❌ Game error: {str(e)}")

    async def award_points_and_show_results(self, ctx: commands.Context, game: dict):
        """Award points and display game results"""
        try:
            user_submissions = game["user_submissions"]
            user_display_names = game["user_display_names"]
            topic_info = game["topic"]
            
            if not user_submissions:
                embed = discord.Embed(
                    title="🎭 Game Complete!",
                    description="No valid submissions were made. Better luck next time!",
                    color=self.nyx_color
                )
                embed.set_footer(text="Thanks for playing the alliteration game!")
                await self.bot.safe_send(ctx.channel, embed=embed)
                return

            # Award points to all participants (5 points per valid submission)
            total_points_awarded = 0
            user_scores = {}
            
            for user_id, submissions in user_submissions.items():
                submission_count = len(submissions)
                points = submission_count * 5  # 5 points per valid submission
                
                if points > 0:
                    await self.memory.add_nyx_notes(user_id, points)
                    total_points_awarded += points
                    user_scores[user_id] = {"points": points, "count": submission_count}
                    
                    # Rate limiting delay between users
                    await asyncio.sleep(0.5)

            # Create results embed
            results_embed = discord.Embed(
                title="🎭 Alliteration Game Complete!",
                description=f"**Topic:** {topic_info['topic'].title()}",
                color=self.nyx_color
            )
            
            # Show participant results
            if user_scores:
                participant_lines = []
                for user_id, score_data in user_scores.items():
                    user_name = user_display_names.get(user_id, "Unknown User")
                    points = score_data["points"]
                    count = score_data["count"]
                    participant_lines.append(f"**{user_name}:** +{points} 🪙 ({count} submissions)")
                
                # Limit to top 5 to avoid embed size limits
                if len(participant_lines) > 5:
                    participant_lines = participant_lines[:5]
                    participant_lines.append("*(and more players...)*")
                
                results_embed.add_field(
                    name="Points Earned",
                    value="\n".join(participant_lines),
                    inline=False
                )
            
            # Game statistics
            total_submissions = sum(len(submissions) for submissions in user_submissions.values())
            results_embed.add_field(
                name="Game Stats",
                value=(
                    f"**{total_points_awarded} 🪙** total awarded\n"
                    f"**{total_submissions}** valid submissions\n"
                    f"**{len(user_submissions)}** players participated"
                ),
                inline=True
            )
            
            results_embed.set_footer(text="Congratulations on completing the alliteration challenge!")
            
            # Send results
            result = await self.bot.safe_send(ctx.channel, embed=results_embed)
            if not result:
                fallback_text = (
                    f"🎭 Alliteration Game Complete!\n"
                    f"Topic: {topic_info['topic'].title()}\n"
                    f"Total Points Awarded: {total_points_awarded} 🪙\n"
                    f"Players: {len(user_submissions)}"
                )
                await self.bot.safe_send(ctx.channel, fallback_text)
                
        except Exception as e:
            self.logger.error(f"Error awarding points and showing results: {e}")
            error_embed = discord.Embed(
                title="Results Error",
                description="Game completed but there was an error displaying results.",
                color=discord.Color.red()
            )
            await self.bot.safe_send(ctx.channel, embed=error_embed)

    @commands.command(name='alliterations', aliases=['alliteration', 'allit'])
    async def alliterations_command(self, ctx: commands.Context):
        """Start the Alliteration Game - submit creative alliterative phrases to earn NyxNotes!"""
        try:
            await self.start_alliteration_game(ctx)
        except Exception as e:
            self.logger.error(f"Error in alliterations_command: {e}")
            await self.bot.safe_send(ctx.channel, "❌ Error starting alliteration game.")

    @commands.command(name='allitcheck', hidden=True)
    async def alliteration_check(self, ctx: commands.Context, *, submission: str = None):
        """Check if a submission would be valid for testing purposes"""
        try:
            if not submission:
                await self.bot.safe_send(ctx.channel, "Please provide a submission to check.")
                return
            
            # Use a general topic for testing
            test_topic = {"topic": "general", "description": "any alliterative phrase"}
            
            is_valid = await self.validate_alliteration_with_ai(submission, test_topic)
            
            embed = discord.Embed(
                title="Alliteration Check",
                color=self.nyx_color if is_valid else discord.Color.red()
            )
            embed.add_field(name="Submission", value=f'"{submission}"', inline=False)
            embed.add_field(name="Valid", value="✅ Yes" if is_valid else "❌ No", inline=True)
            embed.add_field(name="Points", value="5 🪙" if is_valid else "0 🪙", inline=True)
            
            # Show validation method
            validation_method = "AI Validation" if (hasattr(self.bot, 'anthropic_client') and self.bot.anthropic_client) else "Basic Validation"
            embed.add_field(name="Method", value=validation_method, inline=True)
            
            result = await self.bot.safe_send(ctx.channel, embed=embed)
            if not result:
                await self.bot.safe_send(ctx.channel, f'"{submission}" - Valid: {"Yes" if is_valid else "No"} - Points: {5 if is_valid else 0} 🪙')
                
        except Exception as e:
            self.logger.error(f"Error in alliteration_check: {e}")
            await self.bot.safe_send(ctx.channel, f"Error checking submission: {e}")


# ★ Standard async setup for cog loader
async def setup(bot):
    await bot.add_cog(AlliterationGame(bot))