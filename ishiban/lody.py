"""Bounded read-only CLI processes for observation and PR enrichment.

For example, ``read_catalogue('leynos')`` terminates the list subprocess after
one complete validated response instead of waiting for transport teardown.
"""

import asyncio
import contextlib
import re
import typing as typ
from itertools import starmap

import msgspec

from ishiban.catalogue_framing import CatalogueFramer
from ishiban.domain import PullRequest
from ishiban.protocol import Catalogue, ProtocolError, decode_catalogue

if typ.TYPE_CHECKING:
    import collections.abc as cabc

PR_URL = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)/?\Z"
)
MAX_GITHUB_BYTES = 2_097_152
MAX_CATALOGUE_BYTES = 32 * 1024 * 1024


@contextlib.asynccontextmanager
async def child(
    command: tuple[str, ...],
) -> cabc.AsyncIterator[asyncio.subprocess.Process]:
    """Own a subprocess and stderr drainer without invoking a shell.

    For example, leaving the context cancels an observer and reaps its child.

    Yields
    ------
    asyncio.subprocess.Process
        Owned read-only CLI process with bounded pipe buffers.
    """
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=1_048_577,
    )
    drainer = asyncio.create_task(_discard_stderr(process))
    try:
        yield process
    finally:
        await _terminate(process)
        drainer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await drainer


async def _discard_stderr(process: asyncio.subprocess.Process) -> None:
    """Drain bounded chunks without retaining potentially credential-bearing text."""
    if process.stderr is None:
        return
    while await process.stderr.read(8192):
        pass


async def _terminate(process: asyncio.subprocess.Process) -> None:
    """Reap a CLI child; for example, kill it if graceful termination stalls."""
    if process.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        process.terminate()
    try:
        async with asyncio.timeout(3):
            await process.wait()
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()


async def read_catalogue(workspace: str, executable: str = "lody") -> Catalogue:
    """Return one complete catalogue response with a sixty-second bound.

    For example, a successful empty list remains a valid catalogue, not a
    deletion instruction for previously journalled sessions.

    Returns
    -------
    Catalogue
        A complete, successful workspace catalogue.

    Raises
    ------
    ProtocolError
        If output exceeds its bound or ends without a workspace snapshot.
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
    async with asyncio.timeout(60), child(command) as process:
        if process.stdout is None:
            message = "Catalogue stdout is unavailable."
            raise ProtocolError(message)
        data = bytearray()
        framer = CatalogueFramer()
        while chunk := await process.stdout.read(65_536):
            data.extend(chunk)
            if len(data) > MAX_CATALOGUE_BYTES:
                message = "Catalogue exceeds the configured safety bound."
                raise ProtocolError(message)
            if framer.feed(chunk):
                return decode_catalogue(bytes(data))
    message = "Catalogue ended without a complete successful response."
    raise ProtocolError(message)


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
    for index, url in enumerate(urls):
        repository = (result.data or {}).get(f"p{index}")
        pr = repository.get("pullRequest") if repository is not None else None
        if pr is not None:
            status = "draft" if pr.is_draft else pr.state.lower()
            records[url] = PullRequest(url=url, status=status, title=pr.title)
        else:
            is_partial = True
    return _PullRequestLookup(records=records, is_partial=is_partial)
