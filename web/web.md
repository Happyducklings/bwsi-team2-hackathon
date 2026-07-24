Since the CTFs are already finished, build the game around them in this order.

# Ground-up development workflow

## 1. Lock the MVP rules

Before coding, write down the exact minimum game:

* Multiple human Survivors
* One AI-controlled Beast
* One shared map
* Several CTF computer stations
* Survivors use SSH to access the premade CTFs
* Completing a required number of CTFs unlocks the exit
* The Beast permanently eliminates players
* At least one surviving player must reach the exit
* If everyone dies, the team loses

Do not add classes, inventories, upgrades, reviving, multiple maps, matchmaking, or advanced graphics yet.

---

## 2. Choose the basic architecture

Divide the project into three parts:

### Web client

Responsible for:

* Rendering the map
* Player controls
* Showing other players
* Showing the Beast
* Computer interactions
* Flag submission
* Progress, death, victory, and defeat screens

### Game server

Responsible for:

* Multiplayer rooms
* Player positions
* Match state
* Beast behavior
* Eliminations
* CTF completion
* Exit unlocking
* Win and loss conditions

### CTF infrastructure

Responsible for:

* Hosting the premade CTFs
* Giving players SSH access
* Separating each challenge
* Resetting challenges between matches

The game server should be the authority. Browsers should display the game state, not decide whether someone died or whether a flag is correct.

---

## 3. Organize the project

Create separate sections for:

```text
project
├── client
├── game-server
├── ctf-environments
└── shared
```

The shared section can contain definitions used by both client and server, such as:

* Match states
* Player states
* Terminal IDs
* Challenge IDs
* Network event names

This prevents the client and server from using different names for the same systems.

---

## 4. Build a single-player movement prototype

Start with only one player and no networking.

Build:

* A basic map
* Player movement
* Camera controls
* Walls and collision
* Computer station objects
* A locked exit
* Interaction detection

At this stage, pressing the interaction key near a computer should open a placeholder panel.

Do not build the Beast or CTF connection until movement and interaction work reliably.

### Completion checkpoint

A player can walk around the map, collide with walls, interact with computers, and approach the locked exit.

---

## 5. Add multiplayer synchronization

Next, connect multiple players to the same game server.

Implement:

* Joining a lobby
* Choosing a display name
* Starting a match
* Spawning players
* Synchronizing movement
* Removing disconnected players
* Showing which players are alive

Keep it to one game lobby for the prototype.

### Completion checkpoint

Two or more browser windows can join and see each other moving through the same map.

---

## 6. Create the match-state system

Define clear match phases:

```text
Lobby
Starting
Playing
Exit Unlocked
Finished
Resetting
```

The server should track:

* Connected players
* Living players
* Eliminated players
* Completed CTFs
* Required number of flags
* Whether the exit is unlocked
* Whether the team won or lost

Do this before adding the Beast because every later system depends on the match state.

### Completion checkpoint

The server can start, finish, and reset a match even without gameplay.

---

## 7. Add the AI Beast

Build the Beast in layers.

### First layer: Basic movement

Make it move between predefined points.

### Second layer: Detection

Allow it to notice nearby living players.

### Third layer: Chasing

Make it select a player and pursue them.

### Fourth layer: Losing targets

When the player gets away, make the Beast search briefly and then return to patrol.

### Fifth layer: Elimination

When the Beast catches a player:

* The server marks them dead
* They can no longer move or submit flags
* Their character is removed or visibly defeated
* They enter spectator mode

Keep the AI simple. It only needs to feel threatening, not intelligent.

### Completion checkpoint

The Beast can patrol, chase multiple players, eliminate one, and continue hunting the others.

---

## 8. Connect computer stations to the premade CTFs

Assign each computer station:

* A terminal ID
* A challenge ID
* SSH connection information
* A completion state

When a player interacts with a station, show:

* Which challenge it opens
* The SSH connection information
* Whether another teammate is already working on it
* Whether the challenge is completed
* A place to submit the flag

The web game does not need to run SSH itself for the MVP. It only needs to direct the player to the correct challenge environment.

### Completion checkpoint

Each in-game computer clearly corresponds to one of your existing CTFs.

---

## 9. Build the flag-validation system

Create a server-side challenge registry.

