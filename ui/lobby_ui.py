"""
Providers the user interface for the lobby.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import discord.ui
from models.game_state import GameError
from services.lobby_service import LobbyService
from views.lobby_views import LobbyViews
from utils.utils import require_channel_id

from .interactions import Interactions

if TYPE_CHECKING:
    from views.renderer import Renderer


class LobbyUI(Interactions):
    """
    The user interface for the lobby, connecting the lobby views to Discord.
    """

    def __init__(
        self, renderer: Renderer, lobby_service: LobbyService, lobby_views: LobbyViews
    ):
        super().__init__()
        self._renderer = renderer
        self.lobby_service = lobby_service
        self.lobby_views = lobby_views

    @discord.ui.button(label="🌟 Join", style=discord.ButtonStyle.blurple)
    async def join(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        """
        The button for joining a lobby.
        """

        cid = require_channel_id(interaction)

        try:
            self.lobby_service.join_lobby(cid, interaction.user)
        except GameError as e:
            await self._renderer.lobby_views.render_error("Game Join", e, interaction)
            return

        lobby = self.lobby_service.get_lobby(cid)
        await self._renderer.update_from_interaction(interaction, lobby)

    @discord.ui.button(label="🚫 Leave", style=discord.ButtonStyle.gray)
    async def leave(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        """
        The button for leaving a lobby.
        """

        cid = require_channel_id(interaction)

        try:
            self.lobby_service.leave_lobby(cid, interaction.user)
        except GameError as e:
            await self._renderer.lobby_views.render_error("Leave", e, interaction)

            return

        lobby = self.lobby_service.get_lobby(cid)

        cog = interaction.client.get_cog("UnoCog")
        if cog:
            cog.restart_solo_lobby_timer(lobby)

        await self._renderer.update_from_interaction(interaction, lobby)

    @discord.ui.button(label="🚀 Start Game", style=discord.ButtonStyle.success)
    async def start(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        """
        The button for lobby creators to start the game.
        """

        cid = require_channel_id(interaction)

        lobby = self.lobby_service.get_lobby(cid)
        if interaction.user.id != lobby.user.id:
            embed = self._renderer.lobby_views.error_embed(
                "Must be host",
                "You must be the host in order to start the game!",
            )
            await interaction.followup.send(embeds=[embed], ephemeral=True)
            return

        self.lobby_service.start_lobby(cid)

        await self._renderer.update_from_interaction(interaction, lobby)

        # Dm every player
        bot = interaction.client
        guild = interaction.guild.id
        for user_id in lobby.game.players():
            user = await bot.fetch_user(user_id)
            hand = lobby.game.hand(user_id)
            embed = self._renderer.hand_views.hand_embed(
                hand,
                optional_message=f"""This is your starting hand.
            \nLink to Game: https://discord.com/channels/{guild}/{cid}/{lobby.main_message}""",
            )

            try:
                await user.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        cog = interaction.client.get_cog("UnoCog")
        if cog:
            cog.start_afk_timer(cid, lobby)

    @discord.ui.button(label="🚨 Disband Game", style=discord.ButtonStyle.danger)
    async def disband(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        """
        The button that disbands a lobby, preventing it from being started.
        """

        cid = require_channel_id(interaction)

        try:
            self.lobby_service.disband_lobby(cid, interaction.user)
        except GameError as e:
            await self._renderer.lobby_views.render_error(
                "Must Be Host", e, interaction
            )
            return

        embed = self.lobby_views.update_embed(
            "Game Disbanded", "The host disbanded the game, so the lobby was deleted."
        )
        await interaction.response.send_message(embeds=[embed])
