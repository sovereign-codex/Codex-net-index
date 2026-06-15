---
mirror_scope_id: convergence_seed_scope
source_system: notion
source_id: "37fc51d5-4b75-8119-8fbe-f737a37904c9"
source_url: "https://app.notion.com/p/37fc51d54b7581198fbef737a37904c9"
title: "30-Day Build Plan — Continuity Seed Node"
canon_posture: staging
artifact_state: content_populated
projection_type: markdown
source_last_seen_at: "2026-06-14T18:04:37.237Z"
exported_at: "2026-06-15T03:00:04Z"
authority: BP-002
notes: "Readable Markdown projection from fetched Notion source. This is not canon promotion."
---

# 30-Day Build Plan — Continuity Seed Node

## Status

Active planning draft.

## Parent Architecture

This plan operationalizes the Convergence Architecture Map — Capability Sovereignty to Hall.

## Goal

Prove a closed continuity loop rather than a grand platform.

## Target State

```plain text
one hardened Linux node
one GitHub operations repository
one exported and normalized Notion memory slice
one read-only query surface over the mirror
one OpenAI interface that reconstructs context from the mirror
all mutations human-approved
```

## Experiment Name

```plain text
continuity_seed_node
```

## Operating Rule

Do not expand beyond this plan until the loop is proven recoverable, reviewable, and understandable.

---

# Phase 1 — Infrastructure Baseline

## Objective

Create the first boring, recoverable node.

## Tasks

```plain text
[ ] Choose hardware candidate: x86-64 mini PC with SSD/NVMe preferred.
[ ] Choose OS baseline: Ubuntu Server or similarly stable Linux distribution.
[ ] Install OS from written notes.
[ ] Create non-root admin user.
[ ] Configure SSH access.
[ ] Enable host firewall.
[ ] Configure regular security updates.
[ ] Document shutdown and power plan.
```

## Output

```plain text
A single reachable Linux node with written setup notes.
```

## Stop Condition

Do not add Docker, Proxmox, or public ingress until SSH, firewall, updates, and notes are complete.

---

# Phase 2 — Canon Repository

## Objective

Create the first canonical operational memory repository.

## Tasks

```plain text
[ ] Create hall-ops or equivalent GitHub repository.
[ ] Add README.md.
[ ] Add docs/ directory.
[ ] Add adr/ directory.
[ ] Add infra/ directory.
[ ] Add exports/manifest/ directory.
[ ] Add issue templates.
[ ] Add CODEOWNERS if ownership boundaries are clear.
[ ] Add branch protection when ready.
```

## Output

```plain text
A GitHub repository that can hold architecture, decisions, manifests, and future export artifacts.
```

## Stop Condition

Do not split into multiple repositories until a real lifecycle, access, or release boundary appears.

---

# Phase 3 — Notion Mirror Pilot

## Objective

Export one bounded Notion scope into durable formats.

## Tasks

```plain text
[ ] Choose one Notion scope only.
[ ] Record source page/database URL.
[ ] Define mirror manifest fields.
[ ] Export or capture Markdown surface.
[ ] Export or capture structured JSONL surface.
[ ] Build or prepare SQLite snapshot surface.
[ ] Generate content hashes.
[ ] Commit or preserve manifest outputs.
```

## Output

```plain text
One Notion memory slice represented outside Notion as Markdown + JSONL + SQLite + manifest.
```

## Stop Condition

Do not attempt whole-workspace sync or two-way sync during this phase.

---

# Phase 4 — Recovery Test

## Objective

Prove the mirror is useful without live Notion access.

## Tasks

```plain text
[ ] Open generated Markdown locally.
[ ] Query or inspect SQLite locally.
[ ] Compare manifest with source scope.
[ ] Identify missing content classes.
[ ] Record gaps.
[ ] Rebuild mirror from source instructions.
```

## Output

```plain text
A documented recovery test showing what can and cannot be reconstructed.
```

## Stop Condition

Do not build Hall UI until the recovery test is understandable.

---

# Phase 5 — Read-Only Capability Surface

## Objective

Expose one safe query route over the mirrored corpus.

## Tasks

```plain text
[ ] Define one read-only capability.
[ ] Define capability input schema.
[ ] Define capability output shape.
[ ] Implement private API or MCP-style surface.
[ ] Test manually first.
[ ] Record limitations.
```

## Candidate First Capability

```plain text
search_mirror
```

## Output

```plain text
A narrow read-only capability that can search or fetch from the mirrored corpus.
```

## Stop Condition

No write tools until read-only capability behavior is logged and understood.

---

# Phase 6 — Intelligence Gateway

## Objective

Connect intelligence to the mirrored corpus through a controlled gateway.

## Tasks

```plain text
[ ] Keep OpenAI API keys server-side only.
[ ] Use project-scoped key or equivalent boundary.
[ ] Route model calls through backend gateway.
[ ] Log prompts, tool calls, outputs, cost, and errors.
[ ] Use structured outputs where possible.
[ ] Keep all mutations manual or approval-gated.
```

## Output

```plain text
A small gateway that lets an intelligence layer reconstruct context from the mirror without owning durable memory.
```

## Stop Condition

No autonomous background mutation until trace, approval, and rollback patterns are proven.

---

# Phase 7 — Review And Decision

## Objective

Decide what to build next based on evidence.

## Review Questions

```plain text
Can we rebuild the node?
Can we recover the mirror?
Can we search the mirror?
Can we cite provenance?
Can we explain what is canonical?
Can we see logs of intelligence interactions?
Can a human approve or deny mutations?
```

## Output

```plain text
A 30-day review note and next-phase recommendation.
```

---

# Deferred Until After 30-Day Loop

```plain text
multi-node infrastructure
graph database adoption
write-capable autonomous agents
Kubernetes
large MCP server ecosystem
two-way Notion/GitHub sync
local AI workloads
public ingress / reverse proxy
```

## Canon Posture

Draft / active implementation plan.

This plan authorizes planning and sequencing only. Purchases, API key creation, infrastructure deployment, repository mutation, MCP deployment, or automated write-capable systems require separate explicit approval.
