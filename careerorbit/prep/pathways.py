"""Structured Learning Pathways for CareerOrbit AI.

Defines role-aligned learning roadmaps that guide candidates through progressive
stages from foundational concepts to advanced application, with automated progress
and completion tracking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


PATHWAY_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "python-data-analysis",
        "title": "Python Data Analysis & Automation",
        "role_target": "Junior Data Analyst & Python Developer",
        "description": "Progressive curriculum from core Python data structures to high-performance Pandas wrangling and API development.",
        "icon": "🐍",
        "stages": [
            {
                "stage_number": 1,
                "title": "Core Python & Data Structures",
                "difficulty_level": "BEGINNER",
                "focus_skills": ["python", "data-structures"],
                "description": "Master Python syntax, lists, dictionaries, tuples, sets, comprehensions, and defensive programming.",
                "canonical_urls": [
                    "https://docs.python.org/3/tutorial/datastructures.html"
                ]
            },
            {
                "stage_number": 2,
                "title": "NumPy & Pandas Fundamentals",
                "difficulty_level": "BEGINNER",
                "focus_skills": ["pandas", "numpy"],
                "description": "Learn vectorized array computations and tabular DataFrame manipulation, filtering, and indexing.",
                "canonical_urls": [
                    "https://pandas.pydata.org/docs/user_guide/10min.html",
                    "https://numpy.org/doc/stable/user/quickstart.html"
                ]
            },
            {
                "stage_number": 3,
                "title": "Practical Data Cleaning & Visualization",
                "difficulty_level": "INTERMEDIATE",
                "focus_skills": ["data-cleaning", "data-visualization"],
                "description": "Clean messy real-world datasets, impute missing values, standardize strings, and plot findings with Seaborn.",
                "canonical_urls": [
                    "https://realpython.com/python-data-cleaning-numpy-pandas/",
                    "https://www.kaggle.com/learn/data-visualization"
                ]
            },
            {
                "stage_number": 4,
                "title": "FastAPI Services & Data Pipelines",
                "difficulty_level": "INTERMEDIATE",
                "focus_skills": ["fastapi", "backend", "pydantic"],
                "description": "Package data transformation logic into modern, type-checked REST APIs using FastAPI and Pydantic.",
                "canonical_urls": [
                    "https://fastapi.tiangolo.com/tutorial/"
                ]
            }
        ]
    },
    {
        "id": "sql-query-mastery",
        "title": "SQL Query Mastery & Relational Database Design",
        "role_target": "Data Analyst & Business Intelligence Specialist",
        "description": "From relational queries and table joins to analytical window functions, query plan optimization, and dimensional modeling.",
        "icon": "🗄️",
        "stages": [
            {
                "stage_number": 1,
                "title": "Relational Basics & Filtering",
                "difficulty_level": "BEGINNER",
                "focus_skills": ["sql", "queries"],
                "description": "Write reliable SELECT, WHERE, GROUP BY, HAVING, and multi-condition filtering queries.",
                "canonical_urls": [
                    "https://www.postgresqltutorial.com/postgresql-getting-started/",
                    "https://sqlzoo.net/wiki/SQL_Tutorial"
                ]
            },
            {
                "stage_number": 2,
                "title": "Joins, Subqueries & Aggregations",
                "difficulty_level": "INTERMEDIATE",
                "focus_skills": ["joins", "subqueries", "analytics"],
                "description": "Master INNER, LEFT, RIGHT, FULL joins, correlated subqueries, CASE expressions, and grouping sets.",
                "canonical_urls": [
                    "https://mode.com/sql-tutorial/intermediate-sql-queries/"
                ]
            },
            {
                "stage_number": 3,
                "title": "Window Functions & Cumulative Metrics",
                "difficulty_level": "INTERMEDIATE",
                "focus_skills": ["window-functions", "ranking"],
                "description": "Calculate running totals, moving averages, row rankings, and period-over-period lags with window functions.",
                "canonical_urls": [
                    "https://www.sqlite.org/windowfunctions.html"
                ]
            },
            {
                "stage_number": 4,
                "title": "Indexing, Optimization & Star Schema",
                "difficulty_level": "ADVANCED",
                "focus_skills": ["indexing", "query-optimization", "star-schema"],
                "description": "Understand B-Tree indexes, sargable queries, EXPLAIN output, and star/snowflake dimensional modeling.",
                "canonical_urls": [
                    "https://use-the-index-luke.com/",
                    "https://en.wikipedia.org/wiki/Star_schema"
                ]
            }
        ]
    },
    {
        "id": "power-bi-business-intelligence",
        "title": "Power BI, DAX & Business Intelligence Analytics",
        "role_target": "Power BI Developer & BI Analyst",
        "description": "End-to-end business intelligence: Power Query ETL, semantic modeling, complex DAX formulas, and performance tuning.",
        "icon": "📊",
        "stages": [
            {
                "stage_number": 1,
                "title": "Power BI Desktop & Power Query",
                "difficulty_level": "BEGINNER",
                "focus_skills": ["power-bi", "power-query"],
                "description": "Connect to diverse sources, clean data in Power Query, and build interactive report layouts.",
                "canonical_urls": [
                    "https://learn.microsoft.com/en-us/training/paths/get-started-power-bi/"
                ]
            },
            {
                "stage_number": 2,
                "title": "Semantic Modeling & Star Schemas",
                "difficulty_level": "INTERMEDIATE",
                "focus_skills": ["data-modeling", "star-schema"],
                "description": "Design star schemas with fact and dimension tables, cardinality, and unidirectional filtering.",
                "canonical_urls": [
                    "https://learn.microsoft.com/en-us/training/paths/model-power-bi/"
                ]
            },
            {
                "stage_number": 3,
                "title": "DAX Formulas & Context Transition",
                "difficulty_level": "INTERMEDIATE",
                "focus_skills": ["dax", "calculate", "time-intelligence"],
                "description": "Master CALCULATE, FILTER, row/filter contexts, and Time Intelligence (YTD, MTD, YoY) measures.",
                "canonical_urls": [
                    "https://dax.guide/calculate/",
                    "https://learn.microsoft.com/en-us/training/paths/dax-power-bi/"
                ]
            },
            {
                "stage_number": 4,
                "title": "Enterprise Performance Tuning",
                "difficulty_level": "ADVANCED",
                "focus_skills": ["optimization", "performance"],
                "description": "Diagnose DAX query bottlenecks using Performance Analyzer and optimize memory footprint.",
                "canonical_urls": [
                    "https://learn.microsoft.com/en-us/power-bi/guidance/power-bi-optimization"
                ]
            }
        ]
    },
    {
        "id": "cloud-data-engineering",
        "title": "Modern Cloud Data Engineering with ADF & PySpark",
        "role_target": "Junior Cloud Data Engineer & ETL Developer",
        "description": "Cloud ETL orchestration using Azure Data Factory, distributed big data processing in PySpark, and Delta Lake medallion architecture.",
        "icon": "☁️",
        "stages": [
            {
                "stage_number": 1,
                "title": "Cloud Orchestration with Azure Data Factory",
                "difficulty_level": "INTERMEDIATE",
                "focus_skills": ["azure", "adf", "etl"],
                "description": "Build automated hybrid ingestion pipelines using ADF linked services, datasets, and triggers.",
                "canonical_urls": [
                    "https://learn.microsoft.com/en-us/training/modules/intro-to-azure-data-factory/"
                ]
            },
            {
                "stage_number": 2,
                "title": "Distributed PySpark DataFrames",
                "difficulty_level": "INTERMEDIATE",
                "focus_skills": ["pyspark", "spark", "big-data"],
                "description": "Process multi-gigabyte datasets with distributed transformations, lazy evaluation, and Spark SQL.",
                "canonical_urls": [
                    "https://spark.apache.org/docs/latest/api/python/getting_started/quickstart_df.html"
                ]
            },
            {
                "stage_number": 3,
                "title": "Delta Lake & Medallion Architecture",
                "difficulty_level": "ADVANCED",
                "focus_skills": ["delta-lake", "medallion-architecture", "acid"],
                "description": "Implement Bronze (raw), Silver (cleansed), and Gold (curated) data lakes with ACID guarantees.",
                "canonical_urls": [
                    "https://docs.delta.io/latest/delta-intro.html"
                ]
            },
            {
                "stage_number": 4,
                "title": "Scalable System Architecture & Best Practices",
                "difficulty_level": "ADVANCED",
                "focus_skills": ["system-design", "scalability", "architecture"],
                "description": "Understand distributed storage, caching layers, asynchronous queues, and resilient system design.",
                "canonical_urls": [
                    "https://github.com/donnemartin/system-design-primer"
                ]
            }
        ]
    }
]


def get_learning_pathways(resources: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """
    Construct the list of structured learning pathways with dynamic progress
    calculations based on the candidate's current resource library status.
    """
    if resources is None:
        from careerorbit.database.db import list_learning_resources
        resources = list_learning_resources(limit=500)

    # Index resources by canonical_url and primary_url
    url_to_resource: Dict[str, Dict[str, Any]] = {}
    for r in resources:
        if r.get("canonical_url"):
            url_to_resource[r["canonical_url"].strip().lower()] = r
        if r.get("primary_url"):
            url_to_resource[r["primary_url"].strip().lower()] = r

    pathway_results: List[Dict[str, Any]] = []

    for pw in PATHWAY_DEFINITIONS:
        total_pw_resources = 0
        completed_pw_resources = 0
        total_pw_minutes = 0
        completed_pw_minutes = 0
        calculated_stages: List[Dict[str, Any]] = []

        for stage in pw["stages"]:
            stage_resources: List[Dict[str, Any]] = []
            seen_ids = set()

            for target_url in stage.get("canonical_urls", []):
                norm_url = target_url.strip().lower()
                matched = url_to_resource.get(norm_url)
                if matched and matched["id"] not in seen_ids:
                    seen_ids.add(matched["id"])
                    stage_resources.append(matched)

            stage_total = len(stage_resources)
            stage_completed = sum(1 for r in stage_resources if r.get("is_completed"))
            stage_minutes = sum(int(r.get("estimated_minutes") or 30) for r in stage_resources)
            stage_completed_minutes = sum(int(r.get("estimated_minutes") or 30) for r in stage_resources if r.get("is_completed"))

            total_pw_resources += stage_total
            completed_pw_resources += stage_completed
            total_pw_minutes += stage_minutes
            completed_pw_minutes += stage_completed_minutes

            stage_progress = round((stage_completed / stage_total * 100.0) if stage_total > 0 else 0.0, 1)

            calculated_stages.append({
                "stage_number": stage["stage_number"],
                "title": stage["title"],
                "difficulty_level": stage["difficulty_level"],
                "focus_skills": stage["focus_skills"],
                "description": stage["description"],
                "total_resources": stage_total,
                "completed_resources": stage_completed,
                "total_minutes": stage_minutes,
                "completed_minutes": stage_completed_minutes,
                "progress_pct": stage_progress,
                "is_completed": stage_completed == stage_total and stage_total > 0,
                "resources": stage_resources
            })

        pw_progress = round((completed_pw_resources / total_pw_resources * 100.0) if total_pw_resources > 0 else 0.0, 1)

        pathway_results.append({
            "id": pw["id"],
            "title": pw["title"],
            "role_target": pw["role_target"],
            "description": pw["description"],
            "icon": pw.get("icon", "📘"),
            "total_stages": len(calculated_stages),
            "total_resources": total_pw_resources,
            "completed_resources": completed_pw_resources,
            "total_minutes": total_pw_minutes,
            "total_hours": round(total_pw_minutes / 60.0, 1),
            "completed_minutes": completed_pw_minutes,
            "completed_hours": round(completed_pw_minutes / 60.0, 1),
            "progress_pct": pw_progress,
            "is_completed": completed_pw_resources == total_pw_resources and total_pw_resources > 0,
            "stages": calculated_stages
        })

    return pathway_results
