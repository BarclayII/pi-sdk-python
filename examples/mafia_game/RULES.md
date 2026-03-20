# Mafia Game Rules

## Roles

- **Villager** — No special abilities. Identify and eliminate Mafia through daily votes.
- **Mafia** — Meets at night to choose a victim. Blends in during the day.
- **Detective** — Investigates one player each night to learn if they are Mafia.
- **Guardian** — Protects one player per night from being killed. Cannot protect self. Cannot protect the same person on consecutive nights.
- **Doctor** — After seeing who the Mafia killed, may use a one-time **Save** (revive the killed player) and/or a one-time **Poison** (immediately kill another player). Each ability can only be used once per game.

### Role Distribution

| Role      | Count                    |
| --------- | ------------------------ |
| Detective | 1                        |
| Guardian  | 1                        |
| Doctor    | 1                        |
| Mafia     | round(√n / 2), minimum 1 |
| Villager  | Remaining players        |

Minimum 5 players required.

## Game Phases (per round)

### 0. Mayor Election (Day 0 only)

Before the first night, all players elect a **Mayor**:

1. **Discussion** — Players discuss who should be Mayor (~15 speaking rounds).
2. **Vote** — Each player votes for any player (including themselves). Simple plurality wins; ties are broken randomly.

The Mayor has three special privileges:

- **Speaks first** in every day meeting.
- **Double vote** — their elimination vote counts as two votes.
- **Succession** — if the Mayor dies (killed, poisoned, or voted out), they appoint a surviving player as the new Mayor before leaving the game.

### 1. Night Phase

Actions happen in this order:

1. **Detective** (if alive) investigates one living player and learns their alignment.
2. **Mafia** discusses and votes on a kill target.
   - Single Mafia: chooses directly.
   - Multiple Mafia: discussion then vote; ties mean no consensus (no kill).
   - Can target anyone alive, including fellow Mafia.
3. **Doctor** (if alive and has remaining abilities) is told who the Mafia killed, then decides:
   - **Save** (one-time): revive the killed player.
   - **Poison** (one-time): immediately kill another player.
   - Both can be used in the same night if still available.
4. **Guardian** (if alive) chooses one player to protect.
5. **Resolution**:
   - If the Doctor saved the Mafia's target, the target survives (regardless of Guardian).
   - If the Guardian protected the Mafia's target (and Doctor didn't save), the target survives.
   - If the Doctor poisoned someone, that player also dies (announced alongside any Mafia kill in the day phase).

### 2. Day Phase

1. **Death announcement** — All players learn who died (if anyone) and their role. This includes both Mafia kills and poison kills.
2. **Discussion meeting** — All alive players discuss suspicions.
   - Facilitator uses weighted speaker selection (favoring those who haven't spoken recently or were just mentioned).
   - Players speak in 2–4 sentence turns.
3. **Elimination vote** — All alive players vote to eliminate one player or abstain.
   - Requires **strict majority (>50% of alive players)** to eliminate.
   - If no majority is reached, no one is eliminated.
   - Players cannot vote for themselves.

### 3. Diary Phase

All players (alive and dead) write reflections:

- `DIARY_<round>.txt` — Summary, thoughts, strategy.
- `KNOWLEDGE_<player>.txt` — Observations about each other alive player.

## Win Conditions

- **Village wins** — All Mafia members are eliminated.
- **Mafia wins** — Mafia members ≥ non-Mafia players (parity or majority).

Checked after night resolution and after day elimination.

## Information Rules

| Who       | Sees                                                                 |
| --------- | -------------------------------------------------------------------- |
| Everyone  | Who is alive, who died and their role, day transcripts, vote results |
| Mafia     | Mafia meeting transcript, identities of fellow Mafia                 |
| Detective | Own investigation results only                                       |
| Guardian  | Own protection notes only                                            |
| Doctor    | Who Mafia killed, own save/poison action notes only                  |

## Other Rules

- Roles are fixed once assigned.
- Dead players cannot participate in day meetings or votes.
- Players must speak in first person (third-person self-references are rejected).
- Guardian protection is voided if the target is invalid (self, same as previous night, or dead).
- Doctor's Save and Poison are each one-time use for the entire game.
