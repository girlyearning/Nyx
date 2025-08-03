# asknyx.py
import os
import json
import asyncio
import aiofiles
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from discord.ext import commands
import discord
import logging

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️ Anthropic not installed. AskNyx functionality will be limited.")

NYX_COLOR = 0x76b887
STORAGE_PATH = os.getenv("STORAGE_PATH", "./nyxnotes")
os.makedirs(STORAGE_PATH, exist_ok=True)

class AskNyx(commands.Cog):
    """Ask Nyx questions with web search capabilities while maintaining her personality."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.storage_path = STORAGE_PATH
        self.asknyx_history_file = os.path.join(self.storage_path, 'asknyx_history.json')
        self._lock = asyncio.Lock()
        self.logger = logging.getLogger("asknyx")
        
        # Rate limiting for API calls
        self._user_cooldowns = {}
        
        # Ensure storage directory exists
        os.makedirs(self.storage_path, exist_ok=True)
        
        # Nyx's personality for AskNyx
        self.nyx_personality = """You are Nyx, the mysteriously charming but edgy Atypical Asylum Nurse. 

PERSONALITY GUIDELINES:
- You are mysteriously charismatic, blending deadpan, edgy humor with intelligent, helpful responses
- You are a strange and oddly comforting asylum nurse who always knows what to say
- You have access to current web information and can search for accurate, up-to-date answers
- You maintain your personality while being genuinely helpful and informative

RESPONSE STYLE:
- Stay true to being a mysteriously comforting but humorously edgy asylum nurse
- Use niche, edgy humor but don't be cringeworthy  
- Always be helpful and provide accurate information when asked questions
- When you use web search results, integrate them naturally into your response
- Keep responses concise but informative
- Always separate more than two sentences with a new line
- Don't use every response style in the same message

