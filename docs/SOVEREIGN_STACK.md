# Sovereign Stack — Technology Choices

Single source for allowed technology choices and the **no-paid-API** rule. No conflicting lists elsewhere. Link from [WORLD_ENGINE_SCALE_OPERATIONS.md](WORLD_ENGINE_SCALE_OPERATIONS.md).

## Component → Sovereign choice

| Component | Sovereign choice |
|-----------|------------------|
| AI inference | Ollama + Llama/Mistral (self-hosted) |
| Vector DB | PGVector (Postgres extension) |
| Maps | OSM + Leaflet |
| Search | Meilisearch / Typesense (self-hosted) |
| Email | Postal (self-hosted) or SMTP |
| SMS | Kannel (self-hosted) |
| Charts | Superset / Chart.js |
| Real-time | Django Channels + Redis channel layer |
| Cache | Redis |
| Queue | Celery + Redis/RabbitMQ |

## No-API rule

**No external SaaS APIs for core features; self-hosted only.** Tenant data and core workflows (grading, attendance, finance, AI-assisted support, reports) must not depend on paid or third-party SaaS APIs. **In-product chat uses self-hosted Ollama** (see `docs/OLLAMA_OPERATIONS_AND_UPDATES.md`). Optional **LiteLLM** proxy for specific gateway tasks is separate and subject to data-tier rules in `docs/architecture/ai_orchestration.md`.

## Vector store (AI memory)

Long-term AI memory (support agent, chat context, RAG) is stored in Postgres using **PGVector** only. Do not introduce ChromaDB or another vector store in parallel for the same use case. See [WORLD_ENGINE_SCALE_OPERATIONS.md](WORLD_ENGINE_SCALE_OPERATIONS.md) and the AI memory service in `services/`.

### Enabling PGVector

- **PostgreSQL:** Install the extension on the server (e.g. `apt install postgresql-16-pgvector` or equivalent). The migration `siteconfig.0123_enable_pgvector_extension` runs `CREATE EXTENSION IF NOT EXISTS vector` on PostgreSQL only; it is a no-op on SQLite. After the extension is enabled, you can add native vector columns (e.g. via `django-pgvector`) for similarity search; until then, embeddings are stored in `AIEmbeddingStore.embedding` (JSONField) and the service uses in-memory similarity when needed.
