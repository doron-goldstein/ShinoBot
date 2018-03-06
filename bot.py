import os
from ssl import SSLContext

import asyncpg
import discord
import yaml
from discord.ext import commands

from utils.resources import VoiceState

token = os.environ.get("TOKEN")
db = os.environ.get("DATABASE_URL")
dev = False
if token is None or db is None:
    with open("config.yaml") as cfg:
        cfg = yaml.load(cfg)
        token = cfg["token"]
        db = cfg["DB"]
        dev = cfg["dev"]


class MusicContext(commands.Context):
    def get_state(self, guild_id):
        state = self.bot.states.get(guild_id)
        if state is None:
            state = VoiceState(self.bot, guild_id)
            self.bot.states[guild_id] = state
        return state

    @property
    def state(self):
        return self.get_state(self.guild.id)

    @property
    def config(self):
        if self.bot.config.get(self.guild.id) is None:
            self.bot.config[self.guild.id] = {'role_id': None, 'songs_max': None, 'length_max': None, 'locked': None}
        return self.bot.config[self.guild.id]


class MusicBot(commands.Bot):
    async def on_message(self, message):
        await self.wait_until_ready()
        if self.dev:
            if message.guild.id != 246291440106340352:
                return

        ctx = await self.get_context(message, cls=MusicContext)
        if ctx.prefix is not None:
            ctx.command = self.all_commands.get(ctx.invoked_with.lower())
            await self.invoke(ctx)

    async def on_ready(self):
        print('Logged in as {0.id}/{0}'.format(self.user))
        print('Dev mode state: ' + ('enabled' if dev else 'disabled'))
        print('------')
        self.dev = dev
        self.load_extension("cogs.music")
        self.load_extension("cogs.config")
        self.pool = await asyncpg.create_pool(db, min_size=4, max_size=9, ssl=SSLContext())
        query = """
            SELECT * FROM config
        """
        self.config = {r['guild_id']: dict(r) for r in await self.pool.fetch(query)}
        if os.name != 'nt':
            try:
                discord.opus.load_opus("libopus.so.0.5.3")
            except Exception as e:
                print(f"Couldnt load opus:\n    {e}\nThe bot might not work.")

    async def close(self):
        print("Cleaning up...")
        await self.pool.close()
        await super().close()


game = discord.Game(name="m!help") if not dev else None
bot = MusicBot(command_prefix=["m!", "M!"], description="Music Bot\n[M] indicates master role only.", activity=game)
bot.run(token)
