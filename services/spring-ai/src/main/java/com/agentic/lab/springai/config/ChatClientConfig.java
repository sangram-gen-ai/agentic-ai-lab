package com.agentic.lab.springai.config;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ChatClientConfig {

    @Bean
    ChatClient chatClient(
            ChatClient.Builder builder,
            @Value("${agentic.ai.system-prompt}") String systemPrompt) {
        return builder
                .defaultSystem(systemPrompt)
                .build();
    }
}
