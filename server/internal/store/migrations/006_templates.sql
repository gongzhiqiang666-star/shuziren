CREATE TABLE speech_templates (
 id uuid PRIMARY KEY,shop_id uuid NOT NULL REFERENCES shops(id),name text NOT NULL,body text NOT NULL,
 version bigint NOT NULL DEFAULT 1,updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX speech_templates_shop ON speech_templates(shop_id,updated_at DESC);
