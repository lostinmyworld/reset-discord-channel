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
CONFIRM_TIMEOUT_SECONDS = 30

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_clears = {}

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
        await self.status_message.edit(content=f"🗑️ Deleting... {self.deleted_count} messages so far. Type `!stop` to stop.")

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

async def delete_history(channel, amount, status_message, progress, stop_requested):
    recent_messages = []

    async for message in channel.history(limit=amount, before=status_message):
        if stop_requested.is_set():
            return

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

async def cancel_prompt(prompt):
    await prompt.edit(content="❌ Clear cancelled.")
    await prompt.delete(delay=5)

async def confirm_full_clear(ctx):
    prompt = await ctx.send(f"⚠️ This deletes every message in this channel. Type `yes` within {CONFIRM_TIMEOUT_SECONDS} seconds to continue.")

    def is_reply_from_author(message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        reply = await bot.wait_for("message", check=is_reply_from_author, timeout=CONFIRM_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await cancel_prompt(prompt)
        return False

    if reply.content.strip().lower() != "yes":
        await cancel_prompt(prompt)
        return False

    return True

async def run_clear(ctx, amount, stop_requested):
    if not amount:
        confirmed = await confirm_full_clear(ctx)
        if not confirmed:
            return

    status_message = await ctx.send("🗑️ Deleting messages...")
    progress = ProgressReporter(status_message)
    await delete_history(ctx.channel, amount, status_message, progress, stop_requested)

    if stop_requested.is_set():
        await status_message.edit(content=f"🛑 Stopped. Deleted {progress.deleted_count} messages.")
    elif amount:
        await status_message.edit(content=f"🗑️ Deleted {progress.deleted_count} messages.")
    else:
        await status_message.edit(content=f"🗑️ Channel cleared! Deleted {progress.deleted_count} messages.")

    # Auto-delete the confirmation message after 5 seconds
    await status_message.delete(delay=5)

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f"⚠️ {error}", delete_after=10)
        return
    await commands.Bot.on_command_error(bot, ctx, error)

@bot.command()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True, read_message_history=True)
async def clear(ctx, amount: int = None):
    await ctx.message.delete()

    if ctx.channel.id in active_clears:
        await ctx.send("⏳ A clear is already running in this channel.", delete_after=5)
        return

    stop_requested = asyncio.Event()
    active_clears[ctx.channel.id] = stop_requested
    try:
        await run_clear(ctx, amount, stop_requested)
    finally:
        del active_clears[ctx.channel.id]

@bot.command()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def stop(ctx):
    await ctx.message.delete()

    stop_requested = active_clears.get(ctx.channel.id)
    if stop_requested is None:
        await ctx.send("ℹ️ No clear is running in this channel.", delete_after=5)
        return

    stop_requested.set()

bot.run(TOKEN)