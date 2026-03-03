"""
Provides a lobby manager.
"""

from discord.interactions import User

from models.game_state import GameError, GameState, Phase
from models.lobby_model import Lobby
from repos.lobby_repo import LobbyRepository


class LobbyService:
    """
    The lobby service which manages various lobbies and provides functions for joining, starting,
    leaving, and disbanding them.
    """

    def __init__(self, repo: LobbyRepository):
        self._lobby_repo = repo

    def create_lobby(self, channel_id: int, user: User) -> Lobby:
        """
        Creates a lobby in a channel.
        """

        if self._lobby_repo.exists(channel_id):
            existing = self._lobby_repo.get(channel_id)

            if existing.game.phase() == Phase.FINISHED:
                self._lobby_repo.delete(channel_id)
            else:
                raise GameError(
                    "A lobby already exists in this channel. Join this lobby or skedaddle!",
                    private=True,
                    title="Lobby Exists",
                )

        self._lobby_repo.set(channel_id, user, GameState())
        self._lobby_repo.get(channel_id).game.add_player(user.id)

        return self._lobby_repo.get(channel_id)

    def start_lobby(self, channel_id: int) -> Lobby:
        """
        Starts a lobby.
        """

        lobby = self._lobby_repo.get(channel_id)
        lobby.game.start_game()

        return self._lobby_repo.get(channel_id)

    def join_lobby(self, channel_id: int, user: User) -> Lobby:
        """
        Adds a user to a lobby.
        """

        if not self._lobby_repo.exists(channel_id):
            raise GameError(
                "There is no lobby in this channel. Run `/create` to make one.",
                private=True,
                title="No Lobby in This Channel",
            )

        lobby = self._lobby_repo.get(channel_id)
        game = lobby.game

        if game.phase() != Phase.LOBBY:
            raise GameError(
                "The game has already started :(\nYou can't join right now.",
                private=True,
                title="Game Started",
            )

        if user.id in game.players():
            raise GameError(
                "You're already in this lobby, you can't join again silly!",
                private=True,
            )

        game.add_player(user.id)

        return lobby

    def leave_lobby(self, channel_id: int, user: User) -> Lobby:
        """
        Removes a user from a lobby.
        """

        if not self._lobby_repo.exists(channel_id):
            raise GameError(
                "There is no lobby in this channel. Run `/create` to make one.",
                private=True,
                title="No Lobby in This Channel",
            )

        lobby = self._lobby_repo.get(channel_id)
        game = lobby.game

        if user.id not in game.players():
            raise GameError("You're not in this lobby", private=True)

        if user.id == lobby.user.id:
            self._lobby_repo.delete(channel_id)
            raise GameError(
                "The host left the game, so the lobby was disbanded and the game was ended.",
                private=False,
                title="Host Left",
            )

        game.remove_player(user.id)

        return lobby

    def disband_lobby(self, channel_id: int, user: User) -> None:
        """
        Disbands a lobby if it exists. Handling error conditions.
        """

        if not self._lobby_repo.exists(channel_id):
            raise GameError(
                "There is no lobby in this channel. Run `/create` to make one.",
                private=True,
                title="No Lobby in This Channel",
            )

        lobby = self._lobby_repo.get(channel_id)

        if user.id != lobby.user.id:
            raise GameError(
                "In order to disband a game, you must be the host.", private=True
            )

        self._lobby_repo.delete(channel_id)

    def get_lobby(self, channel_id: int) -> Lobby:
        """
        Gets a lobby and returns it. Raises an error otherwise.
        """

        if not self._lobby_repo.exists(channel_id):
            raise GameError("Lobby doesn't exist.")

        return self._lobby_repo.get(channel_id)
