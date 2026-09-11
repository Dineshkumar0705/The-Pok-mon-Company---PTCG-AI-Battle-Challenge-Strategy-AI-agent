# Pokémon TCG AI Agent — v6: Expert Priors from Real Competitive Play

*Sep 10, 2026 · Extends `docs/v5-architecture.md`. Different kind of input
than v3–v5: those layers all came from this repo's own self-play data (real
engine, real games, real A/B results). v6 comes from external, cited
competitive-play sources instead — the deck's own mirror-match self-play
tooling structurally cannot produce the opponent this fix targets, so the
gap could only be found by research, not by measurement. See "Why this
couldn't be an A/B result" below.*

## What prompted this

The agent's heuristic layer (`scoring/option_scorer.py`, `threats/`) already
encodes a lot of hand-tuned, human-authored priors — every weight in
`score_option()` was a person's judgment call about this deck. What it
didn't yet have was a threat entry grounded in a *specific, verified,
external* competitive-play source, the same way `threats/crustle.py` and
`threats/alakazam_ex.py` encode real printed card text for cards this deck's
own dev/test loop happened to run into. v6 adds one: **Cornerstone Mask
Ogerpon ex**, this deck's real, named structural counter in the competitive
meta.

## Research grounding

- **Real decklist context** (`deck.csv`, this repo): the deck this agent
  plays is Duraludon/Archaludon ex/Relicanth with no poison support — a
  "pure wall" build leaning on `Full Metal Lab`'s -30 damage reduction to
  Metal Pokémon, `Hero's Cape`'s +100 HP, Archaludon ex's 300 HP and
  `Metal Defender`'s next-turn Weakness immunity, fueled by
  `Ultra Ball`/`Night Stretcher` discarding and recurring Basic Metal Energy
  for `Assemble Alloy` to reattach on evolution. This matches the deck
  archetype's real competitive pedigree: Limitless TCG's own tournament
  history for the Archaludon archetype shows **13 Regional Top 8 and 2
  International Top 8 finishes**, $50,750 in tracked prize money
  ([limitlesstcg.com/decks/315](https://limitlesstcg.com/decks/315),
  checked 2026-09-10) — a real, actively-played archetype, not a
  hypothetical build.
- **The structural weakness**: Deltia's Gaming's Archaludon ex deck guide
  ([deltiasgaming.com](https://deltiasgaming.com/pokemon-tcg-best-archaludon-ex-deck-guide/),
  checked 2026-09-10) names Cornerstone Mask Ogerpon ex specifically as what
  the deck is "weak to," describing it as shutting down most of the deck's
  Abilities.
- **The exact mechanism, verified against this project's own card-data
  table** (`data/raw/EN_Card_Data_canonical.csv`, card ID 117): Cornerstone
  Mask Ogerpon ex's Ability, Cornerstone Stance, reads "Prevent all damage
  from attacks done to this Pokémon by your opponent's Pokémon that have an
  Ability." That's a physical-attacker-has-an-Ability trigger, not a
  blanket lock — checked directly against the real printed text rather than
  taken on the secondary source's word alone, which matters here: the
  secondary source's "shuts down Abilities" phrasing could be misread as a
  full ability-lock (which would block nothing, since this deck's abilities
  are all utility, not damage sources); the real mechanism is narrower and
  more specific than that, and coding the wrong mechanism would have been
  worse than not coding one.

## What was actually built

In this deck, **Archaludon ex is the only physical attacker with an Ability
of its own** (Assemble Alloy). Duraludon has none. That holds even when
Archaludon ex throws a Duraludon attack borrowed via Relicanth's Memory Dive
(`attack_plans.py`) — Archaludon ex is still the physical attacker, so
Cornerstone Stance still blocks it. The correct real-play line into this
matchup is to lean on Duraludon as the active attacker, not to keep planning
(and losing tempo on) a guaranteed no-op Archaludon ex swing.

`src/pokemon_agent/threats/cornerstone_ogerpon.py` (new) encodes this the
same way `threats/crustle.py` encodes Mysterious Rock Inn:

- `is_blocked_by_cornerstone_stance(target_id, attacker_id)` — the
  guaranteed-no-op predicate.
- `cornerstone_ogerpon_switch_target_penalty(card_id)` — discourages
  spending a `Boss's Orders` to gust up the one card that walls this deck's
  main attacker for free, mirroring `crustle_switch_target_penalty` exactly.

Wired into two places, unconditionally (not behind `config/search_config.yaml`
— see "Why this ships unconditional" below):

- `scoring/damage.py::dyn_damage()` — zeroes the pairing, the same tier as
  the existing Crustle and Full Metal Lab terms.
- `attack_plans.py::build_attack_plan()` — skips the pairing entirely in the
  planner loop, so the agent never "plans" a no-op line and falls through to
  Duraludon if it's a viable attacker.
- `scoring/option_scorer.py` — adds the switch-target penalty next to the
  existing Crustle one in the `Boss's Orders`/forced-switch scoring branch.

## Why this ships unconditional, not behind a flag

v3–v5's search/belief/learning layers are *unvalidated until proven* —
genuinely new decision-making machinery that could be wrong in ways only a
real A/B result would catch, so they stay opt-in by design. This is a
different category: it corrects a place where the existing heuristic was
about to plan and execute a move the real printed card text guarantees does
zero damage. That's the same class of change as the original Crustle and
Alakazam ex fixes (`threats/crustle.py`, `threats/alakazam_ex.py`), both of
which are also unconditional, already-scored-path fixes, not opt-in
experiments. Leaving a known, source-verified zero-damage line in the
default planner would be a bug kept for consistency's sake, not a
conservative choice.

## Why this couldn't be an A/B result (stated honestly, not glossed over)

Every other real result in this repo (v4's search A/B, v5's learned-leaf A/B)
came from this project's self-play tooling, which mirrors this exact deck
against itself (`scripts/ab_test_search_vs_heuristic.py` and siblings both
seats build the same `deck.csv`). **Cornerstone Mask Ogerpon ex can never
appear as an opponent in that tooling** — it belongs to a different
archetype this repo has no decklist or scoring logic for, and building one
just to validate a single card interaction would mean writing and trusting
an entire second, independent agent implementation, which is disproportionate
and would introduce its own unverified assumptions. This is not a gap unique
to this fix: `replays/audit/` (where real, non-mirror battle data would need
to live to validate this kind of thing) is empty in this environment, the
same real constraint already named in `docs/v5-architecture.md` for Phase 3.

What *was* verified, honestly stated as a different (and appropriate) tier
of evidence than an A/B result:
1. The blocking mechanism is checked against this project's own real card
   data table, not asserted from the secondary source.
2. `tests/test_scoring.py` (4 new tests) and
   `tests/test_cornerstone_ogerpon_planning.py` (2 new tests) unit-test the
   damage-zeroing, the predicate, the switch-target penalty, and the
   planner's fall-through to Duraludon — all against mock fixtures, the same
   validation tier the original Crustle and Alakazam ex fixes used (neither
   has a real-game A/B result in this repo either, for the identical reason).
3. `tests/test_agent_matches_legacy.py` (the full v1-parity real-engine
   test) still passes — confirming this fix changes nothing about the
   default decision path for any game that doesn't involve this specific
   opponent card, which is the actual safety property that matters here.

## Test suite

81 tests total (up from v5's 76), all passing: +4 in `test_scoring.py`
(damage-zeroing for Archaludon ex vs. not-Duraludon, the predicate, the
switch-target penalty), +2 in the new
`tests/test_cornerstone_ogerpon_planning.py` (planner falls through to
Duraludon; planner finds nothing when only the blocked attacker is viable).
Every real-engine test in this repo (v1 through v6) still passes.

## Scoped out of this cycle, honestly

Other real cards surfaced during this research (e.g. Klefki's Memory Lock,
which locks a *specific* chosen attack rather than blocking by attacker
type) were not coded into a threat module — their relevance to this deck's
actual meta share wasn't independently confirmed the way Cornerstone Mask
Ogerpon ex's was (both a real printed-text mechanism check and a named
community source calling it out specifically), and this project's own rule
is not to add matchup logic on a guess. The Limitless Labs matchup table
found during research ([labs.limitlesstcg.com/0048/decks/archaludon-ex/matchups](https://labs.limitlesstcg.com/0048/decks/archaludon-ex/matchups),
checked 2026-09-10) showed real per-opponent win rates for one specific
tournament, but at n=1–3 games per matchup it's too small a sample to turn
into coded priors without overfitting to that one event — flagged here
rather than quietly used.
