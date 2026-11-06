"""Test suite verifying the Application Tracker UI components, modals, filters, and scripts."""
from pathlib import Path
import re
import pytest

INDEX_HTML_PATH = Path("careerorbit/web/static/index.html")


@pytest.fixture(scope="module")
def index_html_content():
    """Reads index.html content."""
    assert INDEX_HTML_PATH.exists(), "index.html must exist"
    return INDEX_HTML_PATH.read_text(encoding="utf-8")


def test_application_tracker_tab_structure(index_html_content):
    """Verifies that the application tracker tab contains KPI cards, toolbar, and enriched table."""
    assert 'id="tab-applications"' in index_html_content
    # KPI stat cards
    for stat_id in [
        "app-stat-total",
        "app-stat-preparing",
        "app-stat-to-apply",
        "app-stat-submitted",
        "app-stat-interview",
        "app-stat-offer",
    ]:
        assert f'id="{stat_id}"' in index_html_content, f"Missing KPI metric: {stat_id}"

    # Search and Filter
    assert 'id="app-search-input"' in index_html_content
    assert 'id="app-stage-filter"' in index_html_content
    assert 'resetApplicationFilters()' in index_html_content

    # Buttons
    assert 'openAddApplicationModal()' in index_html_content
    assert 'exportApplicationTimelineHistory()' in index_html_content

    # Table
    assert 'id="applications-table-body"' in index_html_content


def test_application_tracker_modals_exist(index_html_content):
    """Verifies all four application CRUD modals exist in index.html."""
    modals = [
        "modal-add-application",
        "modal-edit-application",
        "modal-view-application",
        "modal-delete-application",
        "confirm-submission-modal",
    ]
    for modal_id in modals:
        assert f'id="{modal_id}"' in index_html_content, f"Missing modal: {modal_id}"


def test_add_application_modal_inputs(index_html_content):
    """Verifies Add Application modal form controls."""
    required_inputs = [
        "add-app-employer",
        "add-app-title",
        "add-app-priority",
        "add-app-arrangement",
        "add-app-stage",
        "add-app-location",
        "add-app-url",
        "add-app-recruiter-name",
        "add-app-recruiter-email",
        "add-app-interview-date",
        "add-app-deadline",
        "add-app-notes",
    ]
    for input_id in required_inputs:
        assert f'id="{input_id}"' in index_html_content, f"Missing add modal input: {input_id}"
    assert 'onclick="submitAddApplication()"' in index_html_content


def test_edit_application_modal_inputs(index_html_content):
    """Verifies Edit Application modal form controls."""
    edit_inputs = [
        "edit-app-id",
        "edit-app-title-display",
        "edit-app-recruiter-name",
        "edit-app-recruiter-email",
        "edit-app-stage",
        "edit-app-interview-date",
        "edit-app-deadline",
        "edit-app-notes",
    ]
    for input_id in edit_inputs:
        assert f'id="{input_id}"' in index_html_content, f"Missing edit modal input: {input_id}"
    assert 'onclick="submitEditApplication()"' in index_html_content


def test_view_and_delete_modals_elements(index_html_content):
    """Verifies View and Delete modal containers and actions."""
    assert 'id="view-app-header-title"' in index_html_content
    assert 'id="view-app-body"' in index_html_content
    assert 'id="modal-delete-app-target-text"' in index_html_content
    assert 'onclick="confirmDeleteApplication()"' in index_html_content


def test_javascript_crud_functions_defined(index_html_content):
    """Verifies all required JavaScript CRUD handler functions are declared."""
    functions = [
        "loadApplications",
        "filterApplications",
        "resetApplicationFilters",
        "renderApplicationsTable",
        "openAddApplicationModal",
        "submitAddApplication",
        "openEditApplicationModal",
        "submitEditApplication",
        "openViewApplicationModal",
        "openDeleteApplicationModal",
        "confirmDeleteApplication",
        "exportApplicationTimelineHistory",
    ]
    for fn in functions:
        pattern = rf"function\s+{fn}\s*\("
        assert re.search(pattern, index_html_content), f"Missing function declaration: {fn}"
