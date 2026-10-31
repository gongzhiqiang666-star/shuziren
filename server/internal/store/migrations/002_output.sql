CREATE TABLE IF NOT EXISTS session_outputs (
    session_id uuid PRIMARY KEY, shop_id uuid NOT NULL,
    width integer NOT NULL DEFAULT 1280 CHECK(width BETWEEN 160 AND 3840),
    height integer NOT NULL DEFAULT 720 CHECK(height BETWEEN 160 AND 3840),
    fit text NOT NULL DEFAULT 'contain' CHECK(fit IN ('contain','cover')),
    background text NOT NULL DEFAULT '#000000',
    enabled boolean NOT NULL DEFAULT false,
    generation bigint NOT NULL DEFAULT 0 CHECK(generation>=0),
    token_hash bytea UNIQUE CHECK(token_hash IS NULL OR octet_length(token_hash)=32),
    lease_id uuid, receiver_id uuid, lease_epoch bigint,
    lease_expires_at timestamptz, last_heartbeat_at timestamptz,
    peer_state text NOT NULL DEFAULT 'closed',
    video_ready boolean NOT NULL DEFAULT false, audio_ready boolean NOT NULL DEFAULT false,
    media_session_id text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(session_id,shop_id) REFERENCES live_sessions(id,shop_id)
);
ALTER TABLE speech_jobs ADD COLUMN IF NOT EXISTS delivery_lease_id uuid;
ALTER TABLE speech_jobs ADD COLUMN IF NOT EXISTS delivery_generation bigint NOT NULL DEFAULT 0;
