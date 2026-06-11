from agent.models import ModelFactory


def test_factory_uses_correct_model_per_tier():
    seen = []

    def fake_builder(model_name):
        seen.append(model_name)
        return f"client::{model_name}"

    f = ModelFactory(builder=fake_builder)
    assert f.get(0) == "client::gemini-2.0-flash-lite"
    assert f.get(1) == "client::gemini-2.0-flash"
    assert f.get(2) == "client::gemini-2.5-flash"
    assert f.get(9) == "client::gemini-2.5-flash"   # clamps to last rung


def test_factory_caches_per_tier():
    calls = []

    def fake_builder(model_name):
        calls.append(model_name)
        return object()

    f = ModelFactory(builder=fake_builder)
    a = f.get(0)
    b = f.get(0)
    assert a is b               # cached, builder called once
    assert calls == ["gemini-2.0-flash-lite"]
