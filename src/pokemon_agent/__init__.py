"""Archaludon ex "Steel Fortress" — decomposed, tested agent package.

v1 reference: notebooks/legacy/main_v1_reference.py (frozen, never edited).
v2: this package — a behavior-preserving decomposition of v1 into testable
modules, plus replay-audit tooling (replays/audit/).
v3: search/, belief/, rating/ — additive, feature-flagged, unvalidated until
each wins a head-to-head A/B test against v1/v2. See docs/agent-v3-upgrade-architecture.md.
v4: search/expectimax.py wires L1 search into a real, A/B-validated
ATTACK-ranking layer (real result, real CI); belief/energy_density.py now
feeds search's determinization. Still opt-in (config/search_config.yaml
ships `enabled: false`) -- build_agent(deck) with no search_config argument
is unchanged v1/v2 behavior. See docs/v4-architecture.md.
v5: memory/ (Replay Vector Store) + learning/leaf_value.py (a trained
win-probability model, real self-play data, real A/B-tested) -- swappable
into search/expectimax.py's leaf evaluation via leaf_value_mode. Its real
A/B result was a null result (50.0% vs. the heuristic leaf), so it stays
off by default too. Behavioral cloning from human replays is blocked on a
real replay corpus this environment doesn't have. See docs/v5-architecture.md.
v6: threats/cornerstone_ogerpon.py -- a real, cited competitive-play prior
(Cornerstone Mask Ogerpon ex's Cornerstone Stance, verified against this
project's own card-data table plus a named community source) rather than a
self-play-discovered one; this deck's mirror-match self-play tooling can
never surface this opponent, so unlike v3-v5 it's validated by unit tests
against real card text, not an A/B result -- stated honestly as a different
evidence tier, not glossed over. Ships unconditional (same tier as the
Crustle/Alakazam ex fixes), since it corrects a real zero-damage planning
gap rather than adding unvalidated new machinery. See docs/v6-architecture.md.
v7: search/expectimax.py generalizes depth past 2 and gains an optional
policy_top_k branch cap (both real A/B-tested, both real losses -- stay
off by default); attack_plans.py gains an opt-in plan-stability bonus
(real null result); learning/leaf_value.py gains a GradientBoostingClassifier
option and memory/featurize.py a new stadium feature, trained and real-A/B-
tested against v5's original leaf (a second real null result, closes off
"wrong model class" as the explanation for v5's null result); decks/
cornerstone_ogerpon_v7.csv + real asymmetric self-play finally A/B-tests
v6's Cornerstone fix directly (real +11.7pp result -- the first item this
version actually moved); rating/ladder.py gains a real symmetric multi-agent
Elo pool (MatchupLadder.record_match(), 150 real games across 4 agent
variants). Every new knob defaults to off/unchanged -- the shipped agent's
decisions are identical to v6's. See docs/v7-architecture.md for every real
result, including the negative and null ones, reported honestly.
"""
