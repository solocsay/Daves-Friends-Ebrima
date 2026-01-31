from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
from deck import Card, Number, Skip, Reverse, DrawTwo, Wild, DrawFourWild

import discord
from discord import app_commands
from discord.ext import commands

from models.game_state import GameState, GameError, Phase


def mention(user_id: int) -> str:
    return f"<@{user_id}>"


def require_channel_id(interaction: discord.Interaction) -> int:
    cid = interaction.channel_id
    if cid is None:
        raise RuntimeError("This command must be used in a server channel (not DMs).")
    return cid


def format_card(card: Card | None) -> str:
    if card is None:
        return "(none)"
    if isinstance(card, Number):
        return f"{card.color.name} {card.number}"
    if isinstance(card, Skip):
        return f"{card.color.name} SKIP"
    if isinstance(card, Reverse):
        return f"{card.color.name} REVERSE"
    if isinstance(card, DrawTwo):
        return f"{card.color.name} DRAW2"
    if isinstance(card, DrawFourWild):
        return f"DRAW4 ({card.color.name if card.color else 'unpicked'})"
    if isinstance(card, Wild):
        return f"WILD ({card.color.name if card.color else 'unpicked'})"
    return str(card)


@dataclass
class Lobby:
    host_id: int
    game: GameState


# One lobby per channel
lobbies: Dict[int, Lobby] = {}


class LobbyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="create", description="Create a lobby in this channel.")
    async def create(self, interaction: discord.Interaction) -> None:
        cid = require_channel_id(interaction)
        uid = interaction.user.id

        if cid in lobbies:
            await interaction.response.send_message(
                "A lobby already exists in this channel. Use /status.",
                ephemeral=True,
            )
            return

        g = GameState()
        g.add_player(uid)
        lobbies[cid] = Lobby(host_id=uid, game=g)

        lobby = lobbies[cid]
        await interaction.response.send_message(
            f"Lobby created.\nHost: {mention(lobby.host_id)}\nPlayers: {len(lobby.game.players())}"
        )

    @app_commands.command(name="join", description="Join the lobby in this channel.")
    async def join(self, interaction: discord.Interaction) -> None:
        cid = require_channel_id(interaction)
        uid = interaction.user.id

        lobby = lobbies.get(cid)
        if lobby is None:
            await interaction.response.send_message(
                "No lobby in this channel. Use /create first.",
                ephemeral=True,
            )
            return

        if lobby.game.phase() != Phase.LOBBY:
            await interaction.response.send_message(
                "Game already started. You can't join right now.",
                ephemeral=True,
            )
            return

        if uid in lobby.game.players():
            await interaction.response.send_message(
                "You're already in this lobby.",
                ephemeral=True,
            )
            return

        try:
            lobby.game.add_player(uid)
        except GameError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        await interaction.response.send_message(
            f"{mention(uid)} joined the lobby. Players: {len(lobby.game.players())}"
        )

    @app_commands.command(name="leave", description="Leave the lobby in this channel.")
    async def leave(self, interaction: discord.Interaction) -> None:
        cid = require_channel_id(interaction)
        uid = interaction.user.id

        lobby = lobbies.get(cid)
        if lobby is None:
            await interaction.response.send_message(
                "No lobby in this channel.",
                ephemeral=True,
            )
            return

        if uid not in lobby.game.players():
            await interaction.response.send_message(
                "You're not in this lobby.",
                ephemeral=True,
            )
            return

        # If host leaves: end lobby (simple + avoids host-transfer edge cases)
        if uid == lobby.host_id:
            del lobbies[cid]
            await interaction.response.send_message("Host left, so the lobby was ended.")
            return

        try:
            lobby.game.remove_player(uid)
        except GameError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        await interaction.response.send_message(
            f"{mention(uid)} left the lobby. Players: {len(lobby.game.players())}"
        )

    @app_commands.command(name="status", description="Show lobby status for this channel.")
    async def status(self, interaction: discord.Interaction) -> None:
        cid = require_channel_id(interaction)
        lobby = lobbies.get(cid)

        if lobby is None:
            await interaction.response.send_message(
                "No lobby in this channel. Use /create.",
                ephemeral=True,
            )
            return

        players_sorted: List[int] = sorted(lobby.game.players())
        players_str = ", ".join(mention(pid) for pid in players_sorted) or "(none)"

        started = lobby.game.phase() != Phase.LOBBY

        await interaction.response.send_message(
            "Lobby status:\n"
            f"Host: {mention(lobby.host_id)}\n"
            f"Players ({len(players_sorted)}): {players_str}\n"
            f"Started: {started}"
        )

    @app_commands.command(name="start", description="Start the lobby game (host only).")
    async def start(self, interaction: discord.Interaction) -> None:
        cid = require_channel_id(interaction)
        uid = interaction.user.id

        lobby = lobbies.get(cid)
        if lobby is None:
            await interaction.response.send_message(
                "No lobby in this channel. Use /create.",
                ephemeral=True,
            )
            return
        elif uid != lobby.host_id:
            await interaction.response.send_message(
                "Only the host can start the lobby.",
                ephemeral=True,
            )
            return
        elif lobby.game.phase() != Phase.LOBBY:
            await interaction.response.send_message(
                "Lobby already started.",
                ephemeral=True,
            )
            return
        elif len(lobby.game.players()) < 2:
            await interaction.response.send_message(
                "Need at least 2 players to start.",
                ephemeral=True,
            )
            return
        else:
            try:
                lobby.game.start_game()
            except NotImplementedError:
                await interaction.response.send_message(
                    "Start logic isn't finished yet (dealing + first start card are teammate-owned).",
                    ephemeral=True,
                )
                return
            except GameError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

            top = lobby.game.top_card()
            turn = lobby.game.current_player()
            hand_sizes = ", ".join(
                f"{mention(pid)}={len(lobby.game.hand(pid))}" for pid in lobby.game.players()
            )

            await interaction.response.send_message(
                "Lobby started.\n"
                f"Phase: {lobby.game.phase().name}\n"
                f"Top card: {format_card(top)}\n"
                f"Turn: {mention(turn)}\n"
                f"Hands: {hand_sizes}"
            )

    @app_commands.command(name="top", description="Show top card + whose turn it is.")
    async def top(self, interaction: discord.Interaction) -> None:
        cid = require_channel_id(interaction)
        lobby = lobbies.get(cid)
        if lobby is None:
            await interaction.response.send_message("No lobby in this channel. Use /create.", ephemeral=True)
            return
        if lobby.game.phase() == Phase.LOBBY:
            await interaction.response.send_message("Game hasn't started yet. Use /start.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Top card: {format_card(lobby.game.top_card())}\n"
            f"Turn: {mention(lobby.game.current_player())}"
        )

    @app_commands.command(name="hand", description="Show your hand (ephemeral).")
    async def hand(self, interaction: discord.Interaction) -> None:
        cid = require_channel_id(interaction)
        uid = interaction.user.id
        lobby = lobbies.get(cid)
        if lobby is None:
            await interaction.response.send_message("No lobby in this channel.", ephemeral=True)
            return
        if lobby.game.phase() != Phase.PLAYING:
            await interaction.response.send_message("Game is not currently playing.", ephemeral=True)
            return

        cards = lobby.game.hand(uid)
        lines = [f"{i}: {format_card(c)}" for i, c in enumerate(cards)]
        await interaction.response.send_message("Your hand:\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="draw", description="Draw 1 card and pass.")
    async def draw(self, interaction: discord.Interaction) -> None:
        cid = require_channel_id(interaction)
        uid = interaction.user.id
        lobby = lobbies.get(cid)
        if lobby is None:
            await interaction.response.send_message("No lobby in this channel.", ephemeral=True)
            return

        try:
            res = lobby.game.draw_and_pass(uid, amt=1)
        except GameError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        await interaction.response.send_message(
            f"{mention(uid)} drew 1 and passed.\nNext: {mention(res.next_player)}"
        )

    @app_commands.command(name="end", description="End the lobby (host only).")
    async def end(self, interaction: discord.Interaction) -> None:
        cid = require_channel_id(interaction)
        uid = interaction.user.id

        lobby = lobbies.get(cid)
        if lobby is None:
            await interaction.response.send_message(
                "No lobby in this channel.",
                ephemeral=True,
            )
            return

        if uid != lobby.host_id:
            await interaction.response.send_message(
                "Only the host can end the lobby.",
                ephemeral=True,
            )
            return

        del lobbies[cid]
        await interaction.response.send_message("Lobby ended.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LobbyCog(bot))
