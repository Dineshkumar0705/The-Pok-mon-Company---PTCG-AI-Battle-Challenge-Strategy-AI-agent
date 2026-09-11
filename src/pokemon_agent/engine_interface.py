"""Observation/area helpers — ported verbatim from v1 main.py's get_card()."""
from __future__ import annotations


def get_card(obs, area, area_type, index, player_index):
    """Resolve a (area, index, player_index) reference to the actual card object.

    `area_type` is the AreaType enum module (mock_engine.AreaType or the real
    cg.api.AreaType) so this function works against either without importing
    a concrete engine.
    """
    ps = obs.current.players[player_index]
    if area == area_type.DECK:
        return obs.select.deck[index]
    if area == area_type.HAND:
        return ps.hand[index]
    if area == area_type.DISCARD:
        return ps.discard[index]
    if area == area_type.ACTIVE:
        return ps.active[index]
    if area == area_type.BENCH:
        return ps.bench[index]
    if area == area_type.PRIZE:
        return ps.prize[index]
    if area == area_type.STADIUM:
        return obs.current.stadium[index]
    if area == area_type.LOOKING:
        return obs.current.looking[index]
    return None
