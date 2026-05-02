#!/usr/bin/env python3
"""
Build automatic relationship artifacts for Codex Net Index.

Outputs:
- relationships/generated/trace-relationships.json
- relationships/generated/repo-relationships.json
- relationships/generated/ontology-relationships.json
- relationships/generated/causal-relationships.json
- avot-links/generated/trace-avot-links.json
- threads/generated/trace-thread-links.json
- data/trace-relationship-index.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
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

SCHEMA_VERSION = "codex.relationships.v1"
GENERATOR_NAME = "scripts/build_relationships.py"


# -----------------------
# Helpers
# -----------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug(value: str) -> str:
    value = (value or "unknown").strip().lower()
    value = value.replace("sovereign-codex/", "")
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "unknown"


def parse_time(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_between(a: str, b: str) -> Optional[int]:
    ta = parse_time(a)
    tb = parse_time(b)
    if not ta or not tb:
        return None
    return int((tb - ta).total_seconds())


# -----------------------
# IO
# -----------------------

def read_json_url(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "codex-net-index-relationship-generator"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_read_trace_detail(trace_id: str) -> Optional[Dict[str, Any]]:
    url = f"{TRACE_DETAIL_BASE_URL}/{trace_id}.json"
    try:
        data = read_json_url(url)
        if isinstance(data, dict):
            return data
    except Exception as exc:
        print(f"[warn] could not read detail for {trace_id}: {exc}", file=sys.stderr)
    return None


# -----------------------
# Normalization
# -----------------------

def normalize_index(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    if isinstance(raw, dict):
        for key in ("traces", "items", "entries"):
            val = raw.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]

        if "trace_id" in raw:
            return [raw]

    return []


def latest_event(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = [e for e in events if isinstance(e, dict)]
    if not items:
        return {}
    return sorted(items, key=lambda e: e.get("timestamp", ""))[-1]


def merge_trace(index_item: Dict[str, Any], detail: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    trace_id = index_item.get("trace_id") or (detail or {}).get("trace_id") or "unknown-trace"

    events = []
    if detail and isinstance(detail.get("events"), list):
        events = [e for e in detail["events"] if isinstance(e, dict)]

    last = latest_event(events)

    context = {}
    ontology = {}

    for src in (index_item, detail or {}, last):
        if isinstance(src.get("context"), dict):
            context.update(src["context"])
        if isinstance(src.get("ontology"), dict):
            ontology.update(src["ontology"])

    repo = index_item.get("last_repo") or index_item.get("repo") or last.get("repo") or context.get("repo") or "unknown-repo"
    workflow = index_item.get("last_workflow") or index_item.get("workflow") or last.get("workflow") or "unknown-workflow"
    status = index_item.get("last_status") or index_item.get("status") or last.get("status") or "unknown-status"
    timestamp = index_item.get("last_timestamp") or index_item.get("timestamp") or last.get("timestamp") or ""

    return {
        "trace_id": trace_id,
        "repo": repo,
        "workflow": workflow,
        "status": status,
        "timestamp": timestamp,
        "context": context,
        "ontology": ontology,
        "events": events,
    }


# -----------------------
# Relationship Builders
# -----------------------

def relationship(rel_type, trace_id, to_kind, to_id, evidence, confidence=0.8):
    return {
        "id": f"rel_{slug(trace_id)}__{rel_type}__{slug(to_id)}",
        "type": rel_type,
        "from": {"kind": "trace", "id": trace_id},
        "to": {"kind": to_kind, "id": to_id},
        "evidence": evidence,
        "confidence": confidence,
    }


def causal_relationship(rel_type, a, b, evidence, confidence):
    return {
        "id": f"cause_{slug(a['trace_id'])}__{rel_type}__{slug(b['trace_id'])}",
        "type": rel_type,
        "from": {"kind": "trace", "id": a["trace_id"]},
        "to": {"kind": "trace", "id": b["trace_id"]},
        "evidence": evidence,
        "confidence": confidence,
    }


# -----------------------
# Dedupe
# -----------------------

def dedupe(rels):
    seen = set()
    out = []
    for r in rels:
        key = (r["type"], r["from"]["id"], r["to"]["id"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# -----------------------
# Causal Engine
# -----------------------

def build_causal_relationships(traces):
    rels = []

    traces = [t for t in traces if t["timestamp"]]
    traces.sort(key=lambda t: t["timestamp"])

    for i, a in enumerate(traces):
        for b in traces[i+1:i+6]:

            delta = seconds_between(a["timestamp"], b["timestamp"])
            if delta is None or delta < 0:
                continue

            if delta > 900:
                break

            if a["trace_id"] == b["trace_id"]:
                rels.append(causal_relationship(
                    "same_trace_lifecycle",
                    a, b,
                    {"reason": "same_trace", "delta": delta},
                    0.95
                ))
                continue

            if a["repo"] == b["repo"] and delta < 300:
                rels.append(causal_relationship(
                    "possibly_related_sequence",
                    a, b,
                    {"reason": "same_repo", "delta": delta},
                    0.55
                ))

    return dedupe(rels)


# -----------------------
# MAIN
# -----------------------

def main():
    generated_at = now_iso()

    raw = read_json_url(TRACE_INDEX_URL)
    index_items = normalize_index(raw)

    traces = []
    for item in index_items:
        detail = safe_read_trace_detail(item.get("trace_id"))
        traces.append(merge_trace(item, detail))

    rels = []
    repo_rels = []
    ontology_rels = []
    avot_links = []
    thread_links = []

    for t in traces:
        tid = t["trace_id"]

        evidence = {
            "repo": t["repo"],
            "workflow": t["workflow"],
            "status": t["status"],
            "timestamp": t["timestamp"],
        }

        if t["repo"] != "unknown-repo":
            r = relationship("observed_in_repo", tid, "repo", t["repo"], evidence, 0.95)
            repo_rels.append(r)
            rels.append(r)

    causal_rels = build_causal_relationships(traces)

    index_payload = {
        "generated_at": generated_at,
        "counts": {
            "traces": len(traces),
            "relationships": len(rels),
            "causal_relationships": len(causal_rels),
        },
        "traces": traces,
    }

    meta = {
        "generated_at": generated_at,
        "schema": SCHEMA_VERSION,
        "generator": GENERATOR_NAME,
    }

    def write(p, data):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))

    write(OUT_DIR / "relationships/generated/trace-relationships.json", {**meta, "relationships": rels})
    write(OUT_DIR / "relationships/generated/repo-relationships.json", {**meta, "relationships": repo_rels})
    write(OUT_DIR / "relationships/generated/causal-relationships.json", {**meta, "relationships": causal_rels})
    write(OUT_DIR / "data/trace-relationship-index.json", index_payload)

    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())