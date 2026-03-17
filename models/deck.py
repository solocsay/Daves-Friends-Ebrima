"""
Defines classes relating to an Uno deck, including proper Deck generation and validating cards can
be played on top of each other properly. Also defines various types for different kinds of cards
so they can be validated by the type system.
"""

from dataclasses import dataclass
from enum import Enum, auto
from random import shuffle


class Color(Enum):
    """
    The color of an Uno card. Can be red, yellow, blue, or green.
    """

    RED = auto()
    YELLOW = auto()
    BLUE = auto()
    GREEN = auto()


class Deck:
    """
    A set of cards and a method to generate cards for a deck.
    """

    cards = []

    def __init__(self):
        """
        Creates an empty deck.
        """
        self.cards = []

    def shuffle(self):
        """
        Shuffles the cards in the deck.
        """
        shuffle(self.cards)

    def add_default_cards(self):
        """
        Adds the default Uno cards (as defined by the rules) to the deck. Does not otherwise
        modify the deck or remove existing cards.
        """
        colors = [Color.RED, Color.YELLOW, Color.BLUE, Color.GREEN]

        self.cards = []

        for color in colors:
            for i in range(0, 10):
                self.cards.append(Number(color, i))
                if i != 0:
                    self.cards.append(Number(color, i))

            for i in range(0, 2):
                self.cards.append(Skip(color))
                self.cards.append(DrawTwo(color))
                self.cards.append(Reverse(color))

        for i in range(0, 4):
            self.cards.append(Wild())
            self.cards.append(DrawFourWild())

        shuffle(self.cards)


@dataclass
class Number:
    """
    A number card, which has a particular color and number.
    """

    color: Color
    number: int


@dataclass
class Wild:
    """
    A wild card, which may or may not have a color depending on whether it has been played.
    """

    color: Color | None = None


@dataclass
class DrawFourWild:
    """
    A plus four wild card, which may or may not have a color depending on whether it has been
    played.
    """

    color: Color | None = None


@dataclass
class Skip:
    """
    A skip card, which has a color. Is considered one of the "Special" cards.
    """

    color: Color


@dataclass
class DrawTwo:
    """
    A +2 card, which has a color. Is considered one of the "Special" cards.
    """

    color: Color


@dataclass
class Reverse:
    """
    A reverse card, which has a color. It is considered one of the "Special" cards.
    """

    color: Color


Card = Number | Wild | DrawFourWild | Reverse | Skip | DrawTwo

COLOR_EMOJIS = {
    Color.RED: "🟥",
    Color.YELLOW: "🟨",
    Color.BLUE: "🟦",
    Color.GREEN: "🟩",
}

NUMBER_EMOJIS = {
    0: "0️⃣",
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
}


def can_play_card(top: Card, playing: Card) -> bool:
    """
    Determines whether or not a card can be played on top of another card according to the UNO
    rules. Wilds can be played on any card, special cards can be placed on other cards with the
    same color or type, and number cards can be placed on other cards with the same color or number.
    """
    if playing == top or (
        type(top) is type(playing) and not isinstance(playing, Number)
    ):
        return True

    can_play = False
    match playing:
        case Wild(_) | DrawFourWild(_):
            can_play = True
        case Skip(c) | Reverse(c) | DrawTwo(c):
            can_play = c == top.color
        case Number(c, n):
            if isinstance(top, Number):
                can_play = c == top.color or n == top.number
            else:
                can_play = c == top.color

    return can_play


def format_card(card: Card | None) -> str:
    """
    Formats the card with an appropriate emoji representing its color or type and the card name or
    number.
    """

    if card is None:
        return "(none)"

    card_str = str(card)

    match card:
        case Number(color, number):
            card_str = f"{COLOR_EMOJIS[color]} {NUMBER_EMOJIS[number]}"
        case Skip(color):
            card_str = f"{COLOR_EMOJIS[color]} ⏭️ SKIP"
        case Reverse(color):
            card_str = f"{COLOR_EMOJIS[color]} 🔄 REVERSE"
        case DrawTwo(color):
            card_str = f"{COLOR_EMOJIS[color]} ➕2 DRAW 2"
        case DrawFourWild(color):
            card_str = "🌈 ➕4 DRAW 4"
        case Wild(color):
            card_str = "🌈 WILD"

    return card_str
