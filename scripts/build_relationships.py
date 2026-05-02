#!/usr/bin/env python3
"""
Build automatic relationship artifacts for Codex Net Index.

Purpose:
- Pull raw trace memory from AVOT-TRACE.
- Preserve trace truth as external evidence, not as rewritten history.
- Generate interpreted relationship files inside Codex-net-index.

Outputs:
- relationships/generated/trace-relationships.json
- relationships/generated/repo-relationships.json
- relationships/generated/ontology-relationships.json
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

GENERATOR_NAME = "build_relationships.py"
SCHEMA_VERSION = "codex.relationships.v1"


# -------------------------
# Helpers
# -------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug(value: str) -> str:
    value = (value or "unknown").strip().lower()
    value = value.replace("sovereign-codex/", "")
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "unknown"


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
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[warn] could not read detail for {trace_id}: {exc}", file=sys.stderr)
    return None


def normalize_index(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("traces", "items", "entries"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if "trace_id" in raw:
            return [raw]
    return []


def latest_event(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    candidates = [event for event in events if isinstance(event, dict)]
    if not candidates:
        return {}
    return sorted(candidates, key=lambda e: e.get("timestamp", ""))[-1]


# -------------------------
# Core merge logic
# -------------------------

def merge_trace(index_item: Dict[str, Any], detail: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    trace_id = index_item.get("trace_id") or (detail or {}).get("trace_id") or "unknown-trace"

    events = []
    if detail and isinstance(detail.get("events"), list):
        events = [event for event in detail["events"] if isinstance(event, dict)]

    last = latest_event(events)

    context: Dict[str, Any] = {}
    ontology: Dict[str, Any] = {}

    for source in (index_item, detail or {}, last):
        if isinstance(source.get("context"), dict):
            context.update(source["context"])
        if isinstance(source.get("ontology"), dict):
            ontology.update(source["ontology"])

    repo = (
        index_item.get("last_repo")
        or index_item.get("repo")
        or last.get("repo")
        or context.get("repo")
        or "unknown-repo"
    )

    workflow = (
        index_item.get("last_workflow")
        or index_item.get("workflow")
        or last.get("workflow")
        or "unknown-workflow"
    )

    status = (
        index_item.get("last_status")
        or index_item.get("status")
        or last.get("status")
        or "unknown-status"
    )

    timestamp = (
        index_item.get("last_timestamp")
        or index_item.get("timestamp")
        or last.get("timestamp")
        or ""
    )

    return {
        "trace_id": trace_id,
        "repo": repo,
        "workflow": workflow,
        "status": status,
        "timestamp": timestamp,
        "events": events,
        "context": context,
        "ontology": ontology,
        "raw_index": index_item,
    }


# -------------------------
# Relationship builders
# -------------------------

def relationship(
    rel_type: str,
    trace_id: str,
    to_kind: str,
    to_id: str,
    evidence: Dict[str, Any],
    confidence: float = 0.85,
) -> Dict[str, Any]:

    clean_to = slug(to_id)

    return {
        "id": f"rel_{slug(trace_id)}__{rel_type}__{clean_to}",
        "type": rel_type,
        "from": {"kind": "trace", "id": trace_id},
        "to": {"kind": to_kind, "id": to_id, "slug": clean_to},
        "evidence": evidence,
        "confidence": confidence,
    }


def dedupe(rels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []

    for r in rels:
        key = (
            r.get("type"),
            r.get("from", {}).get("id"),
            r.get("to", {}).get("id"),
        )

        if key not in seen:
            seen.add(key)
            out.append(r)

    return out


def infer_avot(repo: str, workflow: str, status: str) -> Optional[str]:
    text = " ".join([repo or "", workflow or "", status or ""]).lower()

    if "archivist" in text:
        return "avot-archivist"
    if "engine" in text or "receiver" in text or "execution" in text:
        return "avot-engine"
    if "trace" in text:
        return "avot-trace"
    if "control" in text or "router" in text or "dispatcher" in text:
        return "control-center"

    return None


def ontology_terms(ontology: Dict[str, Any]) -> List[Tuple[str, str]]:
    terms: List[Tuple[str, str]] = []

    for axis, value in ontology.items():
        if isinstance(value, list):
            for item in value:
                if item:
                    terms.append((str(axis), str(item)))
        elif value:
            terms.append((str(axis), str(value)))

    return terms


# -------------------------
# IO
# -------------------------

def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[write] {path}")


# -------------------------
# Main
# -------------------------

def main() -> int:
    generated_at = now_iso()

    raw_index = read_json_url(TRACE_INDEX_URL)
    index_items = normalize_index(raw_index)

    traces: List[Dict[str, Any]] = []

    for item in index_items:
        trace_id = item.get("trace_id")
        detail = safe_read_trace_detail(trace_id) if trace_id else None
        traces.append(merge_trace(item, detail))

    rels: List[Dict[str, Any]] = []
    repo_rels: List[Dict[str, Any]] = []
    ontology_rels: List[Dict[str, Any]] = []
    avot_links: List[Dict[str, Any]] = []
    thread_links: List[Dict[str, Any]] = []

    for trace in traces:
        trace_id = trace["trace_id"]

        evidence = {
            "repo": trace["repo"],
            "workflow": trace["workflow"],
            "status": trace["status"],
            "timestamp": trace["timestamp"],
        }

        # Repo relationship
        if trace["repo"] and trace["repo"] != "unknown-repo":
            r = relationship("observed_in_repo", trace_id, "repo", trace["repo"], evidence, 0.95)
            repo_rels.append(r)
            rels.append(r)

        # AVOT
        avot = (
            trace["context"].get("avot")
            or trace["context"].get("agent")
            or infer_avot(trace["repo"], trace["workflow"], trace["status"])
        )

        if avot:
            r = relationship("associated_with_avot", trace_id, "avot", avot, evidence, 0.75)
            avot_links.append(r)
            rels.append(r)

        # Thread
        thread = trace["context"].get("thread") or trace["context"].get("topic")

        if thread:
            r = relationship("linked_to_thread", trace_id, "thread", str(thread), evidence, 0.8)
            thread_links.append(r)
            rels.append(r)

        # Ontology
        for axis, term in ontology_terms(trace["ontology"]):
            r = relationship(
                "tagged_with_ontology",
                trace_id,
                "ontology",
                f"{axis}:{term}",
                {**evidence, "axis": axis, "term": term},
                0.9,
            )
            ontology_rels.append(r)
            rels.append(r)

    # 🔁 Deduplicate
    rels = dedupe(rels)
    repo_rels = dedupe(repo_rels)
    ontology_rels = dedupe(ontology_rels)
    avot_links = dedupe(avot_links)
    thread_links = dedupe(thread_links)

    # Index summary
    index_payload = {
        "generated_at": generated_at,
        "source": {
            "repo": "sovereign-codex/AVOT-TRACE",
            "trace_index_url": TRACE_INDEX_URL,
        },
        "counts": {
            "traces": len(traces),
            "relationships": len(rels),
            "repo_relationships": len(repo_rels),
            "ontology_relationships": len(ontology_rels),
            "avot_links": len(avot_links),
            "thread_links": len(thread_links),
        },
        "traces": [
            {
                "trace_id": t["trace_id"],
                "repo": t["repo"],
                "workflow": t["workflow"],
                "status": t["status"],
                "timestamp": t["timestamp"],
                "context": t["context"],
                "ontology": t["ontology"],
            }
            for t in traces
        ],
    }

    metadata = {
        "generated_at": generated_at,
        "source": "AVOT-TRACE",
        "generator": GENERATOR_NAME,
        "schema": SCHEMA_VERSION,
    }

    # Write outputs
    write_json(OUT_DIR / "relationships/generated/trace-relationships.json", {**metadata, "relationships": rels})
    write_json(OUT_DIR / "relationships/generated/repo-relationships.json", {**metadata, "relationships": repo_rels})
    write_json(OUT_DIR / "relationships/generated/ontology-relationships.json", {**metadata, "relationships": ontology_rels})
    write_json(OUT_DIR / "avot-links/generated/trace-avot-links.json", {**metadata, "relationships": avot_links})
    write_json(OUT_DIR / "threads/generated/trace-thread-links.json", {**metadata, "relationships": thread_links})
    write_json(OUT_DIR / "data/trace-relationship-index.json", index_payload)

    print(json.dumps(index_payload["counts"], indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())