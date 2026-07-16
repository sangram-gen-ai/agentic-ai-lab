-- Durable chat conversation / audit log (Phase 2)
-- Redis holds ephemeral session context; this table keeps permanent history.
-- Runs against the "spring_ai" schema (spring.flyway.schemas) — not "public",
-- which n8n_user has blanket default privileges on. See scripts/init-db.sql.

CREATE TABLE chat_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    session_id      VARCHAR(64)  NOT NULL,
    user_message    TEXT         NOT NULL,
    assistant_message TEXT       NOT NULL,
    model_id        VARCHAR(128) NOT NULL,
    client_ip       VARCHAR(64),
    latency_ms      BIGINT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chat_audit_session_created
    ON chat_audit_log (session_id, created_at DESC);

CREATE INDEX idx_chat_audit_created
    ON chat_audit_log (created_at DESC);
