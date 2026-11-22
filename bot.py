import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

BULK_DELETE_MAX_AGE = timedelta(days=14)
BULK_DELETE_BATCH_SIZE = 100
SINGLE_DELETE_DELAY_SECONDS = 1.1
PROGRESS_UPDATE_INTERVAL_SECONDS = 10

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

class ProgressReporter:
    def __init__(self, status_message):
        self.status_message = status_message
        self.deleted_count = 0
        self.last_update = time.monotonic()

    async def add(self, count):
        self.deleted_count += count
        if self.is_update_due():
            await self.show_count()

    def is_update_due(self):
        seconds_since_update = time.monotonic() - self.last_update
        return seconds_since_update >= PROGRESS_UPDATE_INTERVAL_SECONDS

    async def show_count(self):
        self.last_update = time.monotonic()
        await self.status_message.edit(content=f"🗑️ Deleting... {self.deleted_count} messages so far.")

def is_bulk_deletable(message):
    cutoff = datetime.now(timezone.utc) - BULK_DELETE_MAX_AGE
    return message.created_at > cutoff

async def bulk_delete(channel, messages, progress):
    if not messages:
        return
    await channel.delete_messages(messages)
    await progress.add(len(messages))

async def single_delete(message, progress):
    try:
        await message.delete()
    except discord.NotFound:
        return
    await progress.add(1)
    await asyncio.sleep(SINGLE_DELETE_DELAY_SECONDS)

async def delete_history(channel, amount, status_message, progress):
    recent_messages = []

    async for message in channel.history(limit=amount, before=status_message):
        if is_bulk_deletable(message):
            recent_messages.append(message)
        else:
            await bulk_delete(channel, recent_messages, progress)
            recent_messages = []
            await single_delete(message, progress)

        if len(recent_messages) == BULK_DELETE_BATCH_SIZE:
            await bulk_delete(channel, recent_messages, progress)
            recent_messages = []

    await bulk_delete(channel, recent_messages, progress)

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = None):
    await ctx.message.delete()

    status_message = await ctx.send("🗑️ Deleting messages...")
    progress = ProgressReporter(status_message)
    await delete_history(ctx.channel, amount, status_message, progress)

    if amount:
        await status_message.edit(content=f"🗑️ Deleted {progress.deleted_count} messages.")
    else:
        await status_message.edit(content=f"🗑️ Channel cleared! Deleted {progress.deleted_count} messages.")

    # Auto-delete the confirmation message after 5 seconds
    await status_message.delete(delay=5)

bot.run(TOKEN)