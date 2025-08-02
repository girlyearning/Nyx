# nyxcore.py

import os
import sys
import logging
import asyncio
from datetime import datetime
import discord
from discord.ext import commands
from dotenv import load_dotenv
from typing import Optional
import traceback

# Add at the top of nyxcore.py after imports:
current_dir = os.path.dirname(os.path.abspath(__file__)) or '.'
sys.path.insert(0, current_dir)

# ★ Load environment variables
load_dotenv()

# ★ BOT CONSTANTS
NYX_COLOR = 0x76b887
FONT = "monospace"
COG_DIRECTORY = "."
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
TOKEN = os.getenv("DISCORD_TOKEN")
LOG_CHANNEL_ID = 1388809359206780998

# ★ Ensure storage directory exists
os.makedirs(STORAGE_PATH, exist_ok=True)

# ★ Validate token
if not TOKEN or TOKEN.strip() == "":
    print("❌ Error: DISCORD_TOKEN not found or empty in environment variables!")
    sys.exit(1)

# ★ Setup Logging FIRST
def setup_logging() -> logging.Logger:
    """Set up logging with file and console only."""
    
    file_formatter = logging.Formatter(
        "[{asctime}] [{levelname}] {name}: {message}",
        style="{"
    )
    
    console_formatter = logging.Formatter(
        "[{levelname}] {name}: {message}",
        style="{"
    )
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler("nyx.log", encoding="utf-8")
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return logging.getLogger("nyxcore")

# ★ Initialize logging system IMMEDIATELY
logger = setup_logging()

# ★ MINIMAL Rate Limiter - MUCH simpler
class GlobalRateLimiter:
    """Minimal global rate limiter for Discord API calls."""
    
    def __init__(self):
        self.last_api_call = 0
        self.min_interval = 3.0  # 3 seconds minimum between API calls (INCREASED)
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self):
        """Wait if we're making API calls too quickly."""
        async with self._lock:
            current_time = asyncio.get_event_loop().time()
            time_since_last = current_time - self.last_api_call
            
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                await asyncio.sleep(wait_time)
            
            self.last_api_call = asyncio.get_event_loop().time()

# ★ Create bot with MINIMAL intents
intents = discord.Intents.default()
intents.message_content = True
# DISABLE UNNECESSARY INTENTS THAT CAUSE API CALLS
intents.presences = False
intents.typing = False
intents.voice_states = False

bot = commands.Bot(
    command_prefix="!", 
    intents=intents,
    help_command=None  # Disable default help to prevent conflicts
)

# ★ Add rate limiter IMMEDIATELY
bot.rate_limiter = GlobalRateLimiter()

# ★ ULTRA-SAFE message sender
async def safe_send_message(channel, content=None, embed=None):
    """Ultra-safe message sender with maximum protection."""
    try:
        # Wait for rate limit
        await bot.rate_limiter.wait_if_needed()
        
        # Make API call with additional safety delay
        await asyncio.sleep(0.1)  # Extra safety delay before each send
        
        if embed and content:
            return await channel.send(content=content, embed=embed)
        elif embed:
            return await channel.send(embed=embed)
        elif content:
            return await channel.send(content=content)
        else:
            return None
            
    except discord.HTTPException as e:
        if e.status == 429:  # Rate limited
            logger.error(f"RATE LIMITED: {e}")
            # Don't retry - just fail silently
            return None
        elif e.status in [403, 404]:
            logger.warning(f"Cannot send message (403/404): {e}")
            return None
        else:
            logger.error(f"HTTP error: {e}")
            return None
    except Exception as e:
        logger.error(f"Unexpected error in safe_send: {e}")
        return None

# Add to bot
bot.safe_send = safe_send_message

# ★ Track if cogs are already loaded
bot._cogs_loaded = False

# ★ MINIMAL event handlers
@bot.event
async def on_ready():
    """Called when bot is ready - ONLY load cogs once."""
    logger.info(f"🤖 Bot ready: {bot.user} (ID: {bot.user.id})")
    
    # CRITICAL: Only load cogs ONCE
    if not bot._cogs_loaded:
        logger.info("🔄 Loading cogs for the first time...")
        await load_cogs()
        bot._cogs_loaded = True
        logger.info("✅ Cogs loaded successfully!")
    else:
        logger.info("ℹ️ Bot reconnected - cogs already loaded")

@bot.event
async def on_command_error(ctx, error):
    """Minimal error handler."""
    # Ignore common non-errors
    if isinstance(error, (commands.CommandNotFound, commands.DisabledCommand)):
        return
    
    # Log serious errors only
    logger.error(f"Command error: {error}")
    
    # Try to send error message (fail silently if rate limited)
    try:
        await safe_send_message(ctx.channel, "❌ Command error occurred.")
    except:
        pass

