import discord
from discord.ext import commands

from cogs.music import master_only
from utils.paginator import Pages


class Configuration:
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(administrator=True)
    @commands.command()
    async def setmaster(self, ctx, *, role: discord.Role):
        """Sets the master role for the server
        The `role` argument can be an ID, name, or mention of a role.
        """
        ctx.config['role_id'] = role.id
        query = """
            INSERT INTO config (guild_id, role_id)
            VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET role_id = EXCLUDED.role_id
        """
        await self.bot.pool.execute(query, ctx.guild.id, role.id)
        await ctx.message.add_reaction("\N{OK HAND SIGN}")

    @master_only()
    @commands.command()
    async def locked(self, ctx, typ="Embed"):
        """List all locked members"""

        entries = [self.bot.get_user(uid) for uid in ctx.config['locked']]

        if typ.lower() in ('embed', 'e'):
            p = Pages(self.bot, message=ctx.message, entries=[e.mention for e in entries])
            p.embed.set_author(name="Locked members")
            await p.paginate()

        elif typ.lower() in ('text', 'txt', 't'):
            fmt = '```'
            for e in entries:
                fmt += e.name + "\n"
            fmt += '```'
            try:
                await ctx.send(fmt)
            except:  # noqa
                await ctx.send(f"List too long, use `{ctx.prefix}locked embed` for a paginated version.")
        else:
            await ctx.send("Invalid type! Can be either `text` or `embed`")

    @master_only()
    @commands.command()
    async def lock(self, ctx, user: discord.Member):
        """[M] Locks a user from using the bot"""

        if ctx.config['locked'] is None:
            ctx.config['locked'] = [user.id]
        else:
            ctx.config['locked'].append(user.id)

        query = """
            UPDATE config
            SET locked = array_append(locked, $2)
            WHERE guild_id = $1
        """
        await self.bot.pool.execute(query, ctx.guild.id, user.id)
        await ctx.message.add_reaction("\N{OK HAND SIGN}")

    @master_only()
    @commands.command()
    async def unlock(self, ctx, user: discord.Member):
        """[M] Unlocks a user from using the bot"""

        if ctx.config['locked'] is None:
            return await ctx.send("There are no locked users.")
        else:
            ctx.config['locked'].remove(user.id)

        query = """
            UPDATE config
            SET locked = array_remove(locked, $2)
            WHERE guild_id = $1
        """
        await self.bot.pool.execute(query, ctx.guild.id, user.id)
        await ctx.message.add_reaction("\N{OK HAND SIGN}")

    @master_only()
    @commands.command()
    async def config(self, ctx, key, value: int):
        """[M] Set config values"""
        if key not in ('length_max', 'songs_max'):
            return await ctx.send("Invalid key! Only `length_max` or `songs_max` can be configured.")

        ctx.config[key] = value
        query = """
            UPDATE config
            SET {} = $2
            WHERE guild_id = $1
        """.format(key)
        await self.bot.pool.execute(query, ctx.guild.id, value)
        await ctx.message.add_reaction("\N{OK HAND SIGN}")


def setup(bot):
    bot.add_cog(Configuration(bot))
