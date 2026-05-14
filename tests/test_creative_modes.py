from worldforger.creative_modes import chat_guides_content, genre_tags_prompt_addon, normalize_chat_guides


def test_normalize_chat_guides_filters_unknown():
    assert normalize_chat_guides(
        ["skill_trees", "nope", "attribute_system", "profession_system", "economy", "ecology"]
    ) == [
        "skill_trees",
        "attribute_system",
        "profession_system",
        "economy",
        "ecology",
    ]
    assert normalize_chat_guides(None) == []


def test_chat_guides_content_joins():
    text = chat_guides_content(["skill_trees", "profession_system", "attribute_system"])
    assert text
    assert "skill_tree" in text.lower() or "技能树" in text
    assert "profession" in text.lower() or "职业" in text
    assert "attribute_system" in text.lower() or "人物属性" in text

    eco = chat_guides_content(["economy"])
    assert eco
    assert "economy" in eco.lower() or "经济" in eco


def test_genre_tags_prompt_addon_empty():
    assert genre_tags_prompt_addon(None) is None
    assert genre_tags_prompt_addon([]) is None


def test_genre_tags_prompt_addon_nonempty():
    s = genre_tags_prompt_addon(["  西北 ", "史诗"])
    assert s
    assert "西北" in s and "史诗" in s
    assert "genre_tags" in s
