"""
Provides storage for lobbies.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from models.game_state import GameState
from models.lobby_model import Lobby, LobbyUser


class LobbyRepository:
    """
    The lobby repository which stores, provides, modifies, and removes lobbies.
    """

    def __init__(self, storage_path: str | Path | None = None):
        self._storage_path = (
            Path(storage_path) if storage_path else self._default_path()
        )
        self.lobbies: dict[int, Lobby] = self._load()

    @staticmethod
    def _default_path() -> Path:
        return Path(__file__).resolve().parent.parent / "data" / "lobbies.pkl"

    def _load(self) -> dict[int, Lobby]:
        if not self._storage_path.exists():
            return {}

        try:
            with self._storage_path.open("rb") as storage_file:
                data = pickle.load(storage_file)
        except (pickle.PickleError, EOFError, OSError, AttributeError, TypeError):
            return {}

        if not isinstance(data, dict):
            return {}

        lobbies: dict[int, Lobby] = {}
        for lobby_id, lobby in data.items():
            if not isinstance(lobby, Lobby):
                continue

            if not isinstance(lobby.user, LobbyUser):
                lobby.user = LobbyUser.from_user(lobby.user)

            if not hasattr(lobby, "channel_id") or lobby.channel_id is None:
                lobby.channel_id = int(lobby_id)

            if not hasattr(lobby, "last_move"):
                lobby.last_move = None

            lobbies[int(lobby_id)] = lobby

        return lobbies

    def save(self) -> None:
        """
        Flushes the current lobby state to disk.
        """
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        with NamedTemporaryFile(
            mode="wb", dir=self._storage_path.parent, delete=False
        ) as temp_file:
            pickle.dump(self.lobbies, temp_file)
            temp_path = Path(temp_file.name)

        temp_path.replace(self._storage_path)

    def get(self, lobby_id: int) -> Lobby:
        """
        Returns a lobby based on its ID.
        """
        return self.lobbies[lobby_id]

    def set(self, lobby_id: int, user: Any, game: GameState) -> None:
        """
        Stores a lobby by ID.
        """
        self.lobbies[lobby_id] = Lobby(
            LobbyUser.from_user(user), game, None, channel_id=lobby_id
        )
        self.save()

    def delete(self, lobby_id: int) -> None:
        """
        Deletes a lobby by ID.
        """
        del self.lobbies[lobby_id]
        self.save()

    def exists(self, lobby_id: int) -> bool:
        """
        Returns whether or not a lobby exists by ID.
        """
        return lobby_id in self.lobbies
