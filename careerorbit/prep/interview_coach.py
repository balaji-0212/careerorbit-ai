"""Role-specific interview preparation coach and technical question generator."""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import re
from careerorbit.config.profile import CANDIDATE_PROFILE
from careerorbit.database.db import (
    save_preparation_plan,
    get_preparation_plan_by_job,
    get_job_by_id,
    save_interview_prep_session,
    get_interview_prep_session_by_job,
    update_interview_prep_session,
    list_interview_prep_sessions,
    create_interview_prep_workspace,
    list_interview_prep_workspaces,
    get_interview_prep_workspace,
    update_interview_prep_workspace,
)
from careerorbit.models.schemas import PreparationPlan
from careerorbit.config.candidate_evidence import candidate_profile_ready_for_resume

DISCLAIMER_TEXT = (
    "Interview practice is based on the role and available vacancy text only. Candidate experience and achievements are not inferred. "
    "Questions are practice prompts, not predictions of a live interview."
)


class InterviewCoach:
    """Generates role-specific technical and behavioral interview preparation packages and briefing sessions."""

    def __init__(self):
        self.profile = CANDIDATE_PROFILE

    @staticmethod
    def create_role_workspace(
        role_title: str,
        job_description: str = "",
        *,
        application_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create deterministic general interview practice without candidate data or a vacancy record."""
        role = (role_title or "").strip()
        description = (job_description or "").strip()
        if len(role) < 2 or len(role) > 120:
            raise ValueError("Enter a target role between 2 and 120 characters.")
        if len(description) > 20000:
            raise ValueError("Job description must be 20,000 characters or fewer.")

        tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", description)
        stop_words = {"with", "that", "this", "from", "will", "your", "have", "you", "and", "the", "for", "are", "our", "their", "years", "experience", "role", "work", "team", "skills", "required", "preferred", "responsibilities"}
        focus_terms = []
        for token in tokens:
            normalized = token.strip(".-")
            if normalized.casefold() not in stop_words and normalized.casefold() not in {item.casefold() for item in focus_terms}:
                focus_terms.append(normalized)
            if len(focus_terms) == 4:
                break
        focus_label = ", ".join(focus_terms) if focus_terms else "the role's core responsibilities"

        questions = [
            {
                "id": 1, "category": "Role alignment",
                "question": f"What interests you about working as a {role}, and how would you prioritize the role's first 90 days?",
                "focus_areas": ["Clarify the role's outcomes", "Connect motivation to the work", "Set measurable first steps"],
                "model_rubric": "A clear answer links the role's stated outcomes to a practical sequence of learning, delivery, and feedback. Adapt it to your own experience; no candidate facts are assumed.",
            },
            {
                "id": 2, "category": "Technical problem solving",
                "question": f"Describe how you would investigate a difficult {role} problem involving {focus_label}.",
                "focus_areas": ["Clarify constraints and success criteria", "Break the problem into testable steps", "Explain trade-offs and validation"],
                "model_rubric": "A strong response states assumptions, chooses an appropriate method, compares trade-offs, and explains how the result would be validated.",
            },
            {
                "id": 3, "category": "Quality and judgment",
                "question": "How do you check the quality of your work when the requirements are incomplete or the available information may be unreliable?",
                "focus_areas": ["Identify uncertainty", "Use independent checks", "Document decisions and residual risk"],
                "model_rubric": "The response distinguishes facts from assumptions, uses proportionate checks, and communicates uncertainty before it creates downstream risk.",
            },
            {
                "id": 4, "category": "Communication and collaboration",
                "question": "Tell me how you would explain a technical decision or project risk to a non-specialist stakeholder.",
                "focus_areas": ["Audience-aware explanation", "Impact and options", "Invite questions and confirm agreement"],
                "model_rubric": "A useful answer makes the impact understandable, presents viable options, and checks that the next step is clear.",
            },
            {
                "id": 5, "category": "Behavioral practice",
                "question": "Choose an example from your own experience where you learned from a setback or changed your approach. What happened and what did you learn?",
                "focus_areas": ["Situation and task", "Specific actions you personally took", "Outcome and reflection"],
                "model_rubric": "Use a truthful STAR structure and describe your own contribution. Do not claim outcomes or experience you cannot support.",
            },
        ]
        role_key = role.casefold()
        if any(term in role_key for term in ("data analyst", "business intelligence", "power bi", "bi analyst")):
            questions[1].update({
                "question": "How would you use SQL to answer a business question from several related tables, and validate the result before presenting it?",
                "focus_areas": ["Join and aggregation choices", "Nulls and duplicate records", "Reconcile results to a trusted total"],
                "model_rubric": "Explain the grain of each table, choose joins and aggregations that preserve it, check null and duplicate behavior, and reconcile the output. Use only examples from your real experience.",
            })
            questions[4].update({
                "question": "A dashboard KPI changes after a source refresh. How would you use SQL and the reporting model to find whether the change is real or caused by a data issue?",
                "focus_areas": ["Compare source and model row counts", "Check filters, joins, and refresh windows", "Communicate the impact and evidence"],
                "model_rubric": "Trace the metric from source through transformation and visualization, compare like-for-like periods, isolate the changed rows or logic, and describe the evidence before recommending a correction.",
            })
        elif any(term in role_key for term in ("data scientist", "machine learning", "ml engineer", "statistician")):
            questions[1].update({
                "question": "How would you build and evaluate a baseline model for a classification problem while avoiding data leakage?",
                "focus_areas": ["Choose a valid train/validation split", "Select metrics for the error costs", "Compare against a simple baseline"],
                "model_rubric": "Describe a split that matches the data-generating process, fit preprocessing only on training data, compare an interpretable baseline, and connect evaluation metrics to the decision being supported.",
            })
            questions[4].update({
                "question": "An experiment shows a small improvement in model performance. What statistical and practical checks would you make before recommending it?",
                "focus_areas": ["Uncertainty and sample size", "Segment and robustness checks", "Operational cost and impact"],
                "model_rubric": "Separate statistical uncertainty from practical value, inspect important segments and robustness, and include operational cost, monitoring, and failure impact in the recommendation.",
            })
        elif any(term in role_key for term in ("software engineer", "developer", "backend", "frontend", "full stack", "python")):
            questions[1].update({
                "question": f"How would you design and test a reliable API feature for a {role}, from request validation through persistence and error handling?",
                "focus_areas": ["Define the request and response contract", "Handle invalid input and retries", "Test behavior at unit and integration boundaries"],
                "model_rubric": "State the contract and invariants, validate untrusted input, make persistence behavior explicit, return useful errors, and test both expected and failure cases.",
            })
            questions[4].update({
                "question": "A production endpoint becomes slow after a new feature ships. How would you find the bottleneck and reduce risk while fixing it?",
                "focus_areas": ["Reproduce and measure the regression", "Inspect database and application traces", "Use a reversible fix and regression test"],
                "model_rubric": "Use measurements to isolate the slow path, compare it with a known-good baseline, make the smallest safe change, and add a regression check before rollout.",
            })
        elif any(term in role_key for term in ("data engineer", "analytics engineer", "etl")):
            questions[1].update({
                "question": "How would you design an idempotent data pipeline that can recover safely after a partial failure?",
                "focus_areas": ["Choose stable keys and checkpoints", "Make retries safe", "Validate freshness and row-level quality"],
                "model_rubric": "Explain how a retry avoids duplicate effects, how checkpoints represent completed work, and which quality and freshness checks prevent incomplete data from reaching consumers.",
            })
            questions[4].update({
                "question": "A downstream report is missing records after an upstream schema change. How would you locate and repair the break while protecting data quality?",
                "focus_areas": ["Trace lineage and schema contracts", "Compare counts and rejected rows", "Backfill and validate affected partitions"],
                "model_rubric": "Trace the change through the pipeline, preserve rejected data for inspection, define a bounded backfill, and reconcile downstream totals before declaring recovery.",
            })
        if description and focus_terms:
            technical_question = questions[1]["question"].casefold()
            if not all(term.casefold() in technical_question for term in focus_terms):
                questions[1]["focus_areas"].append(
                    f"Apply the supplied job-description context: {focus_label}"
                )
        for index, question in enumerate(questions):
            question["difficulty"] = ("Foundational", "Intermediate", "Intermediate", "Intermediate", "Advanced")[index]
        checklist = [
            {"task": "Review the target role and identify its main outcomes.", "completed": False},
            {"task": "Practice explaining one role-relevant technical problem step by step.", "completed": False},
            {"task": "Prepare a truthful example from your own experience using STAR.", "completed": False},
            {"task": "Write two questions you want to ask the interviewer.", "completed": False},
        ]
        source_type = "JOB_DESCRIPTION" if description else "ROLE"
        source_note = "The supplied job description was used only as text for topic cues." if description else "Generated from the target role title only."
        if application_context:
            employer = str(application_context.get("employer") or "").strip()
            stage = str(application_context.get("stage") or "").strip()
            application_id = application_context.get("application_id")
            source_note = "Started from your saved application"
            if employer:
                source_note += f" with {employer}"
            if stage:
                source_note += f" ({stage})"
            source_note += ". " + ("The saved job description was used only as text for topic cues." if description else "No saved job description was available; practice uses the role title only.")
        return create_interview_prep_workspace({
            "source_type": source_type,
            "role_title": role,
            "job_description": description,
            "briefing": {
                "summary": f"General practice for {role}. No resume, candidate profile, job match score, or external AI service was used.",
                "source_note": source_note,
                **({"application_context": {
                    "application_id": int(application_id),
                    "employer": employer,
                    "stage": stage,
                }} if application_context else {}),
                "questions": questions,
                "readiness_checklist": checklist,
            },
            "checklist": checklist,
            "disclaimer": "Practice prompts are deterministic preparation material, not predictions of actual interview questions. Candidate examples must be supplied and verified by you.",
        })

    def get_or_create_briefing(self, job_id: int) -> Dict[str, Any]:
        """Fetches existing interview prep briefing session or generates and persists a new one."""
        existing = get_interview_prep_session_by_job(job_id)
        if existing:
            return existing

        job_dict = get_job_by_id(job_id)
        if not job_dict:
            raise ValueError(f"Job with ID {job_id} not found in database.")

        briefing_payload = self._generate_briefing_content(job_dict)
        session_data = {
            "job_id": job_id,
            "employer_name": job_dict.get("employer", "Unknown Employer"),
            "role_title": job_dict.get("title", "Technical Role"),
            "briefing": briefing_payload,
            "candidate_notes": "",
            "confidence_rating": 0,
            "checklist": briefing_payload.get("readiness_checklist", []),
            "answer_drafts": {},
            "disclaimer": DISCLAIMER_TEXT,
        }
        save_interview_prep_session(session_data)
        saved = get_interview_prep_session_by_job(job_id)
        return saved or session_data

    def _generate_briefing_content(self, job_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Generates 5 tailored role-specific questions with rubrics, evidence linkage, and checklist."""
        company = job_dict.get("employer", "the company")
        title = job_dict.get("title", "Candidate Role")
        p_cat = job_dict.get("priority_category", 1)

        if p_cat == 1:  # Data Analyst / BI
            questions = [
                {
                    "id": 1,
                    "category": "Data Modeling & SQL Architecture",
                    "question": f"How would you design an optimized reporting model for {company}'s core business metrics, balancing Star Schema design against Power BI DirectQuery latency?",
                    "focus_areas": [
                        "Star Schema vs Snowflake schema trade-offs",
                        "Window functions (ROW_NUMBER, DENSE_RANK, LEAD/LAG)",
                        "Pre-aggregated summary tables for DirectQuery",
                    ],
                    "model_rubric": (
                        "A strong answer articulates fact and dimension table relationships, explains composite indexing on filtering keys, "
                        "and highlights how pre-aggregations reduce DirectQuery memory overhead without sacrificing granular reporting."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 2,
                    "category": "Candidate Project Evidence",
                    "question": "If you have a relevant SQL or Power BI project, how did you validate the result? If not, how would you investigate and measure a query-performance problem?",
                    "focus_areas": [
                        "Query execution plan analysis",
                        "CTE vs subquery refactoring",
                        "DAX calculate context transitions",
                    ],
                    "model_rubric": (
                        "A useful answer separates measured results from expectations, explains the investigation and trade-offs, and names the evidence "
                        "used to validate the outcome. Label coursework, personal projects, and hypothetical examples accurately."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 3,
                    "category": "KPI Definition & Data Integrity",
                    "question": f"When building executive metrics for {company}, how do you ensure data accuracy when raw sources contain duplicate transactions or null timestamps?",
                    "focus_areas": [
                        "Data deduplication strategies",
                        "Handling null timestamps and time zones",
                        "Audit validation scripts and reconciliations",
                    ],
                    "model_rubric": (
                        "Clear articulation of data validation checkpoints: unique constraints, windowed deduplication (ROW_NUMBER() OVER PARTITION BY), "
                        "and reconciliation reports between staging and dimensional models."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 4,
                    "category": "STAR Behavioral & Stakeholder Defense",
                    "question": "Tell me about a situation where a business stakeholder questioned the accuracy of your dashboard metrics. How did you resolve it?",
                    "focus_areas": [
                        "STAR method structured narrative",
                        "Data auditing and root-cause tracing",
                        "Diplomatic stakeholder communication",
                    ],
                    "model_rubric": (
                        "Situation: Disputed KPI. Task: Validate calculation logic and source data. Action: Walked stakeholder through execution plan, "
                        "demonstrated audit query, corrected upstream filter discrepancy. Result: Stakeholder trust restored and documentation published."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 5,
                    "category": "System & Quality",
                    "question": "What is the difference between ROW_NUMBER(), RANK(), and DENSE_RANK() in SQL, and when would each be required in financial or operational reporting?",
                    "focus_areas": [
                        "Tie-handling differences",
                        "Gap behavior across ranks",
                        "Use cases in top-N percentile calculations",
                    ],
                    "model_rubric": (
                        "ROW_NUMBER assigns distinct consecutive integers; RANK assigns identical ranks to ties and skips subsequent numbers; "
                        "DENSE_RANK assigns identical ranks to ties without skipping numbers. Essential for top-N ranking without missing positions."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
            ]
        elif p_cat == 3:  # Software Engineer
            questions = [
                {
                    "id": 1,
                    "category": "Python Architecture & Performance",
                    "question": f"How do you design scalable Python microservices for {company}, considering memory management, generators, and GIL constraints?",
                    "focus_areas": [
                        "Generator memory efficiency",
                        "GIL implications for I/O vs CPU bound tasks",
                        "FastAPI / Flask async handling",
                    ],
                    "model_rubric": (
                        "Explains how generators stream data with O(1) memory, leverages asyncio or multi-processing to circumvent GIL for CPU bounds, "
                        "and uses Pydantic schema validation for deterministic request typing."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 2,
                    "category": "Candidate Project Evidence",
                    "question": "Describe a software feature or learning project you worked on and how you checked its quality. If you have no comparable example, explain the steps you would take hypothetically.",
                    "focus_areas": [
                        "Agile Scrum ceremonies and PR reviews",
                        "PyTest automated test suite coverage",
                        "Resolving electronic data configuration discrepancies",
                    ],
                    "model_rubric": (
                        "Look for a clear account of the person's own contribution, the checks they actually performed, the result they can substantiate, "
                        "and any limits in their experience. Hypothetical plans should be identified as hypothetical."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 3,
                    "category": "API Design & Idempotency",
                    "question": f"How do you ensure idempotency and robust error handling across RESTful APIs in a distributed environment like {company}'s stack?",
                    "focus_areas": [
                        "Idempotency keys and transactional boundaries",
                        "HTTP status codes and exception middleware",
                        "Request schema validation with Pydantic",
                    ],
                    "model_rubric": (
                        "Explains unique request tokens stored in distributed cache (Redis) or DB unique constraints, database transactions (ACID), "
                        "and standardized error response schemas avoiding sensitive stack trace leaks."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 4,
                    "category": "STAR Behavioral & Collaboration",
                    "question": "Describe a time when you uncovered a critical edge case during peer code review or test readiness reviews. How did you communicate and address it?",
                    "focus_areas": [
                        "Collaborative feedback",
                        "Constructive root-cause identification",
                        "Regression test authoring",
                    ],
                    "model_rubric": (
                        "STAR response detailing the discovery of an unhandled boundary case, demonstrating the failure via an isolated test fixture, "
                        "partnering with the author to implement a fix, and preventing deployment of a regression."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 5,
                    "category": "Data Structures & Big-O Optimization",
                    "question": "How do you evaluate time and space complexity trade-offs when optimizing high-throughput lookup operations in Python?",
                    "focus_areas": [
                        "Hash map O(1) average lookup vs worst-case collisions",
                        "Set operations vs list scanning O(N)",
                        "Memory footprint considerations for large collections",
                    ],
                    "model_rubric": (
                        "Compares hash maps and sets against sequential scanning, explains Python dict hash collision handling, and details how caching (functools.lru_cache) "
                        "or generators balance memory consumption and CPU speed."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
            ]
        elif p_cat in (2, 4):  # Data Scientist / AI Engineer
            questions = [
                {
                    "id": 1,
                    "category": "Machine Learning & Model Evaluation",
                    "question": f"When training machine learning models for {company}, how do you address severe class imbalance and choose between ROC-AUC, F1-Score, and Precision-Recall curves?",
                    "focus_areas": [
                        "Class imbalance techniques (SMOTE, class weighting)",
                        "Precision-Recall vs ROC-AUC under skew",
                        "Threshold calibration based on business cost",
                    ],
                    "model_rubric": (
                        "Explains why ROC-AUC can be deceptively optimistic under high negative class skew, advocates for Precision-Recall AUC, "
                        "and details calibrating decision thresholds according to asymmetric business costs (false positives vs false negatives)."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 2,
                    "category": "Candidate Project Evidence",
                    "question": "If you have an ML project, describe its design and evaluation. Otherwise, explain how you would build and assess a baseline model, labeling the answer hypothetical.",
                    "focus_areas": [
                        "CNN feature extraction layers and dropout",
                        "Data augmentation on a public image dataset",
                        "Flask inference optimization and verified model results",
                    ],
                    "model_rubric": (
                        "A strong response explains the problem, data, baseline, evaluation method, and trade-offs. State measured outcomes only when "
                        "they were actually measured; distinguish a proposed approach from completed work."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 3,
                    "category": "Deep Learning & Regularization",
                    "question": "What mechanisms prevent overfitting in deep neural networks, and how do Batch Normalization and Dropout interact during training and inference?",
                    "focus_areas": [
                        "Dropout random deactivation and ensemble effect",
                        "Batch normalization mean/variance shifting",
                        "Eval mode behavior during inference",
                    ],
                    "model_rubric": (
                        "Contrasts Dropout (active during training, disabled during eval) with Batch Normalization (using batch statistics during train, "
                        "running averages during eval), noting potential variance conflicts when placed in certain ordering."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 4,
                    "category": "STAR Behavioral & Research Defense",
                    "question": "Tell me about defending your research methodology or technical architecture, such as during your a research or technical presentation.",
                    "focus_areas": [
                        "Handling rigorous peer review questions",
                        "Defending algorithmic trade-offs",
                        "Clear, evidence-backed scientific delivery",
                    ],
                    "model_rubric": (
                        "Narrative covering the technical publication or presentation, articulating why specific design choices "
                        "were made, addressing technical inquiries from reviewers, and validating architectural throughput."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 5,
                    "category": "ML System Deployment & Monitoring",
                    "question": f"How would you deploy and monitor a computer vision or tabular ML pipeline in {company}'s production environment to prevent model drift?",
                    "focus_areas": [
                        "REST / gRPC inference endpoints",
                        "Data drift and concept drift detection",
                        "Model versioning and rollback procedures",
                    ],
                    "model_rubric": (
                        "Outlines containerized model serving, feature distribution monitoring (KS-test / PSI), latency metrics, and automated alerts "
                        "triggering retraining pipelines when drift exceeds tolerances."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
            ]
        else:  # Data Engineer / General Technical
            questions = [
                {
                    "id": 1,
                    "category": "ETL Pipeline Architecture",
                    "question": f"How do you architect an idempotent ELT pipeline for {company} that guarantees exact data delivery and supports schema evolution?",
                    "focus_areas": [
                        "Pipeline idempotency and checkpointing",
                        "Schema evolution handling",
                        "Staging vs presentation layer transformations",
                    ],
                    "model_rubric": (
                        "Explains using staging tables, merge/upsert operations based on natural keys, schema versioning, and dead-letter queues "
                        "for unparseable records to ensure re-running the pipeline produces identical states."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 2,
                    "category": "Candidate Project Evidence",
                    "question": "Describe a reporting workflow you have worked on and how you checked its result. If you have not worked on one, explain a possible approach as a hypothetical.",
                    "focus_areas": [
                        "Legacy manual process replacement",
                        "Automated validation scripts",
                        "Clean dataset staging for stakeholders",
                    ],
                    "model_rubric": (
                        "Assess whether the answer explains the workflow, the person's actual contribution, validation evidence, and limitations. "
                        "Do not imply a quantified improvement unless it was measured."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 3,
                    "category": "Data Warehousing Optimization",
                    "question": "How do you optimize large-scale analytical tables using partitioning, clustering, and materialized views?",
                    "focus_areas": [
                        "Date / timestamp partitioning",
                        "Clustering on high-cardinality query keys",
                        "Materialized view query rewriting",
                    ],
                    "model_rubric": (
                        "Explains pruning scanned bytes via date partitioning, co-locating data with clustering to reduce shuffle, and leveraging "
                        "materialized views for pre-computed aggregates in reporting tools."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 4,
                    "category": "STAR Behavioral & Outage Response",
                    "question": "Tell me about a time when a critical pipeline failed or produced bad data. How did you diagnose the issue and communicate with affected teams?",
                    "focus_areas": [
                        "Incident triage and root-cause analysis",
                        "Stakeholder notification and SLA management",
                        "Post-mortem and preventative guardrails",
                    ],
                    "model_rubric": (
                        "Details immediate impact assessment, rolling back or pausing downstream consumers, identifying the root cause (e.g. malformed CSV header), "
                        "patching validation logic, backfilling clean data, and publishing an incident post-mortem."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
                {
                    "id": 5,
                    "category": "Data Quality & Contract Testing",
                    "question": "What automated checks do you implement to enforce data quality SLAs before data enters presentation tables?",
                    "focus_areas": [
                        "Null and uniqueness checks",
                        "Referential integrity and distribution tests",
                        "Alerting thresholds and pipeline fail-safes",
                    ],
                    "model_rubric": (
                        "Describes automated assertions for non-null primary keys, range checks, foreign key validity, and anomaly detection "
                        "on row counts to halt pipelines before tainted data impacts business dashboards."
                    ),
                    "candidate_example_prompt": "Use a truthful real example you can support; if none applies, say so and answer hypothetically.",
                },
            ]

        readiness_checklist = [
            {"id": 1, "task": f"Review {company} core business model & tech stack", "completed": False},
            {"id": 2, "task": f"Rehearse talking points for {title} key requirements", "completed": False},
            {"id": 3, "task": "Review verified candidate evidence and explain the project outcomes", "completed": False},
            {"id": 4, "task": "Prepare 2-3 strategic questions to ask the interviewer", "completed": False},
        ]

        summary = (
            f"Tailored interview briefing for {title} at {company}. "
            "Focus on demonstrating grounded candidate evidence, deep domain architecture, and clear STAR storytelling."
        )

        return {
            "summary": summary,
            "questions": questions,
            "readiness_checklist": readiness_checklist,
            "recommended_focus": [q["category"] for q in questions[:3]],
        }

    def update_notes(self, job_id: int, notes: str, confidence_rating: Optional[int] = None) -> Dict[str, Any]:
        """Updates candidate notes and optional confidence rating for an interview prep session."""
        self.get_or_create_briefing(job_id)
        updates: Dict[str, Any] = {"candidate_notes": notes}
        if confidence_rating is not None:
            updates["confidence_rating"] = max(1, min(5, int(confidence_rating)))
        updated = update_interview_prep_session(job_id, updates)
        if not updated:
            raise ValueError(f"Failed to update notes for job_id {job_id}")
        return updated

    def update_checklist(self, job_id: int, checklist: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Updates readiness checklist item statuses for an interview prep session."""
        self.get_or_create_briefing(job_id)
        updated = update_interview_prep_session(job_id, {"checklist": checklist})
        if not updated:
            raise ValueError(f"Failed to update checklist for job_id {job_id}")
        return updated

    def save_answer_draft(self, job_id: int, question_index: int, draft_text: str) -> Dict[str, Any]:
        """Saves a candidate's drafted rehearsal answer for a specific question."""
        session = self.get_or_create_briefing(job_id)
        drafts = session.get("answer_drafts", {})
        if not isinstance(drafts, dict):
            drafts = {}
        drafts[str(question_index)] = draft_text
        updated = update_interview_prep_session(job_id, {"answer_drafts": drafts})
        if not updated:
            raise ValueError(f"Failed to save draft for job_id {job_id}")
        return updated

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists active interview prep briefing sessions."""
        return list_interview_prep_sessions(limit=limit)

    def generate_prep_package(self, job_dict: Dict[str, Any], application_id: int = None) -> Dict[str, Any]:
        """Legacy helper: creates a comprehensive preparation package and legacy study plan model."""
        if not candidate_profile_ready_for_resume():
            raise ValueError("Candidate data needs source verification or candidate confirmation before candidate-specific interview preparation.")
        job_id = job_dict["id"]
        company = job_dict["employer"]
        title = job_dict["title"]
        p_cat = job_dict.get("priority_category", 1)

        # 1. Technical Topics & Concepts
        if p_cat == 1:  # Data Analyst / BI
            topics = [
                "SQL: Window Functions (ROW_NUMBER, DENSE_RANK, LEAD, LAG)",
                "SQL: Common Table Expressions (CTEs), GROUP BY, HAVING, and indexing optimization",
                "Power BI: DAX Calculated Columns vs Calculated Measures (Context Transition)",
                "Power BI: Star Schema vs Snowflake Schema data modeling",
                "Excel: Power Query M transformations, advanced VLOOKUP/XLOOKUP, Dynamic Pivot Tables",
                "Business Analytics: KPI definition (Default Rates, Approval Ratios, Churn, ROI)",
                "Exploratory Data Analysis (EDA) using Python (Pandas & NumPy)",
            ]
            practice_exercises = [
                {
                    "title": "SQL Portfolio Risk Analysis Query",
                    "prompt": "Write a SQL query using window functions to find the top 3 highest-risk borrower accounts per loan category based on unpaid balance.",
                    "sample_solution": (
                        "WITH RankedLoans AS (\n"
                        "    SELECT borrower_id, loan_category, unpaid_balance,\n"
                        "           DENSE_RANK() OVER (PARTITION BY loan_category ORDER BY unpaid_balance DESC) as rk\n"
                        "    FROM loan_portfolio\n"
                        ")\n"
                        "SELECT borrower_id, loan_category, unpaid_balance\n"
                        "FROM RankedLoans WHERE rk <= 3;"
                    ),
                },
                {
                    "title": "DAX Cumulative Portfolio Default Measure",
                    "prompt": "Create a DAX measure to calculate Month-To-Date (MTD) Default Rate against Total Originations.",
                    "sample_solution": (
                        "DefaultRate_MTD = \n"
                        "DIVIDE(\n"
                        "    CALCULATE(SUM(Loans[DefaultAmount]), DATESMTD('Calendar'[Date])),\n"
                        "    CALCULATE(SUM(Loans[TotalLoanAmount]), DATESMTD('Calendar'[Date])),\n"
                        "    0\n"
                        ")"
                    ),
                },
            ]
            interview_questions = [
                {
                    "question": f"Why do you want to join {company} as a Data Analyst?",
                    "model_answer": (
                        f"Connect a specific, publicly verifiable aspect of {company} to your genuine interest in the work. Then support your answer "
                        "with a real project, coursework, or learning example, labeled accurately. Do not claim prior employment or results you cannot support."
                    ),
                },
                {
                    "question": "How would you investigate SQL query performance? If you have a relevant project, explain what you measured; otherwise keep the answer hypothetical.",
                    "model_answer": (
                        "A sound approach inspects the query plan, checks row counts and filters, establishes a repeatable baseline, then tests one change at a time. "
                        "Report measured impact only if you actually measured it; otherwise describe the proposed validation as hypothetical."
                    ),
                },
                {
                    "question": "What is the difference between ROW_NUMBER(), RANK(), and DENSE_RANK() in SQL?",
                    "model_answer": (
                        "ROW_NUMBER assigns a unique sequential integer to each row without ties. RANK assigns the same rank to identical values "
                        "but skips subsequent ranks (e.g., 1, 2, 2, 4). DENSE_RANK also assigns identical ranks to ties but does not skip any ranks (e.g., 1, 2, 2, 3)."
                    ),
                },
            ]
        elif p_cat == 3:  # Software Engineer
            topics = [
                "Python: OOP Principles (Inheritance, Polymorphism, Encapsulation, Abstract Base Classes)",
                "Python: Memory management, generators, decorators, and GIL fundamentals",
                "FastAPI & Flask: RESTful API design, request validation (Pydantic), and middleware",
                "Data Structures: Hash maps, binary trees, recursion, and Big-O time complexity",
                "Database: ACID properties, transactions, and SQL vs NoSQL trade-offs",
                "Engineering Practices: Unit testing (PyTest), Git branching (GitFlow), and CI/CD pipelines",
            ]
            practice_exercises = [
                {
                    "title": "FastAPI Health & Metrics Endpoint with Pydantic",
                    "prompt": "Implement a secure FastAPI router endpoint with request validation for recording application telemetry.",
                    "sample_solution": (
                        "from fastapi import APIRouter, HTTPException\n"
                        "from pydantic import BaseModel\n\n"
                        "router = APIRouter()\n"
                        "class MetricPayload(BaseModel):\n"
                        "    metric_name: str\n"
                        "    value: float\n\n"
                        "@router.post('/telemetry')\n"
                        "async def log_telemetry(payload: MetricPayload):\n"
                        "    return {'status': 'recorded', 'metric': payload.metric_name}"
                    ),
                },
                {
                    "title": "Two-Sum / Hash Map Optimization",
                    "prompt": "Find two numbers in an array that add up to a target in O(N) time.",
                    "sample_solution": (
                        "def two_sum(nums, target):\n"
                        "    seen = {}\n"
                        "    for idx, num in enumerate(nums):\n"
                        "        comp = target - num\n"
                        "        if comp in seen:\n"
                        "            return [seen[comp], idx]\n"
                        "        seen[num] = idx\n"
                        "    return []"
                    ),
                },
            ]
            interview_questions = [
                {
                    "question": "Describe a software feature you worked on, or explain how you would approach one if you have no comparable experience yet.",
                    "model_answer": (
                        "Use a real work, coursework, or personal project and state which it is. Explain your own contribution, the decisions you made, "
                        "how you checked the result, and what you would improve. If you lack an example, say so and outline a hypothetical approach."
                    ),
                },
                {
                    "question": "How do you ensure code quality before pushing to production?",
                    "model_answer": (
                        "I follow a disciplined pipeline: writing comprehensive unit and integration tests using PyTest, running linters and "
                        "type checks, validating PRs through GitHub Actions CI workflows, and participating in rigorous peer code reviews."
                    ),
                },
            ]
        elif p_cat in (2, 4):  # Data Scientist / AI Engineer
            topics = [
                "Machine Learning: Supervised vs Unsupervised algorithms, bias-variance trade-off",
                "Model Evaluation: Precision, Recall, F1-score, ROC-AUC, Confusion Matrix",
                "Deep Learning: CNN architectures, convolution, pooling, batch normalization, dropout",
                "Computer Vision: OpenCV pipeline, image preprocessing, data augmentation",
                "Inference & Deployment: Model quantization, latency reduction, Flask/FastAPI model serving",
            ]
            practice_exercises = [
                {
                    "title": "Confusion Matrix & F1-Score Computation in Scikit-Learn",
                    "prompt": "Write a Python snippet to compute multi-class precision, recall, and classification report.",
                    "sample_solution": (
                        "from sklearn.metrics import classification_report, confusion_matrix\n"
                        "print(classification_report(y_true, y_pred))\n"
                        "print(confusion_matrix(y_true, y_pred))"
                    ),
                }
            ]
            interview_questions = [
                {
                    "question": "If you have an ML project, explain its design and evaluation. If not, outline a baseline approach and label it hypothetical.",
                    "model_answer": (
                        "A useful outline identifies the problem and data, establishes a baseline, selects metrics tied to the decision, and checks for leakage. "
                        "Describe completed work only when it is yours; label a proposed design as hypothetical and report metrics only when measured."
                    ),
                }
            ]
        else:  # Data Engineer / General Technical
            topics = [
                "ETL Pipeline Architecture: Extraction, transformation, validation, and loading",
                "SQL Transformations & Stored Procedures",
                "Data Quality: Anomaly detection, null handling, schema validation",
                "Cloud Data Warehousing: Google BigQuery, partitioned tables, clustering",
            ]
            practice_exercises = [
                {
                    "title": "PySpark / Python Data Validation Function",
                    "prompt": "Write a validation function to verify schema adherence and zero null keys.",
                    "sample_solution": (
                        "def validate_records(df):\n"
                        "    null_counts = df.isnull().sum()\n"
                        "    assert null_counts['id'] == 0, 'Null ID detected!'\n"
                        "    return True"
                    ),
                }
            ]
            interview_questions = [
                {
                    "question": "Describe a data pipeline you have worked on, or outline a safe design if you have no comparable experience yet.",
                    "model_answer": (
                        "A strong design names stable keys, validation checks, retry behavior, and reconciliation. Use a real example if you have one; "
                        "otherwise clearly label the design as hypothetical and do not imply it was deployed."
                    ),
                }
            ]

        # 2. Daily 3.5-hour Study Plan Blocks
        study_blocks = [
            {
                "block_number": 1,
                "title": "Block 1: Application Review & Target Alignment",
                "duration_minutes": 30,
                "activities": [
                    f"Review {company} role requirements and confirmed interview stages.",
                    "Verify deadlines and check outreach follow-up status.",
                ],
            },
            {
                "block_number": 2,
                "title": "Block 2: Hands-On Technical Practice (Coding & SQL)",
                "duration_minutes": 75,
                "activities": [
                    "Complete practical SQL queries and data modeling challenges.",
                    "Solve algorithmic exercises / DAX measure calculations.",
                ],
            },
            {
                "block_number": 3,
                    "title": "Block 3: Role-Relevant Example or Design Practice",
                "duration_minutes": 75,
                "activities": [
                    "Practice explaining one real project or learning exercise; distinguish measured outcomes from estimates.",
                    "If no comparable example exists, rehearse a clearly labeled hypothetical design and its trade-offs.",
                ],
            },
            {
                "block_number": 4,
                "title": "Block 4: Behavioral STAR Practice & Tomorrow's Agenda",
                "duration_minutes": 30,
                "activities": [
                    "Practice STAR behavioral responses (collaboration, handling defects, Agile ceremonies).",
                    "Update completed task checklists and schedule tomorrow's 8:00 PM session.",
                ],
            },
        ]

        revision_checklist = [
            {"task": "Review SQL window functions and execution plans", "done": False},
            {"task": f"Prepare 2 tailored questions to ask the {company} interviewer", "done": False},
            {"task": "Choose a truthful role-relevant example or prepare a clearly labeled hypothetical", "done": False},
            {"task": "Check notice period alignment and remote/hybrid work setup", "done": False},
        ]

        now_iso = datetime.now(timezone.utc).isoformat()
        next_rev = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()[:10]

        plan_model = PreparationPlan(
            job_id=job_id,
            application_id=application_id,
            role_title=title,
            company=company,
            target_priority=p_cat,
            daily_time_allocated_hours=3.5,
            study_plan_blocks=study_blocks,
            technical_topics=topics,
            practice_exercises=practice_exercises,
            interview_questions=interview_questions,
            completed_tasks=[],
            weak_areas=["Optional review topic: choose a cloud or lakehouse concept relevant to this role"],
            revision_checklist=revision_checklist,
            next_revision_date=next_rev,
            created_at=now_iso,
            updated_at=now_iso,
        )

        plan_id = save_preparation_plan(plan_model)

        return {
            "plan_id": plan_id,
            "job_id": job_id,
            "role_title": title,
            "company": company,
            "study_blocks": study_blocks,
            "technical_topics": topics,
            "practice_exercises": practice_exercises,
            "interview_questions": interview_questions,
            "revision_checklist": revision_checklist,
        }
