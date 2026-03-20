"""Role definitions for the Mafia game."""

from roles.detective import (
    INVESTIGATE_SCHEMA,
    ROLE_DESCRIPTION as DETECTIVE_DESCRIPTION,
    detective_prompt,
)
from roles.doctor import (
    DOCTOR_ACTION_SCHEMA,
    ROLE_DESCRIPTION as DOCTOR_DESCRIPTION,
    doctor_prompt,
)
from roles.guardian import (
    PROTECT_SCHEMA,
    ROLE_DESCRIPTION as GUARDIAN_DESCRIPTION,
    guardian_prompt,
)
from roles.mafia import ROLE_DESCRIPTION as MAFIA_DESCRIPTION
from roles.villager import ROLE_DESCRIPTION as VILLAGER_DESCRIPTION

__all__ = [
    "DETECTIVE_DESCRIPTION",
    "DOCTOR_DESCRIPTION",
    "GUARDIAN_DESCRIPTION",
    "MAFIA_DESCRIPTION",
    "VILLAGER_DESCRIPTION",
    "INVESTIGATE_SCHEMA",
    "PROTECT_SCHEMA",
    "DOCTOR_ACTION_SCHEMA",
    "detective_prompt",
    "guardian_prompt",
    "doctor_prompt",
]
