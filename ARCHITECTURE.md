# Architecture of Our Bot

## Computer network diagram (Adam Khan)
This diagram shows how users interact with the UNO bot through Discord servers, where Discord acts as an intermediary that forwards events to the bot via the Discord API and returns the bot’s responses to users.

<img width="971" height="133" alt="image" src="https://github.com/user-attachments/assets/87b3e8ff-e2bd-4f6e-ad93-9a992ac6b90c" />

---

## System Context Diagram (Rio Dumecquias)
This diagram shows the Discord bot as the system, interacting with the external entities: Discord users, the Discord API, and a potentiall database. It notes all inputes to and outputs from the bot.

<img width="1094" height="689" alt="image" src="https://github.com/user-attachments/assets/596e8dd0-9867-4333-8adf-c2a382b89c40" />

---
## Data Flow Diagram (Ali Salaka)
The data flow diagram shows how Discord users interact with our bot through slash commands. Commands are routed through the bot's lobby/game processes, which update the stored game state and return results as Discord messages.
<img width="1584" height="752" alt="image" src="https://github.com/user-attachments/assets/cabd33b5-82ae-4aa0-8c34-383a931c3b68" />

---
## Class Diagram (Anna Liberty)
The class diagram shows the relationship between the different classes used to construct the bot. These are roughly divided into those related to the Deck class and those related to the GameState class.

<img width="1694" height="1641" alt="Class Diagram" src="https://github.com/user-attachments/assets/6945b068-7b02-4758-82f2-f1961371e846" />

---
## <Diagram Type> (<Name>)
<1–2 sentences explaining what this diagram shows>
