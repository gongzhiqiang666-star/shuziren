CREATE TABLE knowledge_embeddings (
 shop_id uuid NOT NULL REFERENCES shops(id),
 knowledge_id uuid NOT NULL REFERENCES knowledge(id) ON DELETE CASCADE,
 content_hash text NOT NULL CHECK(length(content_hash)=64),
 model_revision text NOT NULL CHECK(length(model_revision)=64),
 embedding real[] NOT NULL CHECK(cardinality(embedding)=512),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(shop_id,knowledge_id)
);
CREATE TABLE taobao_rooms (
 shop_id uuid NOT NULL REFERENCES shops(id),
 session_id uuid PRIMARY KEY,
 live_id text NOT NULL UNIQUE,
 updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(session_id,shop_id) REFERENCES live_sessions(id,shop_id)
);
CREATE TABLE taobao_events (
 id uuid PRIMARY KEY,shop_id uuid NOT NULL REFERENCES shops(id),session_id uuid NOT NULL,
 message_id text NOT NULL,live_id text NOT NULL,comment text NOT NULL,
 source text NOT NULL CHECK(source IN ('taobao','replay')),
 dedup_key text NOT NULL,epoch bigint NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','generating','drafted','failed','ignored')),
 job_id uuid REFERENCES speech_jobs(id),error_code text NOT NULL DEFAULT '',
 received_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(shop_id,source,dedup_key),
 FOREIGN KEY(session_id,shop_id) REFERENCES live_sessions(id,shop_id)
);
CREATE INDEX taobao_events_session ON taobao_events(shop_id,session_id,received_at DESC);
CREATE TABLE taobao_actions (
 request_id uuid PRIMARY KEY,shop_id uuid NOT NULL REFERENCES shops(id),session_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('push_item','report')),epoch bigint NOT NULL CHECK(epoch>0),
 payload_hash text NOT NULL CHECK(length(payload_hash)=64),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','succeeded','failed','delivery_unknown')),
 error_code text NOT NULL DEFAULT '',created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(session_id,shop_id) REFERENCES live_sessions(id,shop_id)
);
