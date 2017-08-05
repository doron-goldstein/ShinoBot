import asyncio
import json
import os
import youtube_dl
import discord
from discord.ext import commands

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
        self.pl_task = self.bot.loop.create_task(self.playlist())

    def toggle_song(self, error):
        if error:
            print(error)
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
            await self.current.ctx.send(embed=embed)
            await self.play_next_song.wait()


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
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)
        await channel.connect()

    @commands.command(name="local", hidden=True)
    async def _local(self, ctx, *, query):
        """Plays a file from the local filesystem"""

        if ctx.voice_client is None:
            if ctx.author.voice.channel:
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.send("Not connected to a voice channel.")

        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()

        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
        ctx.voice_client.play(source, after=lambda e: print('Player error: %s' % e) if e else self.toggle_song())
        await ctx.send('Now playing: {}'.format(query))

    @commands.command()
    async def play(self, ctx, *, query):
        """Streams from a query (almost anything youtube_dl supports)"""
        if ctx.voice_client is None:
            if ctx.author.voice.channel:
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.send(":exclamation: Not connected to a voice channel.")
        state = self.get_state(ctx.guild.id)
        player = await YTDLSource.from_query(query, loop=self.bot.loop)
        song = Song(ctx, player)
        await state.queue.put(song)
        await ctx.send(f'Enqueued:\n     {player.title}')

    @commands.command()
    async def queue(self, ctx):
        """Shows the currently queued songs"""
        state = self.get_state(ctx.guild.id)
        q = state.queue
        msg = "\n".join([f"{song.player.title}\n    Queuer: {song.ctx.author.name}" for song in q._queue if not state.queue.empty()])
        await ctx.send(msg)

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume
        await ctx.send("Changed volume to {}%".format(volume))


    @commands.command()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        await ctx.send("<:blobstop:340118614848045076>")
        await ctx.voice_client.disconnect()


bot = commands.Bot(command_prefix=commands.when_mentioned_or("m!"),
                   description='Simple Music Bot')

@bot.event
async def on_ready():
    print('Logged in as {0.id}/{0}'.format(bot.user))
    print('------')

bot.add_cog(Music(bot))
bot.run(token)
