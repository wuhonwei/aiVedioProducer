from aivp.visual.location_description_qa import qa_location_description


def test_qa_pass_when_materials_in_evidence():
    profile = {
        "name": "渡口",
        "prompt_zh": "青石埠头渡口",
        "palette": ["青灰"],
        "materials": ["青石"],
    }
    entity = {"evidence": "青石铺就的埠头，江雾弥漫"}
    out = qa_location_description(profile, entity, llm=None)
    assert out["ok"] is True


def test_qa_marks_ungrounded_when_no_evidence():
    profile = {
        "name": "龙宫",
        "prompt_zh": "金碧辉煌龙宫",
        "materials": ["琉璃"],
    }
    entity = {"evidence": "小河渡口"}
    out = qa_location_description(profile, entity, llm=None)
    assert out["ok"] is False or out["warnings"]
