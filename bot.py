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
    print(f"Health check server started on port {port}")

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extract_flat': 'in_playlist',
    'skip_download': True,
    'noprogress': True,
    'cachedir': False,
    'youtube_include_dash_manifest': False,
    'youtube_include_hls_manifest': False,
    'http_chunk_size': 1048576,
    'referer': 'https://www.youtube.com/',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'geo_bypass': True,
    'socket_timeout': 30,
    'retries': 10,
    'extractor_args': {'youtube': ['player_client=android']},
}

if os.path.exists('cookies.txt'):
    ytdl_format_options['cookiefile'] = 'cookies.txt'
    print("[YTDL] Found cookies.txt - Using for authentication")

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 100M -analyzeduration 100M',
    'options': '-vn -b:a 192k -af "volume=1.0" -preset veryfast -thread_queue_size 2048 -movflags faststart',
}

AUDIO_FILTERS = {
    "NONE": "",
    "BASSBOOST": "bass=g=15,equalizer=f=40:width_type=h:width=50:g=10",
    "NIGHTCORE": "atempo=1.06,asetrate=44100*1.25",
    "VAPORWAVE": "atempo=0.8,asetrate=44100*0.8",
    "EARRAKE": "volume=10",
    "CHIPMUNK": "asetrate=44100*1.5",
}

def get_ffmpeg_options(filter_name="NONE"):
    options = ffmpeg_options['options']
    if filter_name != "NONE" and filter_name in AUDIO_FILTERS:
        options += f' -af "{AUDIO_FILTERS[filter_name]}"'
    return options

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

def format_duration(duration):
    if duration:
        return str(datetime.timedelta(seconds=int(duration)))
    return "Unknown"

def create_progress_bar(current, total):
    if not total: 
        return "━" * 15
    
    size = 15
    current = min(current, total)
    progress = int((current / total) * size)
    bar = "━" * progress + "●" + "─" * (size - progress)
    return f"`{format_duration(current)}` {bar} `{format_duration(total)}`"

