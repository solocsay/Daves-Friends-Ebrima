"""
Provides classes and functions related to the operation of a game.
"""

import random
import time
from datetime import datetime, timedelta, timezone

from dataclasses import dataclass, field
from typing import Any
from enum import Enum, auto

from models.deck import (
    Card,
    Color,
    Deck,
    Wild,
    DrawFourWild,
    can_play_card,
    Skip,
    Reverse,
    DrawTwo,
    Number,
)
from models import bot


class Phase(Enum):
    """
    The current phase of the game. LOBBY is before the game starts and when players can join.
    PLAYING is when the game is being played and players can play cards. FINISHED is when the game
    has ended and a winner has been declared.
    """

    LOBBY = auto()
    PLAYING = auto()
    FINISHED = auto()


class Direction(Enum):
    """
    The current direction of turn progression.
    """

    COUNTER_CLOCKWISE = auto()
    CLOCKWISE = auto()


class GameError(Exception):
    """
    Describes an error that has occurred with the game.
    """

    def __init__(self, msg: str, private: bool = False, title: str = ""):
        super().__init__(msg)
        self.private = private
        self.title = title


@dataclass
class PlayResult:
    """
    The result of a played card, containing information about its effects on the game.
    """

    # pylint: disable=too-many-instance-attributes
    played_by: int
    played_card: Card
    chosen_color: Color | None = None

    reversed: bool = False
    skipped: bool = False
    drew_cards: dict[int, int] = field(default_factory=dict)

    next_player: int | None = None
    winner: int | None = None


@dataclass
class DrawResult:
    """
    The result of drawing cards, containing information about who drew the cards and whose turn is
    next.
    """

    user_id: int
    drawn: list[Card]
    next_player: int


def _deal_starting_hands(
    players: list[int], draw_pile: list[Card], cards_per_player: int = 7
) -> dict[int, list[Card]]:
    if len(players) < 2:
        raise GameError("Need at least 2 players to deal hands.")
    if cards_per_player <= 0:
        raise GameError("cards_per_player must be >= 1.")

    hands: dict[int, list[Card]] = {uid: [] for uid in players}

    for _ in range(cards_per_player):
        for uid in players:
            if not draw_pile:
                raise GameError("Deck ran out while dealing starting hands.")
            hands[uid].append(draw_pile.pop())

    return hands


