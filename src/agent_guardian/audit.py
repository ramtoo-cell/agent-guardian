"""Tamper-evident, hash-chained JSONL audit log.

Every record appended to the log carries the SHA-256 hash of the previous
record, forming a chain: editing or deleting any earlier record breaks every
hash after it. :func:`verify_log` replays the chain and reports the first
record that fails verification.

Record layout (one JSON object per line)::

    {"seq": 3, "ts": 1727..., "agent": "my-agent", "kind": "agent_call",
     "payload": {...}, "prev": "<hash of record 2>", "hash": "<this record>"}

Concurrency guarantee:
    * **Threads** — :meth:`AuditLog.append` is serialized by an instance
      lock: concurrent writers in one process never interleave bytes or
      reuse sequence numbers.
    * **Processes** — on POSIX, writers take an advisory ``flock(LOCK_EX)``
      on the log file and re-read the log tail under the lock, so two
      processes appending to the same file stay consistent.  On platforms
      without ``fcntl``/``msvcrt`` this degrades to thread-safety only and a
      warning is logged once.

Tamper model:
    The chain is tamper-*evident*, not tamper-proof.  Anyone with write
    access to the file can rewrite history — but :func:`verify_log` will
    detect it.  For stronger guarantees, store the log on write-once /
    append-only storage (WORM bucket, immutable volume) and verify often.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, BinaryIO

from .exceptions import AuditError

logger = logging.getLogger(__name__)

__all__ = [
    "GENESIS_HASH",
    "AuditError",
    "AuditLog",
    "AuditVerification",
    "verify_log",
]

GENESIS_HASH = "0" * 64

#: How many bytes of the log tail are scanned to find the last record.
#: Records are small (payloads are capped by callers); a single record
#: larger than this would not be found — documented, not silently wrong:
#: :meth:`AuditLog.append` keeps payloads JSON-compact.
_TAIL_SCAN_BYTES = 65536

_lock_warning_emitted = False


def _canonical(obj: Any) -> bytes:
    """Deterministic JSON encoding used for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")


