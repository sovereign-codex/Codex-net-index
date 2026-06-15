-- convergence_seed_scope mirror schema placeholder
-- Canon posture: staging placeholder
-- No exported Notion records are present in this file.

CREATE TABLE IF NOT EXISTS mirror_artifacts (
  artifact_id TEXT PRIMARY KEY,
  source_page_id TEXT,
  title TEXT,
  artifact_kind TEXT NOT NULL,
  canon_posture TEXT NOT NULL DEFAULT 'staging',
  source_surface TEXT NOT NULL DEFAULT 'notion',
  target_surface TEXT NOT NULL DEFAULT 'github',
  exported_at TEXT,
  checksum TEXT,
  relative_path TEXT
);

CREATE TABLE IF NOT EXISTS mirror_trace_events (
  event_id TEXT PRIMARY KEY,
  artifact_id TEXT,
  event_type TEXT NOT NULL,
  occurred_at TEXT,
  agent TEXT,
  runtime_packet_id TEXT,
  notes TEXT,
  FOREIGN KEY (artifact_id) REFERENCES mirror_artifacts(artifact_id)
);
