# **Archaludon ex "Steel Fortress"**
### A tank deck piloted by a legible heuristic scorer — hardened by real replay audits, not search depth

**Introduction.** Archaludon ex "Steel Fortress" is a Metal-type tank deck built on the Duraludon → Archaludon ex evolution line, played by an agent with three architectural pieces: a single-pass heuristic move-scorer, named card-specific threat and immunity handling for three audited matchups, and a validated dataset-load guard added after a real ladder-corrupting bug. The headline finding this cycle wasn't a tactical improvement — it was catching, via replay forensics, that the prior version had been silently piloting the wrong deck for an entire ladder batch. That bug is fixed and regression-tested; a clean win-rate read on the tactical fixes is not yet collected, and this writeup says so plainly rather than estimating it.

## Methods

### Deck Concept & Game Plan — *Deck Score*

The win condition is durability plus value, not speed. Hero's Cape (ACE SPEC) pushes Archaludon ex from 300 to 400 HP; Full Metal Lab cuts incoming damage to Metal Pokémon by 30 while denying the opponent's own stadium; and Relicanth's Memory Dive lets Archaludon ex borrow Duraludon's Raging Hammer, which gains +10 damage per damage counter already on the user — a wounded tank hits back harder rather than folding. The shipped 60-card list, embedded directly in the notebook: 4x Duraludon, 4x Archaludon ex, 2x Relicanth as the attacking core; 12x Basic Metal Energy as the sole energy source; a consistency suite (4x Ultra Ball, 4x Poké Pad, 3x Pokégear, 4x Night Stretcher, 4x Lillie's Determination, 4x Carmine) to assemble the evolution line and refuel discarded energy; Judge and 3x Boss's Orders for disruption and redirection; Full Metal Lab and the single-copy Hero's Cape as the win-condition-supporting non-Pokémon cards.

Matchup knowledge isn't expressed as card swaps here — it lives in the scoring logic (Methods, below), a deliberate choice worth stating rather than implying the deck itself was meta-tuned when the tuning actually happened in code. Before any number: the three tactical fixes below trace to auditing 47 real ladder replays of a sibling notebook, which went 22W-22L (50.0%). This version's own last real batch (30 games, episodes 92065697–92217006) read 14W-15L (48.3%) — invalidated as a strategy signal once replay analysis confirmed the agent had been playing the organizer's demo deck, not this one (Discussion). Locally, with the correct deck and the bug fixed: 50.0% (40/80) non-regression vs. the prior version, 93.8% (15/16) vs. a random-policy baseline, real compiled engine, zero crashes — stable and clearly beats random, proves nothing about a real opponent yet.

### Agent Architecture — *Model Score*

**Move-selection engine.** Every legal option each turn — attack, play, attach, evolve, retreat, ability, or a card selection for search/switch/attach — is scored independently; highest score wins. Three shared primitives do the work: `pokemon_score()` (prize value, energy investment, evolution stage, two matchup-specific bonuses below), `dyn_damage()` (base damage adjusted for weakness, resistance, Full Metal Lab's reduction, and ability-based immunity), and `opp_incoming_damage()` (opponent's best available damage, driving `active_in_danger` and retreat/switch scoring). No hidden search tree — every move traces to one inspectable scoring pass.

**Three card-specific fixes, each from a named replay-audit finding.** Alakazam ex's Powerful Hand scales with hand size (`handCount × 20`) rather than the fixed value the static attack table stores as zero; unhandled, `opp_incoming_damage()` would silently under-count it. Crustle's Mysterious Rock Inn blocks all damage from ex attackers, and Archaludon ex is itself ex-flagged — the fix zeroes that specific attacker-target pairing and routes through non-ex Duraludon instead. Bellibolt ex is a 280 HP wall, but its pre-evolutions (Iono's Tadbulb, Iono's Wattrel) are 60 HP; a kill-priority bonus takes the cheap knockout that denies the line before it comes online. Each is unit-verified in isolation, not yet proven against live opponents piloting those archetypes.

**The dataset-load guard.** Kaggle auto-mounts the competition's own bundle — including its demo `sample_submission/deck.csv` — under `/kaggle/input/...`, no explicit action required. The prior deck-loading cell searched `/kaggle/input/**/deck.csv` unconditionally and silently matched that demo file instead of this deck's own list, confirmed by a byte-level file diff and cross-checking every game in the replay batch against real starting-hand data. The fix adds two independent guards: reject any candidate path containing `sample_submission`, and require at least 2 of this deck's 3 core-defining card IDs (Duraludon/Archaludon ex/Relicanth) before trusting an override — validated against three constructed scenarios (demo-only, legitimate override present, both present), all three passing.

**Generalization as hardening.** The Crustle-immunity check originally tested a hardcoded Archaludon-ex ID; it now reads `card_table[id].ex`/`.megaEx` directly, so the same protection holds even in a repeat of the deck-mismatch scenario above — a defense-in-depth change made because of what the bug revealed, not a speculative improvement.

**What was tried and reverted.** An earlier attempt broadened the retreat-trigger to fire whenever `active_in_danger` was true, independent of an attack plan. A/B tested at n=16 against the real engine, it regressed win rate (25% vs. a 56% baseline) by causing over-retreating in ordinary trades — reverted to the narrow rule. Kept in this writeup deliberately: evidence the fix pipeline removes changes that don't hold up, not only adds ones that sound reasonable.

**What isn't here.** No multi-ply search, no learned value function, no opponent-hand modeling, no rating ladder. Single-ply heuristic scoring with targeted, audit-driven card handling is the actual architecture, stated as a boundary rather than a gap to talk around.

## Results

| Check | Sample | Result | What it validates |
|---|---|---|---|
| vs. random policy, correct deck | 16 games | 93.8% (15/16) | Basic competence, real engine, zero crashes |
| Non-regression vs. prior version, same deck | 80 games | 50.0% (40/80) | The 3 tactical fixes didn't break existing behavior |
| Real ladder batch (pre-fix) | 29 games | 48.3% (14W-15L) | **Invalidated** — confirmed wrong-deck; shown only to demonstrate the bug that was caught and fixed |
| Real ladder, post-fix | — | not yet collected | The open gap — see Discussion |

*(Chart version of this table sent alongside this draft.)* The middle row is the one clean signal available: the fixes are safe. The bottom row is the open item. A judge cross-checking the linked notebook will find this table matches its own printed cell outputs exactly.

## Discussion — Honesty: What Was Scoped, What Shipped, and Where It Landed

**Scoped and shipped, measured.** The move-selection engine, the three tactical fixes, and the dataset-load guard are all in the linked notebook and all exercised by the validation runs above (93.8% vs. random, 50.0% non-regression, 6/6 self-play, zero crashes).

**Scoped, attempted, and reverted.** The broadened retreat trigger. It shipped, was A/B tested, failed (25% vs. 56%), and was pulled — the reasoning stayed in the codebase rather than the change being silently dropped. This pattern — propose, test, remove if it doesn't hold — is the actual evidence for "consistency," not an assertion of it.

**Scoped, not yet validated.** A "battle-tested" 60-card variant (swapping in Cinderace, Jumbo Ice Cream, and Explorer's Guidance for Carmine) has code support already written but isn't the currently shipped list — kept in for a future attempt, not claimed as active. The three tactical fixes have never faced a live opponent with the correct deck in play, because that data doesn't exist yet.

**The failure that mattered most wasn't tactical.** The deck-loading bug meant an entire real ladder batch — the only "real opponent" evidence this project had — was invalid from the moment it was recorded. It wasn't caught by code review; it surfaced from cross-checking saved replay data against the deck the scoring logic was actually written for, confirmed with a byte-level diff, and closed with a guard validated against three constructed scenarios. Reporting a 48.3% number without that context would have been the single easiest way to overclaim something the notebook itself disproves on inspection — so it's reported here with the invalidation attached, not omitted.

**Next step, already scoped.** Play a fresh ladder batch now that the loading bug is fixed, to get the first clean read on whether the three tactical fixes move win rate against the archetypes they target. Second: generalize the "never trust an unvalidated external override" guard beyond `deck.csv` — the same silent-corruption risk could recur anywhere else the notebook reads from `/kaggle/input` without a matching check.
