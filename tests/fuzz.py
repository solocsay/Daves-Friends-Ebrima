"""
Fuzzes some parts of the bot code using atheris.
"""

#!/usr/bin/python3

import sys

try:
    import atheris
except ImportError:  # pragma: no cover - only hit when fuzz deps are absent
    atheris = None
    from models import deck
    from models.deck import Color
else:
    with atheris.instrument_imports():
        from models import deck
        from models.deck import Color


def create_random_card(fdp):
    """
    Creates a random Uno card. It can be any type of card with any number or color.
    """
    card_types = [0, 1, 2, 3, 4, 5]
    card_type = card_types[fdp.ConsumeIntInRange(0, 4)]
    colors = [Color.RED, Color.YELLOW, Color.BLUE, Color.GREEN]
    color = colors[fdp.ConsumeIntInRange(0, 3)]

    match card_type:
        case 0:
            number = fdp.ConsumeIntInRange(0, 9)
            return deck.Number(color, number)
        case 1:
            if fdp.ConsumeBool():
                color = None
            return deck.Wild(color)
        case 2:
            if fdp.ConsumeBool():
                color = None
            return deck.DrawFourWild(color)
        case 3:
            return deck.Skip(color)
        case 4:
            return deck.DrawTwo(color)
        case 5:
            return deck.Reverse(color)


def test_deck(data):
    """
    Fuzz the deck code, making sure various random cards can be played on each other without
    errors.
    """
    fdp = atheris.FuzzedDataProvider(data)

    card1 = create_random_card(fdp)
    card2 = create_random_card(fdp)

    deck.can_play_card(card1, card2)


def main():
    """
    Runs the atheris fuzzer when the optional fuzz dependency is installed.
    """
    if atheris is None:
        raise SystemExit(
            "Install fuzz deps first with: pip install --editable '.[fuzz]'"
        )

    atheris.Setup(sys.argv, test_deck)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
