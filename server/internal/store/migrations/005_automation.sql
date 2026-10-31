CREATE TABLE generation_limits (
 shop_id uuid PRIMARY KEY REFERENCES shops(id),
 requests_per_minute integer NOT NULL DEFAULT 10 CHECK(requests_per_minute BETWEEN 1 AND 60),
 daily_request_limit bigint NOT NULL DEFAULT 0 CHECK(daily_request_limit BETWEEN 0 AND 100000),
 daily_token_limit bigint NOT NULL DEFAULT 0 CHECK(daily_token_limit BETWEEN 0 AND 1000000000),
 version bigint NOT NULL DEFAULT 1, updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE usage_events ADD COLUMN reserved_tokens bigint NOT NULL DEFAULT 0;
ALTER TABLE usage_events ADD COLUMN charged_tokens bigint NOT NULL DEFAULT 0;
ALTER TABLE usage_events ADD COLUMN quota_date date NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')::date;
UPDATE usage_events SET charged_tokens=input_tokens+output_tokens,quota_date=(created_at AT TIME ZONE 'UTC')::date WHERE status='complete';
CREATE INDEX usage_quota_idx ON usage_events(shop_id,quota_date,created_at);
CREATE FUNCTION update_usage_charge() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.status='complete' THEN NEW.charged_tokens=NEW.input_tokens+NEW.output_tokens;
 ELSE NEW.charged_tokens=NEW.reserved_tokens;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER usage_charge_set BEFORE UPDATE OF status ON usage_events FOR EACH ROW EXECUTE FUNCTION update_usage_charge();
ALTER TABLE speech_jobs ADD COLUMN priority integer NOT NULL DEFAULT 50 CHECK(priority BETWEEN 0 AND 100);
ALTER TABLE speech_jobs ADD COLUMN expires_at timestamptz;
CREATE TABLE speech_schedules (
 id uuid PRIMARY KEY, shop_id uuid NOT NULL REFERENCES shops(id),
 session_id uuid NOT NULL,job_id uuid NOT NULL REFERENCES speech_jobs(id),
 run_at timestamptz NOT NULL, expires_at timestamptz NOT NULL CHECK(expires_at>run_at),
 status text NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled','dispatching','sent','failed','cancelled','delivery_unknown')),
 reason text NOT NULL DEFAULT '',error_code text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(session_id,shop_id) REFERENCES live_sessions(id,shop_id)
);
CREATE UNIQUE INDEX schedule_active_job_idx ON speech_schedules(job_id) WHERE status IN ('scheduled','dispatching');
CREATE INDEX schedule_due_idx ON speech_schedules(run_at) WHERE status='scheduled';
