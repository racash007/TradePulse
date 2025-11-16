from enum import StrEnum


class OutcomeType(StrEnum):
    NO_HIT = "no_hit"
    WIN = "win"
    LOSS = "loss"
    EXIT = "exit"