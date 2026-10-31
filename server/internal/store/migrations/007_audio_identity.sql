ALTER TABLE speech_jobs ADD COLUMN audio_engine_id text NOT NULL DEFAULT ''
 CHECK(audio_engine_id='' OR audio_engine_id ~ '^[a-f0-9]{64}$');
