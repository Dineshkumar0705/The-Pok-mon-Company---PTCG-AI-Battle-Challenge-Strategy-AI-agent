"""Card/attack table loading — live engine when available, cleaned CSV dataset otherwise.

v1's main.py always called `cg.api.all_card_data()` / `all_attack()`, which only
exist inside a real competition episode. That's fine for the scored agent, but
it means nothing could be tested or analyzed offline. This module keeps the
engine path as the default and adds a second, real path: build an equivalent
lookup straight from the cleaned reference dataset (data/raw/), which this
project already produced and verified (see data/raw/DATA_QUALITY_REPORT.md).

Honesty about the CSV path's limits (don't skip this when using it):
- It reconstructs per-card HP/type/weakness/resistance/retreat and each
  move's name/cost/damage/effect text reliably — the columns are literal.
- It does NOT reproduce the live engine's internal integer `attackId` numbering
  scheme (attack_table.png), because that numbering is assigned at runtime by
  `cg` and isn't present in the dataset. Anything keyed by attackId in v1's
  main.py (e.g. `attack_table[aid].damage`) cannot be faithfully replayed from
  the CSV alone — this loader exposes attacks by (card_id, move_name) instead.

v7 dataset-upgrade fix, two real bugs found and closed together:
1. **A real attribute-name mismatch, not just an accuracy gap.**
   `attack_plans.py`'s live decision code reads `getattr(mdata, "ex", False)`
   and `getattr(mdata, "megaEx", False)` — the real engine `CardData`
   dataclass's own attribute names. `CardRecord` here only ever exposed
   `is_ex`/`is_mega_ex` as *properties* (different names entirely), so in
   CSV-only fallback mode those `getattr()` calls always silently returned
   the default `False`, for every card, regardless of the heuristic below —
   including this deck's own Archaludon ex. That made the CSV-fallback
   path's ex-detection structurally inert, not just approximate; the live
   engine path (`source="engine"`, what an actual scored submission uses)
   was never affected, since real `CardData` objects always had real `.ex`/
   `.megaEx` fields.
2. **The heuristics themselves, now cross-validated against real engine
   ground truth** (`scripts/build_engine_enriched_dataset.py`,
   `data/raw/DATASET_UPGRADE_REPORT.md`): the old `"ex" in rule.lower()`
   heuristic was wrong for all 30 real Mega Evolution Pokémon ex cards in
   this dataset (e.g. "Mega Lucario ex" — real TCG rules keep `ex` and
   `megaEx` as separate flags with separate prize-card counts, but the
   heuristic's substring match can't tell them apart); the `"mega" in
   name.lower()` heuristic was wrong for 4 real non-Mega cards whose name
   merely starts with "Mega" (e.g. "Meganium", "Megaton Blower").

Fixed by giving `CardRecord` real `ex`/`megaEx`/`tera`/`aceSpec`/
`evolvesFrom` fields (matching the engine's own attribute names) and, when
`data/raw/cards_enriched.csv` exists (built by
`scripts/build_engine_enriched_dataset.py` from real, cross-validated
engine ground truth), populating them from THAT instead of a heuristic —
real data, not a better guess. When the enriched file is absent,
`load_card_records()` falls back to the exact same two heuristics as
before (never worse than the prior behavior, and `tera`/`aceSpec` simply
default `False` in that case, same as their total absence before this
fix). `is_ex`/`is_mega_ex` remain as properties, now just aliasing the
real fields, for anything still reading the old names.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_EN_CSV = Path(__file__).resolve().parents[2] / "data" / "raw" / "EN_Card_Data_canonical.csv"
DEFAULT_ENRICHED_CSV = Path(__file__).resolve().parents[2] / "data" / "raw" / "cards_enriched.csv"


@dataclass
class MoveRecord:
    name: str
    cost: str
    damage: str
    effect: str

    @property
    def energy_cost_count(self) -> int:
        """Number of energy symbols in `cost` (e.g. '{L}{L}{P}' -> 3, '●●' -> 2)."""
        if not self.cost or self.cost == "n/a":
            return 0
        # Cost is written either as {X}{Y}... tokens or as repeated '●' (colorless-count shorthand).
        brace_count = self.cost.count("{")
        if brace_count:
            return brace_count
        return len(self.cost.strip())


@dataclass
class CardRecord:
    card_id: int
    name: str
    expansion: str
    stage: str
    rule: str
    category: str
    hp: Optional[int]
    type_: str
    weakness: str
    resistance: str
    retreat: Optional[int]
    moves: list = field(default_factory=list)  # list[MoveRecord]
    # v7: real fields (matching the live engine CardData's own attribute
    # names -- see this module's docstring for the real bug this fixes).
    # Populated from data/raw/cards_enriched.csv's engine ground truth when
    # that file exists; otherwise from the same two heuristics this module
    # always used (ex/megaEx only -- tera/aceSpec have no prior heuristic
    # and stay False, same as their total absence before this field existed).
    ex: bool = False
    megaEx: bool = False
    tera: bool = False
    aceSpec: bool = False
    evolvesFrom: Optional[str] = None

    @property
    def is_ex(self) -> bool:
        return self.ex

    @property
    def is_mega_ex(self) -> bool:
        return self.megaEx


def _load_enriched_flags(enriched_csv_path: Optional[Path]) -> dict[int, dict]:
    """Real engine-ground-truth ex/megaEx/tera/aceSpec/evolvesFrom per card
    id, from data/raw/cards_enriched.csv (scripts/build_engine_enriched_dataset.py).
    Returns {} (never raises) if the file is missing or unreadable -- a
    missing enriched file must fall back to the old heuristic path exactly,
    never crash `load_card_records()`."""
    if enriched_csv_path is None or not Path(enriched_csv_path).exists():
        return {}
    out: dict[int, dict] = {}
    try:
        with open(enriched_csv_path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    cid = int(row["card_id"])
                except (KeyError, ValueError):
                    continue

                def _bool(v):
                    return str(v).strip().lower() == "true"

                out[cid] = {
                    "ex": _bool(row.get("is_ex")),
                    "megaEx": _bool(row.get("is_mega_ex")),
                    "tera": _bool(row.get("is_tera")),
                    "aceSpec": _bool(row.get("is_ace_spec")),
                    "evolvesFrom": (row.get("evolves_from") or "") or None,
                }
    except Exception:  # noqa: BLE001 -- fail closed to "no enrichment available"
        return {}
    return out


def load_card_records(csv_path: Path = DEFAULT_EN_CSV,
                       enriched_csv_path: Optional[Path] = DEFAULT_ENRICHED_CSV) -> dict[int, CardRecord]:
    """Load the cleaned EN CSV into one CardRecord per unique Card ID, moves
    aggregated. `enriched_csv_path` (default: data/raw/cards_enriched.csv,
    if it exists) supplies real engine ground truth for ex/megaEx/tera/
    aceSpec/evolvesFrom instead of the old text heuristics -- pass `None` to
    force the pre-v7 heuristic-only behavior exactly."""
    enriched = _load_enriched_flags(enriched_csv_path)
    records: dict[int, CardRecord] = {}
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cid = int(row["Card ID"])
            except (KeyError, ValueError):
                continue
            if cid not in records:
                def _int_or_none(v):
                    v = (v or "").strip()
                    return int(v) if v.isdigit() else None

                rule = row.get("Rule", "")
                name = row.get("Card Name", "")
                enriched_row = enriched.get(cid)
                if enriched_row is not None:
                    ex = enriched_row["ex"]
                    mega_ex = enriched_row["megaEx"]
                    tera = enriched_row["tera"]
                    ace_spec = enriched_row["aceSpec"]
                    evolves_from = enriched_row["evolvesFrom"]
                else:
                    # Pre-v7 heuristic fallback, unchanged.
                    ex = "ex" in (rule or "").lower()
                    mega_ex = "mega" in (name or "").lower()
                    tera = False
                    ace_spec = False
                    evolves_from = None

                records[cid] = CardRecord(
                    card_id=cid,
                    name=name,
                    expansion=row.get("Expansion", ""),
                    stage=row.get("Stage (Pokémon)/Type (Energy and Trainer)", ""),
                    rule=rule,
                    category=row.get("Category", ""),
                    hp=_int_or_none(row.get("HP", "")),
                    type_=row.get("Type", ""),
                    weakness=row.get("Weakness", ""),
                    resistance=row.get("Resistance (Type)", ""),
                    retreat=_int_or_none(row.get("Retreat", "")),
                    ex=ex, megaEx=mega_ex, tera=tera, aceSpec=ace_spec, evolvesFrom=evolves_from,
                )
            move_name = row.get("Move Name", "")
            if move_name and move_name != "n/a":
                records[cid].moves.append(
                    MoveRecord(
                        name=move_name,
                        cost=row.get("Cost", ""),
                        damage=row.get("Damage", ""),
                        effect=row.get("Effect Explanation", ""),
                    )
                )
    return records


def load_card_table(prefer_engine: bool = True, csv_path: Path = DEFAULT_EN_CSV):
    """Return (card_table, attack_table, source) using the live engine if present, else the CSV.

    `source` is "engine" or "csv" — callers that need engine-exact attackId
    semantics (v1's main.py logic, ported into scoring/) MUST check this and
    refuse to run in "csv" mode; callers doing offline analysis (v3's belief
    module, tests, the replay auditor) are fine with either.
    """
    if prefer_engine:
        try:
            from cg.api import all_card_data, all_attack  # type: ignore

            all_card = all_card_data()
            all_atk = all_attack()
            card_table = {c.cardId: c for c in all_card}
            attack_table = {a.attackId: a for a in all_atk}
            return card_table, attack_table, "engine"
        except ImportError:
            pass
    card_table = load_card_records(csv_path)
    return card_table, None, "csv"
