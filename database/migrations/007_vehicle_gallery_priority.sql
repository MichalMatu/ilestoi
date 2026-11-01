ALTER TABLE field_photos ADD COLUMN vehicle_gallery_priority INTEGER NOT NULL DEFAULT 0
    CHECK (vehicle_gallery_priority BETWEEN 0 AND 3);
CREATE INDEX IF NOT EXISTS idx_field_photos_vehicle_gallery
    ON field_photos (vehicle_gallery_priority DESC, created_at DESC)
    WHERE issue_type = 'vehicle' AND public_review_status = 'approved'
      AND vehicle_resolution_status = 'active' AND vehicle_gallery_priority > 0;
INSERT OR IGNORE INTO schema_migrations (version) VALUES ('007_vehicle_gallery_priority');
