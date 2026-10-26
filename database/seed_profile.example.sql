-- Fictional demonstration profile for CareerForge.
-- This file is safe example data, not a real person's resume.
-- Apply database/schema.sql first.
-- Run this seed manually; setup scripts should never apply it automatically.

BEGIN;

WITH demo_profile AS (
    INSERT INTO career_profiles (
        full_name,
        email,
        location,
        professional_summary
    )
    VALUES (
        'Alex Example',
        'alex.example@example.com',
        'Nairobi, Kenya',
        'Entry-level software developer interested in backend APIs and database-driven applications.'
    )
    RETURNING id
)
INSERT INTO education (
    profile_id,
    institution,
    qualification,
    field_of_study,
    start_date,
    end_date
)
SELECT
    id,
    'Example University',
    'Bachelor of Science',
    'Information Technology',
    DATE '2022-09-01',
    DATE '2026-06-30'
FROM demo_profile;

COMMIT;
