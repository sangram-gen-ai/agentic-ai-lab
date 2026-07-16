package com.agentic.lab.springai.repository;

import com.agentic.lab.springai.entity.ChatAuditLog;
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ChatAuditLogRepository extends JpaRepository<ChatAuditLog, Long> {

    List<ChatAuditLog> findBySessionId(String sessionId, Pageable pageable);

    long deleteByCreatedAtBefore(Instant cutoff);
}
