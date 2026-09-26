"""Tamper-evident, hash-chained JSONL audit log.

Every record appended to the log carries the SHA-256 hash of the previous
record, forming a chain: editing or deleting any earlier record breaks every
hash after it. :func:`verify_log` replays the chain and reports the first
record that fails verification.

Record layout (one JSON object per line)::

    {"seq": 3, "ts": 1727..., "agent": "my-agent", "kind": "agent_call",
     "payload": {...}, "prev": "<hash of record 2>", "hash": "<this record>"}
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

GENESIS_HASH = "0" * 64


def _canonical(obj: Any) -> bytes:
    """Deterministic JSON encoding used for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")


def _record_hash(prev_hash: str, seq: int, ts: float,
                 agent_id: str, kind: str, payload: Dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(prev_hash.encode("utf-8"))
    digest.update(_canonical({"seq": seq, "ts": ts, "agent": agent_id,
                              "kind": kind, "payload": payload}))
    return digest.hexdigest()


class AuditLog:
    """Append-only audit log with a SHA-256 hash chain.

    If ``path`` already exists, the chain continues from its last record so
    a long-running agent can keep one log across restarts.
    """

    def __init__(self, path: str, agent_id: str = "agent") -> None:
        self.path = path
        self.agent_id = agent_id
        self._seq = 0
        self._prev = GENESIS_HASH
        if os.path.exists(path):
            self._resume()

    def _resume(self) -> None:
        last: Optional[Dict[str, Any]] = None
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # verify_log() will flag the corruption
                if isinstance(record, dict) and "seq" in record and "hash" in record:
                    last = record
        if last is not None:
            self._seq = int(last["seq"])
            self._prev = str(last["hash"])

    def append(self, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Append an event; returns the full chained record."""
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
        record["hash"] = _record_hash(self._prev, self._seq, ts,
                                      self.agent_id, kind, payload)
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        self._prev = record["hash"]
        return record

    def __len__(self) -> int:
        return self._seq

    def iter_records(self) -> Iterator[Dict[str, Any]]:
        """Yield parsed records (skips blank lines)."""
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)


@dataclass
class AuditVerification:
    """Outcome of :func:`verify_log`."""
    ok: bool
    records_checked: int
    first_bad_seq: Optional[int]
    message: str


def verify_log(path: str) -> AuditVerification:
    """Replay the hash chain in ``path``; detect any tampering.

    Returns an :class:`AuditVerification`. ``ok`` is True only when every
    record parses, sequence numbers are contiguous from 1, and every hash
    (including the ``prev`` links) recomputes correctly.
    """
    if not os.path.exists(path):
        return AuditVerification(False, 0, None, f"log file not found: {path}")

    prev = GENESIS_HASH
    expected_seq = 1
    checked = 0
    with open(path, "r", encoding="utf-8") as fh:
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
            for key in ("seq", "ts", "agent", "kind", "payload", "prev", "hash"):
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
