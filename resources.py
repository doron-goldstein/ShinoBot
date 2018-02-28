import asyncio
import os

import discord
import youtube_dl
from mutagen.mp3 import MP3

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''


ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0'  # ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'before_options': '-nostdin',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')
        self.length = data.get('duration')
        self.filename = ytdl.prepare_filename(data)

    @classmethod
    async def from_query(cls, query, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, ytdl.extract_info, query)
        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

    @classmethod
    def from_file(cls, filename):
        info = MP3(filename).info
        data = {'title': filename, 'duration': info.length}
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class VoiceState:
    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild = bot.get_guild(guild_id)
        self.queue = asyncio.Queue()
        self.current = None
        self.play_next_song = asyncio.Event()
        self.skips = []
        self.pl_task = self.bot.loop.create_task(self.playlist())
        r_id = self.bot.masters[self.guild.id]
        if r_id:
            self.master = discord.utils.get(self.guild.roles, id=r_id)

    def skip_song(self):
        if len(self.skips) >= (len(self.current.ctx.voice_client.channel.members) - 1) * 0.34:
            self.current.ctx.voice_client.stop()
            self.toggle_song(None)

    def toggle_song(self, error):
        if error:
            print(error)
        self.skips = []
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

    async def playlist(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            self.play_next_song.clear()
            try:
                os.remove(self.current.player.filename)
            except Exception as e:
                print(e)
            self.current = await self.queue.get()
            self.current.ctx.voice_client.play(self.current.player, after=self.toggle_song)
            embed = discord.Embed(title="Now playing")
            embed.add_field(name="Queuer", value=self.current.ctx.author.name, inline=False)
            embed.add_field(name="Song", value=self.current.player.title, inline=False)
            if not self.current.ctx.guild.me.game:
                game = discord.Game(name=self.current.player.title, type=2)
                await self.bot.change_presence(game=game)
            await self.current.ctx.send(embed=embed)
            await self.play_next_song.wait()

            if self.bot.dev:
                await self.bot.change_presence()
            else:
                await self.bot.change_presence(game=discord.Game(name="m!help"))
