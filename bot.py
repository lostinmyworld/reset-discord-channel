import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

BULK_DELETE_MAX_AGE = timedelta(days=14)
BULK_DELETE_BATCH_SIZE = 100
SINGLE_DELETE_DELAY_SECONDS = 1.1
PROGRESS_UPDATE_INTERVAL_SECONDS = 10
CONFIRM_TIMEOUT_SECONDS = 30

class ClearBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = ClearBot()

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
        await self.status_message.edit(content=f"🗑️ Deleting... {self.deleted_count} messages so far. Use `/stop` to stop.")

class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=CONFIRM_TIMEOUT_SECONDS)
        self.confirmed = False

    @discord.ui.button(label="Yes, delete everything", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        self.confirmed = True
        await interaction.response.edit_message(content="🗑️ Clearing the channel...", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="❌ Clear cancelled.", view=None)
        self.stop()

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

async def confirm_full_clear(interaction):
    view = ConfirmView()
    await interaction.response.send_message("⚠️ This deletes every message in this channel.", view=view, ephemeral=True)

    timed_out = await view.wait()
    if timed_out:
        await interaction.edit_original_response(content="❌ Clear cancelled.", view=None)

    return view.confirmed

async def run_clear(interaction, amount, stop_requested):
    if amount is None:
        confirmed = await confirm_full_clear(interaction)
        if not confirmed:
            return
    else:
        await interaction.response.send_message(f"🗑️ Deleting the last {amount} messages...", ephemeral=True)

    status_message = await interaction.channel.send("🗑️ Deleting messages...")
    progress = ProgressReporter(status_message)
    await delete_history(interaction.channel, amount, status_message, progress, stop_requested)

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

@bot.tree.error
async def on_app_command_error(interaction, error):
    if isinstance(error, (app_commands.MissingPermissions, app_commands.BotMissingPermissions)):
        await interaction.response.send_message(f"⚠️ {error}", ephemeral=True)
        return
    await app_commands.CommandTree.on_error(bot.tree, interaction, error)

@bot.tree.command(name="clear", description="Delete messages in this channel.")
@app_commands.describe(amount="How many recent messages to delete. Leave empty to delete all.")
@app_commands.guild_only()
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True, send_messages=True)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1] = None):
    if interaction.channel_id in active_clears:
        await interaction.response.send_message("⏳ A clear is already running in this channel.", ephemeral=True)
        return

    stop_requested = asyncio.Event()
    active_clears[interaction.channel_id] = stop_requested
    try:
        await run_clear(interaction, amount, stop_requested)
    finally:
        del active_clears[interaction.channel_id]

@bot.tree.command(name="stop", description="Stop the running clear in this channel.")
@app_commands.guild_only()
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.has_permissions(manage_messages=True)
async def stop(interaction: discord.Interaction):
    stop_requested = active_clears.get(interaction.channel_id)
    if stop_requested is None:
        await interaction.response.send_message("ℹ️ No clear is running in this channel.", ephemeral=True)
        return

    stop_requested.set()
    await interaction.response.send_message("🛑 Stopping...", ephemeral=True)

bot.run(TOKEN)