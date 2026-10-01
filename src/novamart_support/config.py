"""Typed application configuration.

AWS credentials intentionally do not belong here. boto3 and the AWS SDK use
the standard AWS credential provider chain.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """NovaMart runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    project_name: str = Field(default="novamart-support", alias="PROJECT_NAME")

    workflow_table_name: str | None = Field(
        default=None,
        alias="WORKFLOW_TABLE_NAME",
    )
    customer_table_name: str | None = Field(
        default=None,
        alias="CUSTOMER_TABLE_NAME",
    )
    order_table_name: str | None = Field(
        default=None,
        alias="ORDER_TABLE_NAME",
    )

    orchestrator_model_id: str = Field(
        default="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        alias="ORCHESTRATOR_MODEL_ID",
    )
    worker_model_id: str = Field(
        default="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        alias="WORKER_MODEL_ID",
    )

    returns_kb_id: str | None = Field(default=None, alias="RETURNS_KB_ID")
    shipping_kb_id: str | None = Field(default=None, alias="SHIPPING_KB_ID")
    warranty_kb_id: str | None = Field(default=None, alias="WARRANTY_KB_ID")

    agentcore_runtime_arn: str | None = Field(
        default=None,
        alias="AGENTCORE_RUNTIME_ARN",
    )

    guardrail_id: str | None = Field(default=None, alias="GUARDRAIL_ID")
    guardrail_version: str | None = Field(default=None, alias="GUARDRAIL_VERSION")

    agent_tracing_enabled: bool = Field(
        default=True,
        alias="AGENT_TRACING_ENABLED",
    )
    agent_trace_sampling_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        alias="AGENT_TRACE_SAMPLING_RATE",
    )
    agent_log_level: str = Field(default="INFO", alias="AGENT_LOG_LEVEL")

    @property
    def resolved_workflow_table_name(self) -> str:
        return self._resolve_resource_name(
            self.workflow_table_name,
            "workflow-state",
        )

    @property
    def resolved_customer_table_name(self) -> str:
        return self._resolve_resource_name(
            self.customer_table_name,
            "customers",
        )

    @property
    def resolved_order_table_name(self) -> str:
        return self._resolve_resource_name(
            self.order_table_name,
            "orders",
        )

    def _resolve_resource_name(
        self,
        configured_name: str | None,
        suffix: str,
    ) -> str:
        if configured_name is not None and configured_name.strip():
            return configured_name.strip()

        return f"{self.project_name.strip()}-{suffix}"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
