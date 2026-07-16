package com.agentic.lab.springai;

import com.agentic.lab.springai.dto.ChatAuditEntry;
import com.agentic.lab.springai.dto.ChatRequest;
import com.agentic.lab.springai.dto.ChatResponse;
import com.redis.testcontainers.RedisContainer;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.RestClient;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

/**
 * Live AWS Bedrock (Nova Lite) integration test.
 *
 * <p>Skipped automatically when {@code AWS_ACCESS_KEY_ID} or {@code AWS_SECRET_ACCESS_KEY}
 * are unset — so default {@code mvn test} stays green in CI without AWS. To run locally
 * or in CI with Bedrock access:
 *
 * <pre>
 *   set -a && source ../../.env && set +a   # from services/spring-ai, or export keys
 *   mvn test -Dtest=BedrockChatIntegrationTest
 * </pre>
 *
 * Tagged {@code bedrock} so you can also select: {@code mvn test -Dgroups=bedrock}.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
@Tag("bedrock")
@EnabledIfEnvironmentVariable(named = "AWS_ACCESS_KEY_ID", matches = ".+")
@EnabledIfEnvironmentVariable(named = "AWS_SECRET_ACCESS_KEY", matches = ".+")
class BedrockChatIntegrationTest {

    private static final String ADMIN_USER = "admin";
    private static final String ADMIN_PASSWORD = "test-admin-password";

    @Container
    static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:16-alpine");

    @Container
    static final RedisContainer REDIS = new RedisContainer(RedisContainer.DEFAULT_IMAGE_NAME);

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);

        registry.add("spring.data.redis.host", REDIS::getRedisHost);
        registry.add("spring.data.redis.port", () -> String.valueOf(REDIS.getRedisPort()));
        registry.add("spring.data.redis.password", () -> "");

        registry.add("spring.ai.bedrock.aws.region",
                () -> firstNonBlank(System.getenv("AWS_REGION"), "us-east-1"));
        registry.add("spring.ai.bedrock.aws.access-key", () -> System.getenv("AWS_ACCESS_KEY_ID"));
        registry.add("spring.ai.bedrock.aws.secret-key", () -> System.getenv("AWS_SECRET_ACCESS_KEY"));
        registry.add("spring.ai.bedrock.converse.chat.options.model",
                () -> firstNonBlank(System.getenv("BEDROCK_MODEL_ID"), "amazon.nova-lite-v1:0"));

        registry.add("agentic.security.admin.username", () -> ADMIN_USER);
        registry.add("agentic.security.admin.password", () -> ADMIN_PASSWORD);
    }

    @LocalServerPort
    int port;

    private RestClient client() {
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory();
        factory.setReadTimeout(Duration.ofSeconds(60));
        return RestClient.builder()
                .baseUrl("http://localhost:" + port)
                .requestFactory(factory)
                .build();
    }

    @Test
    @Timeout(90)
    void chatCompletesAgainstNovaLiteAndPersistsAudit() {
        ChatResponse response = client().post()
                .uri("/api/v1/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ChatRequest(
                        "Reply with exactly one word: pong",
                        "bedrock-it-" + System.currentTimeMillis()))
                .retrieve()
                .body(ChatResponse.class);

        assertThat(response).isNotNull();
        assertThat(response.message()).containsIgnoringCase("pong");
        assertThat(response.model()).containsIgnoringCase("nova");
        assertThat(response.sessionId()).startsWith("bedrock-it-");
        assertThat(response.rateLimitRemaining()).isGreaterThanOrEqualTo(0);

        // Audit is @Async — wait briefly for the row to land in Postgres.
        await().atMost(Duration.ofSeconds(15))
                .pollInterval(Duration.ofMillis(250))
                .untilAsserted(() -> {
                    List<ChatAuditEntry> audit = client().get()
                            .uri("/api/v1/chat/sessions/{id}/audit", response.sessionId())
                            .headers(h -> h.setBasicAuth(ADMIN_USER, ADMIN_PASSWORD))
                            .retrieve()
                            .body(new ParameterizedTypeReference<>() {});

                    assertThat(audit).isNotNull().isNotEmpty();
                    assertThat(audit.getFirst().userMessage()).contains("pong");
                    assertThat(audit.getFirst().assistantMessage()).containsIgnoringCase("pong");
                    assertThat(audit.getFirst().modelId()).containsIgnoringCase("nova");
                });
    }

    @Test
    @Timeout(90)
    void multiTurnSessionUsesRedisHistoryAgainstBedrock() {
        String sessionId = "bedrock-multi-" + System.currentTimeMillis();

        ChatResponse first = client().post()
                .uri("/api/v1/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ChatRequest("Remember the secret codeword is ORBIT. Confirm with OK.", sessionId))
                .retrieve()
                .body(ChatResponse.class);

        assertThat(first).isNotNull();
        assertThat(first.sessionId()).isEqualTo(sessionId);

        ChatResponse second = client().post()
                .uri("/api/v1/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ChatRequest(
                        "What is the secret codeword I just told you? Reply with only that word.",
                        sessionId))
                .retrieve()
                .body(ChatResponse.class);

        assertThat(second).isNotNull();
        assertThat(second.message()).containsIgnoringCase("ORBIT");
    }

    private static String firstNonBlank(String... values) {
        return Arrays.stream(values)
                .filter(v -> v != null && !v.isBlank())
                .findFirst()
                .orElse("");
    }
}
