"""Bellibolt ex (269) line — pre-evolution snipe priority.

Finding: Bellibolt ex itself is a 280 HP wall, but its pre-evolutions
(Iono's Tadbulb 268, Iono's Wattrel 270) are cheap, 60 HP setup pieces.
Sniping either on the bench before it evolves denies the whole Electric
Streamer engine from ever coming online. Adds a kill-priority bonus so the
agent takes a "small" free knockout over passing on it.
"""

Bellibolt_ex = 269
Iono_Tadbulb = 268
Iono_Wattrel = 270
BELLIBOLT_SNIPE_IDS = {Iono_Tadbulb, Iono_Wattrel}
SNIPE_PRIORITY_BONUS = 500


def bellibolt_snipe_bonus(target_pokemon_id: int) -> int:
    return SNIPE_PRIORITY_BONUS if target_pokemon_id in BELLIBOLT_SNIPE_IDS else 0
