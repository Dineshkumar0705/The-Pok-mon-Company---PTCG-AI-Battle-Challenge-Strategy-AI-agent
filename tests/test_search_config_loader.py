"""Guards the actual shipped config/search_config.yaml, not just the loader
code: build_agent(deck) with no search_config argument -- what a real
submission entrypoint calls -- must resolve to search DISABLED, because
that's what the shipped yaml says right now. If someone edits the yaml to
`enabled: true` without updating this test, this is the test that should
force them to notice and make that a deliberate, visible decision (see the
yaml's own comment on why it stays false).

Also covers the fail-closed guarantee directly: a missing or corrupt config
path must load ExpectimaxConfig()'s inert defaults, never raise, and never
turn search on by accident.
"""
from __future__ import annotations

from pokemon_agent.search.config_loader import load_search_config, DEFAULT_CONFIG_PATH
from pokemon_agent.search.expectimax import ExpectimaxConfig


def test_shipped_config_file_exists():
    assert DEFAULT_CONFIG_PATH.exists(), (
        "config/search_config.yaml is missing -- load_search_config() will "
        "still fail closed (enabled=False), but that's not the intended "
        "state for this repo's checked-in config."
    )


def test_shipped_config_loads_with_search_disabled_by_default():
    config = load_search_config()
    assert isinstance(config, ExpectimaxConfig)
    assert config.enabled is False, (
        "config/search_config.yaml's `enabled` flag changed -- this is the "
        "one test that should catch a scored submission entrypoint silently "
        "picking up search-enabled behavior. If this was deliberate, update "
        "this test alongside the yaml change, not instead of it."
    )
    # The recommended (A/B-validated) depth still ships as data even while disabled.
    assert config.depth == 2
    # v5: leaf_value_mode stays "heuristic" -- the learned leaf's real A/B
    # result was a null result (50.0% at both depth 1 and depth 2), not a
    # win, so it never becomes the default. See docs/v5-architecture.md.
    assert config.leaf_value_mode == "heuristic"
    # v7: policy_top_k's real A/B result was a loss (35.0%, n=40) -- stays
    # unset (None) in the shipped yaml, same "never default without a real
    # win" rule as everything else in this file.
    assert config.policy_top_k is None


def test_policy_top_k_actually_threads_through_the_yaml_loader(tmp_path):
    """v7 wiring regression test: ExpectimaxConfig.policy_top_k was added
    without being read by load_search_config() -- a real gap found during
    the v7 deploy check, since nothing exercised the yaml round-trip for a
    field added after the loader was first written. Setting it in yaml must
    actually reach the returned ExpectimaxConfig, not be silently dropped."""
    cfg_file = tmp_path / "search_config.yaml"
    cfg_file.write_text("search:\n  enabled: true\n  depth: 2\n  policy_top_k: 3\n")
    config = load_search_config(path=str(cfg_file))
    assert config.policy_top_k == 3


def test_missing_policy_top_k_key_falls_back_to_none(tmp_path):
    cfg_file = tmp_path / "search_config.yaml"
    cfg_file.write_text("search:\n  enabled: true\n  depth: 2\n")
    config = load_search_config(path=str(cfg_file))
    assert config.policy_top_k is None


def test_load_search_config_source_mentions_every_expectimax_config_field():
    """Hardening test for the exact bug class policy_top_k's own regression
    test above was written to catch: a field gets added to ExpectimaxConfig
    but the yaml loader is never updated to read it, so setting it in
    config/search_config.yaml silently does nothing. This can't assert
    load_search_config()'s RETURN VALUE generically (fields legitimately
    have different types/parsing), so instead it inspects the loader's own
    source text for each real dataclass field name -- cheap, real, and it
    would have caught policy_top_k's own gap before a person had to notice
    it by hand."""
    import inspect
    from dataclasses import fields as dataclass_fields

    from pokemon_agent.search.expectimax import ExpectimaxConfig
    import pokemon_agent.search.config_loader as config_loader_module

    source = inspect.getsource(config_loader_module)
    missing = [
        f.name for f in dataclass_fields(ExpectimaxConfig)
        if f.name not in source
    ]
    assert not missing, (
        f"ExpectimaxConfig field(s) {missing} are never referenced in "
        "config_loader.py -- add them to load_search_config() (and to "
        "config/search_config.yaml with a comment explaining the default), "
        "the same way every other field is threaded through."
    )


def test_missing_config_path_fails_closed_to_inert_defaults():
    config = load_search_config(path="/nonexistent/path/search_config.yaml")
    assert config.enabled is False
    assert config.depth == 0


def test_corrupt_config_path_fails_closed_to_inert_defaults(tmp_path):
    bad_file = tmp_path / "search_config.yaml"
    bad_file.write_text("not: [valid: yaml: at: all:::")
    config = load_search_config(path=str(bad_file))
    assert config.enabled is False
    assert config.depth == 0
