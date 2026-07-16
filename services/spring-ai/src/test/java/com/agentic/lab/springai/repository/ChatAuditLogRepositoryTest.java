package com.agentic.lab.springai.repository;

import com.agentic.lab.springai.entity.ChatAuditLog;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Exercises the real Flyway migration (V1__chat_audit_log.sql) against the
 * "spring_ai" schema on a real Postgres, not just the repository interface —
 * catching drift between the entity mapping and the migration SQL that a
 * mocked-repository test never would.
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class ChatAuditLogRepositoryTest {

    @Container
    static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:16-alpine");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @Autowired
    ChatAuditLogRepository repository;

    @PersistenceContext
    EntityManager entityManager;

    @Test
    void migrationCreatesTableAndSaveRoundTrips() {
        ChatAuditLog saved = repository.save(
                new ChatAuditLog("session-1", "hi", "hello", "amazon.nova-lite-v1:0", "127.0.0.1", 42L));

        assertThat(saved.getId()).isNotNull();

        List<ChatAuditLog> found = repository.findBySessionId("session-1", PageRequest.of(0, 10));
        assertThat(found).hasSize(1);
        assertThat(found.get(0).getUserMessage()).isEqualTo("hi");
        assertThat(found.get(0).getAssistantMessage()).isEqualTo("hello");
    }

    @Test
    void findBySessionIdPaginatesInChronologicalOrder() {
        for (int i = 0; i < 5; i++) {
            repository.save(new ChatAuditLog(
                    "paged-session", "msg" + i, "reply" + i, "model", "127.0.0.1", 1L));
        }

        Sort byCreatedAtAsc = Sort.by("createdAt").ascending();
        List<ChatAuditLog> page0 = repository.findBySessionId("paged-session", PageRequest.of(0, 2, byCreatedAtAsc));
        List<ChatAuditLog> page1 = repository.findBySessionId("paged-session", PageRequest.of(1, 2, byCreatedAtAsc));

        assertThat(page0).extracting(ChatAuditLog::getUserMessage).containsExactly("msg0", "msg1");
        assertThat(page1).extracting(ChatAuditLog::getUserMessage).containsExactly("msg2", "msg3");
    }

    @Test
    void deleteByCreatedAtBeforeRemovesOnlyOldEntries() {
        ChatAuditLog oldEntry = repository.save(
                new ChatAuditLog("old-session", "old msg", "old reply", "model", "127.0.0.1", 1L));
        ChatAuditLog recentEntry = repository.save(
                new ChatAuditLog("recent-session", "recent msg", "recent reply", "model", "127.0.0.1", 1L));

        // Backdate the "old" row directly in the DB — the entity has no setter
        // for createdAt, and the constructor always stamps Instant.now().
        entityManager.createNativeQuery("UPDATE spring_ai.chat_audit_log SET created_at = ?1 WHERE id = ?2")
                .setParameter(1, Instant.now().minus(100, ChronoUnit.DAYS))
                .setParameter(2, oldEntry.getId())
                .executeUpdate();
        entityManager.clear();

        long deleted = repository.deleteByCreatedAtBefore(Instant.now().minus(90, ChronoUnit.DAYS));

        assertThat(deleted).isEqualTo(1);
        assertThat(repository.findById(oldEntry.getId())).isEmpty();
        assertThat(repository.findById(recentEntry.getId())).isPresent();
    }
}
