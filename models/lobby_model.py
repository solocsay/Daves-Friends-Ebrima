"""
Provides a model to represent a lobby.
"""

from dataclasses import dataclass
from typing import Any

from models.game_state import GameState


@dataclass(frozen=True)
class LobbyAvatar:
    """
    A small serializable avatar reference used by embed rendering.
    """

    url: str | None = None


@dataclass
class LobbyUser:
    """
    A serializable snapshot of the Discord user who owns the lobby.
    """

    id: int
    name: str
    avatar_url: str | None = None

    @property
    def display_avatar(self) -> LobbyAvatar:
        """
        Matches the Discord user shape expected by the existing views.
        """
        return LobbyAvatar(self.avatar_url)

    @classmethod
    def from_user(cls, user: Any) -> "LobbyUser":
        """
        Builds a snapshot from either a Discord user or an existing LobbyUser.
        """
        if isinstance(user, cls):
            return user

        avatar = getattr(user, "display_avatar", None)
        avatar_url = getattr(avatar, "url", None)
        return cls(id=user.id, name=user.name, avatar_url=avatar_url)


@dataclass
class Lobby:
    """
    A lobby, including the user that created it, the game state, and the message ID.
    """

    user: LobbyUser
    game: GameState
    main_message: int | None
    channel_id: int | None = None
    last_move: Any | None = None
