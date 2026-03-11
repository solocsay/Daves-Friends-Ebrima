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
from models.game_state import GameError
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

            if card_index is None and color is None:
                raise GameError(
                    "You must specify either a card index or a color.",
                    title="Game Error",
                    private=True,
                )

            self.game_service.play_card(
                cid,
                interaction.user.id,
                card_index,
                Color[color.value.upper()] if color else None,
            )
        except GameError as e:
            embed = self._renderer.lobby_views.error_embed(
                "Lobby Exists" if e.title == "" else e.title, str(e)
            )

            await interaction.followup.send(embeds=[embed], ephemeral=e.private)
            return

        await self._renderer.update_by_message_id(self.bot, cid, main_msg_id, lobby)
        await self.dm_current_player_turn(lobby, cid)
        self.start_afk_timer(cid, lobby)
        await interaction.followup.send("Successfully played card!", ephemeral=True)

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
        
    @app_commands.command(name="kick", description="Kick a player from the game.")
    async def kick(self, interaction: discord.Interaction, player: discord.Member):

        await interaction.response.defer(ephemeral=True)

        cid = require_channel_id(interaction)

        try:
            lobby = self.lobby_service.get_lobby(cid)

            if interaction.user.id != lobby.user.id:
                raise GameError(
                    "Only the host can kick players.",
                    private=True,
                    title="Host Only"
                )

            if player.id not in lobby.game.players():
                raise GameError(
                    "That player is not in the game.",
                    private=True,
                    title="Player Not Found"
                )

            self.game_service.kick_player(cid, player.id)

        except GameError as e:
            embed = self._renderer.lobby_views.error_embed(
                "Game Error" if e.title == "" else e.title,
                str(e)
            )
            await interaction.followup.send(embeds=[embed], ephemeral=e.private)
            return

        await self._renderer.update_by_message_id(
            self.bot,
            cid,
            lobby.main_message,
            lobby
        )

        try:
            await player.send("You were kicked from the UNO game.")
        except (discord.Forbidden, discord.HTTPException):
            pass

        await interaction.followup.send(
            f"{player.display_name} was kicked from the game.",
            ephemeral=True
        )
                
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

                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(
                        f" <@{player_id}> was AFK. They drew a card and was skipped."
                    )

                    await self._renderer.update_by_message_id(
                        self.bot,
                        channel_id,
                        lobby.main_message,
                        lobby,
                    )
            except GameError as e:
                print(f"AFK Timer Error: {e}")

    def start_afk_timer(self, channel_id: int, lobby) -> None:
        """Starts an AFK timer task for the current player."""
        game = lobby.game

        if game.phase().name != "PLAYING":
            return

        asyncio.create_task(
            self.run_afk_timer(channel_id, game.current_player(), game.turn_count())
        )


async def setup(bot: commands.Bot) -> None:
    """
    Adds a new instance of UnoCog to the bot.
    """

    await bot.add_cog(UnoCog(bot))
