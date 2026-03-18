"""
Provides the Discord commands and high-level validation of them.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.app_commands.errors import CommandInvokeError
from discord.ext import commands

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
        self._afk_timers: dict[int, asyncio.Task] = {}

    async def restore_persisted_lobbies(self) -> None:
        """
        Rehydrates saved lobbies after the bot reconnects.
        """
        await self.bot.wait_until_ready()

        for channel_id, lobby in list(self.lobby_repo.lobbies.items()):
            if not await self._restore_lobby(channel_id, lobby):
                self.lobby_repo.delete(channel_id)

    async def _restore_lobby(self, channel_id: int, lobby) -> bool:
        """
        Restores one saved lobby, returning False if it is stale and should be deleted.
        """
        if lobby.main_message is None or lobby.channel_id is None:
            return False

        if lobby.game.phase() == Phase.LOBBY:
            try:
                await self._renderer.update_by_message_id(
                    self.bot, channel_id, lobby.main_message, lobby
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return False

            if len(lobby.game.players()) <= 1:
                self.restart_solo_lobby_timer(lobby, reset_deadline=False)
            else:
                await self._clear_solo_timer_message(lobby)
            await self._send_restore_notice(lobby)
            return True

        await self._clear_solo_timer_message(lobby)

        if lobby.game.phase() == Phase.PLAYING:
            self._reset_restored_turn_timer(lobby)

        try:
            await self._renderer.update_by_message_id(
                self.bot, channel_id, lobby.main_message, lobby
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False

        if lobby.game.phase() == Phase.PLAYING:
            self.start_afk_timer(channel_id, lobby)

        await self._send_restore_notice(lobby)
        return True

    async def _get_channel(self, channel_id: int | None):
        """
        Gets a Discord channel from cache or the API.
        """
        if channel_id is None:
            return None

        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            return channel

        try:
            return await self.bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _send_restore_notice(self, lobby) -> None:
        """
        Notifies the channel when a saved lobby or game has been restored.
        """
        channel = await self._get_channel(lobby.channel_id)
        if channel is None:
            return

        if lobby.game.phase() == Phase.LOBBY:
            message = "Lobby reinstated. Saved state restored after the bot restarted."
        elif lobby.game.phase() == Phase.PLAYING:
            message = "Game reinstated. Saved state restored after the bot restarted."
        else:
            message = "Saved state restored after the bot restarted."

        try:
            await channel.send(message)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    @staticmethod
    def _normalize_utc(dt_value: datetime | None) -> datetime | None:
        """
        Ensures a datetime is timezone-aware in UTC.
        """
        if dt_value is None:
            return None
        if dt_value.tzinfo is None:
            return dt_value.replace(tzinfo=timezone.utc)
        return dt_value.astimezone(timezone.utc)

    def _reset_restored_turn_timer(self, lobby) -> None:
        """
        Gives the current player a fresh AFK window after a bot restart.
        """
        lobby.game.state["afk_deadline"] = datetime.now(timezone.utc) + timedelta(
            seconds=60
        )
        self.lobby_service.save()

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
        self.lobby_service.save()
        self.restart_solo_lobby_timer(lobby, reset_deadline=True)

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

            self.game_service.play_card(
                cid,
                interaction.user.id,
                card_index,
                Color[color.value.upper()] if color else None,
            )

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

            await self._kick_player(lobby, player.id, channel_id=cid)

        except GameError as e:
            await self._renderer.lobby_views.render_error("Game Error", e, interaction)
            return

        await interaction.followup.send(
            f"{player.display_name} was kicked from the game.", ephemeral=True
        )

    @app_commands.command(name="leave", description="Leave the current UNO game or lobby.")
    async def leave(self, interaction: discord.Interaction) -> None:
        """
        Lets a player leave the game. Works in both LOBBY and PLAYING phases.
        """
        await interaction.response.defer(ephemeral=True)

        cid = require_channel_id(interaction)

        try:
            lobby = self.lobby_service.get_lobby(cid)

            if interaction.user.id not in lobby.game.players():
                raise GameError("You are not in this game.", private=True, title="Not In Game")

            phase = self.game_service.leave_player(cid, interaction.user.id)

        except GameError as e:
            embed = self._renderer.lobby_views.error_embed(
                "Error" if e.title == "" else e.title, str(e)
            )
            await interaction.followup.send(embeds=[embed], ephemeral=True)
            return

        await interaction.followup.send("You have left the game.", ephemeral=True)

        channel = self.bot.get_channel(cid)
        if channel:
            await channel.send(f"<@{interaction.user.id}> has left the game.")

        await self._renderer.update_by_message_id(
            self.bot, cid, lobby.main_message, lobby
        )

        if phase == Phase.LOBBY:
            self.restart_solo_lobby_timer(lobby, reset_deadline=True)

        elif phase == Phase.PLAYING:
            if lobby.game.phase() == Phase.FINISHED:
                if channel:
                    await channel.send("Game ended due to a lack of players.")
            else:
                self.start_afk_timer(cid, lobby)
                await self.dm_current_player_turn(lobby, cid)

    
    async def _kick_player(
        self, lobby, player_id: int, afk: bool = False, channel_id: int | None = None
    ):
        """
        Helper to remove a player from the game.
        afk=True changes messages to AFK-specific ones
        """
        cid = channel_id if channel_id is not None else lobby.channel_id
        game = lobby.game

        try:
            self.game_service.kick_player(cid, player_id)

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
        self,
        channel_id: int,
        player_id: int,
        start_turn_count: int,
        delay_seconds: float,
    ):
        """
        Skips a player's turn if they don't play in 60 seconds.
        Kicks them if they've been AFK 5 times.
        """
        await asyncio.sleep(max(delay_seconds, 0))

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
                result = game.draw_and_pass(player_id)

                # update last move
                lobby.last_move = {
                    "type": "draw",
                    "player": player_id,
                    "count": len(result.drawn),
                }

                # increment AFK count
                game.state["afk_counts"][player_id] = (
                    game.state["afk_counts"].get(player_id, 0) + 1
                )
                afk_count = game.state["afk_counts"][player_id]
                self.lobby_service.save()

                channel = self.bot.get_channel(channel_id)
                if channel and afk_count <= 4:
                    if game.phase() == Phase.FINISHED and game.ended_in_draw():
                        message = (
                            f" <@{player_id}> was AFK. No cards were available to draw, "
                            "so the game ended in a draw."
                        )
                    elif len(result.drawn) == 0:
                        message = (
                            f" <@{player_id}> was AFK. No cards were available to draw, "
                            "and their turn was skipped."
                        )
                    elif len(result.drawn) == 1:
                        message = f" <@{player_id}> was AFK. They drew 1 card and were skipped."
                    else:
                        message = (
                            f" <@{player_id}> was AFK. They drew {len(result.drawn)} cards "
                            "and were skipped."
                        )
                    await channel.send(message)

                    await self._renderer.update_by_message_id(
                        self.bot, channel_id, lobby.main_message, lobby
                    )

                # auto kick if afk 5 times
                if afk_count >= 5 and game.phase() == Phase.PLAYING:
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

        existing = self._afk_timers.get(channel_id)
        if existing and not existing.done():
            existing.cancel()

        deadline = game.afk_deadline()
        delay_seconds = 60.0
        if deadline is not None:
            deadline = self._normalize_utc(deadline)
            delay_seconds = max(
                (deadline - datetime.now(timezone.utc)).total_seconds(),
                0.0,
            )

        self._afk_timers[channel_id] = asyncio.create_task(
            self.run_afk_timer(
                channel_id,
                game.current_player(),
                game.turn_count(),
                delay_seconds,
            )
        )

    async def _clear_solo_timer_message(self, lobby, clear_deadline: bool = True):
        """
        Deletes the countdown message for a solo lobby if one exists.
        """
        channel = await self._get_channel(lobby.channel_id)

        if channel is not None and lobby.solo_timer_message is not None:
            try:
                timer_msg = await channel.fetch_message(lobby.solo_timer_message)
                await timer_msg.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        lobby.solo_timer_message = None
        if clear_deadline:
            lobby.solo_expires_at = None
        self.lobby_service.save()

    async def _get_or_create_solo_timer_message(self, lobby):
        """
        Fetches the solo timer message, or creates it if missing.
        """
        channel = await self._get_channel(lobby.channel_id)
        if channel is None:
            return None

        if lobby.solo_timer_message is not None:
            try:
                return await channel.fetch_message(lobby.solo_timer_message)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                lobby.solo_timer_message = None
                self.lobby_service.save()

        timer_msg = await channel.send(
            embed=discord.Embed(
                title="⏳ Solo Lobby Timer",
                description="Lobby expires in **120** seconds if nobody joins.",
                color=discord.Color.orange(),
            )
        )
        lobby.solo_timer_message = timer_msg.id
        self.lobby_service.save()
        return timer_msg

    async def _run_solo_timer_tick(self, lobby, timer_msg):
        """
        Updates the solo timer once and returns the next action to take.
        """
        if len(lobby.game.players()) > 1 or lobby.game.phase() != Phase.LOBBY:
            await self._clear_solo_timer_message(lobby)
            return timer_msg, "stop"

        if lobby.solo_expires_at is None:
            lobby.solo_expires_at = datetime.now(timezone.utc) + timedelta(seconds=120)
            self.lobby_service.save()

        lobby.solo_expires_at = self._normalize_utc(lobby.solo_expires_at)
        remaining = int(
            (lobby.solo_expires_at - datetime.now(timezone.utc)).total_seconds()
        )

        if remaining <= 0:
            return timer_msg, "expire"

        minutes, seconds = divmod(remaining, 60)
        timer_embed = discord.Embed(
            title="⏳ Solo Lobby Timer",
            description=f"Lobby expires in **{minutes}:{seconds:02d}** if nobody joins.",
            color=discord.Color.orange(),
        )

        try:
            await timer_msg.edit(embed=timer_embed)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            timer_msg = await self._get_or_create_solo_timer_message(lobby)
            if timer_msg is None:
                return None, "stop"

        await asyncio.sleep(1)
        return timer_msg, "continue"

    async def start_solo_lobby_timer(self, lobby):
        """
        Starts a solo lobby timer for a lobby with only one player.
        Sends a separate countdown embed. Replaces it with a "Lobby expired" embed
        when timer ends and deletes the main lobby embed.
        """
        if (
            lobby.channel_id is None
            or not getattr(lobby, "main_message", None)
            or lobby.game.phase() != Phase.LOBBY
        ):
            return

        try:
            timer_msg = await self._get_or_create_solo_timer_message(lobby)
        except (discord.Forbidden, discord.HTTPException):
            return

        if timer_msg is None:
            return

        try:
            while True:
                timer_msg, next_action = await self._run_solo_timer_tick(
                    lobby, timer_msg
                )
                if next_action == "continue":
                    continue
                if next_action == "stop":
                    return
                break

            channel = await self._get_channel(lobby.channel_id)
            if channel is None:
                return

            self.lobby_service.disband_lobby(lobby.channel_id, lobby.user)

            timer_embed = discord.Embed(
                title="🕒 Lobby Expired",
                description="The solo lobby has expired due to inactivity.",
                color=discord.Color.orange(),
            )
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
            await self._clear_solo_timer_message(lobby)
            raise

        except (discord.HTTPException, discord.Forbidden, GameError) as e:
            print(f"Solo lobby timer error: {e}")

    def restart_solo_lobby_timer(self, lobby, reset_deadline: bool = True):
        """
        Starts the solo timer if there's 1 player, cancels it otherwise.
        """
        cid = lobby.channel_id

        task = self._solo_lobby_timers.get(cid)
        if task and not task.done():
            task.cancel()

        if len(lobby.game.players()) == 1 and lobby.game.phase() == Phase.LOBBY:
            if reset_deadline or lobby.solo_expires_at is None:
                lobby.solo_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=120
                )
            else:
                lobby.solo_expires_at = self._normalize_utc(lobby.solo_expires_at)
            self.lobby_service.save()
            self._solo_lobby_timers[cid] = asyncio.create_task(
                self.start_solo_lobby_timer(lobby)
            )
        else:
            asyncio.create_task(self._clear_solo_timer_message(lobby))


async def setup(bot: commands.Bot) -> None:
    """
    Adds a new instance of UnoCog to the bot.
    """

    cog = UnoCog(bot)
    await bot.add_cog(cog)
    await cog.restore_persisted_lobbies()
