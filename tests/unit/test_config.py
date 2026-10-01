from novamart_support.config import Settings


def test_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.aws_region == "us-east-1"
    assert settings.project_name == "novamart-support"
    assert settings.agent_tracing_enabled is True
    assert settings.agent_trace_sampling_rate == 1.0


def test_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_NAME", "novamart-test")
    monkeypatch.setenv("AGENT_TRACE_SAMPLING_RATE", "0.5")

    settings = Settings(_env_file=None)

    assert settings.project_name == "novamart-test"
    assert settings.agent_trace_sampling_rate == 0.5
