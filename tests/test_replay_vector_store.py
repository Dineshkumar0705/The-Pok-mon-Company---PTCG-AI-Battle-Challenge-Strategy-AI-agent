from __future__ import annotations

from pokemon_agent.memory.replay_store import ReplayVectorStore


def test_log_and_query_similar_returns_closest_first():
    store = ReplayVectorStore()
    store.log_decision([1.0, 0.0, 0.0], label=1.0, meta={"game_id": 0})
    store.log_decision([0.0, 1.0, 0.0], label=0.0, meta={"game_id": 1})
    store.log_decision([0.9, 0.1, 0.0], label=1.0, meta={"game_id": 2})

    results = store.query_similar([1.0, 0.0, 0.0], k=2)
    assert len(results) == 2
    # The exact match (game 0) should be the closest, then the near-match (game 2).
    assert results[0][0].meta["game_id"] == 0
    assert results[1][0].meta["game_id"] == 2


def test_query_similar_on_empty_store_returns_empty():
    store = ReplayVectorStore()
    assert store.query_similar([1.0, 2.0], k=3) == []


def test_save_and_load_round_trips():
    store = ReplayVectorStore()
    store.log_decision([1.0, 2.0], label=1.0, meta={"a": 1})
    store.log_decision([3.0, 4.0], label=0.0, meta={"b": 2})

    import tempfile
    import os
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "store.jsonl")
        store.save(path)
        loaded = ReplayVectorStore.load(path)

    assert len(loaded) == 2
    assert loaded.records[0].features == [1.0, 2.0]
    assert loaded.records[0].label == 1.0
    assert loaded.records[1].meta == {"b": 2}


def test_len_reflects_logged_decisions():
    store = ReplayVectorStore()
    assert len(store) == 0
    store.log_decision([1.0], label=0.5)
    assert len(store) == 1
