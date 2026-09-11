"""Loads config/search_config.yaml into an ExpectimaxConfig -- keeps the
feature flag, search depth, and cache size as data the repo ships, not
constants buried in agent.py. Missing file or missing keys fall back to
ExpectimaxConfig()'s own defaults (enabled=False, depth=0), which is the
same as v1/v2 behavior -- a missing/corrupt config file can never silently
turn search ON.

v7 wiring fix: `ExpectimaxConfig.policy_top_k` was added in v7 but this
loader never read it from the yaml -- a real gap found during the v7
deploy check (every OTHER field added since v4 has always been threaded
through here; this one was missed when it was added). Setting
`policy_top_k` in config/search_config.yaml would have silently done
nothing. Fixed here; `None` (the shipped yaml's value) is still the
inert v4/v5/v6-identical default.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .expectimax import ExpectimaxConfig

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "search_config.yaml"


def load_search_config(path: Optional[Path] = None) -> ExpectimaxConfig:
    path = path or DEFAULT_CONFIG_PATH
    try:
        import yaml
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except Exception:
        return ExpectimaxConfig()

    s = raw.get("search", {}) or {}
    defaults = ExpectimaxConfig()
    leaf_value_model_path = s.get("leaf_value_model_path", defaults.leaf_value_model_path)
    if leaf_value_model_path:
        # Resolve relative to the repo root (config/search_config.yaml's own
        # directory's parent), not the caller's cwd, so `build_agent(deck)`
        # works the same from any working directory.
        candidate = Path(leaf_value_model_path)
        if not candidate.is_absolute():
            leaf_value_model_path = str(DEFAULT_CONFIG_PATH.parent.parent / candidate)
    return ExpectimaxConfig(
        enabled=bool(s.get("enabled", defaults.enabled)),
        depth=int(s.get("depth", defaults.depth)),
        max_branch_steps=int(s.get("max_branch_steps", defaults.max_branch_steps)),
        transposition_table_size=int(s.get("transposition_table_size", defaults.transposition_table_size)),
        belief_informed_determinization=bool(
            s.get("belief_informed_determinization", defaults.belief_informed_determinization)
        ),
        leaf_value_mode=str(s.get("leaf_value_mode", defaults.leaf_value_mode)),
        leaf_value_model_path=leaf_value_model_path,
        policy_top_k=(
            int(s["policy_top_k"])
            if s.get("policy_top_k") is not None
            else defaults.policy_top_k
        ),
    )
