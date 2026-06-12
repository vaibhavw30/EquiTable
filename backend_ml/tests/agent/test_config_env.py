import importlib


def _reload_config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import agent.config as cfg
    return importlib.reload(cfg)


def test_defaults_when_no_env(monkeypatch):
    for k in ("REFRESH_MAX_SOURCES", "REFRESH_MAX_COST_USD", "REFRESH_FRESHNESS_HOURS"):
        monkeypatch.delenv(k, raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.MAX_SOURCES_PER_RUN == 25
    assert cfg.MAX_COST_USD == 0.50
    assert cfg.FRESHNESS_FLOOR_HOURS == 24


def test_env_overrides_apply(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        REFRESH_MAX_SOURCES="2",
        REFRESH_MAX_COST_USD="0.05",
        REFRESH_FRESHNESS_HOURS="0",
    )
    assert cfg.MAX_SOURCES_PER_RUN == 2
    assert cfg.MAX_COST_USD == 0.05
    assert cfg.FRESHNESS_FLOOR_HOURS == 0


def test_invalid_env_falls_back_to_default(monkeypatch):
    cfg = _reload_config(monkeypatch, REFRESH_MAX_SOURCES="not-a-number")
    assert cfg.MAX_SOURCES_PER_RUN == 25
