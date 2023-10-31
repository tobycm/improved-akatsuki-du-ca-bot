"""
This is the music cog.
"""

from logging import Logger
from typing import Literal

from discord import Embed, Interaction, Member
from discord.app_commands import checks, command, guild_only
from discord.ext.commands import Cog, GroupCog
from wavelink import (
    Node, NodePool, SoundCloudPlaylist, TrackEventPayload,
    WebsocketClosedPayload, YouTubePlaylist
)
from wavelink.ext.spotify import SpotifyClient

from akatsuki_du_ca import AkatsukiDuCa
from config import config
from models.music_embeds import (
    NewPlaylistEmbed, NewTrackEmbed, QueuePaginator, make_queue_embed
)
from models.music_player import Player
from modules import wavelink_helpers
from modules.lang import get_lang
from modules.misc import (
    GuildTextableChannel, rich_embed, seconds_to_time, user_cooldown_check
)
from modules.wavelink_helpers import get_lang_and_player, search


class RadioMusic(GroupCog, name = "radio"):
    """
    Radio commands for bot
    """

    def __init__(self, bot: AkatsukiDuCa) -> None:
        self.bot = bot
        self.logger = bot.logger
        super().__init__()

    async def cog_load(self) -> None:
        self.logger.info("Radio cog loaded")
        return await super().cog_load()

    async def cog_unload(self) -> None:
        self.logger.info("Radio cog unloaded")
        return await super().cog_unload()

    @checks.cooldown(1, 10, key = user_cooldown_check)
    @command(name = "suggest")
    async def suggest(self, interaction: Interaction, song: str):
        """
        Got new songs for my radio? Thank you so much ♥
        """

        suggests_channel = self.bot.get_channel(957341782721585223)
        if not isinstance(suggests_channel, GuildTextableChannel):
            return

        await suggests_channel.send(
            f"{interaction.user} suggested {song} \n" +
            f"User ID: {interaction.user.id}, Guild ID: {interaction.guild_id}"
        )

        lang = await get_lang(interaction.user.id)

        await interaction.response.send_message(lang("music.suggestion_sent"))