class GameState:
    """
    The main GameState that describes operation of the Uno game at a fundamental level. Stores
    information about the current state of the game in a dictionary which can be accessed with
    accessor functions. Provides functions for modifying game state and progressing the game.
    """

    def __init__(self) -> None:
        self._rng = random.Random()
        self.state: dict[str, Any] = self._new_state()

    def _new_state(self) -> dict[str, Any]:
        return {
            "phase": Phase.LOBBY,  # stores enum
            "players": [],  # stores discord user ids
            "bots": [],  # the indices of the users which are bots
            "hands": {},  # stores user id -> list with cards
            "deck": [],  # list with cards
            "discard": [],
            "turn_index": 0,  # index representing which users turn it is
            "turn_count": 0,  # counter representing the current turn #
            "afk_deadline": None,  # AFK timer deadline (UTC datetime)
            "afk_counts": {},  # track AFK skips
            "uno_grace_until": 0.0,  # timestamp when others may start catching
            "uno_vulnerable": None,  # user_id who has 1 card and can be caught
            "direction": Direction.CLOCKWISE,
            "winner": None,
        }

    def reset(self) -> None:
        """
        Resets the game, erasing all game state.
        """
        self.state = self._new_state()

    # Getters
    def phase(self) -> Phase:
        """
        Returns the current phase of the game.
        """
        return self.state["phase"]

    def players(self) -> list[int]:
        """
        Returns the user ids of the players in the game.
        """
        return list(self.state["players"])

    def current_player(self) -> int:
        """
        Returns the user id of the player whose turn it is from the state.
        Throws GameError if there are no players in the game.
        """
        if not self.state["players"]:
            raise GameError("No players.")
        return self.state["players"][self.state["turn_index"]]

    def is_bot(self, user_id) -> bool:
        """
        Returns whether or not a player is a bot
        """
        return user_id < 0

    def hand(self, user_id: int) -> list[Card]:
        """
        Returns a player's hand as a list of cards
        """
        return list(self.state["hands"].get(user_id, []))

    def top_card(self) -> Card | None:
        """
        Returns the top card, which is played upon.
        """
        discard = self.state["discard"]
        return discard[-1] if discard else None

    def turn_count(self) -> int:
        """
        Returns how many turns have passed.
        """
        return self.state["turn_count"]

    def afk_deadline(self):
        """
        Returns the deadline for the current player to finish their turn as a UTC timestamp.
        """
        return self.state.get("afk_deadline")

    def uno_vulnerable(self) -> int | None:
        """
        Returns the user id of the user with only one card left.
        """
        return self.state["uno_vulnerable"]

    def uno_grace_active(self) -> bool:
        """
        Returns whether or not the grace period for catching someone for not calling Uno is active.
        """
        return (
            self.state["uno_vulnerable"] is not None
            and self._now() < self.state["uno_grace_until"]
        )

    # Actions
    def add_player(self, user_id: int) -> None:
        """
        Adds a new player by id to the game.
        """
        if self.state["phase"] != Phase.LOBBY:
            raise GameError("Game state has already been started.")
        if user_id in self.state["players"]:
            raise GameError("Player already in lobby.")
        self.state["players"].append(user_id)
        self.state["hands"][user_id] = []
        self.state["afk_counts"][user_id] = 0

    def remove_player(self, user_id: int) -> None:
        """
        Removes a player by id from the game. Throws an error if the player is not in the lobby or
        if the game has already started.
        """
        if self.phase() != Phase.LOBBY:
            raise GameError("You can't leave after the game starts.")
        if user_id not in self.state["players"]:
            raise GameError("Player not in lobby.")
        self.state["players"].remove(user_id)
        self.state["hands"].pop(user_id, None)

    def kick_player(self, user_id: int) -> None:
        """
        Removes a player from the game during play. Adjusts turn order safely.
        """
        players = self.state["players"]

        if user_id not in players:
            raise GameError("Player not in game.")

        idx = players.index(user_id)

        players.remove(user_id)
        self.state["hands"].pop(user_id, None)

        self.state["afk_counts"].pop(user_id, None)

        # If only one player remains, end the game
        if len(players) <= 1:
            self.state["phase"] = Phase.FINISHED
            if players:
                self.state["winner"] = players[0]
            return

        turn_index = self.state["turn_index"]

        if idx < turn_index:
            self.state["turn_index"] -= 1
        elif idx == turn_index:
            self.state["turn_index"] %= len(players)

    def add_bot(self) -> None:
        """
        Adds a new bot to the game (with a negative user ID)
        """
        # Choose a new negative user ID less than any existing bot
        m = 0
        for user_id in self.state["players"]:
            m = min(m, user_id)

        self.add_player(m - 1)

    def start_game(self) -> None:
        """
        Starts a new game, transitioning the phase from lobby to playing.
        """
        if self.phase() != Phase.LOBBY:
            raise GameError("Game already started.", private=True)
        if len(self.state["players"]) < 2:
            raise GameError("Need at least 2 players to start.", private=True)

        deck = Deck()
        deck.add_default_cards()
        draw_pile: list[Card] = list(deck.cards)
        self._rng.shuffle(draw_pile)

        hands = _deal_starting_hands(self.state["players"], draw_pile)
        discard_pile: list[Card] = []
        _ = self._draw_first_valid_start_card(draw_pile, discard_pile)

        self.state["hands"] = hands
        self.state["deck"] = draw_pile
        self.state["discard"] = discard_pile
        self.state["turn_index"] = 0
        self.state["direction"] = Direction.CLOCKWISE
        self.state["winner"] = None
        self.state["phase"] = Phase.PLAYING
        self._set_afk_deadline(60)

    def play(
        self, user_id: int, card_index: int, choose_color: Color | None = None
    ) -> PlayResult:
        """
        Plays a card for a player by user id, card index, and color (if the card is a wild).
        If color is provided and the card is not a wild, it is silently ignored.
        """
        if self.phase() != Phase.PLAYING:
            raise GameError(
                "The game has not started yet!", title="Game Not Started", private=True
            )
        if user_id != self.current_player():
            raise GameError(
                "It is currently not your turn to play.",
                title="Wrong Turn",
                private=True,
            )

        hand = self.state["hands"].get(user_id, [])
        if card_index < 0 or card_index >= len(hand):
            raise GameError(
                "That is not a valid card index",
                title="Invalid Card Index",
                private=True,
            )

        top = self.top_card()
        if top is None:
            raise GameError(
                "There is no card on top!", title="No Top Card!", private=True
            )

        card = hand[card_index]

        if isinstance(card, (Wild, DrawFourWild)):
            if choose_color is None:
                raise GameError(
                    "You must choose a color for Wild/Draw4.",
                    title="Picked Incorrectly",
                    private=True,
                )
            card.color = choose_color

        if not can_play_card(top, card):
            raise GameError(
                "You can't play that card on the current top card.",
                title="Incorrect Card",
                private=True,
            )

        played = hand.pop(card_index)
        self.state["discard"].append(played)
        self._start_uno_window_if_needed(user_id)

        res = PlayResult(
            played_by=user_id,
            played_card=played,
            chosen_color=(
                choose_color if isinstance(played, (Wild, DrawFourWild)) else None
            ),
        )

        if len(hand) == 0:
            self._clear_uno()
            self.state["phase"] = Phase.FINISHED
            self.state["winner"] = user_id
            res.winner = user_id
            return res

        self._apply_effects_and_advance(played, res)
        res.next_player = self.current_player()
        return res

    def play_bot(self):
        """
        Chooses a card for the bot to play based on a bot strategy and plays it with `play`.
        """
        if not self.is_bot(self.current_player()):
            raise GameError("Current player isn't a bot")

        user_id = self.current_player()
        top = self.top_card()

        hand = self.state["hands"][user_id]
        index, color = bot.play_card(bot.Strategy.RANDOM, hand, top)

        if index is None:
            self.draw_and_pass(user_id)
        else:
            self.play(user_id, index, color)

    def draw_and_pass(self, user_id: int, amt: int = 1) -> DrawResult:
        """
        Adds `amt` cards to a user's hand and skips their turn. The game must be active.
        """
        if self.phase() != Phase.PLAYING:
            raise GameError(
                "Game is not currently playing.", title="Game Not Started", private=True
            )
        if user_id != self.current_player():
            raise GameError(
                "It's not your turn to play.", title="Wrong Turn", private=True
            )
        if amt <= 0:
            raise GameError("Amt must be >= 1.", title="Invalid Amount", private=True)

        draw_pile: list[Card] = self.state["deck"]
        discard_pile: list[Card] = self.state["discard"]
        hand: list[Card] = self.state["hands"][user_id]

        drawn: list[Card] = []
        for _ in range(amt):
            c = self._draw_one(draw_pile, discard_pile)
            hand.append(c)
            drawn.append(c)

        if self.state["uno_vulnerable"] == user_id:
            self._clear_uno()

        self._advance_turn(steps=1)
        return DrawResult(
            user_id=user_id, drawn=drawn, next_player=self.current_player()
        )

    def _draw_first_valid_start_card(
        self, draw_pile: list[Card], discard_pile: list[Card]
    ) -> Card:
        if not draw_pile:
            raise GameError("Deck is empty; can't pick a start card.")

        rejected: list[Card] = []

        while draw_pile:
            card = draw_pile.pop()

            if isinstance(card, Number):
                discard_pile.append(card)

                if rejected:
                    draw_pile.extend(rejected)
                    self._rng.shuffle(draw_pile)

                return card

            rejected.append(card)

        draw_pile.extend(rejected)
        self._rng.shuffle(draw_pile)
        raise GameError("Couldn't find a valid start Number card in the deck.")

    def _apply_effects_and_advance(self, played: Card, res: PlayResult) -> None:
        players = self.state["players"]
        n = len(players)

        match played:
            case Skip(_):
                res.skipped = True
                self._advance_turn(steps=2)

            case Reverse(_):
                self.state["direction"] = (
                    Direction.COUNTER_CLOCKWISE
                    if self.state["direction"] == Direction.CLOCKWISE
                    else Direction.CLOCKWISE
                )
                res.reversed = True

                if n == 2:
                    res.skipped = True
                    self._advance_turn(steps=2)
                else:
                    self._advance_turn(steps=1)

            case DrawTwo(_):
                target = self._peek_next_player_id()
                self._draw_many_to(target, 2)
                res.drew_cards[target] = 2
                res.skipped = True
                self._advance_turn(steps=2)

            case DrawFourWild(_):
                target = self._peek_next_player_id()
                self._draw_many_to(target, 4)
                res.drew_cards[target] = 4
                res.skipped = True
                self._advance_turn(steps=2)

            case Wild(_):
                self._advance_turn(steps=1)

            case Number(_, _):
                self._advance_turn(steps=1)

            case _:
                self._advance_turn(steps=1)

    def _advance_turn(self, steps: int = 1) -> None:
        players: list[int] = self.state["players"]
        if not players:
            return
        n = len(players)
        self.state["turn_index"] = (
            self.state["turn_index"] + steps * self._dir_sign()
        ) % n
        self.state["turn_count"] += 1
        self._set_afk_deadline(60)

    def _peek_next_player_id(self) -> int:
        players: list[int] = self.state["players"]
        if not players:
            raise GameError("No players.")
        n = len(players)
        idx = self.state["turn_index"]
        next_idx = (idx + self._dir_sign()) % n
        return players[next_idx]

    def _draw_many_to(self, user_id: int, count: int) -> None:
        if count <= 0:
            return
        if user_id not in self.state["hands"]:
            raise GameError("Target player not found.")

        draw_pile: list[Card] = self.state["deck"]
        discard_pile: list[Card] = self.state["discard"]
        hand: list[Card] = self.state["hands"][user_id]

        for _ in range(count):
            hand.append(self._draw_one(draw_pile, discard_pile))

    def _draw_one(self, draw_pile: list[Card], discard_pile: list[Card]) -> Card:
        if draw_pile:
            return draw_pile.pop()

        if len(discard_pile) <= 1:
            raise GameError("No cards left to draw.")

        top = discard_pile[-1]
        refill = discard_pile[:-1]
        discard_pile[:] = [top]

        # Reset Wild colors before recycling discard back into the deck
        for c in refill:
            if isinstance(c, (Wild, DrawFourWild)):
                c.color = None

        self._rng.shuffle(refill)
        draw_pile.extend(refill)

        return draw_pile.pop()

    def _dir_sign(self) -> int:
        return 1 if self.state["direction"] == Direction.CLOCKWISE else -1

    def _now(self) -> float:
        return time.monotonic()

    def _set_afk_deadline(self, seconds: int = 60) -> None:
        self.state["afk_deadline"] = datetime.now(timezone.utc) + timedelta(
            seconds=seconds
        )

    def _clear_uno(self) -> None:
        self.state["uno_vulnerable"] = None
        self.state["uno_grace_until"] = 0.0

    # start/reset uno if player is at 1 card; otherwise clear
    def _start_uno_window_if_needed(self, user_id: int) -> None:
        hand = self.state["hands"].get(user_id, [])
        if len(hand) == 1:
            self.state["uno_vulnerable"] = user_id
            self.state["uno_grace_until"] = self._now() + 2.0
        else:
            if self.state["uno_vulnerable"] == user_id:
                self._clear_uno()

    def call_uno(self, caller_id: int) -> dict[str, Any]:
        """
        Calls Uno. If the caller is the current player, the player is now safe from being caught.
        If the caller is another player and the grace period has passed, the vulnerable player is
        caught.
        """
        if self.phase() != Phase.PLAYING:
            raise GameError("Game is not currently playing.", private=True)

        target = self.state["uno_vulnerable"]
        if target is None:
            return {"result": "no_target", "caller": caller_id}

        # if vulnerable player calls uno (safe, clear window)
        if caller_id == target:
            self._clear_uno()
            return {"result": "safe", "target": target, "caller": caller_id}

        # other players trying to catch vulnerable player
        if self._now() < self.state["uno_grace_until"]:
            return {"result": "too_early", "target": target, "caller": caller_id}

        self._draw_many_to(target, 2)
        self._clear_uno()
        return {"result": "penalty", "target": target, "caller": caller_id}
