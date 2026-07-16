package com.agentic.lab.springai.service;

import com.redis.testcontainers.RedisContainer;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class ChatSessionServiceTest {

    @Container
    static final RedisContainer REDIS = new RedisContainer(RedisContainer.DEFAULT_IMAGE_NAME);

    static StringRedisTemplate redisTemplate;

    @BeforeAll
    static void setUpRedis() {
        LettuceConnectionFactory factory =
                new LettuceConnectionFactory(REDIS.getRedisHost(), REDIS.getRedisPort());
        factory.afterPropertiesSet();
        redisTemplate = new StringRedisTemplate(factory);
    }

    @Test
    void newSessionHasEmptyHistory() {
        ChatSessionService service = new ChatSessionService(redisTemplate, 30, 20);
        assertThat(service.getHistory("nonexistent-" + UUID.randomUUID())).isEmpty();
    }

    @Test
    void appendThenGetHistoryPreservesOrder() {
        ChatSessionService service = new ChatSessionService(redisTemplate, 30, 20);
        String sessionId = "order-" + UUID.randomUUID();

        service.append(sessionId, "hello", "hi there");
        service.append(sessionId, "how are you", "great, thanks");

        List<ChatSessionService.ChatTurn> history = service.getHistory(sessionId);
        assertThat(history).extracting(ChatSessionService.ChatTurn::content)
                .containsExactly("hello", "hi there", "how are you", "great, thanks");
    }

    @Test
    void trimsOldestTurnsOnceOverCap() {
        ChatSessionService service = new ChatSessionService(redisTemplate, 30, 4);
        String sessionId = "trim-" + UUID.randomUUID();

        service.append(sessionId, "msg1", "reply1");
        service.append(sessionId, "msg2", "reply2");
        service.append(sessionId, "msg3", "reply3");

        List<ChatSessionService.ChatTurn> history = service.getHistory(sessionId);
        assertThat(history).extracting(ChatSessionService.ChatTurn::content)
                .containsExactly("msg2", "reply2", "msg3", "reply3");
    }

    @Test
    void concurrentAppendsToSameSessionDoNotLoseTurns() throws InterruptedException {
        ChatSessionService service = new ChatSessionService(redisTemplate, 30, 1000);
        String sessionId = "concurrent-" + UUID.randomUUID();
        int callers = 10;

        ExecutorService pool = Executors.newFixedThreadPool(callers);
        CountDownLatch latch = new CountDownLatch(callers);
        for (int i = 0; i < callers; i++) {
            int idx = i;
            pool.submit(() -> {
                try {
                    service.append(sessionId, "msg" + idx, "reply" + idx);
                } finally {
                    latch.countDown();
                }
            });
        }
        assertThat(latch.await(10, TimeUnit.SECONDS)).isTrue();
        pool.shutdown();

        // Every caller's user+assistant turn must survive — no lost updates.
        assertThat(service.getHistory(sessionId)).hasSize(callers * 2);
    }
}
