"""
Tests local file persistence for lobby and game state.
"""

from services.game_service import GameService
from services.lobby_service import LobbyService
from repos.lobby_repo import LobbyRepository
from models.game_state import Phase


class _FakeAvatar:
    def __init__(self, url: str):
        self.url = url


class _FakeUser:
    def __init__(self, user_id: int, name: str):
        self.id = user_id
        self.name = name
        self.display_avatar = _FakeAvatar(f"https://example.com/{user_id}.png")


def test_lobby_state_is_restored_from_local_file(tmp_path):
    """
    A lobby should survive a repository reload using the local persistence file.
    """
    storage_path = tmp_path / "lobbies.pkl"
    repo = LobbyRepository(storage_path=storage_path)
    lobby_service = LobbyService(repo)
    game_service = GameService(lobby_service)

    host = _FakeUser(1, "Host")
    guest = _FakeUser(2, "Guest")

    lobby = lobby_service.create_lobby(12345, host)
    lobby.main_message = 67890
    lobby_service.save()

    lobby_service.join_lobby(12345, guest)
    lobby_service.start_lobby(12345)

    current_player = lobby.game.current_player()
    game_service.draw(12345, current_player)

    reloaded_repo = LobbyRepository(storage_path=storage_path)
    reloaded_lobby = reloaded_repo.get(12345)

    assert reloaded_lobby.user.id == host.id
    assert reloaded_lobby.user.name == host.name
    assert reloaded_lobby.main_message == 67890
    assert reloaded_lobby.channel_id == 12345
    assert reloaded_lobby.game.phase() == Phase.PLAYING
    assert reloaded_lobby.game.players() == [1, 2]
    assert len(reloaded_lobby.game.hand(current_player)) == 8
    assert reloaded_lobby.last_move == {"type": "draw", "player": current_player}


def test_deleted_lobbies_are_removed_from_local_file(tmp_path):
    """
    Deleting a lobby should remove it from the persisted file as well.
    """
    storage_path = tmp_path / "lobbies.pkl"
    repo = LobbyRepository(storage_path=storage_path)
    lobby_service = LobbyService(repo)

    lobby_service.create_lobby(222, _FakeUser(10, "Host"))
    repo.delete(222)

    reloaded_repo = LobbyRepository(storage_path=storage_path)

    assert not reloaded_repo.exists(222)