def _record_hash(prev_hash: str, seq: int, ts: float,
                 agent_id: str, kind: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(prev_hash.encode("utf-8"))
    digest.update(_canonical({"seq": seq, "ts": ts, "agent": agent_id,
                              "kind": kind, "payload": payload}))
    return digest.hexdigest()


@contextlib.contextmanager
def _exclusive_file_lock(fh: BinaryIO) -> Iterator[None]:
    """Hold an advisory exclusive lock on ``fh`` for the block.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows.
    Where neither exists, yields without locking (and logs a warning once)
    — thread-safety is still provided by :class:`AuditLog`'s own lock.
    """
    global _lock_warning_emitted
    locked = False
    try:
        import fcntl  # POSIX
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        locked = True
    except ImportError:
        try:
            import msvcrt  # Windows
            fh.seek(0, os.SEEK_END)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            locked = True
        except (ImportError, OSError):
            if not _lock_warning_emitted:
                logger.warning(
                    "no OS file locking available; multi-process appends "
                    "to the same audit log are not serialized")
                _lock_warning_emitted = True
    try:
        yield
    finally:
        if locked:
            try:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except ImportError:  # pragma: no cover - Windows path
                import msvcrt
                try:
                    fh.seek(0, os.SEEK_END)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass


def _read_last_record(path: str) -> dict[str, Any] | None:
    """Return the last well-formed record in ``path``, or ``None``.

    Scans at most the final ``_TAIL_SCAN_BYTES`` of the file, so this stays
    O(1) even for very large logs.
    """
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            if size == 0:
                return None
            fh.seek(max(0, size - _TAIL_SCAN_BYTES))
            chunk = fh.read().decode("utf-8", errors="replace")
    except OSError as exc:
        raise AuditError(f"cannot read audit log {path!r}: {exc}") from exc
    for line in reversed(chunk.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and "seq" in record and "hash" in record:
            return record
    return None


class AuditLog:
    """Append-only audit log with a SHA-256 hash chain.

    Args:
        path: Log file path (created with parent directories as needed).
        agent_id: Label recorded on every entry.

    If ``path`` already exists, the chain continues from its last record so
    a long-running agent can keep one log across restarts.

    Thread-safety: :meth:`append` may be called concurrently from any number
    of threads; calls are serialized and sequence numbers stay unique and
    contiguous.  Multi-process writers are serialized via an advisory file
    lock on POSIX (see module docstring).
    """

    def __init__(self, path: str, agent_id: str = "agent") -> None:
        self.path = path
        self.agent_id = agent_id
        self._lock = threading.Lock()
        self._seq = 0
        self._prev = GENESIS_HASH
        if os.path.exists(path):
            self._resume()

    def _resume(self) -> None:
        """Continue ``_seq``/``_prev`` from the last record on disk."""
        last = _read_last_record(self.path)
        if last is not None:
            self._seq = int(last["seq"])
            self._prev = str(last["hash"])
            logger.debug("resumed audit log %r at seq %d",
                         self.path, self._seq)

    def append(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append an event; return the full chained record.

        The write is atomic with respect to other threads and (on POSIX)
        other processes: the file lock is held from the tail re-read through
        the ``fsync``, so ``seq`` values are never duplicated and bytes never
        interleave.

        Args:
            kind: Event kind, e.g. ``"agent_call"`` or ``"policy_denial"``.
            payload: JSON-serializable event data (non-serializable values
                are coerced with ``str()``).

        Returns:
            The chained record that was written, including ``seq``,
            ``prev`` and ``hash``.

        Raises:
            AuditError: If the log cannot be written.
        """
        with self._lock:
            directory = os.path.dirname(os.path.abspath(self.path))
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as exc:
                raise AuditError(
                    f"cannot create directory for audit log {self.path!r}: "
                    f"{exc}") from exc

            try:
                # Binary mode: we manage the encoding so the byte offset
                # math in _read_last_record stays exact.
                with open(self.path, "ab") as fh, _exclusive_file_lock(fh):
                    # Re-read the tail under the lock: another process
                    # may have appended since we resumed.
                    last = _read_last_record(self.path)
                    if last is not None and int(last["seq"]) > self._seq:
                        self._seq = int(last["seq"])
                        self._prev = str(last["hash"])
                    self._seq += 1
                    ts = time.time()
                    record = {
                        "seq": self._seq,
                        "ts": ts,
                        "agent": self.agent_id,
                        "kind": kind,
                        "payload": payload,
                        "prev": self._prev,
                    }
                    record["hash"] = _record_hash(
                        self._prev, self._seq, ts, self.agent_id,
                        kind, payload)
                    fh.write(_canonical(record) + b"\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                    self._prev = record["hash"]
            except OSError as exc:
                raise AuditError(
                    f"cannot append to audit log {self.path!r}: {exc}"
                ) from exc

            logger.debug("audit append seq=%d kind=%s", self._seq, kind)
            return record

    def __len__(self) -> int:
        """Number of records appended through this instance."""
        with self._lock:
            return self._seq

    def iter_records(self) -> Iterator[dict[str, Any]]:
        """Yield parsed records in order (skips blank lines)."""
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)


@dataclass
class AuditVerification:
    """Outcome of :func:`verify_log`.

    Attributes:
        ok: True only when every record parses, sequence numbers are
            contiguous from 1, and every hash (including the ``prev``
            links) recomputes correctly.
        records_checked: Number of records that verified.
        first_bad_seq: Sequence number of the first failing record, if any.
        message: Human-readable summary.
    """

    ok: bool
    records_checked: int
    first_bad_seq: int | None
    message: str


def verify_log(path: str) -> AuditVerification:
    """Replay the hash chain in ``path`` and detect any tampering.

    Args:
        path: Path to a JSONL audit log written by :class:`AuditLog`.

    Returns:
        An :class:`AuditVerification`.  ``ok`` is True only when every
        record parses, sequence numbers are contiguous from 1, and every
        hash (including the ``prev`` links) recomputes correctly.
    """
    if not os.path.exists(path):
        return AuditVerification(False, 0, None,
                                 f"log file not found: {path}")

    prev = GENESIS_HASH
    expected_seq = 1
    checked = 0
    try:
        # Closed by `with fh:` below; this shape keeps the OSError ->
        # AuditVerification path without deep re-indentation.
        fh = open(path, encoding="utf-8")  # noqa: SIM115
    except OSError as exc:
        return AuditVerification(False, 0, None,
                                 f"cannot read log file {path}: {exc}")
    with fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return AuditVerification(
                    False, checked, None,
                    f"line {lineno} is not valid JSON (possible tampering)")
            for key in ("seq", "ts", "agent", "kind", "payload",
                        "prev", "hash"):
                if key not in record:
                    return AuditVerification(
                        False, checked, None,
                        f"record at line {lineno} is missing key {key!r}")
            if int(record["seq"]) != expected_seq:
                return AuditVerification(
                    False, checked, int(record["seq"]),
                    f"sequence break at line {lineno}: expected seq "
                    f"{expected_seq}, found {record['seq']}")
            if record["prev"] != prev:
                return AuditVerification(
                    False, checked, expected_seq,
                    f"chain link broken at seq {expected_seq} "
                    f"(prev hash mismatch)")
            recomputed = _record_hash(prev, int(record["seq"]),
                                      float(record["ts"]), str(record["agent"]),
                                      str(record["kind"]),
                                      dict(record["payload"]))
            if recomputed != record["hash"]:
                return AuditVerification(
                    False, checked, expected_seq,
                    f"hash mismatch at seq {expected_seq} (record altered)")
            prev = record["hash"]
            expected_seq += 1
            checked += 1

    return AuditVerification(
        True, checked, None,
        f"ok: {checked} records verified, chain intact")
