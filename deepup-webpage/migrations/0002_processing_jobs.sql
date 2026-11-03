CREATE TABLE IF NOT EXISTS processing_jobs (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  guest_token TEXT,
  media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video')),
  category TEXT NOT NULL DEFAULT '풍경',
  original_name TEXT NOT NULL,
  original_r2_key TEXT,
  result_r2_key TEXT,
  preview_r2_key TEXT,
  replicate_prediction_id TEXT,
  model_key TEXT NOT NULL DEFAULT 'default',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'succeeded', 'failed', 'canceled')),
  progress INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  file_size INTEGER NOT NULL DEFAULT 0,
  source_width INTEGER,
  source_height INTEGER,
  result_width INTEGER,
  result_height INTEGER,
  duration_seconds INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  expires_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_user_created
ON processing_jobs(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_status
ON processing_jobs(status);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_guest
ON processing_jobs(guest_token, created_at DESC);
