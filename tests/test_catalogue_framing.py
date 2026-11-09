"""Catalogue framing remains incremental across arbitrary UTF-8 byte chunks."""

import msgspec
import pytest
from hypothesis import given
from hypothesis import strategies as st

from ishiban.catalogue_framing import CatalogueFramer
from ishiban.protocol import ProtocolError


@given(text=st.text(max_size=100), chunk_size=st.integers(min_value=1, max_value=32))
def test_framing_ignores_delimiters_in_strings_across_chunk_boundaries(
    text: str, chunk_size: int
) -> None:
    """Only the root closing delimiter completes a valid encoded JSON object."""
    payload = msgspec.json.encode({"text": text, "nested": [{"value": 1}]})
    framer = CatalogueFramer()
    for offset in range(0, len(payload), chunk_size):
        chunk = payload[offset : offset + chunk_size]
        assert framer.feed(chunk) == (offset + len(chunk) == len(payload)), (
            "Quoted delimiters, escapes, or split UTF-8 must not end the root early."
        )


@pytest.mark.parametrize("data", [b"[]", b'"value"', b"null"])
def test_catalogue_framing_requires_an_object_root(data: bytes) -> None:
    """A catalogue's top-level object cannot be replaced by another JSON type."""
    with pytest.raises(ProtocolError, match="JSON object"):
        CatalogueFramer().feed(data)


def test_catalogue_framing_accepts_leading_whitespace_and_stays_complete() -> None:
    """Completion is stable and does not depend on the child closing stdout."""
    framer = CatalogueFramer()
    assert not framer.feed(b" \n\t"), "Whitespace is not a complete catalogue."
    assert not framer.feed(b'{"title":"escaped \\"'), (
        "An escaped quote must not leave string context."
    )
    assert framer.feed(b'quote"}'), "The root object must complete after its string."
    assert framer.feed(b"ignored"), "A completed framer must not restart its state."
