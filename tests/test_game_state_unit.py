"""
Tests the game state class.
"""

import time

import pytest

from models.game_state import GameState, GameError, Phase
from models.deck import Color, Number, Wild


def test_start_game_requires_two_players():
    """
    Game should not start with fewer than 2 players.
    """
    g = GameState()
    g.add_player(1)

    with pytest.raises(GameError) as e:
        g.start_game()

    assert str(e.value) == "Need at least 2 players to start."


def test_start_game_already_started():
    """
    Test trying to start a game that has already been started.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    with pytest.raises(GameError) as e:
        g.start_game()

    assert str(e.value) == "Game already started."


def test_add_player_when_started():
    """
    Test trying to add a player into a game that has already started.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    with pytest.raises(GameError) as e:
        g.add_player(3)

    assert str(e.value) == "Game state has already been started."


def test_remove_player():
    """
    Test removing a player from a game.
    """
    g = GameState()
    g.add_player(1)
    g.remove_player(1)
    assert not g.players()


def test_remove_player_running_game():
    """
    Test trying to remove a player from an ongoing game.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    with pytest.raises(GameError) as e:
        g.remove_player(2)

    assert str(e.value) == "You can't leave after the game starts."


def test_remove_player_non_existent():
    """
    Test trying to remove a player that does not exist.
    """
    g = GameState()
    g.add_player(1)

    with pytest.raises(GameError) as e:
        g.remove_player(2)

    assert str(e.value) == "Player not in lobby."


def test_no_current_player():
    """
    Test trying to retrieve the current player when one does not exists.
    """
    g = GameState()
    with pytest.raises(GameError) as e:
        g.current_player()

    assert str(e.value) == "No players."


def test_add_duplicate_player_raises_error():
    """
    Adding the same player twice should raise a GameError.
    """
    g = GameState()
    g.add_player(1)

    with pytest.raises(GameError) as e:
        g.add_player(1)

    assert str(e.value) == "Player already in lobby."


def test_draw_advances_turn():
    """
    When a player draws and passes, the turn should move
    to the next player.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)

    assert g.phase() == Phase.LOBBY

    g.start_game()

    first_player = g.current_player()
    result = g.draw_and_pass(first_player, amt=1)

    assert result.next_player != first_player
    assert g.current_player() == result.next_player
    assert g.phase() == Phase.PLAYING


def test_draw_adds_card():
    """
    Tests a player adds a card to their hand when they draw a card.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    # Draw 1 and pass
    old_count = len(g.hand(1))
    g.draw_and_pass(1)
    assert len(g.hand(1)) == old_count + 1

    # Draw 2 and pass
    old_count = len(g.hand(2))
    g.draw_and_pass(2, 2)
    assert len(g.hand(2)) == old_count + 2


def test_draw_wrong_turn():
    """
    Tests drawing a card on the wrong turn.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    with pytest.raises(GameError) as e:
        g.draw_and_pass(2)

    assert str(e.value) == "It's not your turn to play."


def test_draw_negative_cards():
    """
    Tests drawing a negative number of cards.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    with pytest.raises(GameError) as e:
        g.draw_and_pass(1, -10)

    assert str(e.value) == "Amt must be >= 1."


def test_draw_wrong_phase():
    """
    Test drawing before the game begins.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    with pytest.raises(GameError) as e:
        g.draw_and_pass(1)

    assert str(e.value) == "Game is not currently playing."


def test_clear_uno_vulnerable():
    """
    Test drawing a card clears Uno vulnerability.
    """
    g = _set_up_uno()
    g.start_game()
    assert g.uno_vulnerable() == 1
    g.draw_and_pass(1)
    assert g.uno_vulnerable() is None


def test_play_card_not_started():
    """
    Test trying to play a card before the game has started.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)

    with pytest.raises(GameError) as e:
        g.play(1, 2)

    assert str(e.value) == "The game has not started yet!"


def test_play_card_wrong_turn():
    """
    Test trying to play a card on the wrong turn.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    with pytest.raises(GameError) as e:
        g.play(2, 2)

    assert str(e.value) == "It is currently not your turn to play."


def test_play_card_invalid_index():
    """
    Test trying to play a card with an invalid index.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    with pytest.raises(GameError) as e1:
        g.play(1, 20)

    assert str(e1.value) == "That is not a valid card index"

    with pytest.raises(GameError) as e2:
        g.play(1, -1)

    assert str(e2.value) == "That is not a valid card index"


def test_play_no_top_card():
    """
    Test trying to play when there is no top card.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()
    g.state["discard"] = []

    with pytest.raises(GameError) as e:
        g.play(1, 1)

    assert str(e.value) == "There is no card on top!"


def test_play_wild_no_color():
    """
    Test trying to play a Wild or Draw4 without choosing a color.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()
    g.state["hands"][1] = [Wild()]

    with pytest.raises(GameError) as e:
        g.play(1, 0)

    assert str(e.value) == "You must choose a color for Wild/Draw4."


def test_play_invalid_card():
    """
    Test trying to play cards that clearly can't be played on each other.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()
    g.state["hands"][1] = [Number(Color.RED, 5)]
    g.state["discard"] = [Number(Color.BLUE, 6)]

    with pytest.raises(GameError) as e:
        g.play(1, 0)

    assert str(e.value) == "You can't play that card on the current top card."


