package com.agentic.lab.springai.service;

import com.redis.testcontainers.RedisContainer;
import java.util.UUID;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Testcontainers
class RateLimitServiceTest {

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
    void allowsRequestsUpToLimitThenThrows() {
        RateLimitService service = new RateLimitService(redisTemplate, 3, 60);
        String clientKey = "client-" + UUID.randomUUID();

        assertThat(service.checkAndIncrement(clientKey)).isEqualTo(2);
        assertThat(service.checkAndIncrement(clientKey)).isEqualTo(1);
        assertThat(service.checkAndIncrement(clientKey)).isEqualTo(0);
        assertThatThrownBy(() -> service.checkAndIncrement(clientKey))
                .isInstanceOf(RateLimitExceededException.class);
    }

    @Test
    void independentClientKeysHaveIndependentLimits() {
        RateLimitService service = new RateLimitService(redisTemplate, 1, 60);
        String clientA = "client-" + UUID.randomUUID();
        String clientB = "client-" + UUID.randomUUID();

        assertThat(service.checkAndIncrement(clientA)).isEqualTo(0);
        assertThatThrownBy(() -> service.checkAndIncrement(clientA))
                .isInstanceOf(RateLimitExceededException.class);

        // A fresh client key (e.g. a different caller) must not be blocked by client A's usage.
        assertThat(service.checkAndIncrement(clientB)).isEqualTo(0);
    }

    @Test
    void selfHealsWhenExpireWasLost() {
        RateLimitService service = new RateLimitService(redisTemplate, 20, 60);
        String clientKey = "heal-" + UUID.randomUUID();
        String redisKey = "rate:chat:" + clientKey;

        service.checkAndIncrement(clientKey);

        // Simulate a lost EXPIRE (e.g. dropped connection between INCR and EXPIRE).
        redisTemplate.persist(redisKey);
        assertThat(redisTemplate.getExpire(redisKey)).isLessThan(0);

        service.checkAndIncrement(clientKey);

        assertThat(redisTemplate.getExpire(redisKey)).isGreaterThan(0);
    }
}
