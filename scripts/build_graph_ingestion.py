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
    "https://raw.githubusercontent.com/sovereign-codex/AVOT-TRACE/main/data/trace-index.json",
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
            "weight": 1,
        }
    else:
        nodes[key]["weight"] += 1
    return key


def add_edge(edges, source, target, rel_type, evidence=None, weight=1):
    edge_id = f"{source}__{rel_type}__{target}"
    if edge_id in edges:
        edges[edge_id]["weight"] += weight
        if evidence:
            edges[edge_id]["evidence"] = evidence
        return
    edges[edge_id] = {
        "id": edge_id,
        "source": source,
        "target": target,
        "type": rel_type,
        "weight": weight,
        "evidence": evidence or {},
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


def semantic_evidence(trace_id, event):
    semantic = event.get("semantic") if isinstance(event.get("semantic"), dict) else {}
    evidence = {
        "trace_id": trace_id,
        "event_id": event.get("event_id"),
        "event_class": event.get("event_class"),
        "protocol_version": event.get("protocol_version"),
        "status": event.get("status"),
        "timestamp": event.get("timestamp"),
        "institutional_state": semantic.get("institutional_state"),
        "execution_state": semantic.get("execution_state"),
        "flow_state": semantic.get("flow_state"),
        "authority_state": semantic.get("authority_state"),
        "next_valid_action": semantic.get("next_valid_action"),
        "review_requirement": semantic.get("review_requirement"),
        "handoff_semantics": semantic.get("handoff_semantics"),
    }
    return {k: v for k, v in evidence.items() if v is not None}


def project_institutional_semantics(nodes, edges, trace_node, trace_id, event):
    """Promote stable institutional actors only; retain mutable state as evidence."""
    semantic = event.get("semantic") if isinstance(event.get("semantic"), dict) else {}
    if not semantic:
        return

    evidence = semantic_evidence(trace_id, event)

    source_role = semantic.get("source_role")
    if source_role:
        source_role_node = add_node(nodes, "role", source_role)
        add_edge(edges, trace_node, source_role_node, "emitted_by_role", evidence)

    receiving_office = semantic.get("receiving_office")
    if receiving_office:
        office_node = add_node(nodes, "office", receiving_office)
        add_edge(edges, trace_node, office_node, "received_by_office", evidence)

    review_role = semantic.get("review_role")
    if review_role:
        review_role_node = add_node(nodes, "role", review_role)
        add_edge(edges, trace_node, review_role_node, "has_review_role", evidence)


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
            base_evidence = semantic_evidence(trace_id, event)
            base_evidence["repo"] = source

            add_edge(edges, trace_node, repo_node, "observed_in_repo", base_evidence)
            add_edge(edges, trace_node, workflow_node, "passed_through_workflow", base_evidence)

            if target:
                target_node = add_node(nodes, "repo", target)
                add_edge(edges, workflow_node, target_node, "routed_to", base_evidence)

            project_institutional_semantics(nodes, edges, trace_node, trace_id, event)

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
                    "to_timestamp": nxt.get("timestamp"),
                },
                "confidence": 0.85,
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
            **stats,
        })

    system_graph = {
        "generated_at": generated_at,
        "schema": "codex.system_graph.v1.1-experimental",
        "source": "AVOT-TRACE",
        "semantic_projection": {
            "promoted_node_kinds": ["office", "role"],
            "promoted_fields": ["semantic.receiving_office", "semantic.source_role", "semantic.review_role"],
            "evidence_only_fields": [
                "semantic.institutional_state",
                "semantic.execution_state",
                "semantic.flow_state",
                "semantic.authority_state",
                "semantic.next_valid_action",
                "semantic.review_requirement",
                "semantic.handoff_semantics",
            ],
            "posture": "conservative-experimental",
        },
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }

    rel_payload = {
        "generated_at": generated_at,
        "schema": "codex.relationships.v1",
        "relationships": temporal_relationships,
    }

    reliability_payload = {
        "generated_at": generated_at,
        "schema": "codex.node_reliability.v1",
        "nodes": reliability_nodes,
    }

    write_json(OUT_DIR / "data/system-graph.json", system_graph)
    write_json(OUT_DIR / "data/node-reliability.json", reliability_payload)
    write_json(OUT_DIR / "relationships/generated/temporal-causal-relationships.json", rel_payload)

    print(json.dumps({
        "nodes": len(system_graph["nodes"]),
        "edges": len(system_graph["edges"]),
        "temporal_relationships": len(temporal_relationships),
        "reliability_nodes": len(reliability_nodes),
        "schema": system_graph["schema"],
    }, indent=2))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[write] {path}")


if __name__ == "__main__":
    main()
