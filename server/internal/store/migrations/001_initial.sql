CREATE TABLE IF NOT EXISTS shops (
    id uuid PRIMARY KEY, name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    knowledge_version bigint NOT NULL DEFAULT 1 CHECK (knowledge_version > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS products (
    id uuid PRIMARY KEY, shop_id uuid NOT NULL REFERENCES shops(id),
    title text NOT NULL, sku text NOT NULL, description text NOT NULL DEFAULT '', specs text NOT NULL DEFAULT '',
    price_cents bigint NOT NULL CHECK (price_cents >= 0), stock bigint NOT NULL CHECK (stock >= 0),
    active boolean NOT NULL DEFAULT true, version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    expires_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(id, shop_id), UNIQUE(shop_id, sku)
);
CREATE TABLE IF NOT EXISTS product_history (
    product_id uuid NOT NULL REFERENCES products(id), version bigint NOT NULL, shop_id uuid NOT NULL REFERENCES shops(id),
    snapshot jsonb NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(product_id,version)
);
CREATE TABLE IF NOT EXISTS personas (
    shop_id uuid PRIMARY KEY REFERENCES shops(id), name text NOT NULL, tone text NOT NULL, prompt text NOT NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS knowledge (
    id uuid PRIMARY KEY, shop_id uuid NOT NULL REFERENCES shops(id), title text NOT NULL, content text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('faq','memory')), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS knowledge_shop_idx ON knowledge(shop_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS live_sessions (
    id uuid PRIMARY KEY, shop_id uuid NOT NULL REFERENCES shops(id), title text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','ended')),
    epoch bigint NOT NULL DEFAULT 1 CHECK (epoch > 0), media_session_id text,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(id,shop_id)
);
CREATE TABLE IF NOT EXISTS speech_jobs (
    id uuid PRIMARY KEY, shop_id uuid NOT NULL REFERENCES shops(id), session_id uuid NOT NULL,
    product_id uuid NOT NULL, product_version bigint NOT NULL, persona_version bigint NOT NULL,
    knowledge_version bigint NOT NULL, epoch bigint NOT NULL,
    source text NOT NULL CHECK (source IN ('manual','deepseek')), question text NOT NULL DEFAULT '', text text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft','blocked','approved','queued','synthesizing','ready','sending','sent','cancelled','failed','delivery_unknown')),
    reason text NOT NULL DEFAULT '', error_code text NOT NULL DEFAULT '',
    input_tokens bigint NOT NULL DEFAULT 0 CHECK(input_tokens >= 0), output_tokens bigint NOT NULL DEFAULT 0 CHECK(output_tokens >= 0),
    approved_at timestamptz, audio_ready boolean NOT NULL DEFAULT false, context_snapshot jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(session_id,shop_id) REFERENCES live_sessions(id,shop_id),
    FOREIGN KEY(product_id,shop_id) REFERENCES products(id,shop_id)
);
CREATE INDEX IF NOT EXISTS jobs_shop_time_idx ON speech_jobs(shop_id,created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_queue_idx ON speech_jobs(created_at) WHERE status='queued';
CREATE INDEX IF NOT EXISTS jobs_session_idx ON speech_jobs(session_id,status);
CREATE TABLE IF NOT EXISTS quality_profiles (
    shop_id uuid PRIMARY KEY REFERENCES shops(id), avatar_name text NOT NULL DEFAULT '', source_resolution text NOT NULL DEFAULT '',
    model_version text NOT NULL DEFAULT '', canvas_resolution text NOT NULL DEFAULT '', fps integer NOT NULL,
    sync_target_ms integer NOT NULL, notes text NOT NULL DEFAULT '', checks jsonb NOT NULL DEFAULT '[]',
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, shop_id uuid REFERENCES shops(id),
    resource_id text NOT NULL DEFAULT '', event text NOT NULL, details jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
