# UNO Discord Bot
A Python Discord bot that lets users play UNO inside a Discord server.

## Setup

In order to run the bot yourself, follow these steps.

Requirements:
- Python 3.10+
- discord.py
- dotenv

Clone the repository:

```sh
git clone https://github.com/CSS360-2026-Winter/Daves-Friends.git
cd Daves-Friends
```

Create a virtual environment:

```sh
python3 -m venv .venv
```

Activate the virtual environment:

**Unix-like (Linux, MacOS, BSD, etc.)**
```bash
source .venv/bin/activate
```

**Windows**
```bash
.venv\Scripts\Activate.ps1
```

To install all dependencies and uno_discord, run the following:
```sh
pip install .
```

For development, run `pip install --editable .`.

Then copy `.env-sample` to `.env` file and set `DISCORD_TOKEN` to the token you created for your instance of the bot.

For optional faster slash commands during development, specify the `GUILD_ID` in `.env`:
```env
GUILD_ID=your_server_id
```

This instantly syncs commands to the server. If not set, commands may take longer to appear.

To run the bot, execute `uno_discord`.

## Testing

To test the bot, ensure that you're in the virtual environment and install test dependencies:
```sh
pip install --editable .["test"]
```

To run the tests, run `pytest` in the virtual environment. This will run everything except the fuzzer, which can be run with `python3 tests/fuzz.py`.

**Note**: It is recommended to run `./run_checks.sh` before commiting code. This will run pytest, pylint, and check the formatting, telling you what went wrong before your code hits CI.

## Usage

After adding the Uno bot to a Discord server, you can start your own Uno games!

### Lobby

`/create` creates a new lobby and a message displaying information about the lobby.

The lobby message has buttons to "Join", "Leave", "Start Game", or "Disband Game". Only the person who started the lobby can start the game or disband the lobby.

### Game

Once the game has been started, the lobby message updates to display the current game state, including the current player's turn.

On a player's turn, they can choose to play a card or to "Draw Card and Pass".

To play a card, the player can use the `/play <card_index> <color>` command. `card_index` is the index displayed when pressing the "View Cards" button. The color of the card must be chosen when playing a Wild or Plus Four Wild, otherwise it can be omitted.

If a player cannot play a card or merely wishes to skip their turn, they can press "Draw Card and Pass".

If, after playing, a player has only one card left, they should press the "Call Uno" button to declare they only have one card left. If they do not press this button within two seconds, another player may press it and inflict a two card penalty on the player who failed to call uno.

If a player does not play within 60 seconds, their turn is skipped and they draw a card automatically.
