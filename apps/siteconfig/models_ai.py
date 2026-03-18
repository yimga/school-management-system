"""
Phase 10 — 2.1: Giant-file decomposition. AI-related models extracted from siteconfig.models.
Same db_table so existing migrations apply. Re-exported from siteconfig.models for backward compatibility.
"""

from django.db import models


class RegionalAIConfig(models.Model):
    """
    World Engine / Sovereign AI: per-region Ollama endpoint and model (public schema).
    Single source of truth for regional AI; fallback to OLLAMA_ENDPOINT/OLLAMA_MODEL in settings when no row exists.
    """

    regional_cluster = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Region identifier (e.g. country code CM, KE, or cluster name cm-west).",
    )
    ollama_base_url = models.URLField(
        max_length=512,
        help_text="Base URL for Ollama API (e.g. http://ollama-region:11434).",
    )
    default_model = models.CharField(
        max_length=128,
        default="llama3",
        help_text="Default model tag (e.g. llama3.1:8b-q4).",
    )
    preferred_model_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="Optional override: when set, used instead of registry/default (Super Admin can flip without touching LB).",
    )
    fallback_model = models.CharField(
        max_length=128,
        blank=True,
        help_text="Fallback model on timeout/5xx (e.g. smaller quantized model).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_regionalaiconfig"
        ordering = ["regional_cluster"]
        verbose_name = "Regional AI config"
        verbose_name_plural = "Regional AI configs"
        app_label = "siteconfig"

    def __str__(self):
        return f"{self.regional_cluster}: {self.default_model}"


class AIModelRegistry(models.Model):
    """
    World Engine: which model version runs per region/hardware (public schema).
    Single source of truth for model versions; used by OllamaInferenceService and sync_regional_models.
    """

    regional_cluster = models.CharField(max_length=32, db_index=True)
    hardware_tier = models.CharField(
        max_length=32,
        default="default",
        help_text="e.g. 8GB_RAM, GPU, default",
    )
    model_id = models.CharField(
        max_length=128,
        help_text="Ollama model tag (e.g. llama3.1:8b-q4).",
    )
    is_active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(
        default=0,
        help_text="Fallback order (higher = preferred).",
    )
    lora_adapter_path = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_aimodelregistry"
        ordering = ["regional_cluster", "-priority", "hardware_tier"]
        unique_together = [["regional_cluster", "hardware_tier"]]
        verbose_name = "AI model registry"
        verbose_name_plural = "AI model registries"
        app_label = "siteconfig"

    def __str__(self):
        return f"{self.regional_cluster}/{self.hardware_tier}: {self.model_id}"


class AIEmbeddingStore(models.Model):
    """
    World Engine D.2: Long-term AI memory (support agent, chat context, RAG).
    Stores embeddings for similarity search. Use PGVector in production (vector column);
    embedding as JSONField (list of floats) works without pgvector extension.
    """

    school_id = models.UUIDField(db_index=True, null=True, blank=True)
    conversation_id = models.CharField(max_length=64, blank=True, db_index=True)
    scope = models.CharField(max_length=32, default="chat", db_index=True)
    text_hash = models.CharField(max_length=64, db_index=True)
    embedding = models.JSONField(
        default=list, help_text="List of floats from Ollama embeddings API"
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "siteconfig_aiembeddingstore"
        ordering = ["-created_at"]
        verbose_name = "AI embedding store"
        verbose_name_plural = "AI embedding stores"
        app_label = "siteconfig"


# Prompt classes (families) for gateway and productized AI; used by AIPromptRegistry and docs.
class AIPromptClass:
    SETUP = "setup"
    WORKFLOW = "workflow"
    POLICY = "policy"
    MIGRATION = "migration"
    DOCUMENT = "document"
    SUPPORT = "support"
    MARKETPLACE = "marketplace"
    DESIGN_EXPERIENCE = "design_experience"
    ANALYTICS = "analytics"
    ADMIN = "admin"


class AIPromptRegistry(models.Model):
    """
    Registry of prompts for gateway and productized AI: owner, purpose, allowed data sources,
    expected output shape, model/backend policy, review status.
    """

    prompt_key = models.CharField(max_length=64, unique=True, db_index=True)
    prompt_class = models.CharField(
        max_length=32,
        db_index=True,
        help_text="Family: setup, workflow, policy, migration, document, support, marketplace, design_experience, analytics, admin",
    )
    owner = models.CharField(max_length=128, blank=True)
    purpose = models.CharField(max_length=256, blank=True)
    template_body = models.TextField(
        help_text="Prompt template; use {context}, {query}, {user_query} etc. as placeholders",
    )
    allowed_data_sources = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed RAG scopes or data source identifiers",
    )
    expected_output_shape = models.CharField(max_length=64, blank=True)
    model_backend_policy = models.JSONField(
        default=dict,
        blank=True,
        help_text="E.g. allowed_backends, preferred_tier, max_tokens",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    review_status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "Draft"),
            ("pending_review", "Pending review"),
            ("approved", "Approved"),
            ("archived", "Archived"),
        ],
        default="draft",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_aipromptregistry"
        ordering = ["prompt_class", "prompt_key"]
        verbose_name = "AI prompt registry"
        verbose_name_plural = "AI prompt registries"
        app_label = "siteconfig"

    def __str__(self):
        return f"{self.prompt_key} ({self.prompt_class})"


class AIGatewayMetric(models.Model):
    """
    Aggregated observability metrics for AI Gateway: volume, latency, backend, failure rate,
    schema-validation failure rate, cost class, and operator review loops.
    """

    date = models.DateField(db_index=True)
    tenant_id = models.UUIDField(db_index=True, null=True, blank=True)
    task_type = models.CharField(max_length=64, db_index=True)
    tier = models.CharField(max_length=32, db_index=True)
    cost_class = models.CharField(max_length=32, default="unclassified", db_index=True)
    request_count = models.PositiveIntegerField(default=0)
    total_latency_ms = models.FloatField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    schema_validation_failures = models.PositiveIntegerField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    accepted_count = models.PositiveIntegerField(default=0)
    manual_correction_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "siteconfig_aigatewaymetric"
        ordering = ["-date", "tenant_id", "task_type"]
        unique_together = (("date", "tenant_id", "task_type", "tier", "cost_class"),)
        verbose_name = "AI gateway metric"
        verbose_name_plural = "AI gateway metrics"
        app_label = "siteconfig"
