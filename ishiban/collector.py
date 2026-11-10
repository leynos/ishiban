"""Supervise one read-only workspace observer and reconcile PR metadata.

For example, ``Collector(store, 'leynos').run()`` reconnects after a source
failure without manufacturing successful or failed turns.
"""

import asyncio
import contextlib
import fcntl
import secrets
import typing as typ

import msgspec

from ishiban.domain import CatalogueEntry, PullRequest
from ishiban.lody import PR_URL, child, read_catalogue, read_pull_requests
from ishiban.protocol import Catalogue, ProtocolError, StreamPosition, decode_event
from ishiban.workflow import classify

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from ishiban.storage import Store


class Collector:
    """Own the observer child and bounded catalogue refresh task.

    Examples
    --------
    ``Collector(store, "leynos", github=False)`` omits optional GitHub reads.
    """

    def __init__(
        self,
        store: Store,
        workspace: str,
        *,
        executable: str = "lody",
        github: bool = True,
    ) -> None:
        """Configure exactly one store and workspace without starting children."""
        self.store = store
        self.workspace = workspace
        self.executable = executable
        self.github = github
        self.pr_cache: dict[str, PullRequest] = {}
        self.generation = 0
        self.enrichment_error: str | None = None

    async def reconcile(self, catalogue: Catalogue) -> None:
        """Merge explicit associations without deleting omitted sessions.

        For example, a failed title lookup preserves previous known PR titles.

        Raises
        ------
        ProtocolError
            If the catalogue is from a different workspace.
        """
        if catalogue.workspace_id != self.store.workspace_id:
            message = "Catalogue belongs to a different workspace."
            raise ProtocolError(message)
        if self.github:
            await self._enrich_prs(catalogue)
        for session in catalogue.sessions:
            prs = [
                self._pr(record.url, record.status) for record in session.pull_requests
            ]
            decision = classify(prs)
            entry = CatalogueEntry(
                session_id=session.id,
                machine_id=session.machine_id,
                title=session.title,
                archived=session.is_archived,
                repo_full_name=session.repo_full_name,
                branch_name=session.branch_name,
                pull_requests=prs,
                stage=decision.stage,
                stage_reason=decision.reason,
                parent_session_id=session.parent_session_id,
                created_at=session.created_at,
            )
            await self.store.catalogue(entry, self.generation)

    def _pr(self, url: str, status: str) -> PullRequest:
        """Use safe validated links; for example, a foreign URL stays unknown.

        Returns
        -------
        PullRequest
            Known cached PR facts or an explicitly unknown association.
        """
        if PR_URL.fullmatch(url) is None:
            return PullRequest(url="", status="unknown")
        cached = self.pr_cache.get(url)
        if status in {"merged", "closed"}:
            return PullRequest(
                url=url,
                status=status,
                title=cached.title if cached is not None else None,
            )
        return cached or PullRequest(url=url, status=status)

    async def _enrich_prs(self, catalogue: Catalogue) -> None:
        """Refresh active PR titles with bounded cached GitHub queries."""
        urls = sorted({
            pr.url
            for session in catalogue.sessions
            for pr in session.pull_requests
            if pr.status in {"draft", "open"} and PR_URL.fullmatch(pr.url)
        })
        try:
            lookup = await read_pull_requests(urls)
            self.pr_cache.update(lookup.records)
            self.enrichment_error = (
                "GitHub title enrichment unavailable; cached facts may be stale."
                if lookup.is_partial
                else None
            )
        except OSError, TimeoutError, ProtocolError, msgspec.DecodeError:
            self.enrichment_error = (
                "GitHub title enrichment unavailable; cached facts may be stale."
            )

    async def run(self, initial: Catalogue | None = None) -> None:
        """Observe continuously until cancellation, with bounded restart backoff.

        A disconnect retains last-known running state and makes source loss
        visible through a separately persisted collector event.
        """
        delay = 1.0
        try:
            while True:
                self.generation = await self.store.begin_generation()
                try:
                    catalogue = initial or await read_catalogue(
                        self.workspace, self.executable
                    )
                    initial = None
                    await self.reconcile(catalogue)
                    await self._follow()
                except (
                    OSError,
                    TimeoutError,
                    ValueError,
                    msgspec.DecodeError,
                ) as error:
                    summary = (
                        f"Lody source failure ({type(error).__name__}); reconnecting."
                    )
                    if isinstance(error, ProtocolError):
                        summary = str(error)
                    await self.store.health("disconnected", self.generation, summary)
                await asyncio.sleep(delay + secrets.randbelow(1000) / 1000)
                delay = min(delay * 2, 30)
        finally:
            await self.store.health("stopped", self.generation)

    async def _follow(self) -> None:
        """Attach one workspace observer and a periodic catalogue refresher.

        Raises
        ------
        ProtocolError
            If stdout is unavailable or the observer exits.
        """
        command = (
            self.executable,
            "session",
            "observe",
            "--workspace",
            self.workspace,
            "--all",
            "--jsonl",
            "--follow",
        )
        refresh = asyncio.create_task(self._refresh())
        try:
            async with child(command) as process:
                if process.stdout is None:
                    message = "Observer stdout unavailable."
                    raise ProtocolError(message)
                position = StreamPosition()
                while line := await process.stdout.readline():
                    event = decode_event(line, self.store.workspace_id, position)
                    await self.store.ingest(event, self.generation, raw=line)
                    if event.type == "ready":
                        await self.store.health(
                            "following", self.generation, self.enrichment_error
                        )
                message = (
                    "Observer exited; historical gaps cannot be replayed upstream."
                )
                raise ProtocolError(message)
        finally:
            refresh.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await refresh

    async def _refresh(self) -> None:
        """Reconcile read-only catalogue associations every five minutes."""
        while True:
            await asyncio.sleep(300)
            try:
                catalogue = await read_catalogue(self.workspace, self.executable)
                await self.reconcile(catalogue)
                await self.store.health(
                    "following", self.generation, self.enrichment_error
                )
            except OSError, TimeoutError, ProtocolError, msgspec.DecodeError:
                await self.store.health(
                    "following",
                    self.generation,
                    "Catalogue refresh unavailable; associations may be stale.",
                )


@contextlib.contextmanager
def collector_lock(directory: pathlib.Path) -> cabc.Iterator[None]:
    """Exclude a second collector; for example, lock the shared state directory.

    Yields
    ------
    None
        Exclusive ownership of the collector state directory.
    """
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "collector.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