You're Nyx answering questions with the help of current web information while maintaining your unique personality."""

    async def cog_load(self):
        """Called when cog is loaded - initialize data"""
        try:
            self.logger.info("AskNyx cog loading...")
            
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
            
            self.logger.info("AskNyx cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Error in asknyx cog_load: {e}")
            raise

    async def cog_unload(self):
        """Called when cog is unloaded - clean up gracefully"""
        try:
            self.logger.info("AskNyx cog unloading...")
            self.logger.info("AskNyx cog unloaded successfully")
        except Exception as e:
            self.logger.error(f"Error during asknyx cog unload: {e}")

    async def load_asknyx_history(self) -> Dict:
        """Load AskNyx conversation history from persistent storage."""
        async with self._lock:
            if os.path.exists(self.asknyx_history_file):
                try:
                    async with aiofiles.open(self.asknyx_history_file, 'r', encoding='utf-8') as f:
                        data = await f.read()
                        if data.strip():
                            return json.loads(data)
                except Exception as e:
                    self.logger.error(f"Error loading asknyx history: {e}")
            
            return {}

    async def save_asknyx_history(self, history: Dict):
        """Save AskNyx conversation history to persistent storage."""
        async with self._lock:
            try:
                os.makedirs(os.path.dirname(self.asknyx_history_file), exist_ok=True)
                
                temp_file = self.asknyx_history_file + '.tmp'
                async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(history, indent=2, ensure_ascii=False))
                
                if os.path.exists(self.asknyx_history_file):
                    backup_file = self.asknyx_history_file + '.backup'
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(self.asknyx_history_file, backup_file)
                    
                os.rename(temp_file, self.asknyx_history_file)
                self.logger.debug(f"AskNyx history saved successfully")
                
            except Exception as e:
                self.logger.error(f"Error saving asknyx history: {e}")
                # Try to restore backup if save failed
                backup_file = self.asknyx_history_file + '.backup'
                if os.path.exists(backup_file) and not os.path.exists(self.asknyx_history_file):
                    try:
                        os.rename(backup_file, self.asknyx_history_file)
                        self.logger.info("Restored asknyx history from backup")
                    except Exception as restore_error:
                        self.logger.error(f"Failed to restore backup: {restore_error}")

    @commands.command(name="asknyx")
    async def asknyx(self, ctx, *, question: str = None):
        """Ask Nyx a question with web search capabilities."""
        if not question:
            embed = discord.Embed(
                title="❓ Ask Nyx",
                description="Please provide a question to ask Nyx.\n\nExample: `!asknyx What's the latest news about Discord?`",
                color=NYX_COLOR
            )
            await self.bot.safe_send(ctx.channel, embed=embed)
            return

        # Rate limiting check
        user_id = ctx.author.id
        now = time.time()
        
        if user_id in self._user_cooldowns:
            if now - self._user_cooldowns[user_id] < 30.0:  # 30 second cooldown
                remaining = int(30 - (now - self._user_cooldowns[user_id]))
                embed = discord.Embed(
                    title="⏰ Cooldown Active",
                    description=f"Please wait {remaining} seconds before asking another question.",
                    color=0xff0000
                )
                await self.bot.safe_send(ctx.channel, embed=embed)
                return

        self._user_cooldowns[user_id] = now

        # Send thinking message
        thinking_msg = await self.bot.safe_send(ctx.channel, "🔍 Searching for the most current information...")
        
        if not thinking_msg:
            return

        try:
            await self.process_question(ctx, question, thinking_msg)
        except Exception as e:
            self.logger.error(f"Error processing question from {ctx.author}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="I encountered an error while processing your question. Please try again later.",
                color=0xff0000
            )
            await self.bot.safe_send(ctx.channel, embed=embed)
            try:
                await thinking_msg.delete()
            except:
                pass

    async def process_question(self, ctx, question: str, thinking_msg):
        """Process the user's question with web search and AI response."""
        try:
            user_id = str(ctx.author.id)
            
            # Load conversation history
            history = await self.load_asknyx_history()
            user_history = history.get(user_id, [])
            
            # Perform web search
            search_results = await self.perform_web_search(question)
            
            # Build conversation context with last 5 exchanges
            conversation = []
            
            # Add recent conversation history (last 5 Q&As)
            recent_history = user_history[-5:] if len(user_history) > 5 else user_history
            for exchange in recent_history:
                conversation.append({
                    'role': 'user',
                    'content': exchange['question']
                })
                conversation.append({
                    'role': 'assistant', 
                    'content': exchange['answer']
                })
            
            # Prepare the current question with search context
            search_context = ""
            if search_results:
                search_context = f"\n\nCurrent web search results for this topic:\n{search_results}"
            
            current_question = f"{question}{search_context}"
            conversation.append({
                'role': 'user',
                'content': current_question
            })
            
            # Generate response using Anthropic
            reply = "I'm having trouble accessing current information right now, but I'll do my best to help with what I know!"
            
            if hasattr(self.bot, 'anthropic_client') and self.bot.anthropic_client:
                try:
                    response = self.bot.anthropic_client.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=500,
                        temperature=0.7,
                        system=self.nyx_personality,
                        messages=conversation[-6:]  # Last 6 messages for context
                    )
                    
                    reply = response.content[0].text
                except Exception as e:
                    self.logger.error(f"Error generating response: {e}")
                    reply = "I'm having a moment of technical difficulty, but I'm still here! Try asking me something else."
            
            # Save exchange to history
            exchange = {
                'question': question,
                'answer': reply,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'had_search_results': bool(search_results),
                'channel_id': ctx.channel.id,
                'channel_name': ctx.channel.name
            }
            
            user_history.append(exchange)
            
            # Keep only last 10 exchanges per user
            if len(user_history) > 10:
                user_history = user_history[-10:]
            
            history[user_id] = user_history
            await self.save_asknyx_history(history)
            
            # Send response
            embed = discord.Embed(
                title="💭 Nyx's Response",
                description=reply,
                color=NYX_COLOR
            )
            embed.set_footer(text=f"Asked by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            
            try:
                await thinking_msg.edit(content="", embed=embed)
            except:
                await self.bot.safe_send(ctx.channel, embed=embed)
                try:
                    await thinking_msg.delete()
                except:
                    pass
            
        except Exception as e:
            self.logger.error(f"Error processing question: {e}")
            raise

    async def perform_web_search(self, query: str) -> str:
        """Perform web search using Google Custom Search API and DuckDuckGo fallback."""
        try:
            import aiohttp
            from urllib.parse import quote_plus
            
            search_results = []
            
            # Approach 1: Google Custom Search API (Primary)
            try:
                google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
                if not google_api_key:
                    self.logger.warning("GOOGLE_SEARCH_API_KEY not found in environment variables")
                    raise Exception("No Google API key available")
                
                search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
                if not search_engine_id:
                    self.logger.warning("GOOGLE_SEARCH_ENGINE_ID not found in environment variables")
                    raise Exception("No Google Search Engine ID available")
                
                google_url = f"https://www.googleapis.com/customsearch/v1?key={google_api_key}&cx={search_engine_id}&q={quote_plus(query)}&num=5"
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                    async with session.get(google_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if data.get('items'):
                                for i, item in enumerate(data['items'][:3]):  # Limit to 3 results
                                    title = item.get('title', 'No title')
                                    snippet = item.get('snippet', 'No description')
                                    link = item.get('link', '')
                                    
                                    # Format result
                                    result_text = f"🔍 **{title}**\n{snippet}"
                                    if len(result_text) > 200:  # Truncate if too long
                                        result_text = result_text[:197] + "..."
                                    
                                    search_results.append(result_text)
                                
                                if search_results:
                                    formatted_results = "\n\n".join(search_results)
                                    return f"🌐 **Current Web Search Results:**\n\n{formatted_results}"
                        
                        elif response.status == 403:
                            self.logger.warning("Google API quota exceeded or invalid key")
                        else:
                            self.logger.warning(f"Google API returned status {response.status}")
                            
            except Exception as google_error:
                self.logger.debug(f"Google search error: {google_error}")
            
            # Approach 2: DuckDuckGo Fallback
            try:
                ddg_url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.get(ddg_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Extract abstract
                            if data.get('Abstract'):
                                search_results.append(f"📖 **Summary:** {data['Abstract']}")
                            
                            # Extract definition
                            if data.get('Definition'):
                                search_results.append(f"📚 **Definition:** {data['Definition']}")
                            
                            # Extract answer
                            if data.get('Answer'):
                                search_results.append(f"💡 **Answer:** {data['Answer']}")
                            
                            # Extract related topics (limit to 2)
                            if data.get('RelatedTopics'):
                                topics_added = 0
                                for topic in data['RelatedTopics']:
                                    if topics_added >= 2:
                                        break
                                    if isinstance(topic, dict) and topic.get('Text'):
                                        search_results.append(f"🔗 **Related:** {topic['Text']}")
                                        topics_added += 1
            
            except Exception as ddg_error:
                self.logger.debug(f"DuckDuckGo search error: {ddg_error}")
            
            # Return results if found
            if search_results:
                formatted_results = "\n\n".join(search_results[:4])  # Limit to 4 results max
                return f"🌐 **Web Search Results:**\n\n{formatted_results}"
            
            # No results found
            return f"🔍 [Searched the web for: {query}] - No specific results found, but I'll use my knowledge to help."
            
        except ImportError:
            self.logger.warning("aiohttp not available for web search")
            return f"🔍 [Search attempted for: {query}] - Limited search capabilities available."
        except Exception as e:
            self.logger.error(f"Error in web search: {e}")
            return f"🔍 [Search error for: {query}] - I'll answer based on my training data."

async def setup(bot):
    await bot.add_cog(AskNyx(bot))