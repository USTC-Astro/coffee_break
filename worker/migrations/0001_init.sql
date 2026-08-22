CREATE TABLE IF NOT EXISTS coffee_votes (
  week TEXT NOT NULL,
  device_id TEXT NOT NULL,
  drink TEXT NOT NULL,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (week, device_id)
);

CREATE TABLE IF NOT EXISTS coffee_vote_archives (
  archive_id TEXT NOT NULL,
  week TEXT NOT NULL,
  device_id TEXT NOT NULL,
  drink TEXT NOT NULL,
  name TEXT NOT NULL,
  voted_at TEXT NOT NULL,
  archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (archive_id, week, device_id)
);

CREATE TABLE IF NOT EXISTS rate_limits (
  key TEXT NOT NULL,
  bucket TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (key, bucket)
);
