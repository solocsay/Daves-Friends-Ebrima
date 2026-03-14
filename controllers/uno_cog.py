"""
Provides the Discord commands and high-level validation of them.
"""

from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from discord.app_commands.errors import CommandInvokeError

from models.deck import Color
from models.game_state import GameError, Phase
from repos.lobby_repo import LobbyRepository
from services.game_service import GameService
from services.lobby_service import LobbyService
from utils.utils import require_channel_id
from views.renderer import Renderer


class UnoCog(commands.Cog):
    """
    The UnoCog which provides Uno commands to the Discord bot and initializes the rest of the game
    state, views, and services.
    """

    def __init__(self, bot: commands.Bot):
        # Bot
        self.bot = bot

        # Repos
        self.lobby_repo = LobbyRepository()

        # Services
        self.lobby_service = LobbyService(self.lobby_repo)
        self.game_service = GameService(self.lobby_service)

        # Initialize renderer
        self._renderer = Renderer(self.lobby_service, self.game_service)

        # Solo timer
        self._solo_lobby_timers: dict[int, asyncio.Task] = {}

    @app_commands.command(name="create", description="Create a lobby in this channel.")
    async def create(self, interaction: discord.Interaction) -> None:
        """
        Creates a new lobby.
        """
        await interaction.response.defer(ephemeral=True)

        cid = require_channel_id(interaction)

        try:
            lobby = self.lobby_service.create_lobby(cid, interaction.user)
        except GameError as e:
            embed = self._renderer.lobby_views.error_embed(
                "Lobby Exists" if e.title == "" else e.title, str(e)
            )
            await interaction.followup.send(embeds=[embed], ephemeral=True)

            return

        embeds, view, files = await self._renderer.render(lobby)
        msg = await interaction.channel.send(embeds=embeds, view=view, files=files)
        lobby.main_message = msg.id

        try:
            await msg.pin()
        except (CommandInvokeError, discord.errors.Forbidden):
            # Silently fail if we can't ping.
            pass

        lobby.channel_id = cid
        asyncio.create_task(self.start_solo_lobby_timer(lobby))

    @app_commands.command(
        name="play",
        description="Play a card from your hand on your turn (index starts at 0).",
    )
    @app_commands.describe(
        card_index="Index of the card in your hand (0-based).",
        color="Required for Wild / Draw4 (red/yellow/blue/green).",
    )
    @app_commands.choices(
        color=[
            app_commands.Choice(name="Red", value="red"),
            app_commands.Choice(name="Yellow", value="yellow"),
            app_commands.Choice(name="Blue", value="blue"),
            app_commands.Choice(name="Green", value="green"),
        ]
    )
    async def play(
        self,
        interaction: discord.Interaction,
        card_index: int | None = None,
        color: app_commands.Choice[str] | None = None,
    ) -> None:
        """
        Plays a card by index, choosing a color if it's a wild.
        """

        # show "Bot is thinking..."
        await interaction.response.defer(ephemeral=True)

        cid = require_channel_id(interaction)

        try:
            lobby = self.lobby_service.get_lobby(cid)
            main_msg_id = lobby.main_message

            if card_index is None:
                raise GameError(
                    "You must specify a card index.",
                    title="Missing Card Index",
                    private=True,
                )

            result = self.game_service.play_card(
                cid,
                interaction.user.id,
                card_index,
                Color[color.value.upper()] if color else None,
            )

            # store last move so the embed can show it
            lobby.last_move = result

        except GameError as e:
            embed = self._renderer.lobby_views.error_embed(
                "Lobby Exists" if e.title == "" else e.title,
                str(e),
            )

            await interaction.followup.send(embeds=[embed], ephemeral=e.private)
            return

        # update the main game embed
        await self._renderer.update_by_message_id(self.bot, cid, main_msg_id, lobby)

        # notify next player
        await self.dm_current_player_turn(lobby, cid)

        # restart AFK timer
        self.start_afk_timer(cid, lobby)

        # confirmation message
        await interaction.followup.send("Successfully played card!", ephemeral=True)

        # send updated hand DM
        bot = interaction.client
        guild = interaction.guild.id
        user = await bot.fetch_user(interaction.user.id)
        hand = lobby.game.hand(interaction.user.id)

        embed = self._renderer.hand_views.hand_embed(
            hand,
            optional_message=f"""This is your new hand after your latest action.
            Link to Game: https://discord.com/channels/{guild}/{cid}/{lobby.main_message}""",
        )

        try:
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # pylint: disable=duplicate-code
    @app_commands.command(name="kick", description="Kick a player from the game.")
    async def kick(self, interaction: discord.Interaction, player: discord.Member):
        """
        Allows the host to remove a player from the current game.
        """
        await interaction.response.defer(ephemeral=True)

        cid = require_channel_id(interaction)

        try:
            lobby = self.lobby_service.get_lobby(cid)

            if interaction.user.id != lobby.user.id:
                raise GameError(
                    "Only the host can kick players.", private=True, title="Host Only"
                )

            if player.id not in lobby.game.players():
                raise GameError(
                    "That player is not in the game.",
                    private=True,
                    title="Player Not Found",
                )

            self._kick_player(lobby, player.id)

        except GameError as e:
            embed = self._renderer.lobby_views.error_embed(
                "Game Error" if e.title == "" else e.title, str(e)
            )
            await interaction.followup.send(embeds=[embed], ephemeral=e.private)
            return

        await interaction.followup.send(
            f"{player.display_name} was kicked from the game.", ephemeral=True
        )

    # pylint: disable=protected-access
    # _kick_player is called _kick_player to differentiate from game_state.py's kick_player
    async def _kick_player(
        self, lobby, player_id: int, afk: bool = False, channel_id: int | None = None
    ):
        """
        Helper to remove a player from the game.
        afk=True changes messages to AFK-specific ones
        """
        cid = channel_id
        game = lobby.game
        channel = self.bot.get_channel(cid)

        try:
            game.kick_player(player_id)

            await self._renderer.update_by_message_id(
                self.bot, cid, lobby.main_message, lobby
            )

            try:
                user = await self.bot.fetch_user(player_id)
                if afk:
                    await user.send(
                        "You were kicked from the UNO game for being AFK 5 times."
                    )
                else:
                    await user.send("You were kicked from the UNO game.")
            except (discord.Forbidden, discord.HTTPException):
                pass

            channel = self.bot.get_channel(cid)
            if channel and afk:
                await channel.send(f"<@{player_id}> has been kicked for being AFK.")

            if game.phase() == Phase.FINISHED and channel:
                if channel:
                    await channel.send("Game ended due to a lack of players.")

        except GameError as e:
            print(f"Kick Error: {e}")

    async def dm_current_player_turn(self, lobby, channel_id: int) -> None:
        """
        DMs the current player when it becomes their turn, including a link to the game.
        """
        game = lobby.game
        if game.phase().name != "PLAYING":
            return

        current = game.current_player()
        if game.is_bot(current):
            return

        if not getattr(lobby, "main_message", None):
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None or channel.guild is None:
            return

        link = (
            f"https://discord.com/channels/"
            f"{channel.guild.id}/{channel_id}/{lobby.main_message}"
        )

        try:
            user = await self.bot.fetch_user(current)
            await user.send(f"🎮 It's your turn!\nLink to Game: {link}")
        except discord.Forbidden:
            pass

    async def run_afk_timer(
        self, channel_id: int, player_id: int, start_turn_count: int
    ):
        """
        Skips a player's turn if they don't play in 60 seconds.
        Kicks them if they've been AFK 5 times.
        """
        await asyncio.sleep(60)

        try:
            lobby = self.lobby_service.get_lobby(channel_id)
            game = lobby.game
        except GameError:
            return

        if game.phase().name != "PLAYING":
            return

        if (
            game.current_player() == player_id
            and game.state["turn_count"] == start_turn_count
        ):
            try:
                game.draw_and_pass(player_id)

                # update last move
                lobby.last_move = {"type": "draw", "player": player_id}

                # increment AFK count
                game.state["afk_counts"][player_id] = (
                    game.state["afk_counts"].get(player_id, 0) + 1
                )
                afk_count = game.state["afk_counts"][player_id]

                channel = self.bot.get_channel(channel_id)
                if channel and afk_count <= 4:
                    await channel.send(
                        f" <@{player_id}> was AFK. They drew a card and was skipped."
                    )

                    await self._renderer.update_by_message_id(
                        self.bot, channel_id, lobby.main_message, lobby
                    )

                # auto kick if afk 5 times
                if afk_count >= 5:
                    await self._kick_player(
                        lobby, player_id, afk=True, channel_id=channel_id
                    )
                    return

            except GameError as e:
                print(f"AFK Timer Error: {e}")

        # restart timer
        if game.phase().name == "PLAYING":
            self.start_afk_timer(channel_id, lobby)

    def start_afk_timer(self, channel_id: int, lobby) -> None:
        """Starts an AFK timer task for the current player."""
        game = lobby.game

        if game.phase().name != "PLAYING":
            return

        asyncio.create_task(
            self.run_afk_timer(channel_id, game.current_player(), game.turn_count())
        )

    async def start_solo_lobby_timer(self, lobby):
        """
        Starts a solo lobby timer for a lobby with only one player.
        Sends a separate countdown embed. Replaces it with a "Lobby expired" embed
        when timer ends and deletes the main lobby embed.
        """
        channel = self.bot.get_channel(lobby.channel_id)
        if channel is None or not getattr(lobby, "main_message", None):
            return

        timer_embed = discord.Embed(
            title="⏳ Solo Lobby Timer",
            description="Lobby expires in **10** seconds if nobody joins.",
            color=discord.Color.orange(),
        )

        try:
            timer_msg = await channel.send(embed=timer_embed)
        except discord.HTTPException:
            return

        total_sec = 10
        interval = 1

        try:
            while total_sec > 0:
                if len(lobby.game.players()) > 1:
                    await timer_msg.delete()
                    return

                minutes, seconds = divmod(total_sec, 60)
                timer_embed.description = (
                    f"Lobby expires in **{minutes}:{seconds:02d}** if nobody joins."
                )

                try:
                    await timer_msg.edit(embed=timer_embed)
                except discord.HTTPException:
                    pass

                await asyncio.sleep(interval)
                total_sec -= interval

            self.lobby_service.disband_lobby(lobby.channel_id, lobby.user)

            timer_embed.title = "🕒 Lobby Expired"
            timer_embed.description = "The solo lobby has expired due to inactivity."
            try:
                await timer_msg.edit(embed=timer_embed)
            except discord.HTTPException:
                pass

            try:
                main_msg = await channel.fetch_message(lobby.main_message)
                await main_msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass

        except asyncio.CancelledError:
            try:
                await timer_msg.delete()
            except discord.HTTPException:
                pass

        except (discord.HTTPException, discord.Forbidden, GameError) as e:
            print(f"Solo lobby timer error: {e}")

    def restart_solo_lobby_timer(self, lobby):
        """
        Starts the solo timer if there's 1 player, cancels it otherwise.
        """
        cid = lobby.channel_id

        task = self._solo_lobby_timers.get(cid)
        if task and not task.done():
            task.cancel()

        if len(lobby.game.players()) == 1:
            self._solo_lobby_timers[cid] = asyncio.create_task(
                self.start_solo_lobby_timer(lobby)
            )

async def setup(bot: commands.Bot) -> None:
    """
    Adds a new instance of UnoCog to the bot.
    """

    await bot.add_cog(UnoCog(bot))
