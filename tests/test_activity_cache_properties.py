"""Generated execution ordering preserves metadata and rejects stale failures."""

from hypothesis import given
from hypothesis import strategies as st

from ishiban.storage.activity_cache import _merge_projection
from ishiban.storage.serialization import encode_json


@given(
    base=st.integers(min_value=1, max_value=10_000),
    watermark=st.integers(min_value=0, max_value=20_000),
    title=st.text(max_size=80),
)
def test_cache_ordering_preserves_current_metadata(
    base: int, watermark: int, title: str
) -> None:
    """Arbitrary execution watermarks cannot regress metadata or revive stale state."""
    incoming: dict[str, object] = {
        "sessionId": "s1",
        "state": "unknown",
        "title": title,
        "lastEventId": 20_001,
        "lastActivityEventId": watermark,
    }
    runtime = encode_json({
        "state": "idle",
        "latestTurn": {"userTurnId": "u1", "state": "failed"},
    })
    restored = _merge_projection(incoming, (base, runtime))
    assert restored["title"] == title, "Runtime restoration must preserve any title."
    assert restored["lastEventId"] == 20_001, "Metadata revisions cannot roll back."
    assert restored["lastActivityEventId"] == watermark, "Execution order is unchanged."
    assert incoming["state"] == "unknown", "The journal projection must not be mutated."
    if watermark > base:
        assert restored == incoming, "Newer execution must reject the older cache."
    else:
        assert restored["state"] == "idle", "Eligible last-known activity is retained."
        assert restored["activitySource"] == "lazy", (
            "Cached facts keep their provenance."
        )
