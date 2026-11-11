"""Bounded read-only CLI processes for observation and PR enrichment.

For example, ``read_catalogue('leynos')`` terminates the list subprocess after
one complete validated response instead of waiting for transport teardown.
"""

import asyncio
import dataclasses
import re
import typing as typ
from itertools import starmap

import msgspec

from ishiban.catalogue_framing import CatalogueFramer
from ishiban.domain import PullRequest
from ishiban.lody_process_cleanup import discard_pipe, reap_child
from ishiban.protocol import Catalogue, ProtocolError, decode_catalogue

if typ.TYPE_CHECKING:
    import collections.abc as cabc

PR_URL = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)/?\Z"
)
MAX_GITHUB_BYTES = 2_097_152
MAX_CATALOGUE_BYTES = 32 * 1024 * 1024


TRANSPORT_LINE = re.compile(
    rb"\[[A-Za-z0-9_-]+\] Remote Streams transport (?:attached|detached)"
)


def _json_after_transport(buffer: bytearray) -> bytes | None:
    """Skip only Lody's known transport prelude.

    For example, configuration reads need not retain transport log text.

    Returns
    -------
    bytes or None
        The JSON start, or None while a prelude line is incomplete.

    Raises
    ------
    ProtocolError
        If a complete non-JSON line is not recognized transport chatter.
    """
    while buffer:
        data = bytes(buffer).lstrip()
        if data.startswith(b"{"):
            return data
        line, separator, rest = data.partition(b"\n")
        if not separator:
            return None
        if line and TRANSPORT_LINE.fullmatch(line.rstrip(b"\r")) is None:
            message = "Unexpected CLI output before JSON."
            raise ProtocolError(message)
        buffer[:] = rest
    return None


async def read_json_object(
    command: tuple[str, ...],
    *,
    max_bytes: int = 1_048_576,
    deadline_seconds: float = 20,
    allow_transport_logs: bool = False,
) -> bytes:
    """Read one bounded CLI JSON object before transport EOF.

    For example, configuration reads may opt into known Lody transport chatter.

    Returns
    -------
    bytes
        The object, ready for the caller's typed decoder.

    Raises
    ------
    ProtocolError
        If stdout is unavailable, too large, or incomplete.
    """
    async with asyncio.timeout(deadline_seconds), child(command) as process:
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is None:
            message = "CLI stdout is unavailable."
            raise ProtocolError(message)
        data = bytearray()
        framer = CatalogueFramer()
        async for chunk in _bounded_json_chunks(
            process.stdout, max_bytes, allow_transport_logs=allow_transport_logs
        ):
            data.extend(chunk)
            if framer.feed(chunk):
                end = framer.consumed_bytes if allow_transport_logs else len(data)
                return bytes(data[:end])
    message = "CLI ended without a complete JSON object."
    raise ProtocolError(message)


async def _bounded_json_chunks(
    stdout: asyncio.StreamReader, max_bytes: int, *, allow_transport_logs: bool
) -> cabc.AsyncIterator[bytes]:
    """Remove known Lody chatter from bounded transport before JSON framing.

    For example, an incomplete transport line waits for the next pipe chunk.

    Yields
    ------
    bytes
        Transport chunks beginning at the JSON object.
    """
    prelude = bytearray()
    async for chunk in _bounded_chunks(stdout, max_bytes):
        if not allow_transport_logs:
            yield chunk
            continue
        prelude.extend(chunk)
        candidate = _json_after_transport(prelude)
        if candidate is None:
            continue
        allow_transport_logs = False
        yield candidate


async def _bounded_chunks(
    stdout: asyncio.StreamReader, max_bytes: int
) -> cabc.AsyncIterator[bytes]:
    """Count raw pipe bytes before parsing; for example, chatter uses the bound.

    Yields
    ------
    bytes
        Raw chunks while the configured bound is respected.

    Raises
    ------
    ProtocolError
        If the subprocess emits more than the allowed raw bytes.
    """
    received = 0
    while chunk := await stdout.read(65_536):
        received += len(chunk)
        if received > max_bytes:
            message = "CLI response exceeds its safety bound."
            raise ProtocolError(message)
        yield chunk


@dataclasses.dataclass(slots=True)
class _OwnedChild:
    """Keep subprocess creation and cleanup in one async context boundary."""

    command: tuple[str, ...]
    process: asyncio.subprocess.Process = dataclasses.field(init=False)
    drainer: asyncio.Task[None] = dataclasses.field(init=False)

    async def __aenter__(self) -> asyncio.subprocess.Process:
        """Spawn a bounded child and drain stderr without retaining secrets.

        Returns
        -------
        asyncio.subprocess.Process
            The owned child process.
        """
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1_048_577,
        )
        self.drainer = asyncio.create_task(discard_pipe(self.process.stderr))
        return self.process

    async def __aexit__(
        self,
        _error_type: type[BaseException] | None,
        body_error: BaseException | None,
        _traceback: object,
    ) -> None:
        """Reap the child while retaining cancellation from the context body."""
        cancellation = (
            body_error if isinstance(body_error, asyncio.CancelledError) else None
        )
        await reap_child(self.process, self.drainer, cancellation=cancellation)


