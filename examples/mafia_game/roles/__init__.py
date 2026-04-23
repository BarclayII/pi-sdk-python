"""Role definitions for the Mafia game."""

from roles.detective import (
    INVESTIGATE_SCHEMA,
    ROLE_DESCRIPTION as DETECTIVE_DESCRIPTION,
    detective_prompt,
    get_role_description as get_detective_description,
)
from roles.doctor import (
    DOCTOR_ACTION_SCHEMA,
    ROLE_DESCRIPTION as DOCTOR_DESCRIPTION,
    doctor_prompt,
    get_role_description as get_doctor_description,
)
from roles.guardian import (
    PROTECT_SCHEMA,
    ROLE_DESCRIPTION as GUARDIAN_DESCRIPTION,
    guardian_prompt,
    get_role_description as get_guardian_description,
)
from roles.mafia import (
    ROLE_DESCRIPTION as MAFIA_DESCRIPTION,
    get_role_description as get_mafia_description,
)
from roles.villager import (
    ROLE_DESCRIPTION as VILLAGER_DESCRIPTION,
    get_role_description as get_villager_description,
)

# Language-aware role description getters keyed by role name
ROLE_DESCRIPTION_GETTERS = {
    "villager": get_villager_description,
    "mafia": get_mafia_description,
    "detective": get_detective_description,
    "guardian": get_guardian_description,
    "doctor": get_doctor_description,
}

__all__ = [
    "DETECTIVE_DESCRIPTION",
    "DOCTOR_DESCRIPTION",
    "GUARDIAN_DESCRIPTION",
    "MAFIA_DESCRIPTION",
    "VILLAGER_DESCRIPTION",
    "ROLE_DESCRIPTION_GETTERS",
    "INVESTIGATE_SCHEMA",
    "PROTECT_SCHEMA",
    "DOCTOR_ACTION_SCHEMA",
    "detective_prompt",
    "guardian_prompt",
    "doctor_prompt",
]
