import asyncio
import discord
import os
import json
import yt_dlp
import datetime
import random
import re
import aiohttp
from aiohttp import web
from discord.ext import commands
from discord import app_commands
from typing import List, Optional, Union
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
YT_COOKIES = os.getenv('YT_COOKIES')

if YT_COOKIES:
    with open('cookies.txt', 'w') as f:
        f.write(YT_COOKIES)
    print("[System] YT_COOKIES environment variable loaded.")

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[System] Web server live on port {port}")

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extract_flat': 'in_playlist',
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'youtube_include_dash_manifest': False,
}

if os.path.exists('cookies.txt'):
    YTDL_OPTIONS['cookiefile'] = 'cookies.txt'

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

def format_duration(duration):
    if duration:
        return str(datetime.timedelta(seconds=int(duration)))
    return "00:00"

def create_progress_bar(current, total):
    if not total: return "━" * 15
    size = 15
    progress = int((min(current, total) / total) * size)
    return f"`{format_duration(current)}` {'━' * progress}●{'─' * (size - progress)} `{format_duration(total)}`"

@lru_cache(maxsize=128)
def get_search_results(query):
    fast_ytdl = yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True, 'default_search': 'ytsearch5'})
    try: return fast_ytdl.extract_info(f"ytsearch5:{query}", download=False)
    except: return None

