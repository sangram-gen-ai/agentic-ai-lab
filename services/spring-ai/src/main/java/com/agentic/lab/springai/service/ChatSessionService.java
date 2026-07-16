package com.agentic.lab.springai.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

/**
 * Stores multi-turn chat history in Redis so follow-up messages keep context
 * without re-sending the full transcript on every request.
 *
 * <p>Each turn is a separate element in a Redis list (RPUSH/LTRIM), not a single
 * read-modify-write JSON blob, so concurrent appends to the same session can't
 * silently overwrite one another.
 */
@Service
public class ChatSessionService {

    private static final String KEY_PREFIX = "chat:session:";

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final Duration ttl;
    private final int maxMessages;

    public ChatSessionService(
            StringRedisTemplate redis,
            @Value("${agentic.redis.session-ttl-minutes:30}") int ttlMinutes,
            @Value("${agentic.redis.session-max-messages:20}") int maxMessages) {
        this.redis = redis;
        this.ttl = Duration.ofMinutes(ttlMinutes);
        this.maxMessages = maxMessages;
    }

    public String resolveSessionId(String sessionId) {
        return (sessionId == null || sessionId.isBlank()) ? UUID.randomUUID().toString() : sessionId;
    }

    public List<ChatTurn> getHistory(String sessionId) {
        List<String> raw = redis.opsForList().range(KEY_PREFIX + sessionId, 0, -1);
        if (raw == null || raw.isEmpty()) {
            return new ArrayList<>();
        }
        List<ChatTurn> history = new ArrayList<>(raw.size());
        for (String json : raw) {
            try {
                history.add(objectMapper.readValue(json, ChatTurn.class));
            } catch (Exception e) {
                // skip a corrupt entry rather than discarding the whole history
            }
        }
        return history;
    }

    public void append(String sessionId, String userMessage, String assistantMessage) {
        String key = KEY_PREFIX + sessionId;
        try {
            redis.opsForList().rightPushAll(key,
                    objectMapper.writeValueAsString(new ChatTurn("user", userMessage)),
                    objectMapper.writeValueAsString(new ChatTurn("assistant", assistantMessage)));
        } catch (Exception e) {
            throw new IllegalStateException("Failed to persist chat session " + sessionId, e);
        }
        redis.opsForList().trim(key, -maxMessages, -1);
        redis.expire(key, ttl);
    }

    public record ChatTurn(String role, String content) {}
}
