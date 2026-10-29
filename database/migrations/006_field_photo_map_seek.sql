-- Keyset pagination orders map rows by created_at and ID. This index also
-- avoids materializing a full sort for the legacy unbounded map endpoint.
CREATE INDEX IF NOT EXISTS idx_field_photos_map_seek
    ON field_photos (created_at DESC, id DESC);

INSERT OR IGNORE INTO schema_migrations (version)
VALUES ('006_field_photo_map_seek');
