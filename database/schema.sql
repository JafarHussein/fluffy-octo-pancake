CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Main career profile
CREATE TABLE career_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    location TEXT,
    linkedin_url TEXT,
    github_url TEXT,
    portfolio_url TEXT,
    professional_summary TEXT,
    profile_version INTEGER NOT NULL DEFAULT 1 CHECK (profile_version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Education
CREATE TABLE education (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    institution TEXT NOT NULL,
    qualification TEXT NOT NULL,
    field_of_study TEXT,
    grade TEXT,
    start_date DATE,
    end_date DATE,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    details JSONB NOT NULL DEFAULT '[]'::jsonb,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
    CHECK (NOT is_current OR end_date IS NULL)
);

-- 3. Work experience and industrial attachment
CREATE TABLE experiences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    employer TEXT NOT NULL,
    job_title TEXT NOT NULL,
    location TEXT,
    employment_type TEXT,
    start_date DATE,
    end_date DATE,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    responsibilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    achievements JSONB NOT NULL DEFAULT '[]'::jsonb,
    skills_used JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
    CHECK (NOT is_current OR end_date IS NULL)
);

-- 4. Projects
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    role TEXT,
    technologies JSONB NOT NULL DEFAULT '[]'::jsonb,
    repository_url TEXT,
    demo_url TEXT,
    achievements JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    start_date DATE,
    end_date DATE,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

-- 5. Certifications
CREATE TABLE certifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    issuer TEXT,
    issued_at DATE,
    expires_at DATE,
    credential_url TEXT,
    credential_id TEXT,
    skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_at IS NULL OR issued_at IS NULL OR expires_at >= issued_at)
);

-- 6. Skills and supporting evidence
CREATE TABLE skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT,
    proficiency TEXT,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (profile_id, name)
);

-- 7. Hackathons and technical events
CREATE TABLE hackathons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    organizer TEXT,
    project_name TEXT,
    role TEXT,
    description TEXT,
    outcome TEXT,
    event_date DATE,
    project_url TEXT,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. Proposed WhatsApp or manual career updates
CREATE TABLE career_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    source TEXT NOT NULL DEFAULT 'whatsapp',
    source_message_id TEXT UNIQUE,
    sender_id TEXT NOT NULL,
    raw_message TEXT NOT NULL,
    proposed_change JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    approval_token_hash TEXT UNIQUE,
    revision_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    CHECK (status IN (
        'pending',
        'approved',
        'rejected',
        'revision_requested',
        'applied',
        'failed'
    ))
);

-- 9. Audit log of changes actually made
CREATE TABLE career_change_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    update_id UUID REFERENCES career_updates(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    previous_data JSONB,
    new_data JSONB,
    changed_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. Versioned ATS rules
CREATE TABLE ats_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version INTEGER NOT NULL UNIQUE CHECK (version > 0),
    rules JSONB NOT NULL,
    source_notes JSONB NOT NULL DEFAULT '[]'::jsonb,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- At most one active ruleset at a time
CREATE UNIQUE INDEX idx_ats_rules_single_active
    ON ats_rules (active)
    WHERE active = TRUE;

-- 11. Job applications and job description analysis
CREATE TABLE job_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL,
    job_title TEXT NOT NULL,
    job_url TEXT,
    job_description TEXT NOT NULL,
    analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'saved',
    applied_at TIMESTAMPTZ,
    deadline DATE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status IN (
        'saved',
        'analyzed',
        'resume_ready',
        'applied',
        'interviewing',
        'offered',
        'rejected',
        'withdrawn'
    ))
);

-- 12. Reusable resume templates
CREATE TABLE resume_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    file_path TEXT,
    format TEXT NOT NULL DEFAULT 'docx',
    version INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (format IN ('docx', 'html'))
);

-- 13. Generated resumes and their validation results
CREATE TABLE generated_resumes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES career_profiles(id) ON DELETE CASCADE,
    application_id UUID REFERENCES job_applications(id) ON DELETE SET NULL,
    template_id UUID REFERENCES resume_templates(id) ON DELETE SET NULL,
    profile_version INTEGER NOT NULL,
    ats_rules_version INTEGER,
    selected_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation_results JSONB NOT NULL DEFAULT '{}'::jsonb,
    docx_path TEXT,
    pdf_path TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status IN (
        'draft',
        'validated',
        'ready',
        'failed'
    ))
);

-- Indexes for common workflow queries
CREATE INDEX idx_education_profile
    ON education(profile_id);

CREATE INDEX idx_experiences_profile
    ON experiences(profile_id);

CREATE INDEX idx_projects_profile
    ON projects(profile_id);

CREATE INDEX idx_certifications_profile
    ON certifications(profile_id);

CREATE INDEX idx_skills_profile
    ON skills(profile_id);

CREATE INDEX idx_hackathons_profile
    ON hackathons(profile_id);

CREATE INDEX idx_career_updates_pending
    ON career_updates(status, created_at);

CREATE INDEX idx_change_log_profile
    ON career_change_log(profile_id, created_at DESC);

CREATE INDEX idx_job_applications_profile
    ON job_applications(profile_id, created_at DESC);

CREATE INDEX idx_generated_resumes_application
    ON generated_resumes(application_id, created_at DESC);
