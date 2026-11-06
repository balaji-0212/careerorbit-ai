from careerorbit.scheduler.run_history import last_success, record_run, workflow_lock


def test_last_success_survives_later_failed_execution():
    record_run("job_discovery", "success", summary={"new_jobs_added": 3})
    record_run("job_discovery", "failed", error="Timeout")
    assert last_success("job_discovery") is not None
    assert last_success("study_plan") is None


def test_overlapping_workflow_is_rejected():
    with workflow_lock("job_discovery") as acquired:
        assert acquired
        with workflow_lock("job_discovery") as second_acquired:
            assert not second_acquired
