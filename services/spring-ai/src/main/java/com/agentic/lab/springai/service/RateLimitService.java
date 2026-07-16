package com.agentic.lab.springai.service;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

/**
 * Fixed-window rate limiter backed by Redis INCR + EXPIRE.
 * Protects Bedrock spend when n8n, FastAPI, or clients call /chat in loops.
 */
@Service
public class RateLimitService {

    private static final String KEY_PREFIX = "rate:chat:";

    private final StringRedisTemplate redis;
    private final int maxRequests;
    private final Duration window;

    public RateLimitService(
            StringRedisTemplate redis,
            @Value("${agentic.redis.rate-limit-max:20}") int maxRequests,
            @Value("${agentic.redis.rate-limit-window-seconds:60}") int windowSeconds) {
        this.redis = redis;
        this.maxRequests = maxRequests;
        this.window = Duration.ofSeconds(windowSeconds);
    }

    /**
     * @return remaining requests in the current window after this call
     * @throws RateLimitExceededException when the caller is over the limit
     */
    public int checkAndIncrement(String clientKey) {
        String key = KEY_PREFIX + clientKey;
        Long count = redis.opsForValue().increment(key);
        if (count == null) {
            count = 1L;
        }

        // Self-heal: if a prior EXPIRE was lost (e.g. connection drop between
        // INCR and EXPIRE), this key would otherwise never get a TTL and the
        // caller would be rate-limited forever. Re-check on every call instead
        // of only when count == 1.
        Long remainingTtl = redis.getExpire(key);
        if (remainingTtl == null || remainingTtl < 0) {
            redis.expire(key, window);
        }

        if (count > maxRequests) {
            throw new RateLimitExceededException(maxRequests, window.getSeconds());
        }
        return (int) (maxRequests - count);
    }

    public int getMaxRequests() {
        return maxRequests;
    }
}