def child(command: tuple[str, ...]) -> _OwnedChild:
    """Own a subprocess and stderr drainer without invoking a shell.

    For example, leaving the context cancels an observer and reaps its child.

    Returns
    -------
    _OwnedChild
        An async context that yields a bounded read-only CLI process.
    """
    return _OwnedChild(command)


async def read_catalogue(workspace: str, executable: str = "lody") -> Catalogue:
    """Return one complete catalogue response with a sixty-second bound.

    For example, a successful empty list remains a valid catalogue, not a
    deletion instruction for previously journalled sessions.

    Returns
    -------
    Catalogue
        A complete, successful workspace catalogue.

    """
    command = (
        executable,
        "session",
        "list",
        "--workspace",
        workspace,
        "--all",
        "--json",
    )
    data = await read_json_object(
        command, max_bytes=MAX_CATALOGUE_BYTES, deadline_seconds=60
    )
    return decode_catalogue(data)


class GitHubPR(msgspec.Struct, rename="camel"):
    """The bounded fields needed to classify a PR."""

    title: str
    state: str
    is_draft: bool


class GitHubResult(msgspec.Struct):
    """GraphQL data with optional failures; errors are never logged verbatim."""

    data: dict[str, dict[str, GitHubPR | None] | None] | None = None
    errors: list[GitHubError] | None = None


class GitHubError(msgspec.Struct):
    """Retain an error marker while ignoring its potentially private fields."""


class _PullRequestLookup(msgspec.Struct):
    """Carry available PR facts and an explicit partial-result marker."""

    records: dict[str, PullRequest]
    is_partial: bool


async def read_pull_requests(urls: list[str]) -> _PullRequestLookup:
    """Read associated PR facts in batches of at most forty GraphQL fields.

    For example, inaccessible PRs are omitted so callers preserve an explicit
    unknown classification rather than inventing a title or draft status. A
    partial result retains facts from successful fields and batches.

    Returns
    -------
    _PullRequestLookup
        Available facts and whether any requested fact could not be refreshed.
    """
    results: dict[str, PullRequest] = {}
    is_partial = False
    for start in range(0, len(urls), 40):
        batch = [url for url in urls[start : start + 40] if PR_URL.fullmatch(url)]
        if batch:
            try:
                lookup = await _read_pr_batch(batch)
            except OSError, TimeoutError, ProtocolError, msgspec.DecodeError:
                is_partial = True
                continue
            results.update(lookup.records)
            is_partial |= lookup.is_partial
    return _PullRequestLookup(records=results, is_partial=is_partial)


async def _read_pr_batch(urls: list[str]) -> _PullRequestLookup:
    """Query one bounded batch of validated GitHub PR URLs.

    Returns
    -------
    _PullRequestLookup
        Available facts and any missing data in this bounded batch.

    Raises
    ------
    ProtocolError
        If required pipes are unavailable or the response exceeds its bound.
    """
    fields = list(starmap(_pr_field, enumerate(urls)))
    request = msgspec.json.encode({"query": "query {" + " ".join(fields) + "}"})
    async with (
        asyncio.timeout(45),
        child(("gh", "api", "graphql", "--input", "-")) as process,
    ):
        if process.stdin is None or process.stdout is None:
            message = "GitHub CLI pipes are unavailable."
            raise ProtocolError(message)
        process.stdin.write(request)
        await process.stdin.drain()
        process.stdin.close()
        chunks = bytearray()
        while block := await process.stdout.read(65_536):
            chunks.extend(block)
            if len(chunks) > MAX_GITHUB_BYTES:
                message = "GitHub response exceeds its bound."
                raise ProtocolError(message)
        output = bytes(chunks)
        returncode = await process.wait()
    result = msgspec.json.decode(output, type=GitHubResult)
    lookup = _pr_results(urls, result)
    return _PullRequestLookup(
        records=lookup.records,
        is_partial=lookup.is_partial or returncode != 0 or bool(result.errors),
    )


def _pr_field(index: int, url: str) -> str:
    """Build a GraphQL selection only from a validated repository URL.

    Returns
    -------
    str
        A GraphQL repository selection with one PR.

    Raises
    ------
    ProtocolError
        If the URL is not an allowed GitHub pull request.
    """
    match = PR_URL.fullmatch(url)
    if match is None:
        message = "Invalid GitHub PR URL."
        raise ProtocolError(message)
    owner, repository, number = match.groups()
    return (
        f'p{index}:repository(owner:"{owner}",name:"{repository}")'
        f"{{pullRequest(number:{number}){{title state isDraft}}}}"
    )


def _pr_results(urls: list[str], result: GitHubResult) -> _PullRequestLookup:
    """Normalize GitHub lifecycle states without leaking response internals.

    Returns
    -------
    _PullRequestLookup
        Known records and a marker for inaccessible or absent items.
    """
    records: dict[str, PullRequest] = {}
    is_partial = result.data is None
    repositories = result.data or {}
    for index, url in enumerate(urls):
        repository = repositories.get(f"p{index}") or {}
        pr = repository.get("pullRequest")
        if pr is None:
            is_partial = True
            continue
        status = pr.state.lower()
        if status == "open" and pr.is_draft:
            status = "draft"
        records[url] = PullRequest(url=url, status=status, title=pr.title)
    return _PullRequestLookup(records=records, is_partial=is_partial)
