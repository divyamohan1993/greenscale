CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user_lat REAL,
  user_lon REAL,
  chosen_region TEXT NOT NULL,
  baseline_region TEXT NOT NULL,
  candidates_json TEXT NOT NULL,
  weights_json TEXT NOT NULL,
  carbon_saved_g REAL NOT NULL,
  latency_overhead_ms REAL NOT NULL,
  reason TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_chosen ON decisions(chosen_region);
