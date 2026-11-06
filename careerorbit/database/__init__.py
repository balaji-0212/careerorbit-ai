"""Database package exports."""
from careerorbit.database.db import (
    init_db,
    get_connection,
    save_job,
    get_job_by_uid,
    get_job_by_id,
    list_jobs,
    get_job_stats,
    create_or_update_application,
    get_application_by_job_id,
    list_applications,
    confirm_user_submission,
    save_preparation_plan,
    get_preparation_plan_by_job,
    list_preparation_plans,
    save_resume_metadata,
    list_resumes,
    export_jobs_to_csv,
    export_applications_to_csv
)

__all__ = [
    "init_db",
    "get_connection",
    "save_job",
    "get_job_by_uid",
    "get_job_by_id",
    "list_jobs",
    "get_job_stats",
    "create_or_update_application",
    "get_application_by_job_id",
    "list_applications",
    "confirm_user_submission",
    "save_preparation_plan",
    "get_preparation_plan_by_job",
    "list_preparation_plans",
    "save_resume_metadata",
    "list_resumes",
    "export_jobs_to_csv",
    "export_applications_to_csv"
]
