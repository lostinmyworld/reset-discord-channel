import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = None):
    await ctx.message.delete()

    if amount:
        # Delete a specific number of messages
        deleted = await ctx.channel.purge(limit=amount)
        msg = await ctx.send(f"🗑️ Deleted {len(deleted)} messages.")
    else:
        # Delete all messages in the channel
        deleted = await ctx.channel.purge(limit=None)
        msg = await ctx.send(f"🗑️ Channel cleared! Deleted {len(deleted)} messages.")
    
    # Auto-delete the confirmation message after 5 seconds
    await msg.delete(delay=5)

bot.run(TOKEN)