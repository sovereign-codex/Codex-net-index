# Relationship Records

Canon posture: staging.

This directory stores explicit relationship records for the `convergence_seed_scope` mirror.

The relationship layer exists so mirrored artifacts can be interpreted as durable memory objects rather than isolated files. Records are intentionally small, line-delimited, and provenance-focused.

## Authorized Relationship Types

- `authorized_by`
- `created_by`
- `reviewed_by`
- `belongs_to_scope`
- `introduced_in_commit`
- `projected_as`
- `indexed_by`
- `available_to_capability`

## Rules

- Do not add relationships outside BP-003 authority.
- Do not infer unknown source metadata.
- Do not broaden the mirror source scope.
- Do not treat staging relationships as canon promotion.
- Preserve ambiguity, especially duplicate titles and unknown hashes.

## Primary File

`relationship_records.jsonl` contains one relationship record per line.