class MusicCog(Cog):
    """Music cog to hold Wavelink related commands and listeners."""

    bot: AkatsukiDuCa
    logger: Logger

    def __init__(self, bot: AkatsukiDuCa) -> None:
        self.bot = bot
        self.logger = bot.logger
        bot.loop.create_task(self.connect_nodes())

    async def cog_load(self) -> None:
        self.logger.info("Music cog loaded")
        return await super().cog_load()

    async def cog_unload(self) -> None:
        self.logger.info("Music cog unloaded")
        return await super().cog_unload()

    async def connect_nodes(self):
        """
        Connect to Lavalink nodes.
        """
        await self.bot.wait_until_ready()

        spotify = SpotifyClient(
            client_id = config.api.spotify.client_id,
            client_secret = config.api.spotify.client_secret,
        )

        await NodePool.connect(
            client = self.bot,
            nodes = [
                Node(uri = node.uri, password = node.password)
                for node in config.lavalink_nodes
            ],
            spotify = spotify,
        )

    @Cog.listener()
    async def on_wavelink_node_ready(self, node: Node):
        """
        Event fired when a node has finished connecting.
        """
        self.logger.info(f"Connected to {node.uri}")

    @Cog.listener()
    async def on_wavelink_websocket_closed(
        self, payload: WebsocketClosedPayload
    ):
        """
        Event fired when the Node websocket has been closed by Lavalink.
        """

        self.logger.info(
            f"Disconnected from {payload.player.current_node.uri}"
        )
        self.logger.info(f"Reason: {payload.reason} | Code: {payload.code}")

    @Cog.listener()
    async def on_wavelink_track_end(self, payload: TrackEventPayload):
        """
        Event fired when a track ends.
        """

        player = payload.player
        assert isinstance(player, Player)
        if player.queue.is_empty:
            player.dj, player.text_channel, player.loop_mode = None, None, "off"
            return await player.disconnect()

        await player.play(await player.queue.get_wait())

    @Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackEventPayload):
        """
        Event fired when a track starts.
        """

        track = payload.track
        player = payload.player
        assert isinstance(player, Player)

        assert player.dj
        lang = await get_lang(player.dj.id)

        embed = NewTrackEmbed(track, lang)
        embed.title = lang("music.misc.now_playing")

        if player.loop_mode == "song":
            player.queue.put_at_front(track)
        elif player.loop_mode == "queue":
            await player.queue.put_wait(track)

        assert player.text_channel
        await player.text_channel.send(
            embed = rich_embed(embed, player.dj, lang)
        )

    @checks.cooldown(1, 1.5, key = user_cooldown_check)
    @command(name = "connect")
    @guild_only()
    async def connect(self, interaction: Interaction):
        """
        Connect to a voice channel.
        """

        return await wavelink_helpers.connect(
            interaction,
            await get_lang(interaction.user.id),
            connecting = True
        )

    @checks.cooldown(1, 1.5, key = user_cooldown_check)
    @command(name = "disconnect")
    @guild_only()
    async def disconnect(self, interaction: Interaction):
        """
        Disconnect from a voice channel.
        """

        return await wavelink_helpers.disconnect(
            interaction, await get_lang(interaction.user.id)
        )

    @checks.cooldown(1, 1.25, key = user_cooldown_check)
    @command(name = "play")
    @guild_only()
    async def play(self, interaction: Interaction, query: str | None = None):
        """
        Play a song.
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if not query:
            if not player.is_paused():
                return await interaction.response.send_message(
                    lang("music.misc.action.error.no_music")
                )
            await player.resume()
            return await interaction.response.send_message(
                lang("music.misc.action.music.resumed")
            )

        assert isinstance(interaction.channel, GuildTextableChannel)
        assert isinstance(interaction.user, Member)
        player.dj, player.text_channel = interaction.user, interaction.channel
        await interaction.response.send_message(
            lang("music.misc.action.music.searching")
        )

        result = await search(query)
        if not result:
            return await interaction.edit_original_response(
                content = lang("music.voice_client.error.not_found")
            )

        await player.queue.put_wait(result)

        embed: Embed
        if isinstance(result, YouTubePlaylist
                      ) or isinstance(result, SoundCloudPlaylist):
            embed = NewPlaylistEmbed(result, lang)
        else:
            embed = NewTrackEmbed(result, lang)

        await interaction.edit_original_response(
            content = "",
            embed = rich_embed(embed, interaction.user, lang),
        )

        if not player.is_playing() and not player.current:
            await player.play(await player.queue.get_wait())

    @checks.cooldown(1, 1.25, key = user_cooldown_check)
    @command(name = "playtop")
    @guild_only()
    async def playtop(self, interaction: Interaction, query: str):
        """
        Play or add a song on top of the queue
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )

        assert isinstance(interaction.channel, GuildTextableChannel)
        assert isinstance(interaction.user, Member)
        player.dj, player.text_channel = interaction.user, interaction.channel
        await interaction.response.send_message(
            lang("music.misc.action.music.searching")
        )

        result = await search(query)
        if not result:
            return await interaction.edit_original_response(
                content = lang("music.voice_client.error.not_found")
            )

        player.queue.put_at_front(result)

        embed: Embed
        if isinstance(result, YouTubePlaylist
                      ) or isinstance(result, SoundCloudPlaylist):
            embed = NewPlaylistEmbed(result, lang)
        else:
            embed = NewTrackEmbed(result, lang)

        await interaction.edit_original_response(
            content = "",
            embed = rich_embed(embed, interaction.user, lang),
        )

        if not player.is_playing() and not player.current:
            await player.play(await player.queue.get_wait())

    @checks.cooldown(1, 1.25, key = user_cooldown_check)
    @command(name = "pause")
    @guild_only()
    async def pause(self, interaction: Interaction):
        """
        Pause a song.
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if not player or not player.current:
            await interaction.response.send_message(
                lang("music.misc.action.error.no_music")
            )
            return

        await player.pause()
        return await interaction.response.send_message(
            lang("music.misc.action.music.paused")
        )

    @checks.cooldown(1, 1.5, key = user_cooldown_check)
    @command(name = "skip")
    @guild_only()
    async def skip(self, interaction: Interaction):
        """
        Skip a song
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if not player.current:
            return await interaction.response.send_message(
                lang("music.misc.action.error.no_music")
            )

        await player.stop()
        return await interaction.response.send_message(
            lang("music.misc.action.music.skipped")
        )

    @checks.cooldown(1, 2, key = user_cooldown_check)
    @command(name = "stop")
    @guild_only()
    async def stop(self, interaction: Interaction):
        """
        Stop playing music.
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if not player.queue.is_empty:
            player.queue.clear()
        await player.stop()
        return await interaction.response.send_message(
            lang("music.misc.action.music.stopped")
        )

    @checks.cooldown(1, 1.5, key = user_cooldown_check)
    @command(name = "queue")
    @guild_only()
    async def queue(self, interaction: Interaction):
        """
        Show the queue.
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if player.queue.is_empty:
            return await interaction.response.send_message(
                lang("music.misc.action.error.no_queue")
            )

        generator = make_queue_embed(player.queue, lang)

        first_embed = next(generator)
        if not first_embed:
            return await interaction.response.send_message(
                lang("music.misc.action.error.no_queue")
            )

        await interaction.response.send_message(
            embed = rich_embed(first_embed[0], interaction.user, lang),
        )

        second_embed = next(generator)

        if second_embed:
            view = QueuePaginator([first_embed[0], second_embed[0]],
                                  interaction, lang, generator)
            await interaction.edit_original_response(view = view)
            await view.wait()
            view.disable()
            await interaction.edit_original_response(view = view)

    @checks.cooldown(1, 1.25, key = user_cooldown_check)
    @command(name = "nowplaying")
    @guild_only()
    async def nowplaying(self, interaction: Interaction):
        """
        Show the now playing song.
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if not player.is_playing():
            await interaction.response.send_message(
                lang("music.misc.action.error.no_music")
            )
            return

        track = player.current
        embed = rich_embed(
            Embed(
                title = lang("music.misc.now_playing"),
                description =
                f"[**{track.title}**]({track.uri}) - {track.author}\n" +
                f"Duration: {seconds_to_time(round(player.position / 1000))}/{seconds_to_time(round(track.duration / 1000))}",
            ),
            interaction.user,
            lang,
        )
        return await interaction.response.send_message(embed = embed)

    @checks.cooldown(1, 1.75, key = user_cooldown_check)
    @command(name = "clear_queue")
    @guild_only()
    async def clear_queue(self, interaction: Interaction):
        """
        Clear the queue
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if player.queue.is_empty:
            return await interaction.response.send_message(
                lang("music.misc.action.error.no_queue")
            )

        player.queue.clear()
        return await interaction.response.send_message(
            lang("music.misc.action.queue.cleared")
        )

    @checks.cooldown(1, 1.25, key = user_cooldown_check)
    @command(name = "loop")
    @guild_only()
    async def loop_music(
        self,
        interaction: Interaction,
        mode: Literal["off", "queue", "song"] | None = None,
    ):
        """
        Loop queue, song or turn loop off
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if not player.is_playing():
            await interaction.response.send_message(
                lang("music.misc.action.error.no_music")
            )
            return

        if mode:
            player.loop_mode = mode
        if mode == "song":
            player.queue.put_at_front(player.current)
        if mode == "off" and player.loop_mode == "song":
            await player.queue.get_wait()

        await interaction.response.send_message(
            lang("music.misc.action.loop")[player.loop_mode] # type: ignore
        )

    @checks.cooldown(1, 1.25, key = user_cooldown_check)
    @command(name = "seek")
    @guild_only()
    async def seek(self, interaction: Interaction, position: int):
        """
        Seeks to a certain point in the current track.
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if not player.is_playing():
            await interaction.response.send_message(
                lang("music.misc.action.error.no_music")
            )
            return

        if player.current.length < position:
            # lmao seek over track
            return await interaction.response.send_message(
                "Lmao how to seek over track"
            )

        await player.seek(position = position)
        return await interaction.response.send_message("Done!")

    @checks.cooldown(1, 1, key = user_cooldown_check)
    @command(name = "volume")
    @guild_only()
    async def volume(
        self, interaction: Interaction, volume: int | None = None
    ):
        """
        Change the player volume.
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if not player.is_playing():
            return await interaction.response.send_message(
                lang("music.misc.action.error.no_music")
            )

        if volume is None:
            return await interaction.response.send_message(
                lang("music.misc.volume.current") % f"{player.volume}%"
            )

        await player.set_volume(volume)
        return await interaction.response.send_message(
            lang("music.misc.volume.changed") % f"{volume}%"
        )

    @checks.cooldown(1, 3, key = user_cooldown_check)
    @command(name = "shuffle")
    @guild_only()
    async def shuffle(self, interaction: Interaction):
        """
        Shuffle the queue
        """

        lang, player = await get_lang_and_player(
            interaction.user.id, interaction
        )
        if player.queue.is_empty:
            return await interaction.response.send_message(
                lang("music.misc.action.error.no_queue")
            )

        player.queue.shuffle()
        return await interaction.response.send_message(
            lang("music.misc.action.queue.shuffled")
        )

    # @checks.cooldown(1, 3, key=user_cooldown_check)
    # @command(name="flip")
    # async def flip(self, interaction: Interaction):
    #     """
    #     Flip the queue
    #     """

    #     lang = await get_lang(interaction.user.id)

    #     player = await self._connect(interaction, lang)
    #     if not player:
    #         return
    #     if player.queue.is_empty:
    #         return await interaction.response.send_message(
    #             lang("music.misc.action.error.no_queue")
    #         )

    #     for _ in range(len(player.queue)):
    #         await player.queue.put_wait(player.queue.get())

    #     return await interaction.response.send_message(
    #         lang("music.misc.action.queue.flipped")
    #     )