# ★ CONSERVATIVE cog loader
async def load_cogs():
    """Load cogs with maximum safety and delays."""
    
    # DEBUG: Log environment info for troubleshooting
    logger.info(f"📂 Script location: {os.path.abspath(__file__)}")
    logger.info(f"📂 Working directory: {os.getcwd()}")
    logger.info(f"📁 Directory contents: {os.listdir('.')}")
    if os.path.exists('cogs'):
        logger.info(f"📁 Cogs directory contents: {os.listdir('cogs')}")
    else:
        logger.error("❌ Cogs directory not found!")
    
    cog_files = [
        "memory.py", "nyxtasks.py", "comfort.py", "prefixgame.py", 
        "unscramble.py", "wordhunt.py", "workshop.py", "asylumchat.py", "alliteration.py"
    ]
    
    loaded = 0
    
    for filename in cog_files:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Try cogs/ subdirectory first (local development)
        cog_path = os.path.join(script_dir, "cogs", filename)
        cog_name = f"cogs.{filename[:-3]}"
        
        # If not found, try root directory (Render deployment)
        if not os.path.exists(cog_path):
            cog_path = os.path.join(script_dir, filename)
            cog_name = filename[:-3]  # Just the module name without cogs prefix
        
        logger.debug(f"🔍 Checking for cog file: {cog_path}")
        
        if not os.path.exists(cog_path):
            logger.warning(f"⚠️ Cog file not found: {cog_path}")
            continue
        
        try:
            # LONG delay between each cog
            if loaded > 0:
                logger.info(f"⏳ Waiting 5 seconds before loading {cog_name}...")
                await asyncio.sleep(5.0)  # 5 second delay!
            
            logger.info(f"🔄 Loading cog: {cog_name}")
            await bot.load_extension(cog_name)
            logger.info(f"✅ Loaded: {cog_name}")
            loaded += 1
            
            # Small delay after successful load
            await asyncio.sleep(1.0)
            
        except Exception as e:
            logger.error(f"❌ Failed to load {cog_name}: {e}")
            logger.error(traceback.format_exc())
            # Wait even after failures
            await asyncio.sleep(2.0)
    
    logger.info(f"🎯 Loaded {loaded}/{len(cog_files)} cogs")

# ★ MINIMAL help command
@bot.command(name='nyxhelp')
async def nyx_help(ctx):
    """Display available commands."""
    try:
        help_text = """🌙 **Nyx Commands**

**📊 Points & Stats**
`!nyxnotes` - View your points
`!leaderboard` - Top users

**🎮 Games**  
`!prefixgame` - Word game
`!unscramble` - Unscramble game
`!easywordhunt` / `!hardwordhunt` - Word hunt

**💬 Chat**
`!dmcomfort` - Support chat
`!asylumchat` - Multi-personality chat

**📝 Workshop**
`!monday` / `!tuesday` / `!thursday` / `!friday` - Daily prompts
`!weekend` / `!weekendsubmit` - Weekend prompts"""

        await safe_send_message(ctx.channel, help_text)
        
    except Exception as e:
        logger.error(f"Error in help: {e}")

# ★ Emergency commands
@bot.command(name='emergency_restart', hidden=True)
@commands.has_permissions(administrator=True)
async def emergency_restart(ctx):
    """Emergency restart."""
    await safe_send_message(ctx.channel, "🚨 Restarting...")
    logger.info("Emergency restart")
    await bot.close()

@bot.command(name='reload_cog', hidden=True)
@commands.has_permissions(administrator=True)
async def reload_cog(ctx, cog_name: str):
    """Reload a specific cog."""
    try:
        await bot.reload_extension(cog_name)
        await safe_send_message(ctx.channel, f"✅ Reloaded {cog_name}")
        logger.info(f"Reloaded cog: {cog_name}")
    except Exception as e:
        await safe_send_message(ctx.channel, f"❌ Failed to reload {cog_name}: {e}")
        logger.error(f"Failed to reload {cog_name}: {e}")

# ★ SIMPLIFIED main function
async def main():
    """Start the bot with maximum safety."""
    try:
        logger.info("🚀 Starting Nyx bot...")
        
        # Start bot - cogs will load in on_ready
        await bot.start(TOKEN)
        
    except KeyboardInterrupt:
        logger.info("⏹️ Shutdown requested")
    except discord.LoginFailure:
        logger.error("💥 Login failed - check token!")
    except Exception as e:
        logger.error(f"💥 Startup failed: {e}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("👋 Shutting down...")
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())