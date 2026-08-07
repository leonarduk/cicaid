import argparse

from cicaid_devtools.lib import llm_common


def test_model_sources_include_local_cloud_remote():
    assert llm_common.MODEL_SOURCES == ("local", "cloud", "remote")


def test_add_model_source_arg_default():
    parser = argparse.ArgumentParser()
    llm_common.add_model_source_arg(parser)
    args = parser.parse_args([])
    assert args.model_source == "local"


def test_add_model_source_arg_custom_default():
    parser = argparse.ArgumentParser()
    llm_common.add_model_source_arg(parser, default="cloud")
    args = parser.parse_args([])
    assert args.model_source == "cloud"


def test_add_model_source_arg_rejects_unknown_choice():
    parser = argparse.ArgumentParser()
    llm_common.add_model_source_arg(parser)
    try:
        parser.parse_args(["--model-source", "bogus"])
        raise AssertionError("expected SystemExit")
    except SystemExit:
        pass


def test_prompt_for_model_source_defaults_to_local_on_eof(monkeypatch):
    def raise_eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert llm_common.prompt_for_model_source() == llm_common.LOCAL


def test_prompt_for_model_source_cloud(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "c")
    assert llm_common.prompt_for_model_source() == llm_common.CLOUD


def test_prompt_for_model_source_remote(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "remote")
    assert llm_common.prompt_for_model_source() == llm_common.REMOTE


def test_describe_model_source_cloud():
    assert llm_common.describe_model_source(llm_common.CLOUD) == "cloud model (DeepSeek)"


def test_describe_model_source_local(monkeypatch):
    monkeypatch.setattr(llm_common, "get_ollama_model", lambda: "qwen2.5-coder:7b")
    monkeypatch.setattr(llm_common, "get_ollama_endpoint", lambda: "http://localhost:11434")
    desc = llm_common.describe_model_source(llm_common.LOCAL)
    assert "qwen2.5-coder:7b" in desc
    assert "http://localhost:11434" in desc


def test_validate_model_source_cloud_requires_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert llm_common.validate_model_source(llm_common.CLOUD) is False

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    assert llm_common.validate_model_source(llm_common.CLOUD) is True


def test_validate_model_source_remote_requires_endpoint(monkeypatch):
    monkeypatch.setattr(llm_common, "get_remote_llm_endpoint", lambda: "")
    assert llm_common.validate_model_source(llm_common.REMOTE) is False

    monkeypatch.setattr(llm_common, "get_remote_llm_endpoint", lambda: "http://my-server:8000")
    assert llm_common.validate_model_source(llm_common.REMOTE) is True


def test_validate_model_source_local_checks_connection(monkeypatch):
    monkeypatch.setattr(llm_common, "get_ollama_endpoint", lambda: "http://localhost:11434")
    monkeypatch.setattr(llm_common, "validate_ollama_connection", lambda endpoint: False)
    assert llm_common.validate_model_source(llm_common.LOCAL) is False

    monkeypatch.setattr(llm_common, "validate_ollama_connection", lambda endpoint: True)
    assert llm_common.validate_model_source(llm_common.LOCAL) is True


def test_fetch_review_dispatches_to_local(monkeypatch):
    monkeypatch.setattr(llm_common, "get_ollama_endpoint", lambda: "http://localhost:11434")
    monkeypatch.setattr(llm_common, "get_ollama_model", lambda: "qwen2.5-coder:7b")
    monkeypatch.setattr(
        llm_common,
        "fetch_ollama_review",
        lambda endpoint, model, prompt: f"local:{endpoint}:{model}:{prompt}",
    )
    assert llm_common.fetch_review(llm_common.LOCAL, "hello") == (
        "local:http://localhost:11434:qwen2.5-coder:7b:hello"
    )


def test_fetch_review_dispatches_to_cloud(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(
        llm_common, "fetch_deepseek_review", lambda api_key, prompt: f"cloud:{api_key}:{prompt}"
    )
    assert llm_common.fetch_review(llm_common.CLOUD, "hello") == "cloud:secret:hello"


def test_fetch_review_dispatches_to_remote(monkeypatch):
    monkeypatch.setattr(llm_common, "get_remote_llm_endpoint", lambda: "http://my-server:8000")
    monkeypatch.setattr(llm_common, "get_remote_llm_model", lambda: "llama3")
    monkeypatch.setenv("REMOTE_LLM_API_KEY", "rkey")
    monkeypatch.setattr(
        llm_common,
        "fetch_remote_openai_review",
        lambda endpoint, model, api_key, prompt: f"remote:{endpoint}:{model}:{api_key}:{prompt}",
    )
    assert llm_common.fetch_review(llm_common.REMOTE, "hello") == (
        "remote:http://my-server:8000:llama3:rkey:hello"
    )