@lru_cache(maxsize=128)
def get_search_results(query):
    fast_ytdl = yt_dlp.YoutubeDL({
        'extract_flat': 'in_playlist',
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch5',
    })
    try:
        return fast_ytdl.extract_info(f"ytsearch5:{query}", download=False)
    except:
        return None

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown')
        self.url = data.get('url')
        self.thumbnail = data.get('thumbnail')
        self.duration = data.get('duration', 0)
        self.requester = data.get('requester')
        self.webpage_url = data.get('webpage_url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False, requester=None, filter_name="NONE"):
        loop = loop or asyncio.get_event_loop()
        
        payload_ytdl = yt_dlp.YoutubeDL({**ytdl_format_options, 'extract_flat': False})
        
        try:
            data = await loop.run_in_executor(None, lambda: payload_ytdl.extract_info(url, download=not stream))
        except Exception as e:
            print(f"[YTDL] Error: {e}")
            raise e

        if 'entries' in data:
            data = data['entries'][0]
        
        data['requester'] = requester
        filename = data.get('url')
        
        if not filename:
            print(f"[YTDL] Critical: No stream URL found for {data.get('title')}")
            raise Exception("No valid stream URL found.")
            
        options = get_ffmpeg_options(filter_name)
        return cls(discord.FFmpegPCMAudio(filename, before_options=ffmpeg_options['before_options'], options=options), data=data)

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
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("Skipped the current track.", ephemeral=True)

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
        if len(self.player.queue) < 2:
            return await interaction.response.send_message("The queue is too short to shuffle.", ephemeral=True)
        random.shuffle(self.player.queue)
        await interaction.response.send_message("The queue has been shuffled.", ephemeral=True)

    @discord.ui.button(label="STOP", style=discord.ButtonStyle.danger, row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player._cog.cleanup(interaction.guild)
        await interaction.response.send_message("Session stopped.", ephemeral=True)

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
        self.filter = "NONE"
        self.mode_247 = False

        self.locked_channel_id = None
        self.bot.loop.create_task(self.player_loop())

    async def update_np_periodically(self):
        while self.current and not self.stopped:
            await asyncio.sleep(5)
            if self.np_message:
                try:
                    await self.np_message.edit(embed=self.create_np_embed())
                except:
                    break

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed() and not self.stopped:
            self.next.clear()
            if self.update_task:
                self.update_task.cancel()

            if not self.loop or not self.current:
                try:
                    async with asyncio.timeout(300):
                        while not self.queue:
                            await asyncio.sleep(1)
                        url, requester = self.queue.pop(0)
                        source = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True, requester=requester, filter_name=self.filter)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    if self.mode_247:
                        continue
                    return self.destroy(self._guild)
                except Exception as e:
                    print(f"[Player] Loop Error: {e}")
                    continue
            else:
                source = await YTDLSource.from_url(self.current.webpage_url, loop=self.bot.loop, stream=True, requester=self.current.requester, filter_name=self.filter)

            source.volume = self.volume
            self.current = source
            self.start_time = datetime.datetime.now()
            self.history.insert(0, source.title)
            if len(self.history) > 10: self.history.pop()

            print(f"[Player] Playing: {source.title}")
            
            if not self._guild.voice_client:
                print(f"[Player] No voice client for {self._guild.name}. Cleaning up.")
                return self.destroy(self._guild)

            self._guild.voice_client.play(source, after=lambda e: self.bot.loop.call_soon_threadsafe(self.next.set if not e else lambda: print(f"[Player] Error: {e}")))
            
            self.np_message = await self._channel.send(embed=self.create_np_embed(), view=MusicControlView(self))
            self.update_task = self.bot.loop.create_task(self.update_np_periodically())
            
            await self.next.wait()
            source.cleanup()
            if not self.loop: self.current = None

    def create_np_embed(self):
        source = self.current
        elapsed = 0
        if self.start_time:
            elapsed = (datetime.datetime.now() - self.start_time).total_seconds()
        
        embed = discord.Embed(
            title="Now Playing",
            description=f"### [{source.title}]({source.webpage_url})",
            color=discord.Color.from_rgb(43, 45, 49)
        )
        embed.set_thumbnail(url=source.thumbnail)
        
        embed.add_field(name="Requested By", value=source.requester.mention, inline=True)
        embed.add_field(name="Volume", value=f"`{int(self.volume * 100)}%`", inline=True)
        embed.add_field(name="Queue", value=f"`{len(self.queue)} songs`", inline=True)
        
        embed.add_field(name="Playback Progress", value=create_progress_bar(elapsed, source.duration), inline=False)
        
        footer = f"Loop: {'Enabled' if self.loop else 'Disabled'}"
        embed.set_footer(text=footer, icon_url=self.bot.user.display_avatar.url)
        return embed

    def destroy(self, guild):
        self.stopped = True
        return self.bot.loop.create_task(self._cog.cleanup(guild))

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players = {}
        self.locked_guild_id = None

    async def cleanup(self, guild):
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
        if guild_id not in self.players:
            self.players[guild_id] = MusicPlayer(ctx)
        return self.players[guild_id]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.locked_guild_id and self.locked_guild_id != interaction.guild_id:
            await interaction.response.send_message("This bot is locked to another server.", ephemeral=True)
            return False
        return True

    @app_commands.command(name='play', description='Play a song from YouTube or a URL')
    @app_commands.describe(search='Song name or YouTube URL')
    async def play(self, interaction: discord.Interaction, search: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("You need to be in a voice channel to play music.", ephemeral=True)

        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        if not interaction.response.is_done():
            await interaction.response.defer()

        if not interaction.guild.voice_client:
            try:
                await interaction.user.voice.channel.connect(timeout=20, reconnect=True)
            except Exception as e:
                return await interaction.followup.send(f"I couldn't join the voice channel: {e}")

        try:
            if 'list=' in search:
                data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False, process=False))
                if 'entries' in data:
                    entries = list(data['entries'])
                    for entry in entries:
                        url = entry.get('url') or entry.get('webpage_url')
                        if url: player.queue.append((url, interaction.user))
                    return await interaction.followup.send(f"Added {len(entries)} tracks to the queue.")

            data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))
            
            if 'entries' in data: 
                if data.get('_type') == 'playlist':
                    entries = list(data['entries'])
                    for entry in entries:
                        url = entry.get('url') or entry.get('webpage_url')
                        if url: player.queue.append((url, interaction.user))
                    return await interaction.followup.send(f"Added {len(entries)} tracks from search.")
                else:
                    data = data['entries'][0]
            
            url = data.get('webpage_url') or data.get('url')
            if not url:
                return await interaction.followup.send("I couldn't find a valid track for that search.")

            player.queue.append((url, interaction.user))
            embed = discord.Embed(description=f"Queued: **{data.get('title', 'Unknown Track')}**", color=discord.Color.from_rgb(43, 45, 49))
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Something went wrong: {e}")

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
                    title = e.get('title', 'Unknown Title')[:100]
                    url = e.get('webpage_url') or e.get('url')
                    if url:
                        choices.append(app_commands.Choice(name=title, value=url))
                
                if not interaction.response.is_done():
                    return choices[:5]
                return []
        except:
            return []

    @app_commands.command(name='help', description='Show the list of available commands')
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Premium Audio Interface",
            description="Minimalist developer build protocol.",
            color=discord.Color.from_rgb(43, 45, 49)
        )
        embed.add_field(name="Commands", value="`/play` · `/pause` · `/resume` · `/247` · `/filter` · `/jump` · `/move` · `/remove` · `/shuffle` · `/clear` · `/queue` · `/history` · `/volume` · `/skip` · `/stop` · `/lockchannel` · `/lockserver` · `/ping`", inline=False)
        embed.add_field(name="System Modes", value="24/7 Persistent Handshake · System Reload · Queue Purge", inline=False)
        embed.add_field(name="Signal Processing", value="Apply DSP filters: Bassboost, Nightcore, Vaporwave, Chipmunk", inline=False)
        embed.add_field(name="Interface Guide", value="Use the control panel for real-time adjustments.", inline=False)
        embed.set_footer(text="Build Version: 2.0.0 Dev")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='pause', description='Pause the music')
    async def pause(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("Paused the current track.")
        else:
            await interaction.response.send_message("Nothing is currently playing.", ephemeral=True)

    @app_commands.command(name='resume', description='Resume the music')
    async def resume(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("Resumed the current track.")
        else:
            await interaction.response.send_message("The track is not paused.", ephemeral=True)

    @app_commands.command(name='queue', description='Show the current music queue')
    async def queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        if not player.queue and not player.current:
            return await interaction.response.send_message("The queue is currently empty.", ephemeral=True)
        
        fmt = f"**Current Track**\n{player.current.title if player.current else 'None'}\n\n**Upcoming**\n"
        fmt += '\n'.join(f"[{i+1}] {s[0]}" for i, s in enumerate(player.queue[:10])) or "Empty"
        
        embed = discord.Embed(title="Session Queue", description=fmt, color=discord.Color.from_rgb(43, 45, 49))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='history', description='Show recently played songs')
    async def history(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        if not player.history: return await interaction.response.send_message("The history is currently empty.", ephemeral=True)
        fmt = '\n'.join(f"[{i+1}] {t}" for i, t in enumerate(player.history))
        await interaction.response.send_message(embed=discord.Embed(title="Session History", description=fmt, color=discord.Color.from_rgb(43, 45, 49)))

    @app_commands.command(name='247', description='Keep the bot in the voice channel 24/7')
    async def mode_247(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        player.mode_247 = not player.mode_247
        status = "Enabled" if player.mode_247 else "Disabled"
        await interaction.response.send_message(f"24/7 mode is now **{status}**.", ephemeral=True)

    @app_commands.command(name='clear', description='Remove all songs from the queue')
    async def clear(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        player.queue.clear()
        await interaction.response.send_message("The queue has been purged.", ephemeral=True)

    @app_commands.command(name='volume', description='Change the music volume')
    async def volume(self, interaction: discord.Interaction, vol: int):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        if not 0 <= vol <= 100: return await interaction.response.send_message("Please provide a volume between 0 and 100.", ephemeral=True)
        player.volume = vol / 100
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = vol / 100
        await interaction.response.send_message(f"Volume has been set to **{vol}%**.", ephemeral=True)

    @app_commands.command(name='skip', description='Skip to the next song')
    async def skip(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        if interaction.guild.voice_client: interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped the current track.", ephemeral=True)

    @app_commands.command(name='stop', description='Stop the music and leave the channel')
    async def stop(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        await self.cleanup(interaction.guild)
        await interaction.response.send_message("Session terminated and disconnected.", ephemeral=True)

    @app_commands.command(name='filter', description='Apply audio effects like Bassboost')
    @app_commands.choices(name=[
        app_commands.Choice(name="None", value="NONE"),
        app_commands.Choice(name="Bassboost", value="BASSBOOST"),
        app_commands.Choice(name="Nightcore", value="NIGHTCORE"),
        app_commands.Choice(name="Vaporwave", value="VAPORWAVE"),
        app_commands.Choice(name="Ear-Rake", value="EARRAKE"),
        app_commands.Choice(name="Chipmunk", value="CHIPMUNK"),
    ])
    async def filter(self, interaction: discord.Interaction, name: app_commands.Choice[str]):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        player.filter = name.value
        await interaction.response.send_message(f"Applied filter: **{name.name}**.", ephemeral=True)

    @app_commands.command(name='remove', description='Remove a specific song from the queue')
    async def remove(self, interaction: discord.Interaction, index: int):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        if 0 < index <= len(player.queue):
            player.queue.pop(index - 1)
            await interaction.response.send_message(f"Removed track at index **{index}**.", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid track index provided.", ephemeral=True)

    @app_commands.command(name='move', description='Change the position of a song in the queue')
    async def move(self, interaction: discord.Interaction, from_index: int, to_index: int):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        if 0 < from_index <= len(player.queue) and 0 < to_index <= len(player.queue):
            track = player.queue.pop(from_index - 1)
            player.queue.insert(to_index - 1, track)
            await interaction.response.send_message(f"Moved track from index **{from_index}** to **{to_index}**.", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid track index provided.", ephemeral=True)

    @app_commands.command(name='jump', description='Skip directly to a specific song in the queue')
    async def jump(self, interaction: discord.Interaction, index: int):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        if 0 < index <= len(player.queue):
            player.queue = player.queue[index-1:]
            if interaction.guild.voice_client:
                interaction.guild.voice_client.stop()
            await interaction.response.send_message(f"Jumped to track index **{index}**.", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid track index provided.", ephemeral=True)

    @app_commands.command(name='shuffle', description='Shuffle the current queue')
    async def shuffle(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        if len(player.queue) < 2:
            return await interaction.response.send_message("The queue is too short to shuffle.", ephemeral=True)
        random.shuffle(player.queue)
        await interaction.response.send_message("The queue has been shuffled.", ephemeral=True)

    @app_commands.command(name='reload', description='Restart the bot (Admin only)')
    @app_commands.checks.has_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction):
        await interaction.response.send_message("Restarting the system... The bot will be back online in a few seconds.", ephemeral=True)
        
        await asyncio.sleep(2)
        
        for guild_id in list(self.players.keys()):
            await self.cleanup(self.bot.get_guild(guild_id))
        
        import sys
        os.execv(sys.executable, ['python'] + sys.argv)

    @app_commands.command(name='sync', description='Update slash commands (Owner only)')
    async def sync_slash(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        try:
            for guild in self.bot.guilds:
                self.bot.tree.copy_global_to(guild=guild)
                await self.bot.tree.sync(guild=guild)
            await interaction.followup.send("System commands synchronized successfully.")
        except Exception as e:
            await interaction.followup.send(f"An error occurred during synchronization: {e}")

    @app_commands.command(name='loop', description='Repeat the current song')
    async def loop_command(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.locked_channel_id and player.locked_channel_id != interaction.channel_id:
            return await interaction.response.send_message(f"Commands are restricted to <#{player.locked_channel_id}>.", ephemeral=True)

        player.loop = not player.loop
        await interaction.response.send_message(f"Repeat mode is now **{'Enabled' if player.loop else 'Disabled'}**.")

    @app_commands.command(name='lockserver', description='Lock the bot to this server (Owner only)')
    async def lockserver(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
        
        if self.locked_guild_id == interaction.guild_id:
            self.locked_guild_id = None
            await interaction.response.send_message("Server lock has been removed.")
        else:
            self.locked_guild_id = interaction.guild_id
            await interaction.response.send_message(f"The bot has been locked to this server.")

    @app_commands.command(name='lockchannel', description='Lock the bot to this text channel (Owner only)')
    async def lockchannel(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
        
        player = self.get_player(interaction)
        if player.locked_channel_id == interaction.channel_id:
            player.locked_channel_id = None
            await interaction.response.send_message("Channel lock has been removed.")
        else:
            player.locked_channel_id = interaction.channel_id
            await interaction.response.send_message(f"The bot has been locked to {interaction.channel.mention}.")

    @commands.command(name='lockchannel')
    async def lockchannel_prefix(self, ctx):
        if not await self.bot.is_owner(ctx.author): return
        player = self.get_player(ctx)
        if player.locked_channel_id == ctx.channel.id:
            player.locked_channel_id = None
            await ctx.send("Channel lock has been removed.")
        else:
            player.locked_channel_id = ctx.channel.id
            await ctx.send(f"The bot has been locked to {ctx.channel.mention}.")

    @commands.command(name='lockserver')
    async def lockserver_prefix(self, ctx):
        if not await self.bot.is_owner(ctx.author): return
        if self.locked_guild_id == ctx.guild.id:
            self.locked_guild_id = None
            await ctx.send("Server lock has been removed.")
        else:
            self.locked_guild_id = ctx.guild.id
            await ctx.send("The bot has been locked to this server.")

    @commands.command(name='reload')
    @commands.has_permissions(administrator=True)
    async def reload_prefix(self, ctx):
        await ctx.send("Restarting the system...")
        await asyncio.sleep(2)
        for guild_id in list(self.players.keys()):
            await self.cleanup(self.bot.get_guild(guild_id))
        import sys
        os.execv(sys.executable, ['python'] + sys.argv)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id: return
        if before.channel and not after.channel:
            vc = member.guild.voice_client
            if vc and len(before.channel.members) == 1:
                await self.cleanup(member.guild)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        await self.add_cog(Music(self))
        self.loop.create_task(start_web_server())

    async def on_ready(self):
        print(f'Logged in as {self.user}')
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/help"))

    @app_commands.command(name='ping', description='Check the bot\'s latency')
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong! Latency: {round(self.latency * 1000)}ms", ephemeral=True)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            cmd = ctx.invoked_with.lower()
            music_cmds = ['play', 'pause', 'resume', 'skip', 'stop', 'queue', 'history', 'volume', 'filter', 'clear', 'shuffle', 'loop', 'jump', 'move', 'remove']
            if cmd in music_cmds:
                await ctx.send(f"Command `!{cmd}` is not available as a text command. Please use the slash command `/{cmd}` instead.")
            return
        raise error

bot = MyBot()

@bot.command()
async def sync(ctx):
    if not await bot.is_owner(ctx.author):
        return
    
    msg = await ctx.send("Syncing commands... Please wait.")
    try:
        await bot.tree.sync()
        bot.tree.copy_global_to(guild=ctx.guild)
        await bot.tree.sync(guild=ctx.guild)
        await msg.edit(content=f"System synchronized! Global commands updated and synced to this server.")
    except Exception as e:
        await msg.edit(content=f"Synchronization error: {e}")

if __name__ == '__main__':
    bot.run(TOKEN)
