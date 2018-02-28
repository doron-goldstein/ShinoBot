import os
from ssl import SSLContext

import asyncpg
import discord
import yaml
from discord.ext import commands

from resources import VoiceState

token = os.environ.get("TOKEN")
db = os.environ.get("DATABASE_URL")
dev = False
if token is None or db is None:
    with open("config.yaml") as cfg:
        cfg = yaml.load(cfg)
        token = cfg["token"]
        db = cfg["DB"]
        dev = True


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


class MusicBot(commands.Bot):
    async def on_message(self, message):
        ctx = await self.get_context(message, cls=MusicContext)
        if ctx.prefix is not None:
            ctx.command = self.all_commands.get(ctx.invoked_with.lower())
            await self.invoke(ctx)

    async def on_ready(self):
        print('Logged in as {0.id}/{0}'.format(self.user))
        print('------')
        self.bot.dev = dev
        self.load_extension("music")
        self.pool = await asyncpg.create_pool(db, ssl=SSLContext())
        query = """
            SELECT * FROM masters
        """
        self.masters = {gid: rid for gid, rid in await self.pool.fetch(query)}
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
bot = MusicBot(command_prefix=["m!", "M!"], description="Music Bot", game=game)
bot.run(token)
