CREATE TABLE live_readiness_runs (
 id uuid PRIMARY KEY,
 shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
 title text NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
 output_mode text NOT NULL CHECK(output_mode IN ('virtual_camera','srs')),
 conclusion text NOT NULL DEFAULT 'incomplete' CHECK(conclusion IN ('incomplete','failed','local_chain_passed_platform_blocked','platform_chain_passed')),
 version bigint NOT NULL DEFAULT 1 CHECK(version > 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX live_readiness_runs_shop_idx ON live_readiness_runs(shop_id,updated_at DESC);
CREATE TABLE live_readiness_gates (
 run_id uuid NOT NULL REFERENCES live_readiness_runs(id) ON DELETE CASCADE,
 name text NOT NULL CHECK(name IN ('install','generation','obs','platform','stability')),
 status text NOT NULL CHECK(status IN ('passed','failed','blocked')),
 evidence jsonb NOT NULL DEFAULT '{}',
 note text NOT NULL DEFAULT '' CHECK(length(note) <= 2000),
 version bigint NOT NULL DEFAULT 1 CHECK(version > 0),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(run_id,name)
);
