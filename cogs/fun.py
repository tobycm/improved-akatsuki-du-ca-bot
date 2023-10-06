"""
Fun cog for the bot.
"""

from random import choice, randint
from string import ascii_letters

from discord import Embed, File, Interaction, Member
from discord.app_commands import checks, command, guild_only
from discord.ext.commands import Cog, GroupCog

from akatsuki_du_ca import AkatsukiDuCa
from config import config
from modules.database import get_user_lang
from modules.exceptions import LangNotAvailable
from modules.gif import construct_gif_embed
from modules.lang import get_lang
from modules.misc import GuildTextableChannel, rich_embed, user_cooldown_check
from modules.quote import get_quote
from modules.waifu import random_image


class GIFCog(GroupCog, name = "gif"):
    """
    GIF related commands.
    """

    async def _gif(self, interaction: Interaction, target: Member):
        assert isinstance(interaction.channel, GuildTextableChannel)
        assert isinstance(interaction.user, Member)
        assert interaction.command

        if target is interaction.client.user:
            return await interaction.response.send_message(
                "etou...", ephemeral = True
            )

        lang = await get_lang(interaction.user.id)

        await interaction.channel.send(
            embed = rich_embed(
                await construct_gif_embed(
                    interaction.user,
                    target,
                    interaction.command.name,
                    config.api.tenor.key,
                    lang,
                ),
                interaction.user,
                lang,
            )
        )
        return await interaction.response.send_message(
            "Sent!", ephemeral = True
        )

    def __init__(self, bot: AkatsukiDuCa) -> None:
        self.logger = bot.logger
        super().__init__()

        async def gif_command(self, interaction: Interaction, target: Member):
            """
            Pat someone xD
            """

            await self._gif(interaction, target)

        for command_name in [
            "hug",
            "pat",
            "punch",
            "kick",
            "bite",
            "cuddle",
            "poke",
        ]:
            setattr(
                self,
                command_name,
                checks.cooldown(1, 1, key = user_cooldown_check)(
                    command(name = command_name)(guild_only()(gif_command))
                ),
            )

    async def cog_load(self) -> None:
        self.logger.info("Fun cog loaded")
        return await super().cog_load()

    async def cog_unload(self) -> None:
        self.logger.info("Fun cog unloaded")
        return await super().cog_unload()


class FunCog(Cog):
    """
    Other fun commands.
    """

    def __init__(self, bot: AkatsukiDuCa) -> None:
        self.bot = bot
        self.logger = bot.logger
        super().__init__()

    @checks.cooldown(1, 5, key = user_cooldown_check)
    @command(name = "alarm")
    @guild_only()
    async def alarm(self, interaction: Interaction):
        """
        Send an alarm >:)
        """

        lang_option = await get_user_lang(interaction.user.id)
        if lang_option != "vi-vn":
            raise LangNotAvailable

        assert isinstance(interaction.channel, GuildTextableChannel)

        await interaction.response.send_message(
            "Đang gửi...", ephemeral = True
        )
        if randint(1, 50) == 25:
            # bro got lucky
            await interaction.channel.send(
                content =
                "Bạn may mắn thật đấy, bạn được Ban Mai gọi dậy nè :))",
                file = File("assets/banmai.mp4"),
            )
        else:
            await interaction.channel.send(
                content =
                "Ngủ nhiều là không tốt đâu đó nha :D \n - Du Ca said - ",
                file = File("assets/duca.mp4"),
            )
        return await interaction.edit_original_response(content = "Đã gửi :D")

    @checks.cooldown(1, 1.5, key = user_cooldown_check)
    @command(name = "waifu")
    async def waifu(self, interaction: Interaction):
        """
        Wan sum waifu?
        """
        lang = await get_lang(interaction.user.id)

        image = await random_image()

        return await interaction.response.send_message(
            embed = rich_embed(
                Embed(
                    title = "Waifu",
                    description = lang("fun.waifu") % image,
                ),
                interaction.user,
                lang,
            ).set_image(url = str(image))
        )

    @checks.cooldown(1, 1.5, key = user_cooldown_check)
    @command(name = "freenitro")
    @guild_only()
    async def freenitro(self, interaction: Interaction):
        """
        OMG free NiTrO!!1! gotta claim fast
        """

        code = ""
        for _ in range(0, 23):
            code += choice(ascii_letters)

        lang = await get_lang(interaction.user.id)

        embed = Embed(
            title = lang("fun.free_nitro.title"),
            description = lang("fun.free_nitro.description") %
            f"[discord.gift/{code}](https://akatsukiduca.tk/verify-nitro?key={code}&id={interaction.user.id})",
            color = 0x2F3136,
        )
        embed.set_image(url = "https://i.ibb.co/5LDTWSj/freenitro.png")
        await interaction.response.send_message(
            lang("fun.free_nitro.success"), ephemeral = True
        )

        assert isinstance(interaction.channel, GuildTextableChannel)
        return await interaction.channel.send(embed = embed)

    @checks.cooldown(1, 1.5, key = user_cooldown_check)
    @command(name = "quote")
    async def quote(self, interaction: Interaction):
        """
        A good quote for the day
        """

        quote = await get_quote()

        return await interaction.response.send_message(
            embed = rich_embed(
                Embed(title = quote.author, description = quote.quote),
                interaction.user,
                await get_lang(interaction.user.id),
            ),
            ephemeral = True,
        )
