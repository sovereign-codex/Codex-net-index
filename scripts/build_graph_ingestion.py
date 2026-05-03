#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

TRACE_INDEX_URL = os.environ.get(
    "TRACE_INDEX_URL",
    "https://raw.githubusercontent.com/sovereign-codex/AVOT-TRACE/main/index/trace-index.json",
)

TRACE_BASE_URL = os.environ.get(
    "TRACE_BASE_URL",
    "https://raw.githubusercontent.com/sovereign-codex/AVOT-TRACE/main/traces",
).rstrip("/")

OUT_DIR = Path(os.environ.get("CODEX_INDEX_ROOT", "."))


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "codex-graph-ingestion"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def slug(value):
    return str(value or "unknown").strip().lower().replace(" ", "-")


def node_key(kind, node_id):
    return f"{kind}:{node_id}"


def add_node(nodes, kind, node_id, label=None):
    key = node_key(kind, node_id)
    if key not in nodes:
        nodes[key] = {
            "key": key,
            "kind": kind,
            "id": node_id,
            "label": label or node_id,
            "weight": 1
        }
    else:
        nodes[key]["weight"] += 1
    return key


def add_edge(edges, source, target, rel_type, evidence=None, weight=1):
    edge_id = f"{source}__{rel_type}__{target}"
    edges[edge_id] = {
        "id": edge_id,
        "source": source,
        "target": target,
        "type": rel_type,
        "weight": weight,
        "evidence": evidence or {}
    }


def health_state(successes, failures):
    total = successes + failures
    if total == 0:
        return "unknown", 100
    score = round((successes / total) * 100)
    if score < 50:
        return "critical", score
    if score < 80:
        return "degraded", score
    return "healthy", score


def main():
    generated_at = now_iso()

    raw_index = read_json_url(TRACE_INDEX_URL)
    trace_items = raw_index.get("traces", []) if isinstance(raw_index, dict) else []

    nodes = {}
    edges = {}
    temporal_relationships = []
    reliability = defaultdict(lambda: {"successes": 0, "failures": 0, "events": 0})

    for item in trace_items:
        trace_id = item.get("trace_id")
        if not trace_id:
            continue

        try:
            trace = read_json_url(f"{TRACE_BASE_URL}/{trace_id}.json")
        except Exception as exc:
            print(f"[warn] could not load trace {trace_id}: {exc}")
            continue

        events = trace.get("events", [])
        if not events:
            continue

        trace_node = add_node(nodes, "trace", trace_id)

        for event in events:
            source = event.get("source") or event.get("repo") or "unknown-source"
            workflow = event.get("workflow") or "unknown-workflow"
            status = event.get("status") or "unknown-status"
            target = event.get("target") or ""

            repo_node = add_node(nodes, "repo", source)
            workflow_node = add_node(nodes, "workflow", workflow)

            add_edge(
                edges,
                trace_node,
                repo_node,
                "observed_in_repo",
                {"trace_id": trace_id, "status": status, "timestamp": event.get("timestamp")}
            )

            add_edge(
                edges,
                trace_node,
                workflow_node,
                "passed_through_workflow",
                {"trace_id": trace_id, "repo": source, "status": status, "timestamp": event.get("timestamp")}
            )

            if target:
                target_node = add_node(nodes, "repo", target)
                add_edge(
                    edges,
                    workflow_node,
                    target_node,
                    "routed_to",
                    {"trace_id": trace_id, "status": status, "timestamp": event.get("timestamp")}
                )

            key = node_key("workflow", workflow)
            reliability[key]["events"] += 1

            s = status.lower()
            if "fail" in s or "error" in s or "no_route" in s:
                reliability[key]["failures"] += 1
            elif "completed" in s or "stored" in s or "sent" in s or "received" in s:
                reliability[key]["successes"] += 1

        ordered = sorted(events, key=lambda e: e.get("timestamp", ""))
        for prev, nxt in zip(ordered, ordered[1:]):
            prev_w = prev.get("workflow") or "unknown-workflow"
            next_w = nxt.get("workflow") or "unknown-workflow"

            prev_node = add_node(nodes, "workflow", prev_w)
            next_node = add_node(nodes, "workflow", next_w)

            causal_type = "chained"
            ps = (prev.get("status") or "").lower()
            if "fail" in ps or "error" in ps:
                causal_type = "fallback"
            elif prev_w == next_w:
                causal_type = "retry"
            elif "stored" in ps or "sent" in ps or "completed" in ps:
                causal_type = "triggered"

            rel = {
                "id": f"causal_{slug(trace_id)}_{slug(prev_w)}_{slug(next_w)}",
                "type": causal_type,
                "from": {"kind": "workflow", "id": prev_w},
                "to": {"kind": "workflow", "id": next_w},
                "evidence": {
                    "trace_id": trace_id,
                    "from_status": prev.get("status"),
                    "to_status": nxt.get("status"),
                    "from_timestamp": prev.get("timestamp"),
                    "to_timestamp": nxt.get("timestamp")
                },
                "confidence": 0.85
            }

            temporal_relationships.append(rel)
            add_edge(edges, prev_node, next_node, causal_type, rel["evidence"], weight=2)

    reliability_nodes = []
    for key, stats in reliability.items():
        state, score = health_state(stats["successes"], stats["failures"])
        kind, node_id = key.split(":", 1)
        reliability_nodes.append({
            "key": key,
            "kind": kind,
            "node_id": node_id,
            "state": state,
            "score": score,
            **stats
        })

    system_graph = {
        "generated_at": generated_at,
        "schema": "codex.system_graph.v1",
        "source": "AVOT-TRACE",
        "nodes": list(nodes.values()),
        "edges": list(edges.values())
    }

    rel_payload = {
        "generated_at": generated_at,
        "schema": "codex.relationships.v1",
        "relationships": temporal_relationships
    }

    reliability_payload = {
        "generated_at": generated_at,
        "schema": "codex.node_reliability.v1",
        "nodes": reliability_nodes
    }

    write_json(OUT_DIR / "data/system-graph.json", system_graph)
    write_json(OUT_DIR / "data/node-reliability.json", reliability_payload)
    write_json(OUT_DIR / "relationships/generated/temporal-causal-relationships.json", rel_payload)

    print(json.dumps({
        "nodes": len(system_graph["nodes"]),
        "edges": len(system_graph["edges"]),
        "temporal_relationships": len(temporal_relationships),
        "reliability_nodes": len(reliability_nodes)
    }, indent=2))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[write] {path}")


if __name__ == "__main__":
    main()