# RunMyCampus AI Architecture and Model Improvement

**Every requirement in this document is non-negotiable.** This is the single source of truth for AI as a platform layer. No item is optional or deferred.

## Core AI philosophy

- Context before cleverness
- Actionable (AI can act with approval, not only advise)
- Safe by design
- Grounded in platform truth
- Continuously improving
- Multi-model

## Top-level architecture

- **Experience surfaces** → AI orchestrator (router, permissions, tool selection, audit)
- **RAG + context layer:** docs, registries, runtime, policies, config, marketplace
- **Model routing layer:** reasoning, prediction, generation, classification, recommendation, embeddings
- **AI capability layer:** Migration AI, Onboarding AI, Workflow AI, Dashboard AI, Policy AI, Support AI, Analytics/Prediction AI, Marketplace AI, Template/Content AI
- **Action layer:** create workflows, apply mappings, generate dashboards, draft templates
- **Insight/prediction layer:** risk scoring, forecasting, recommendations
- **Data + learning layer:** canonical model, event streams, support logs, feedback, synthetic data, evaluation sets, telemetry

## Capability modules (all required)

- **Migration AI:** source detection, schema fingerprinting, field mapping, duplicate detection, repair suggestions, cutover strategy, parity review
- **Onboarding AI:** recommend blueprints/dashboards/workflows, infer setup from questions/website, explain plans
- **Workflow AI:** generate workflow from intent, triggers, roles, approval steps, simulate, lint
- **Dashboard AI:** suggest KPIs/widgets, generate layouts, benchmarks
- **Policy AI:** explain bundles, compare, impact, conflicts, region-compatible suggestions
- **Marketplace AI:** recommend apps/packs by institution, starter bundles, trust/compliance
- **Support AI:** explain behavior, diagnose config, suggest fixes, KB retrieval
- **Analytics/Prediction AI:** attendance/fee risk, enrollment forecast, intervention recommendations
- **Template/Content AI:** communication drafts, report narratives, onboarding content

## Improving the AI model (all required)

- **Education data lake:** anonymized telemetry (migrations, workflows, config, support, adoption); patterns for training
- **Domain fine-tuning:** education policies, workflows, migration mappings, onboarding decision trees; fine-tuned models per task
- **RAG:** retrieve from platform docs, tenant runtime, registries, workflow/policy definitions, marketplace metadata; reduce hallucinations. Ref: `AIEmbeddingStore`, `services/ai_memory.py`, inference
- **Continuous feedback:** accepted/rejected suggestions, overrides, migration corrections; feedback as training signal
- **Synthetic data:** migration/workflow/policy simulations for safe training and QA. Ref: Dry-run and sandbox as data sources
- **Evaluation harness:** per-capability evaluation sets; regression and quality gates
- **AI observability:** task success rate, acceptance rate, error rate, rollback rate, time saved; dashboards. Required
- **Multi-model routing:** different models for reasoning, prediction, generation, classification; router selects by task. Ref: RegionalAIConfig, AIModelRegistry, inference.py
- **Human-in-the-loop:** approval for policy changes, migration repairs, workflow deploy, mass comms; audit and rollback

## Action flow

Intent → Orchestrator → Context + permission → Action plan → Preview/simulation → Approval (if needed) → Execution → Audit + outcome

## Risks and guardrails (all required)

- Hallucinations, privacy, unsafe automation, bias, tenant isolation
- Tenant-scoped retrieval, role checks, approval, audit, confidence scores, sandbox-first

## Additional AI improvements (all non-negotiable)

- **Education knowledge graph:** entities (School, Student, Teacher, Guardian, Course, Section, Attendance, Grade, Policy, Workflow); relationships for reasoning
- **Action layer:** AI must be able to act (create workflow, configure, deploy with approval), not only advise
- **Learning layer:** every interaction improves the system (accepted/rejected suggestions, overrides, corrections as training signal)
- **AI simulation engine:** run simulations (admissions season, attendance crisis, fee drop, policy change) before deploying
- **AI observability:** task success rate, acceptance rate, error rate, rollback rate, time saved; dashboards
- **AI marketplace (installable AI skills):** e.g. Admissions AI, Attendance Risk AI, Finance Collections AI, Student Success AI, Counselor Assistant AI

## Gateway and tiered implementation

All product AI goes through the **RunMyCampus AI Gateway** (`services.ai_gateway`): task-based routing (Ollama, vLLM, LiteLLM, rules), structured output validation, audit, data-tier governance. Scope, phases, and deliverables are tracked only in the **RunMyCampus Open-Source AI Adoption Blueprint** (single plan); do not duplicate in other backlog files. See [docs/architecture/ai_orchestration.md](architecture/ai_orchestration.md) and [docs/architecture/ai_tiered_ollama.md](architecture/ai_tiered_ollama.md).

## References

- [AI_MODEL_LIFECYCLE.md](AI_MODEL_LIFECYCLE.md)
- [architecture/ai_orchestration.md](architecture/ai_orchestration.md), [architecture/ai_tiered_ollama.md](architecture/ai_tiered_ollama.md)
- RegionalAIConfig, AIEmbeddingStore, AIModelRegistry
- services/inference.py, services/ai_gateway.py, services/ai_schemas.py, services/embeddings.py, services/ai_memory.py
- Super AI model hub
