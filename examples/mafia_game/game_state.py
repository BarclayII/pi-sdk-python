from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import ClassVar

from roles import (
    DETECTIVE_DESCRIPTION,
    DOCTOR_DESCRIPTION,
    GUARDIAN_DESCRIPTION,
    MAFIA_DESCRIPTION,
    VILLAGER_DESCRIPTION,
)


@dataclass
class GameState:
    """Tracks the state of a Mafia game."""

    players: list[str]  # All player names (directory names)
    alive: set[str] = field(default_factory=set)
    roles: dict[str, str] = field(
        default_factory=dict
    )  # name -> "villager"|"mafia"|"detective"|"doctor"|"guardian"
    round_id: int = 0
    mayor: str | None = None
    guardian_last_protected: str | None = None
    doctor_has_save: bool = True
    doctor_has_poison: bool = True
    eliminated: list[tuple[int, str, str]] = field(
        default_factory=list
    )  # (round, name, cause)
    data_dir: str = "./data"

    def __post_init__(self):
        if not self.alive:
            self.alive = set(self.players)

    def assign_roles(self) -> None:
        """Randomly assign roles: 1 detective, 1 guardian, 1 doctor, round(sqrt(n)/2) mafia (min 1), rest villagers."""
        n = len(self.players)
        num_mafia = max(1, round(math.sqrt(n) / 2))
        shuffled = list(self.players)
        random.shuffle(shuffled)

        self.roles = {}
        self.roles[shuffled[0]] = "detective"
        self.roles[shuffled[1]] = "guardian"
        self.roles[shuffled[2]] = "doctor"
        for i in range(3, 3 + num_mafia):
            self.roles[shuffled[i]] = "mafia"
        for i in range(3 + num_mafia, n):
            self.roles[shuffled[i]] = "villager"

    ROLE_DESCRIPTIONS: ClassVar[dict[str, str]] = {
        "villager": VILLAGER_DESCRIPTION,
        "mafia": MAFIA_DESCRIPTION,
        "detective": DETECTIVE_DESCRIPTION,
        "guardian": GUARDIAN_DESCRIPTION,
        "doctor": DOCTOR_DESCRIPTION,
    }

    def get_role_description(self, name: str) -> str:
        """Get the role description text for a player."""
        role = self.roles[name]
        return self.ROLE_DESCRIPTIONS[role]

    def get_by_role(self, role: str) -> list[str]:
        """Get alive players with a given role."""
        return [p for p in self.alive if self.roles.get(p) == role]

    def eliminate(self, name: str, cause: str) -> None:
        """Remove a player from the game."""
        self.alive.discard(name)
        self.eliminated.append((self.round_id, name, cause))

    def check_win(self) -> str | None:
        """Check win condition. Returns 'village', 'mafia', or None."""
        mafia_alive = sum(1 for p in self.alive if self.roles[p] == "mafia")
        non_mafia_alive = len(self.alive) - mafia_alive
        if mafia_alive == 0:
            return "village"
        if mafia_alive >= non_mafia_alive:
            return "mafia"
        return None