class MusicControlView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player

    @discord.ui.button(label="VOL-", style=discord.ButtonStyle.secondary)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.volume = max(0.0, self.player.volume - 0.1)
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = self.player.volume
        await interaction.response.edit_message(embed=self.player.create_np_embed())

    @discord.ui.button(label="II", style=discord.ButtonStyle.primary)
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc: return
        if vc.is_playing():
            vc.pause()
            button.label = ">"
            button.style = discord.ButtonStyle.success
        elif vc.is_paused():
            vc.resume()
            button.label = "II"
            button.style = discord.ButtonStyle.primary
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc: vc.stop()
        await interaction.response.send_message("Skipped track.", ephemeral=True)

    @discord.ui.button(label="VOL+", style=discord.ButtonStyle.secondary)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.volume = min(1.0, self.player.volume + 0.1)
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = self.player.volume
        await interaction.response.edit_message(embed=self.player.create_np_embed())

    @discord.ui.button(label="LOOP", style=discord.ButtonStyle.secondary, row=1)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop = not self.player.loop
        button.style = discord.ButtonStyle.success if self.player.loop else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="SHUFFLE", style=discord.ButtonStyle.secondary, row=1)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.player.queue) < 2: return await interaction.response.send_message("Queue too short.", ephemeral=True)
        random.shuffle(self.player.queue)
        await interaction.response.send_message("Queue shuffled.", ephemeral=True)

    @discord.ui.button(label="STOP", style=discord.ButtonStyle.danger, row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player._cog.cleanup(interaction.guild)
        await interaction.response.send_message("Stopped.", ephemeral=True)

class MusicPlayer:
    def __init__(self, ctx: Union[discord.Interaction, commands.Context]):
        self.bot = ctx.client if isinstance(ctx, discord.Interaction) else ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = self.bot.get_cog('Music')
        self.queue = []
        self.history = []
        self.next = asyncio.Event()
        self.np_message = None 
        self.volume = .5
        self.current = None
        self.loop = False
        self.stopped = False
        self.start_time = None
        self.update_task = None
        self.mode_247 = False
        self.locked_channel_id = None
        self.bot.loop.create_task(self.player_loop())

    async def update_np_periodically(self):
        while self.current and not self.stopped:
            await asyncio.sleep(5)
            if self.np_message:
                try: await self.np_message.edit(embed=self.create_np_embed())
                except: break

    async def player_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed() and not self.stopped:
            self.next.clear()
            if self.update_task: self.update_task.cancel()

            if not self.loop or not self.current:
                try:
                    async with asyncio.timeout(300):
                        while not self.queue: await asyncio.sleep(1)
                        url, requester = self.queue.pop(0)
                        data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                        if 'entries' in data: data = data['entries'][0]
                        self.current = data
                        self.current['requester'] = requester
                except:
                    if self.mode_247: continue
                    return self.destroy(self._guild)

            try:
                source = await discord.FFmpegOpusAudio.from_probe(self.current['url'], **FFMPEG_OPTIONS)
                source = discord.PCMVolumeTransformer(source, volume=self.volume)
                self.start_time = datetime.datetime.now()
                self._guild.voice_client.play(source, after=lambda e: self.bot.loop.call_soon_threadsafe(self.next.set))
                self.np_message = await self._channel.send(embed=self.create_np_embed(), view=MusicControlView(self))
                self.update_task = self.bot.loop.create_task(self.update_np_periodically())
                await self.next.wait()
            except Exception as e:
                print(f"[Player] Error: {e}")
                await asyncio.sleep(5)
            
            if not self.loop: self.current = None

    def create_np_embed(self):
        data = self.current
        elapsed = (datetime.datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        embed = discord.Embed(title="Now Playing", description=f"### [{data['title']}]({data.get('webpage_url', data['url'])})", color=discord.Color.from_rgb(43, 45, 49))
        if data.get('thumbnail'): embed.set_thumbnail(url=data['thumbnail'])
        embed.add_field(name="Requested By", value=data['requester'].mention, inline=True)
        embed.add_field(name="Volume", value=f"`{int(self.volume * 100)}%`", inline=True)
        embed.add_field(name="Queue", value=f"`{len(self.queue)} songs`", inline=True)
        embed.add_field(name="Playback Progress", value=create_progress_bar(elapsed, data.get('duration', 0)), inline=False)
        embed.set_footer(text=f"Loop: {'Enabled' if self.loop else 'Disabled'}")
        return embed

    def destroy(self, guild):
        self.stopped = True
        return self.bot.loop.create_task(self._cog.cleanup(guild))

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players = {}
        self.locked_guild_id = None

    async def cleanup(self, guild: discord.Guild):
        try: await guild.voice_client.disconnect()
        except: pass
        player = self.players.get(guild.id)
        if player:
            player.stopped = True
            if player.np_message:
                try: await player.np_message.delete()
                except: pass
            del self.players[guild.id]

    def get_player(self, ctx: Union[discord.Interaction, commands.Context]):
        guild_id = ctx.guild.id if isinstance(ctx, commands.Context) else ctx.guild_id
        if guild_id not in self.players: self.players[guild_id] = MusicPlayer(ctx)
        return self.players[guild_id]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.locked_guild_id and self.locked_guild_id != interaction.guild_id:
            await interaction.response.send_message("Bot is locked to another server.", ephemeral=True)
            return False
        return True

    @app_commands.command(name='play', description='Play a song from YouTube or a URL')
    @app_commands.describe(search='Song name or YouTube URL')
    async def play(self, interaction: discord.Interaction, search: str):
        if not interaction.user.voice: return await interaction.response.send_message("Join a voice channel first!", ephemeral=True)
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Restricted to <#{player.locked_channel_id}>.", ephemeral=True)
        
        await interaction.response.defer()
        if not interaction.guild.voice_client:
            try: await interaction.user.voice.channel.connect(timeout=20, reconnect=True)
            except Exception as e: return await interaction.followup.send(f"Join failed: {e}")

        try:
            data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))
            if 'entries' in data:
                if data.get('_type') == 'playlist':
                    for entry in data['entries']:
                        if entry: player.queue.append((entry.get('webpage_url') or entry.get('url'), interaction.user))
                    return await interaction.followup.send(f"Queued {len(data['entries'])} tracks.")
                data = data['entries'][0]
            
            player.queue.append((data.get('webpage_url') or data.get('url'), interaction.user))
            await interaction.followup.send(embed=discord.Embed(description=f"Queued: **{data.get('title', 'Track')}**", color=discord.Color.from_rgb(43, 45, 49)))
        except Exception as e: await interaction.followup.send(f"Error: {e}")

    @play.autocomplete('search')
    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if not current or len(current) < 3: return []
        try:
            async with asyncio.timeout(2.0):
                data = await self.bot.loop.run_in_executor(None, get_search_results, current)
                if not data or 'entries' not in data: return []
                choices = []
                for e in data['entries']:
                    if not e: continue
                    choices.append(app_commands.Choice(name=e.get('title', 'Unknown')[:100], value=e.get('url')))
                return choices[:5]
        except: return []

    @app_commands.command(name='help', description='Show available commands')
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Music Bot Commands", color=discord.Color.from_rgb(43, 45, 49))
        embed.add_field(name="Commands", value="`/play`, `/pause`, `/resume`, `/skip`, `/stop`, `/queue`, `/history`, `/volume`, `/247`, `/loop`, `/shuffle`, `/ping`, `/lockserver`, `/lockchannel`, `/reload`", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='pause', description='Pause music')
    async def pause(self, interaction: discord.Interaction):
        if interaction.guild.voice_client: interaction.guild.voice_client.pause()
        await interaction.response.send_message("Paused.")

    @app_commands.command(name='resume', description='Resume music')
    async def resume(self, interaction: discord.Interaction):
        if interaction.guild.voice_client: interaction.guild.voice_client.resume()
        await interaction.response.send_message("Resumed.")

    @app_commands.command(name='skip', description='Skip song')
    async def skip(self, interaction: discord.Interaction):
        if interaction.guild.voice_client: interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped.")

    @app_commands.command(name='stop', description='Stop and leave')
    async def stop(self, interaction: discord.Interaction):
        await self.cleanup(interaction.guild)
        await interaction.response.send_message("Disconnected.")

    @app_commands.command(name='queue', description='Show queue')
    async def queue(self, interaction: discord.Interaction):
        p = self.get_player(interaction)
        if not p.queue and not p.current: return await interaction.response.send_message("Queue is empty.", ephemeral=True)
        fmt = f"**Playing**: {p.current['title'] if p.current else 'None'}\n\n"
        fmt += "\n".join(f"{i+1}. {s[0]}" for i, s in enumerate(p.queue[:10]))
        await interaction.response.send_message(embed=discord.Embed(title="Queue", description=fmt, color=discord.Color.from_rgb(43, 45, 49)))

    @app_commands.command(name='ping', description='Check latency')
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Latency: {round(self.bot.latency * 1000)}ms", ephemeral=True)

    @app_commands.command(name='reload', description='Restart bot')
    @app_commands.checks.has_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction):
        await interaction.response.send_message("Restarting...", ephemeral=True)
        await asyncio.sleep(2)
        for guild_id in list(self.players.keys()):
            await self.cleanup(self.bot.get_guild(guild_id))
        import sys
        os.execv(sys.executable, ['python'] + sys.argv)

    @app_commands.command(name='lockserver', description='Lock to server')
    async def lockserver(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user): return
        self.locked_guild_id = None if self.locked_guild_id else interaction.guild_id
        await interaction.response.send_message(f"Server lock: {'Enabled' if self.locked_guild_id else 'Disabled'}")

    @app_commands.command(name='lockchannel', description='Lock to channel')
    async def lockchannel(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user): return
        p = self.get_player(interaction)
        p.locked_channel_id = None if p.locked_channel_id else interaction.channel_id
        await interaction.response.send_message(f"Channel lock: {'Enabled' if p.locked_channel_id else 'Disabled'}")

    @commands.command(name='sync')
    async def sync_prefix(self, ctx: commands.Context):
        if not await self.bot.is_owner(ctx.author): return
        await self.bot.tree.sync()
        self.bot.tree.copy_global_to(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)
        await ctx.send("Synced.")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        await self.add_cog(Music(self))
        self.loop.create_task(start_web_server())

    async def on_ready(self):
        print(f'[System] Logged in as {self.user}')
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/help"))

bot = MyBot()
if __name__ == '__main__':
    bot.run(TOKEN)
