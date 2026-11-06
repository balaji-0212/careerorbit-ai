import json

from careerorbit.config.profile import DEFAULT_CANDIDATE_PROFILE, load_candidate_profile


def test_missing_private_profile_uses_blank_schema(tmp_path):
    profile = load_candidate_profile(tmp_path / "missing.json")

    assert profile["personal"]["full_name"] == ""
    assert profile["personal"]["email"] == ""
    assert profile["employment"] == []
    assert profile["projects"] == []
    assert profile == DEFAULT_CANDIDATE_PROFILE


def test_private_profile_load_preserves_values_and_numeric_priority_keys(tmp_path):
    profile_path = tmp_path / "candidate_profile_private.json"
    profile_path.write_text(json.dumps({
        "personal": {"full_name": "Alex Example"},
        "priority_roles": {"1": {"category": "Data Analyst"}},
    }), encoding="utf-8")

    loaded = load_candidate_profile(profile_path)

    assert loaded["personal"]["full_name"] == "Alex Example"
    assert loaded["personal"]["email"] == ""
    assert 1 in loaded["priority_roles"]
    assert loaded["priority_roles"][1]["category"] == "Data Analyst"
