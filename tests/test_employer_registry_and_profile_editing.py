"""Unit and integration tests for Employer ATS Registry and Candidate Profile Editing."""
import pytest
from careerorbit.discovery.registry import (
    list_employer_sources, add_employer_source, update_employer_source,
    delete_employer_source, get_employer_source, record_source_check
)
from careerorbit.config.candidate_evidence import (
    update_candidate_field_value, get_profile_change_history,
    candidate_evidence_summary, get_profile_with_evidence
)
from careerorbit.config.profile import CANDIDATE_PROFILE
from careerorbit.models.schemas import ApplicationStatus
from careerorbit.discovery.registry import DEFAULT_SEEDS


def test_unavailable_automattic_lever_seed_is_disabled():
    source = next(s for s in DEFAULT_SEEDS if s["id"] == "automattic-lever")
    assert source["enabled"] is False
    assert "404" in source["error_details"]

def test_employer_registry_crud():
    # 1. Add source
    source = add_employer_source(
        employer_name="Stripe Global",
        official_domain="stripe.com",
        ats_provider="Greenhouse",
        board_id="stripe",
        enabled=True,
        notes="Fintech infrastructure leader"
    )
    assert source["id"].startswith("stripe-global-greenhouse")
    assert source["status"] == "CONFIGURED"
    
    # 2. Get and list
    found = get_employer_source(source["id"])
    assert found is not None
    assert found["employer_name"] == "Stripe Global"
    
    all_sources = list_employer_sources()
    assert any(s["id"] == source["id"] for s in all_sources)
    
    # 3. Update
    updated = update_employer_source(source["id"], {"notes": "Updated description", "enabled": False})
    assert updated["notes"] == "Updated description"
    assert updated["enabled"] is False
    
    # 4. Record source check
    record_source_check(source["id"], success=True, jobs_found=15)
    checked = get_employer_source(source["id"])
    assert checked["jobs_discovered"] == 15
    assert checked["status"] == "OK"
    assert checked["last_successful_check"] is not None
    
    # 5. Delete
    deleted = delete_employer_source(source["id"])
    assert deleted is True
    assert get_employer_source(source["id"]) is None


def test_candidate_profile_field_editing_and_history():
    # Update a specific field
    result = update_candidate_field_value(
        field="personal.notice_period_status",
        new_value="30 Days (Immediate joining preferred)",
        state="CONFIRMED",
        note="Candidate explicitly specified 30 days notice",
        author="Example Candidate"
    )
    assert result["field"] == "personal.notice_period_status"
    assert result["new_value"] == "30 Days (Immediate joining preferred)"
    assert result["evidence"]["state"] == "CONFIRMED_BY_CANDIDATE"
    
    # Check change history
    history = get_profile_change_history(limit=5)
    assert len(history) > 0
    latest = history[0]
    assert latest["field"] == "personal.notice_period_status"
    assert latest["new_value"] == "30 Days (Immediate joining preferred)"
    assert latest["author"] == "Example Candidate"
    
    # Verify in full profile
    full = get_profile_with_evidence()
    assert full["personal"]["notice_period_status"]["value"] == "30 Days (Immediate joining preferred)"
    assert full["personal"]["notice_period_status"]["state"] == "CONFIRMED_BY_CANDIDATE"


def test_invalid_candidate_evidence_does_not_partially_mutate_profile():
    """Rejected field edits must leave both the in-memory profile and file overrides unchanged."""
    from careerorbit.config.settings import current_data_dir

    field = "personal.notice_period_status"
    before = CANDIDATE_PROFILE["personal"]["notice_period_status"]
    overrides_path = current_data_dir() / "candidate_profile_overrides.json"
    original_overrides = overrides_path.read_bytes() if overrides_path.exists() else None

    with pytest.raises(ValueError, match="cannot be marked not provided"):
        update_candidate_field_value(
            field=field,
            new_value="value must not persist after rejection",
            state="NOT_PROVIDED",
            note="invalid state for a field with a stored claim",
        )

    assert CANDIDATE_PROFILE["personal"]["notice_period_status"] == before
    if original_overrides is None:
        assert not overrides_path.exists()
    else:
        assert overrides_path.read_bytes() == original_overrides


def test_application_statuses_expansion():
    # Verify all expected application pipeline statuses exist
    expected = [
        "DISCOVERED", "VERIFIED", "MATCHED", "SAVED",
        "RESUME_READY", "PACKAGE_READY", "AWAITING_APPROVAL",
        "READY_TO_APPLY", "SUBMITTED_CONFIRMED", "SUBMITTED",
        "UNDER_REVIEW", "ASSESSMENT", "INTERVIEW",
        "INTERVIEW_SCHEDULED", "REJECTED", "OFFER", "WITHDRAWN"
    ]
    for status_str in expected:
        status_enum = ApplicationStatus(status_str)
        assert status_enum.value == status_str
