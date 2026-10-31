ALTER TABLE speech_jobs ADD COLUMN business_fingerprint text NOT NULL DEFAULT '';

CREATE TABLE persona_history (
    shop_id uuid NOT NULL REFERENCES shops(id), version bigint NOT NULL,
    snapshot jsonb NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(shop_id,version)
);
INSERT INTO persona_history(shop_id,version,snapshot)
SELECT shop_id,version,to_jsonb(personas) FROM personas;
CREATE FUNCTION archive_persona() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO persona_history(shop_id,version,snapshot) VALUES(NEW.shop_id,NEW.version,to_jsonb(NEW));
    RETURN NEW;
END $$;
CREATE TRIGGER persona_archive AFTER INSERT OR UPDATE ON personas FOR EACH ROW EXECUTE FUNCTION archive_persona();

ALTER TABLE knowledge ADD COLUMN version bigint NOT NULL DEFAULT 1 CHECK(version > 0);
ALTER TABLE knowledge ADD COLUMN source text NOT NULL DEFAULT 'operator';
ALTER TABLE knowledge ADD COLUMN scope text NOT NULL DEFAULT 'shop' CHECK(scope IN ('shop','product','session'));
ALTER TABLE knowledge ADD COLUMN scope_id uuid;
ALTER TABLE knowledge ADD COLUMN expires_at timestamptz;
ALTER TABLE knowledge ADD COLUMN deleted_at timestamptz;
ALTER TABLE knowledge ADD CONSTRAINT knowledge_scope_target_check CHECK((scope='shop' AND scope_id IS NULL) OR (scope<>'shop' AND scope_id IS NOT NULL));
CREATE TABLE knowledge_history (
    resource_id uuid NOT NULL, shop_id uuid NOT NULL REFERENCES shops(id), version bigint NOT NULL,
    snapshot jsonb NOT NULL, deleted boolean NOT NULL DEFAULT false,
    recorded_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(resource_id,version)
);
INSERT INTO knowledge_history(resource_id,shop_id,version,snapshot)
SELECT id,shop_id,version,to_jsonb(knowledge) FROM knowledge;
CREATE FUNCTION version_knowledge() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.version := OLD.version + 1; NEW.updated_at := now(); RETURN NEW; END $$;
CREATE TRIGGER knowledge_version BEFORE UPDATE ON knowledge FOR EACH ROW EXECUTE FUNCTION version_knowledge();
CREATE FUNCTION archive_knowledge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE tombstone jsonb;
BEGIN
    IF TG_OP='DELETE' THEN
        tombstone := to_jsonb(OLD) || jsonb_build_object('version',OLD.version+1,'deleted_at',now(),'updated_at',now());
        INSERT INTO knowledge_history(resource_id,shop_id,version,snapshot,deleted) VALUES(OLD.id,OLD.shop_id,OLD.version+1,tombstone,true);
        RETURN OLD;
    END IF;
    INSERT INTO knowledge_history(resource_id,shop_id,version,snapshot,deleted) VALUES(NEW.id,NEW.shop_id,NEW.version,to_jsonb(NEW),NEW.deleted_at IS NOT NULL);
    RETURN NEW;
END $$;
CREATE TRIGGER knowledge_archive AFTER INSERT OR UPDATE OR DELETE ON knowledge FOR EACH ROW EXECUTE FUNCTION archive_knowledge();

CREATE TABLE promotions (
    id uuid PRIMARY KEY, shop_id uuid NOT NULL REFERENCES shops(id), product_id uuid,
    title text NOT NULL, description text NOT NULL DEFAULT '', offer_price_cents bigint CHECK(offer_price_cents >= 0 AND offer_price_cents <= 1000000000000),
    starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL CHECK(ends_at > starts_at), active boolean NOT NULL DEFAULT false,
    version bigint NOT NULL DEFAULT 1 CHECK(version > 0), updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(product_id,shop_id) REFERENCES products(id,shop_id)
);
CREATE INDEX promotions_shop_idx ON promotions(shop_id,ends_at);
CREATE TABLE promotion_history (
    resource_id uuid NOT NULL REFERENCES promotions(id), shop_id uuid NOT NULL REFERENCES shops(id), version bigint NOT NULL,
    snapshot jsonb NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(resource_id,version)
);

CREATE TABLE assets (
    id uuid PRIMARY KEY, shop_id uuid NOT NULL REFERENCES shops(id), kind text NOT NULL CHECK(kind IN ('avatar','voice','model')),
    name text NOT NULL, identifier text NOT NULL, sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), model_version text NOT NULL DEFAULT '',
    authorized boolean NOT NULL DEFAULT false, active boolean NOT NULL DEFAULT false CHECK(NOT active OR authorized),
    version bigint NOT NULL DEFAULT 1 CHECK(version > 0), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX assets_active_kind_idx ON assets(shop_id,kind) WHERE active;
CREATE TABLE asset_history (
    resource_id uuid NOT NULL REFERENCES assets(id), shop_id uuid NOT NULL REFERENCES shops(id), version bigint NOT NULL,
    snapshot jsonb NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(resource_id,version)
);

CREATE TABLE cost_settings (
    shop_id uuid PRIMARY KEY REFERENCES shops(id), input_cny_per_million numeric(16,6), output_cny_per_million numeric(16,6),
    electricity_cny_per_kwh numeric(16,6), device_watts numeric(16,3), monthly_budget_cny numeric(16,4),
    notes text NOT NULL DEFAULT '', version bigint NOT NULL DEFAULT 1 CHECK(version > 0), updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK(input_cny_per_million>=0 AND output_cny_per_million>=0 AND electricity_cny_per_kwh>=0 AND device_watts>=0 AND monthly_budget_cny>=0)
);
CREATE TABLE usage_events (
    id uuid PRIMARY KEY, shop_id uuid NOT NULL REFERENCES shops(id), session_id uuid NOT NULL, job_id uuid REFERENCES speech_jobs(id),
    model text NOT NULL, status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','complete','unknown')),
    input_tokens bigint NOT NULL DEFAULT 0 CHECK(input_tokens>=0), output_tokens bigint NOT NULL DEFAULT 0 CHECK(output_tokens>=0),
    error_code text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(session_id,shop_id) REFERENCES live_sessions(id,shop_id)
);
CREATE UNIQUE INDEX usage_job_idx ON usage_events(job_id) WHERE job_id IS NOT NULL;
CREATE INDEX usage_shop_idx ON usage_events(shop_id,created_at DESC);
