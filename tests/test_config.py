import importlib


def test_vision_model_env_override(monkeypatch):
    import docval.config as config

    monkeypatch.setenv("DOCVAL_VISION_MODEL", "google/gemini-2.5-flash")
    importlib.reload(config)
    assert config.VISION_MODEL == "google/gemini-2.5-flash"
    # pricing must follow the model or cost tracking silently lies
    assert config.PRICE_IN_PER_MTOK == 0.30
    assert config.PRICE_OUT_PER_MTOK == 2.50

    monkeypatch.delenv("DOCVAL_VISION_MODEL")
    importlib.reload(config)
    assert config.VISION_MODEL == "google/gemini-2.5-flash-lite"
    assert config.PRICE_IN_PER_MTOK == 0.10
    assert config.PRICE_OUT_PER_MTOK == 0.40
