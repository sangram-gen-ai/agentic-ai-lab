package com.agentic.lab.springai.service;

import com.agentic.lab.springai.repository.ChatAuditLogRepository;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.dao.DataAccessResourceFailureException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ChatAuditServiceTest {

    @Test
    void recordSwallowsRepositoryFailuresInsteadOfPropagating() {
        ChatAuditLogRepository repository = mock(ChatAuditLogRepository.class);
        when(repository.save(any())).thenThrow(new DataAccessResourceFailureException("db unavailable"));

        ChatAuditService service = new ChatAuditService(repository, 90);

        // A Postgres outage must never surface as a failure to the chat caller —
        // the audit trail is a durability nice-to-have, not a hard dependency.
        assertThatCode(() -> service.record("session-1", "hi", "hello", "model", "127.0.0.1", 10L))
                .doesNotThrowAnyException();
    }

    @Test
    void purgeDeletesEntriesOlderThanConfiguredRetention() {
        ChatAuditLogRepository repository = mock(ChatAuditLogRepository.class);
        when(repository.deleteByCreatedAtBefore(any())).thenReturn(3L);
        ChatAuditService service = new ChatAuditService(repository, 90);

        service.purgeExpiredEntries();

        ArgumentCaptor<Instant> cutoffCaptor = ArgumentCaptor.forClass(Instant.class);
        verify(repository).deleteByCreatedAtBefore(cutoffCaptor.capture());

        Instant expectedCutoff = Instant.now().minus(90, ChronoUnit.DAYS);
        assertThat(cutoffCaptor.getValue()).isCloseTo(expectedCutoff, within(5, ChronoUnit.SECONDS));
    }

    private static org.assertj.core.data.TemporalUnitWithinOffset within(long amount, ChronoUnit unit) {
        return new org.assertj.core.data.TemporalUnitWithinOffset(amount, unit);
    }
}
