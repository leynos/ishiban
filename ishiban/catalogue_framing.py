"""Locate a catalogue object's boundary without repeatedly parsing its buffer.

This private Lody adapter tracks framing only. The protocol decoder still
validates the complete JSON document, including delimiters and trailing data.
"""

import typing as typ

from ishiban.protocol import ProtocolError

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class CatalogueFramer:
    """Scan each received byte once, retaining only JSON lexical state.

    For example, ``feed(b'{"sessions":[')`` waits for the root object's close.
    Escapes and braces inside quoted strings do not affect nesting depth.
    """

    def __init__(self) -> None:
        """Start fresh; for example, ``feed(b'{}')`` can consume one root object."""
        self._consumed_bytes = 0
        self._depth = 0
        self._is_complete = False
        self._is_escaped = False
        self._consume: cabc.Callable[[int], None] = self._start

    def feed(self, chunk: bytes) -> bool:
        """Advance framing state and report whether the root object has ended.

        For example, ``CatalogueFramer().feed(b'{}')`` returns ``True`` without
        waiting for EOF. The caller must then decode its whole buffered input.

        Returns
        -------
        bool
            Whether a complete root object boundary has been encountered.
        """
        if self._is_complete:
            return True
        for byte in chunk:
            self._consumed_bytes += 1
            self._consume(byte)
            if self._is_complete:
                break
        return self._is_complete

    @property
    def consumed_bytes(self) -> int:
        """The root object's boundary offset.

        For example, a CLI adapter can discard trailing transport chatter.

        Returns
        -------
        int
            Bytes scanned through the root object's closing delimiter.
        """
        return self._consumed_bytes

    def _start(self, byte: int) -> None:
        """Skip whitespace; for example, spaces preserve state until ``{`` arrives.

        Raises
        ------
        ProtocolError
            If the first non-whitespace byte cannot begin a catalogue object.
        """
        if byte in b" \t\r\n":
            return
        if byte != ord("{"):
            message = "Catalogue must begin with a JSON object."
            raise ProtocolError(message)
        self._depth = 1
        self._consume = self._outside_string

    def _outside_string(self, byte: int) -> None:
        """Track delimiters; for example, ``[`` increases structural depth."""
        if byte == ord('"'):
            self._consume = self._inside_string
        elif byte in b"{[":
            self._depth += 1
        elif byte in b"}]":
            self._depth -= 1
            self._is_complete = self._depth == 0

    def _inside_string(self, byte: int) -> None:
        """Ignore structure; for example, an escaped quote leaves the string open."""
        if self._is_escaped:
            self._is_escaped = False
        elif byte == ord("\\"):
            self._is_escaped = True
        elif byte == ord('"'):
            self._consume = self._outside_string
