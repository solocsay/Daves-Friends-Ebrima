"""
Provides services for interacting with various games.
"""

from typing import Any

from discord.interactions import User

from models.deck import Color
from models.game_state import Phase, GameError
from services.lobby_service import LobbyService


class GameService:
    """
    The game service which provides a higher level interface for interacting with games within
    lobbies.
    """

    def __init__(self, lobby_service: LobbyService):
        self.lobby_service = lobby_service

    def play_card(
        self, channel_id: int, user_id: int, card_index: int, color: Color | None
    ):
        """
        Instructs a lobby's game to play a card.
        """

        lobby = self.lobby_service.get_lobby(channel_id)
        result = lobby.game.play(user_id, card_index, color)

        # autoplay bots (supports bot chains)
        while lobby.game.phase() == Phase.PLAYING and lobby.game.is_bot(
            lobby.game.current_player()
        ):
            lobby.game.play_bot()

        lobby.last_move = result
        self.lobby_service.save()
        return result

    def draw(self, channel_id: int, user_id: int):
        """
        Instructs the game to draw and pass for a channel
        """

        lobby = self.lobby_service.get_lobby(channel_id)
        result = lobby.game.draw_and_pass(user_id)
        lobby.last_move = {
            "type": "draw",
            "player": user_id,
            "count": len(result.drawn),
        }
        self.lobby_service.save()
        return result

    def call_uno(self, channel_id: int, caller_id: int) -> dict[str, Any]:
        """
        Instructs the game to process a Call UNO button press.
        """
        lobby = self.lobby_service.get_lobby(channel_id)
        result = lobby.game.call_uno(caller_id)
        self.lobby_service.save()
        return result

    def end_game(self, channel_id: int) -> None:
        """
        Ends the current game for a channel.
        """
        lobby = self.lobby_service.get_lobby(channel_id)
        lobby.game.reset()
        lobby.last_move = None
        self.lobby_service.save()

    def delete_game(self, channel_id: int, caller: User) -> None:
        """
        Deletes the current game for a channel.
        """
        self.lobby_service.disband_lobby(channel_id, caller)

    def kick_player(self, channel_id: int, target_id: int):
        """
        Removes a player from the game in a lobby.
        """
        lobby = self.lobby_service.get_lobby(channel_id)
        lobby.game.kick_player(target_id)
        self.lobby_service.save()

    def leave_player(self, channel_id: int, user_id: int):
        """
        Removes a player from the game, using remove_player in LOBBY or kick_player during PLAYING.
        """
        lobby = self.lobby_service.get_lobby(channel_id)
        phase = lobby.game.phase()
        if phase == Phase.LOBBY:
            lobby.game.remove_player(user_id)
        elif phase == Phase.PLAYING:
            lobby.game.kick_player(user_id)
        else:
            raise GameError("You can't leave a finished game.")
        self.lobby_service.save()
        return phase