def test_play_victory():
    """
    Test playing a winning card.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()
    g.state["hands"][1] = [Number(Color.RED, 5)]
    g.state["discard"] = [Number(Color.RED, 6)]

    result = g.play(1, 0)

    assert g.state["phase"] == Phase.FINISHED
    assert g.state["winner"] == 1
    assert result.winner == 1


def test_add_bot():
    """
    Test adding a bot to a game, ensuring IDs are sequential negative integers.
    """
    g = GameState()
    g.add_player(1)
    g.add_bot()
    g.add_player(2)
    g.add_bot()
    g.add_bot()

    g.start_game()

    assert g.state["players"][1] == -1
    assert g.state["players"][3] == -2
    assert g.state["players"][4] == -3


def test_is_bot():
    """
    Ensure is_bot properly determines what is and is not a bot.
    """
    g = GameState()
    g.add_player(1)
    g.add_bot()
    g.add_player(2)
    g.add_bot()
    g.add_bot()

    players = g.state["players"]

    g.start_game()
    assert not g.is_bot(players[0])
    assert g.is_bot(players[1])
    assert not g.is_bot(players[2])
    assert g.is_bot(players[3])
    assert g.is_bot(players[4])


def test_run_bots():
    """
    Make sure bots run smoothly playing with each other. Creates 10 games and
    has three bots play 50 rounds of each.
    """
    g = GameState()

    for _ in range(0, 10):
        g.add_bot()
        g.add_bot()
        g.add_bot()

        g.start_game()

        for _ in range(0, 50):
            try:
                g.play_bot()
            except GameError as e:
                if str(e) == "Game is not currently playing.":
                    break
                raise e
        g.reset()


def test_run_human_as_bot():
    """
    Test trying to run a human player as a bot.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    with pytest.raises(GameError) as e:
        g.play_bot()

    assert str(e.value) == "Current player isn't a bot"


def test_kick():
    """
    Test kicking users from a game.
    """
    g = GameState()
    g.add_player(1)
    g.kick_player(1)
    assert len(g.players()) == 0


def test_kick_bot():
    """
    Test kicking a bot from a game.
    """
    g = GameState()
    g.add_bot()
    g.add_bot()
    g.kick_player(-1)
    assert len(g.players()) == 1


def test_kick_non_existent():
    """
    Test trying to kick a user that isn't in the game.
    """
    g = GameState()
    g.add_player(1)

    with pytest.raises(GameError) as e:
        g.kick_player(2)

    assert str(e.value) == "Player not in game."


def test_kick_turn_order():
    """
    Test fixing turn order after kicking a user.
    """
    g = GameState()
    g.add_bot()
    g.add_bot()
    g.add_bot()
    g.add_bot()
    g.start_game()

    # Ensure their hands are empty so they can't play cards that mess with turn order.
    g.state["hands"][-1] = [Number(Color.RED, 3)]
    g.state["hands"][-2] = [Number(Color.RED, 3)]
    g.state["hands"][-3] = [Number(Color.RED, 3)]
    g.state["hands"][-4] = [Number(Color.RED, 3)]

    # Ensure they can't play any cards and everything they can draw is
    # unplayable so the game doesn't end early.
    g.state["discard"] = [Number(Color.BLUE, 2)]
    g.state["deck"] = [
        Number(Color.GREEN, 4),
        Number(Color.GREEN, 4),
        Number(Color.GREEN, 4),
        Number(Color.GREEN, 4),
        Number(Color.GREEN, 4),
        Number(Color.GREEN, 4),
    ]

    g.play_bot()
    g.play_bot()
    g.play_bot()

    assert g.state["turn_index"] == 3
    g.kick_player(-4)
    assert g.state["turn_index"] == 0

    g.play_bot()
    g.play_bot()

    g.kick_player(-1)
    assert g.state["turn_index"] == 1


def test_turn_count():
    """
    Test getting the number of turns passed.
    """
    g = GameState()
    g.add_bot()
    g.add_bot()

    g.start_game()
    assert g.turn_count() == 0
    g.play_bot()
    assert g.turn_count() >= 1


def _set_up_uno() -> GameState:
    """
    Sets up a new game with player 1 at Uno for calling UNo tests.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.state["hands"][1] = [Number(Color.RED, 5)]
    g.state["uno_vulnerable"] = 1
    assert g.uno_vulnerable() == 1
    return g


def test_call_uno():
    """
    Tests a player with one card calling Uno.
    """
    g = _set_up_uno()
    g.start_game()

    assert g.call_uno(1) == {"result": "safe", "target": 1, "caller": 1}


def test_call_uno_other():
    """
    Tests calling Uno on another player.
    """
    g = _set_up_uno()
    g.start_game()

    assert g.call_uno(2) == {"result": "penalty", "caller": 2, "target": 1}


def test_call_uno_early():
    """
    Tests calling Uno on another player during the grace period.
    """
    g = _set_up_uno()
    g.state["uno_grace_until"] = time.monotonic() + 2.0
    g.start_game()

    assert g.uno_grace_active()
    assert g.call_uno(2) == {"result": "too_early", "target": 1, "caller": 2}


def test_getter_afk_deadline():
    """
    Test getting the afk deadline.
    """
    g = GameState()
    assert g.afk_deadline() is None


def test_call_uno_lobby():
    """
    Test trying to call Uno when the game hasn't started yet.
    """
    g = GameState()
    g.add_player(1)

    with pytest.raises(GameError) as e:
        g.call_uno(1)

    assert str(e.value) == "Game is not currently playing."


def test_call_uno_none_vulnerable():
    """
    Test trying to call Uno when no player is vulnerable.
    """
    g = GameState()
    g.add_player(1)
    g.add_player(2)
    g.start_game()

    assert g.call_uno(1) == {"result": "no_target", "caller": 1}
