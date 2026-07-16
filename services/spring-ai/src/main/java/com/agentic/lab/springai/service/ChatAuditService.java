package com.agentic.lab.springai.service;

import com.agentic.lab.springai.entity.ChatAuditLog;
import com.agentic.lab.springai.repository.ChatAuditLogRepository;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Pageable;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Persists each chat turn to PostgreSQL for durable conversation / audit history.
 * Redis holds short-lived session context; this table survives restarts and TTL expiry.
 *
 * <p>record() is fire-and-forget: it must never fail or block the chat response,
 * since the audit trail is a durability nice-to-have, not a requirement for the
 * chat call itself (Bedrock already answered and Redis history already updated
 * by the time this runs).
 */
@Service
public class ChatAuditService {

    private static final Logger log = LoggerFactory.getLogger(ChatAuditService.class);

    private final ChatAuditLogRepository repository;
    private final int retentionDays;

    public ChatAuditService(
            ChatAuditLogRepository repository,
            @Value("${agentic.audit.retention-days:90}") int retentionDays) {
        this.repository = repository;
        this.retentionDays = retentionDays;
    }

    // No @Transactional here: repository.save() already runs in its own
    // transaction (Spring Data JPA wraps CRUD methods), and an outer
    // @Transactional would open the DB connection before this method body
    // runs, throwing outside the try/catch below.
    @Async
    public void record(
            String sessionId,
            String userMessage,
            String assistantMessage,
            String modelId,
            String clientIp,
            long latencyMs) {
        try {
            ChatAuditLog entry = new ChatAuditLog(
                    sessionId, userMessage, assistantMessage, modelId, clientIp, latencyMs);
            repository.save(entry);
            log.debug("Audited chat turn sessionId={} latencyMs={}", sessionId, latencyMs);
        } catch (Exception e) {
            log.warn("Failed to persist chat audit log sessionId={}", sessionId, e);
        }
    }

    @Transactional(readOnly = true)
    public List<ChatAuditLog> findBySession(String sessionId, Pageable pageable) {
        return repository.findBySessionId(sessionId, pageable);
    }

    /**
     * Unlike Redis (TTL + max-messages cap), chat_audit_log has no built-in expiry —
     * a session reused indefinitely would otherwise grow this table forever. Mirrors
     * Redis's TTL concept at the durable-storage layer.
     */
    @Scheduled(cron = "${agentic.audit.purge-cron:0 0 3 * * *}")
    @Transactional
    public void purgeExpiredEntries() {
        Instant cutoff = Instant.now().minus(retentionDays, ChronoUnit.DAYS);
        long deleted = repository.deleteByCreatedAtBefore(cutoff);
        if (deleted > 0) {
            log.info("Purged {} chat audit log entries older than {} days", deleted, retentionDays);
        }
    }
}