Each challenge should include:

* Challenge ID
* Associated computer station
* Correct flag or validation method
* Completion status

When a player submits a flag:

1. The client sends it to the game server.
2. The server validates it.
3. A correct flag marks the challenge complete.
4. The completion is shared with every player.
5. Incorrect flags only notify the submitting player.

Never place the correct flags in the browser client.

### Completion checkpoint

One player completing a CTF updates the progress counter for the whole team.

---

## 10. Connect CTF progress to the exit

Choose the required number of completed challenges.

For example:

```text
Three CTFs exist
Two must be completed
```

When the requirement is reached:

* The server changes the match state
* The exit unlocks
* All living players are notified
* The Beast continues chasing
* Players must physically travel to the exit

Decide whether:

* The first escape ends the match, or
* The match continues until every living player escapes or dies

For the prototype, ending when the first player escapes is easier.

### Completion checkpoint

Completing enough CTFs unlocks the exit, but does not instantly win the game.

---

## 11. Add death, spectating, victory, and defeat

### When a player dies

* Disable their controls
* Remove them from Beast targeting
* Prevent flag submission
* Let them spectate living teammates

### Victory

The team wins when a living player reaches the unlocked exit.

### Defeat

The team loses when no living players remain.

### Match end

Show:

* Victory or defeat
* CTFs completed
* Players who escaped
* Players eliminated
* Restart button

### Completion checkpoint

The entire match can progress from lobby to either victory or defeat.

---

## 12. Connect and reset the CTF environments

The CTFs should begin each match in a known state.

Create a reset process that:

* Starts or restores each challenge
* Clears changes made by previous players
* Generates or assigns SSH access
* Confirms every challenge is available
* Stops or resets everything after the match

For the first version, resetting all challenges when the host restarts the game is acceptable.

Do not allow challenge environments to access sensitive files or unrestricted parts of the host machine.

---

## 13. Test systems separately

Test in this order:

### Movement test

* Player moves
* Walls work
* Computers can be interacted with
* Exit blocks the player

### Multiplayer test

* Players join
* Players see each other
* Disconnecting does not break the match

### Beast test

* Beast patrols
* Beast detects players
* Beast eliminates players
* Dead players are no longer targeted

### CTF test

* Every station shows the correct challenge
* Every challenge accepts SSH connections
* Correct flags are recognized
* Wrong flags are rejected

### Match test

* Required flags unlock the exit
* Living players can escape
* Everyone dying causes defeat
* Restart returns everything to its starting state

Only combine everything after each system works independently.

---

# Four-hour build order

## Hour 1: Foundation

* Create the client and server
* Build one map
* Add movement and collision
* Place computers and an exit
* Establish multiplayer connections

## Hour 2: Multiplayer and Beast

* Synchronize players
* Add match state
* Add Beast patrol and chasing
* Add permanent elimination

## Hour 3: CTF integration

* Associate stations with existing CTFs
* Display SSH information
* Add flag submission
* Add shared challenge progress

## Hour 4: Complete and test the loop

* Unlock the exit
* Add victory and defeat
* Add spectator behavior
* Add restarting
* Test with every team member
* Fix only game-breaking bugs

# Team task split

With four people:

| Person | Main responsibility                      |
| ------ | ---------------------------------------- |
| 1      | Map, movement, interaction, exit         |
| 2      | Multiplayer and match state              |
| 3      | Beast AI, chasing, elimination           |
| 4      | CTF connections, flag validation, resets |

With three people:

| Person | Main responsibility              |
| ------ | -------------------------------- |
| 1      | Client map and movement          |
| 2      | Server, multiplayer, match state |
| 3      | Beast AI and CTF integration     |

Integrate after each major checkpoint instead of waiting until the final hour.

# Final development order

```text
Map and movement
        ↓
Multiplayer
        ↓
Match-state system
        ↓
AI Beast
        ↓
Computer interactions
        ↓
CTF connections
        ↓
Flag validation
        ↓
Exit unlocking
        ↓
Victory and defeat
        ↓
CTF and match reset
        ↓
Full multiplayer testing
```

The most important target is not polish. It is completing one full playable match where players join, get hunted, solve existing CTFs through SSH, unlock the exit, and either escape or die.
