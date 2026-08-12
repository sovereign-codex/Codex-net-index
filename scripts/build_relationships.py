#!/usr/bin/env python3
"""
Build automatic relationship artifacts for Codex Net Index.

Extended with Cross-Trace Intelligence Layer.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

TRACE_INDEX_URL = os.environ.get(
    "TRACE_INDEX_URL",
    "https://raw.githubusercontent.com/sovereign-codex/AVOT-TRACE/main/data/trace-index.json",
)

TRACE_DETAIL_BASE_URL = os.environ.get(
    "TRACE_DETAIL_BASE_URL",
    "https://raw.githubusercontent.com/sovereign-codex/AVOT-TRACE/main/traces",
).rstrip("/")

OUT_DIR = Path(os.environ.get("CODEX_INDEX_ROOT", "."))

SCHEMA_VERSION = "codex.relationships.v2"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug(value: str) -> str:
    value = (value or "unknown").strip().lower()
    value = value.replace("sovereign-codex/", "")
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "unknown"


def read_json_url(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "codex-net-index"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_read_trace_detail(trace_id: str) -> Optional[Dict[str, Any]]:
    if not trace_id:
        return None
    encoded_trace_id = urllib.parse.quote(str(trace_id), safe="")
    url = f"{TRACE_DETAIL_BASE_URL}/{encoded_trace_id}.json"
    try:
        data = read_json_url(url)
        if isinstance(data, dict):
            return data
    except Exception as exc:
        print(f"[warn] could not read {trace_id}: {exc}", file=sys.stderr)
    return None


def normalize_index(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("traces", "items", "entries"):
            if isinstance(raw.get(key), list):
                return raw[key]
    return []


def timestamp_key(value: Any) -> str:
    return value if isinstance(value, str) else ""


def latest_event(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    events = [e for e in events if isinstance(e, dict)]
    if not events:
        return {}
    return sorted(events, key=lambda e: timestamp_key(e.get("timestamp")))[-1]


def merge_trace(index_item: Dict[str, Any], detail: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    trace_id = index_item.get("trace_id")

    events = []
    if detail and isinstance(detail.get("events"), list):
        events = detail["events"]

    last = latest_event(events)

    return {
        "trace_id": trace_id,
        "repo": last.get("repo") or index_item.get("repo"),
        "workflow": last.get("workflow") or index_item.get("workflow"),
        "status": last.get("status") or index_item.get("status"),
        "timestamp": last.get("timestamp") or index_item.get("timestamp") or index_item.get("latest") or "",
        "events": events,
    }


def relationship(rel_type, from_id, to_kind, to_id, evidence, confidence=0.8):
    return {
        "id": f"rel_{slug(from_id)}__{rel_type}__{slug(to_id)}",
        "type": rel_type,
        "from": {"kind": "trace", "id": from_id},
        "to": {"kind": to_kind, "id": to_id},
        "evidence": evidence,
        "confidence": confidence,
    }


def build_cross_trace_intelligence(traces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rels = []

    traces_sorted = sorted(traces, key=lambda t: timestamp_key(t.get("timestamp")))

    for i in range(len(traces_sorted)):
        a = traces_sorted[i]

        for j in range(i + 1, min(i + 6, len(traces_sorted))):
            b = traces_sorted[j]

            if not a.get("timestamp") or not b.get("timestamp"):
                continue

            try:
                ta = datetime.fromisoformat(str(a["timestamp"]).replace("Z", "+00:00"))
                tb = datetime.fromisoformat(str(b["timestamp"]).replace("Z", "+00:00"))
                delta = (tb - ta).total_seconds()
            except Exception:
                continue

            evidence = {
                "time_delta": delta,
                "a_status": a.get("status"),
                "b_status": b.get("status"),
                "a_repo": a.get("repo"),
                "b_repo": b.get("repo"),
            }

            if delta < 10:
                rels.append(
                    relationship(
                        "possibly_related",
                        a.get("trace_id"),
                        "trace",
                        b.get("trace_id"),
                        evidence,
                        0.5,
                    )
                )

            if "dispatch" in (a.get("workflow") or "").lower() and "receive" in (b.get("workflow") or "").lower():
                rels.append(
                    relationship(
                        "likely_triggered",
                        a.get("trace_id"),
                        "trace",
                        b.get("trace_id"),
                        evidence,
                        0.85,
                    )
                )

            if "fail" in (a.get("status") or "").lower() and "success" in (b.get("status") or "").lower():
                rels.append(
                    relationship(
                        "recovered_by",
                        a.get("trace_id"),
                        "trace",
                        b.get("trace_id"),
                        evidence,
                        0.75,
                    )
                )

            if a.get("repo") == b.get("repo"):
                rels.append(
                    relationship(
                        "same_execution_family",
                        a.get("trace_id"),
                        "trace",
                        b.get("trace_id"),
                        evidence,
                        0.6,
                    )
                )

    return rels


def write_json(path: Path, payload: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[write] {path}")


def main():
    generated_at = now_iso()

    raw_index = read_json_url(TRACE_INDEX_URL)
    index_items = normalize_index(raw_index)

    traces = []
    for item in index_items:
        if not isinstance(item, dict):
            continue
        detail = safe_read_trace_detail(item.get("trace_id"))
        traces.append(merge_trace(item, detail))

    cross_trace = build_cross_trace_intelligence(traces)

    metadata = {
        "generated_at": generated_at,
        "schema": SCHEMA_VERSION,
    }

    write_json(
        OUT_DIR / "relationships/generated/cross-trace-intelligence.json",
        {**metadata, "relationships": cross_trace},
    )

    print(f"cross-trace relationships: {len(cross_trace)}")


if __name__ == "__main__":
    main()
