from aivp.llm.fake import FakeLlm


def test_fake_llm_returns_scripted_json():
    llm = FakeLlm(script={"hello": {"ok": True}})
    assert llm.complete_json("sys", "hello") == {"ok": True}


def test_fake_llm_missing_key_raises():
    llm = FakeLlm(script={})
    try:
        llm.complete_json("sys", "missing")
        assert False, "expected KeyError"
    except KeyError:
        pass
