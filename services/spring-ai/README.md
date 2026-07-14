# Spring AI Service (Phase 2)

Spring Boot + Spring AI service integrated with AWS Bedrock (Amazon Nova Lite).

## Planned responsibilities

- REST API for chat completion and AI orchestration
- Connect to `postgres:5432` and `redis:6379` on `agentic-ai-network`
- AWS Bedrock runtime client for Nova Lite
- Expose `http://spring-ai:8080` for n8n workflows (Phase 5)
- Load agent prompts from `../../prompts/agents/`

## Scaffold checklist

- [ ] Initialize Spring Boot 3 project (Java 21)
- [ ] Add Spring AI + AWS Bedrock dependencies
- [ ] Add `Dockerfile`
- [ ] Uncomment `spring-ai` service in `docker-compose.yml`
