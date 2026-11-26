"""
Tests for knowledge_base.py — ensures the AI prompt contains the safety rules
that stop the bot from inventing prices or guarantees.
"""

from knowledge_base import ABOUT_TEXT, SERVICES, build_system_prompt


def test_system_prompt_contains_rules():
    prompt = build_system_prompt()
    assert "NEVER invent prices" in prompt
    assert "NEVER promise" in prompt


def test_system_prompt_contains_all_services():
    prompt = build_system_prompt()
    for svc in SERVICES.values():
        assert svc["title"] in prompt


def test_system_prompt_contains_about():
    prompt = build_system_prompt()
    assert ABOUT_TEXT in prompt


def test_services_have_required_fields():
    for key, svc in SERVICES.items():
        assert "title" in svc, key
        assert "summary" in svc, key
        assert "details" in svc, key
        assert isinstance(svc["details"], list)
