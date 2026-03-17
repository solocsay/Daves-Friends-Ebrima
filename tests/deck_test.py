"""
Tests deck generation and validation code.
"""

from models.deck import (
    Color,
    Deck,
    DrawFourWild,
    DrawTwo,
    Number,
    Reverse,
    Skip,
    Wild,
    can_play_card,
    format_card,
)


def test_deck_generation():
    """
    Ensures a deck generates without error and has the right size.
    """

    deck = Deck()
    deck.add_default_cards()
    assert len(deck.cards) == 108


def test_wilds():
    """
    Ensures both wilds and drawfourwilds can be played on all other cards.
    """

    deck = Deck()
    deck.add_default_cards()

    for card in deck.cards:
        assert can_play_card(card, Wild())
        assert can_play_card(card, DrawFourWild())


def test_identical_cards():
    """
    Ensures all identical cards can be played on top of each other.
    """

    deck = Deck()
    deck.add_default_cards()

    for card in deck.cards:
        assert can_play_card(card, card)


def test_special():
    """
    Ensures special cards can be played on other cards with the same color or type.
    """

    deck = Deck()
    deck.add_default_cards()

    kinds = [Skip(Color.BLUE), Reverse(Color.BLUE), DrawTwo(Color.BLUE)]

    for kind in kinds:
        for card in deck.cards:
            if card.color == Color.BLUE:
                assert can_play_card(card, kind)
            elif type(card) is type(kind):
                assert can_play_card(card, kind)
            else:
                assert not can_play_card(card, kind)


def test_number_cards():
    """
    Ensures number cards can be played on other number cards with the same color or number, but
    not with neither.
    """

    assert can_play_card(Number(Color.BLUE, 10), Number(Color.RED, 10))
    assert can_play_card(Number(Color.BLUE, 10), Number(Color.BLUE, 5))
    assert not can_play_card(Number(Color.BLUE, 10), Number(Color.RED, 5))


def test_play_on_wilds():
    """
    Ensures cards can be properly played on wilds when their color is selected.
    """

    assert can_play_card(Wild(Color.BLUE), Number(Color.BLUE, 10))
    assert not can_play_card(Wild(Color.BLUE), Number(Color.RED, 10))


def test_format_card():
    """
    Test cards are formatted properly.
    """
    assert format_card(None) == "(none)"
    assert format_card(Number(Color.RED, 1)) == "🟥 1️⃣"
    assert format_card(Skip(Color.BLUE)) == "🟦 ⏭️ SKIP"
    assert format_card(Reverse(Color.YELLOW)) == "🟨 🔄 REVERSE"
    assert format_card(DrawTwo(Color.GREEN)) == "🟩 ➕2 DRAW 2"
    assert format_card(DrawFourWild(Color.RED)) == "🌈 ➕4 DRAW 4"
    assert format_card(Wild(Color.RED)) == "🌈 WILD"
