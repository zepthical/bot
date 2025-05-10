import os
import discord
from discord.ext import commands
import random
import requests
from github import Github
from github.GithubException import RateLimitExceededException
import time
from datetime import datetime
import asyncio

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# GitHub configuration
GITHUB_TOKEN = os.getenv('GIT_TOKEN')
REPO_NAME = "zepthical/k"
KEYS_RAW_URL = "https://raw.githubusercontent.com/zepthical/k/main/Keys.txt"
KEYS_FILE = "Keys.txt"
USED_KEYS_FILE = "used_keys.txt"
LOG_CHANNEL_ID = 1369717331730894991

# Initialize GitHub client
g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)

def fetch_keys_from_raw_url():
    try:
        response = requests.get(KEYS_RAW_URL)
        response.raise_for_status()
        return response.text.splitlines()
    except requests.RequestException as e:
        print(f"Error fetching keys: {e}")
        return []

def get_file_content(file_path):
    for attempt in range(3):
        try:
            file_content = repo.get_contents(file_path)
            return file_content.decoded_content.decode('utf-8').splitlines(), file_content.sha
        except RateLimitExceededException:
            reset_time = g.get_rate_limit().core.reset
            wait_seconds = (reset_time - datetime.utcnow()).total_seconds() + 5
            print(f"Rate limit exceeded. Waiting {wait_seconds} seconds...")
            time.sleep(max(wait_seconds, 0))
        except Exception as e:
            print(f"Error fetching {file_path}: {e}")
            return [], None
    print("Failed to fetch file after retries.")
    return [], None

def update_file(file_path, content, sha, commit_message):
    for attempt in range(3):
        try:
            repo.update_file(file_path, commit_message, content, sha)
            return True
        except RateLimitExceededException:
            reset_time = g.get_rate_limit().core.reset
            wait_seconds = (reset_time - datetime.utcnow()).total_seconds() + 5
            print(f"Rate limit exceeded. Waiting {wait_seconds} seconds...")
            time.sleep(max(wait_seconds, 0))
        except Exception as e:
            print(f"Error updating {file_path}: {e}")
            return False
    print("Failed to update file after retries.")
    return False

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command()
@commands.cooldown(1, 86400, commands.BucketType.user)
async def getkey(ctx):
    confirm_msg = await ctx.send(f"{ctx.author.mention}, react with ✅ to receive a key in DMs. (Expires in 30 seconds)")
    await confirm_msg.add_reaction("✅")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

    try:
        await bot.wait_for('reaction_add', timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await confirm_msg.delete()
        await ctx.send(f"{ctx.author.mention}, key request timed out.")
        return

    await confirm_msg.delete()
    keys = fetch_keys_from_raw_url()
    valid_keys = [key.strip() for key in keys if key.strip() and any(c.isalnum() for c in key.strip())]

    if not valid_keys:
        await ctx.send("No valid keys available.")
        return

    selected_key = random.choice(valid_keys)
    await ctx.send("Key generated! Check your DMs.")

    try:
        await ctx.author.send(f"Your key: **{selected_key}**")
    except discord.Forbidden:
        await ctx.send(f"{ctx.author.mention}, I couldn't DM you. Enable DMs from server members.")
        return

    keys_content, keys_sha = get_file_content(KEYS_FILE)
    updated_keys = [key for key in keys_content if key.strip() != selected_key]

    if not update_file(KEYS_FILE, '\n'.join(updated_keys), keys_sha, f"Remove key {selected_key}"):
        await ctx.send("Error updating key list.")
        return

    used_keys, used_keys_sha = get_file_content(USED_KEYS_FILE)
    used_keys.append(selected_key)

    if not update_file(USED_KEYS_FILE, '\n'.join(used_keys), used_keys_sha, f"Add used key {selected_key}"):
        await ctx.send("Error updating used keys.")
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        log_message = f"**Key Distributed**\nUser: {ctx.author.name} ({ctx.author.id})\nKey: {selected_key}\nTimestamp: {timestamp}"
        try:
            await log_channel.send(log_message)
        except discord.Forbidden:
            print(f"Error: Cannot send to log channel {LOG_CHANNEL_ID}")
    else:
        print(f"Error: Log channel {LOG_CHANNEL_ID} not found")

@bot.command()
async def verifykey(ctx, key: str):
    used_keys, _ = get_file_content(USED_KEYS_FILE)
    try:
        message = f"The key **{key}** is valid and has been used." if key.strip() in [k.strip() for k in used_keys] else f"The key **{key}** is not found in used keys."
        await ctx.author.send(message)
        await ctx.send("Verification result sent to your DMs.")
    except discord.Forbidden:
        await ctx.send(f"{ctx.author.mention}, I couldn't DM you. Enable DMs from server members.")

@bot.command()
async def cooldown(ctx):
    command = bot.get_command('getkey')
    cooldown = command.get_cooldown_retry_after(ctx) if command else 0
    if cooldown > 0:
        hours = int(cooldown // 3600)
        minutes = int((cooldown % 3600) // 60)
        await ctx.send(f"{ctx.author.mention}, you can use !getkey again in {hours} hours and {minutes} minutes.")
    else:
        await ctx.send(f"{ctx.author.mention}, you can use !getkey now!")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        retry_after = error.retry_after
        hours = int(retry_after // 3600)
        minutes = int((retry_after % 3600) // 60)
        await ctx.send(f"{ctx.author.mention}, you can use this command again in {hours} hours and {minutes} minutes.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"{ctx.author.mention}, please provide a key. Usage: !verifykey <key>")
    else:
        print(f"Error: {error}")
        raise error

BOT_TOKEN = os.getenv('DISCORD_TOKEN')

bot.run(BOT_TOKEN)
