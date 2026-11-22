# reset-discord-channel
A Discord bot that deletes messages from a channel, while keeping the channel itself (ID, webhooks, pins, permissions).

## Commands
| Command | What it does |
|---|---|
| `!clear` | Deletes every message in the channel. Asks you to type `yes` within 30 seconds first. |
| `!clear X` | Deletes the last `X` messages. Example: `!clear 4` |
| `!stop` | Stops a running clear in the channel. |

- Only one clear runs per channel at a time.
- A status message shows how many messages are deleted so far, and disappears 5 seconds after the clear ends.
- Messages posted after the clear starts are not deleted.
- You need the **Manage Messages** permission to use the commands.

## Speed
Discord limits how fast messages can be deleted:
- Messages newer than 14 days are deleted 100 at a time — fast.
- Older messages are deleted one by one, about 1 per second. 10,000 old messages take about 3 hours.

If the bot stops mid-clear, run `!clear` again — it continues with what is left.

## Setup
1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Under **Bot**, turn on **Message Content Intent**.
3. Invite the bot to your server with these permissions:
   - View Channels
   - Send Messages
   - Manage Messages
   - Read Message History
4. Create a `.env` file next to `bot.py`:
   ```
   DISCORD_TOKEN=<your bot token>
   ```
5. Install and run:
   ```
   pip install -r requirements.txt
   python bot.py
   ```

You can run it on your own PC or host it anywhere. If you run it locally, keep the PC awake during long clears.
