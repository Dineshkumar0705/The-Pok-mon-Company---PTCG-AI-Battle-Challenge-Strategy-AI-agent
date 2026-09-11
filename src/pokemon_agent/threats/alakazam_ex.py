"""Alakazam ex (743) — Powerful Hand.

Finding: Powerful Hand's damage is handCount * 20, not a fixed number. The
static attack table stores 0/placeholder damage for hand-scaling attacks, so
opp_incoming_damage() would silently under-count it and the agent could walk
into a hit it should have retreated from. Fixed by computing the damage
explicitly from the opponent's hand size wherever this card ID is the
opponent's active Pokemon.
"""

Alakazam_PowerfulHand = 743
HAND_SCALING_DAMAGE_PER_CARD = 20


def powerful_hand_damage(op_hand_count: int) -> int:
    return op_hand_count * HAND_SCALING_DAMAGE_PER_CARD
