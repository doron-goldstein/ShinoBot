import asyncio
import json
import os
import youtube_dl
import discord
from discord.ext import commands
from utils.paginator import Pages

token = os.environ.get("TOKEN")
if token is None:
    with open("config.json") as cfg:
        token = json.load(cfg)["token"]

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''


ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0' # ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'before_options': '-nostdin',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class Song:
    def __init__(self, ctx, player):
        self.ctx = ctx
        self.player = player

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_query(cls, query, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, ytdl.extract_info, query)

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class VoiceState:
    def __init__(self, bot):
        self.bot = bot
        self.queue = asyncio.Queue()
        self.current = None
        self.play_next_song = asyncio.Event()
        self.skips = []
        self.pl_task = self.bot.loop.create_task(self.playlist())

    def skip_song(self):
        if len(self.skips) >= (len(self.current.ctx.voice_client.channel.members) - 1)*0.34:
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
            self.current = await self.queue.get()
            self.current.ctx.voice_client.play(self.current.player, after=self.toggle_song)
            embed = discord.Embed(title="Now playing")
            embed.add_field(name="Queuer", value=self.current.ctx.author.name, inline=False)
            embed.add_field(name="Song", value=self.current.player.title, inline=False)
            if not self.current.ctx.guild.me.game:
                game = discord.Game(name=self.current.player.title, type=2)
                await self.current.ctx.bot.change_presence(game=game)
            await self.current.ctx.send(embed=embed)
            await self.play_next_song.wait()
            await self.current.ctx.bot.change_presence()


class Music:
    def __init__(self, bot):
        self.bot = bot
        self.states = {}

    def get_state(self, guild_id):
        state = self.states.get(guild_id)
        if state is None:
            state = VoiceState(self.bot)
            self.states[guild_id] = state
        return state

    @commands.command()
    async def summon(self, ctx):
        """Joins the channel you're currently in"""
        if ctx.author.voice:
            return await ctx.voice_client.move_to(ctx.author.voice.channel)
        await ctx.send(":exclamation: You're not connected to a voice channel!")

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""
        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)
        await channel.connect()

    @commands.command()
    async def play(self, ctx, *, query):
        """Streams from a query (almost anything youtube_dl supports)"""
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.send(":exclamation: Not connected to a voice channel.")

        state = self.get_state(ctx.guild.id)
        async with ctx.typing():
            player = await YTDLSource.from_query(query, loop=self.bot.loop)
        song = Song(ctx, player)
        await state.queue.put(song)
        await ctx.send(f'Enqueued:\n     {player.title}')

    @commands.command(aliases=["np"])
    async def playing(self, ctx):
        """Shows the currently playing song"""
        song = self.get_state(ctx.guild.id).current
        embed = discord.Embed(title=song.ctx.author.name, description=song.player.title)
        await ctx.send(embed=embed)

    @commands.command()
    async def skip(self, ctx):
        """Votes to skip the current song"""
        state = self.get_state(ctx.guild.id)
        if ctx.author.id in state.skips:
            await ctx.send("You've voted already!")
        else:
            state.skips.append(ctx.author.id)
            await ctx.send("Added vote to skip the song")
            state.skip_song()

    @commands.command()
    async def queue(self, ctx):
        """Shows the currently queued songs"""
        state = self.get_state(ctx.guild.id)
        q = state.queue
        if q.empty():
            return await ctx.send("The queue is currently empty.\nYou can queue songs by typing `m!play <song name>`.")
        queue = [f"{song.player.title}\n    By: {song.ctx.author.name}" for song in q._queue]
        p = Pages(self.bot, message=ctx.message, entries=queue)
        p.embed.set_author(name="Music Queue")
        await p.paginate()

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume/100
        await ctx.send("Changed volume to {}%".format(volume))


    @commands.command()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        await ctx.send("<:blobstop:340118614848045076>")
        await ctx.voice_client.disconnect()


bot = commands.Bot(command_prefix="m!",
                   description='Simple Music Bot')

@bot.event
async def on_ready():
    print('Logged in as {0.id}/{0}'.format(bot.user))
    print('------')
    discord.opus.load_opus("libopus.so.0.5.3")
bot.add_cog(Music(bot))
bot.run(token)
