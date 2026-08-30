-- PostgreSQL baseline schema for the AI Interview Coach.
-- The application keeps SQLite-compatible SQL in its repository layer, while
-- PostgreSQL uses native JSONB columns for evolving payloads.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    email TEXT UNIQUE,
    password_hash TEXT,
    is_temporary BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    user_agent TEXT,
    ip_address TEXT
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    skills_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    projects_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    education TEXT,
    experience TEXT,
    constraints_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    title TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    jd_text TEXT NOT NULL DEFAULT '',
    skills_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_license TEXT,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    mode TEXT NOT NULL,
    role TEXT NOT NULL,
    job_text TEXT NOT NULL,
    profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    current_question_json JSONB,
    matched_skills_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS match_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_key TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    score INTEGER NOT NULL,
    source TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (user_id, target_key, input_hash, scoring_version)
);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    url TEXT,
    license TEXT,
    source_type TEXT NOT NULL,
    version TEXT,
    published_at TEXT,
    accessed_at TEXT,
    redistribution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    pii_redacted BOOLEAN NOT NULL DEFAULT TRUE,
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
    skill_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    process_type TEXT NOT NULL,
    role TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    question TEXT NOT NULL,
    follow_ups_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    rubric_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    function_name TEXT,
    tests_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    source_confidence TEXT NOT NULL DEFAULT 'unknown',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS question_skills (
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, skill_id)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    from_type TEXT NOT NULL,
    from_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    to_type TEXT NOT NULL,
    to_id TEXT NOT NULL,
    source_id TEXT,
    UNIQUE (from_type, from_id, relation, to_type, to_id)
);

CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL,
    question_text TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT '',
    code TEXT,
    language TEXT,
    parent_turn_id TEXT,
    answer_mode TEXT NOT NULL DEFAULT 'answer',
    algorithm_result_json JSONB,
    created_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE turns ADD COLUMN IF NOT EXISTS question_text TEXT NOT NULL DEFAULT '';
ALTER TABLE turns ADD COLUMN IF NOT EXISTS parent_turn_id TEXT;
ALTER TABLE turns ADD COLUMN IF NOT EXISTS answer_mode TEXT NOT NULL DEFAULT 'answer';

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS model_invocations (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    task TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    latency_ms DOUBLE PRECISION,
    status TEXT NOT NULL,
    fallback_reason TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd DOUBLE PRECISION,
    attempt INTEGER,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS question_favorites (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, question_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    title TEXT NOT NULL DEFAULT '',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    extracted_text TEXT NOT NULL DEFAULT '',
    parsed_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'uploaded',
    provider TEXT,
    error TEXT,
    linked_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_match_snapshots_lookup ON match_snapshots(user_id, target_key, input_hash, scoring_version);
CREATE INDEX IF NOT EXISTS idx_reports_user ON reports(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_feedback_turn ON feedback(turn_id);
CREATE INDEX IF NOT EXISTS idx_questions_process ON questions(process_type);
CREATE INDEX IF NOT EXISTS idx_questions_active ON questions(is_active);
CREATE INDEX IF NOT EXISTS idx_edges_from ON graph_edges(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON question_favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_candidate_documents_user ON candidate_documents(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id, expires_at);

INSERT INTO schema_migrations(version, description, applied_at)
VALUES (1, 'initial interview and knowledge schema', NOW())
ON CONFLICT (version) DO NOTHING;
INSERT INTO schema_migrations(version, description, applied_at)
VALUES (2, 'source provenance fields and soft-delete support', NOW())
ON CONFLICT (version) DO NOTHING;
INSERT INTO schema_migrations(version, description, applied_at)
VALUES (3, 'temporary users, profiles, jobs, favorites and reports', NOW())
ON CONFLICT (version) DO NOTHING;
INSERT INTO schema_migrations(version, description, applied_at)
VALUES (4, 'model invocation token, cost and retry telemetry', NOW())
ON CONFLICT (version) DO NOTHING;
INSERT INTO schema_migrations(version, description, applied_at)
VALUES (5, 'candidate resume and job-description documents', NOW())
ON CONFLICT (version) DO NOTHING;
INSERT INTO schema_migrations(version, description, applied_at)
VALUES (6, 'registered accounts and hashed authentication sessions', NOW())
ON CONFLICT (version) DO NOTHING;
INSERT INTO schema_migrations(version, description, applied_at)
VALUES (7, 'persisted resume and job match score snapshots', NOW())
ON CONFLICT (version) DO NOTHING;
