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
## Use Case Diagram (Khalid Abdullahi)
The diagram shows how players interact with the UNO Discord Bot through lobby commands, gameplay commands, and game logic based on what we have now.

<img width="732" height="1148" alt="image" src="https://github.com/user-attachments/assets/ee8f1b3a-7927-4bb7-89be-6158053b463c" />

---
## Class Diagram (Anna Liberty)
The class diagram shows the relationship between the different classes used to construct the bot. These are roughly divided into those related to the Deck class and those related to the GameState class.

<img width="1694" height="1641" alt="Class Diagram" src="https://github.com/user-attachments/assets/6945b068-7b02-4758-82f2-f1961371e846" />

---
## Activity Diagram (Ebrima Ceesay)
The diagram shows the step-by-step flow for a player using the /play command. It demonstrates how the decision steps and the game rules are executed in order for example if the move is valid, the bot updates the game state, applies any special card effects, advances the turn, and checks for a win.

<img width="1046" height="1366" alt="image" src="https://github.com/user-attachments/assets/3e7b5af5-7cd9-432f-9569-bf5201026660" />
<img width="1021" height="1353" alt="image" src="https://github.com/user-attachments/assets/dc0418af-f65d-4576-bab5-a7b3acd9795c" />


