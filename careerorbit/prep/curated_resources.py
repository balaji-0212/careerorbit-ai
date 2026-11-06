"""Curated Learning Resources Catalog for CareerOrbit AI.

Provides high-quality, verified educational resources and an idempotent seeder
for candidate skill development in Data Analysis, SQL, Python, Business Intelligence,
and Data Engineering.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import sqlite3

CURATED_LEARNING_RESOURCES: List[Dict[str, Any]] = [
    # ----------------- 1. Python Data Analysis & Scripting -----------------
    {
        "title": "Official Python Tutorial: Data Structures & Control Flow",
        "category": "Technical Learning Materials",
        "sub_category": "Python Core",
        "skill_tag": "python",
        "difficulty_level": "BEGINNER",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 120,
        "canonical_url": "https://docs.python.org/3/tutorial/datastructures.html",
        "primary_url": "https://docs.python.org/3/tutorial/datastructures.html",
        "all_urls": ["https://docs.python.org/3/tutorial/datastructures.html"],
        "source": "Curated Catalog",
        "summary": "Master essential Python collections: lists, tuples, dictionaries, sets, comprehensions, and looping techniques.",
        "raw_excerpt": "Comprehensive reference covering list comprehensions, dict operations, tuple packing/unpacking, and built-in sequence functions.",
        "tags": ["python", "basics", "data-structures", "core"],
        "notes": "Fundamental foundation required for all junior software engineering and data analyst roles."
    },
    {
        "title": "Pandas Getting Started: 10 Minutes to Pandas",
        "category": "Technical Learning Materials",
        "sub_category": "Data Wrangling",
        "skill_tag": "python",
        "difficulty_level": "BEGINNER",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 60,
        "canonical_url": "https://pandas.pydata.org/docs/user_guide/10min.html",
        "primary_url": "https://pandas.pydata.org/docs/user_guide/10min.html",
        "all_urls": ["https://pandas.pydata.org/docs/user_guide/10min.html"],
        "source": "Curated Catalog",
        "summary": "Quick introduction to Pandas Series and DataFrames, indexing, filtering, missing data handling, and grouping operations.",
        "raw_excerpt": "Hands-on guide to DataFrame creation, selection by label (.loc) and position (.iloc), boolean indexing, and descriptive stats.",
        "tags": ["python", "pandas", "dataframe", "data-cleaning"],
        "notes": "Essential guide for Data Analyst coding tests and screening rounds."
    },
    {
        "title": "RealPython: Python Pandas Guide to Practical Data Cleaning",
        "category": "Technical Learning Materials",
        "sub_category": "Data Wrangling",
        "skill_tag": "python",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "INTERACTIVE_TUTORIAL",
        "estimated_minutes": 90,
        "canonical_url": "https://realpython.com/python-data-cleaning-numpy-pandas/",
        "primary_url": "https://realpython.com/python-data-cleaning-numpy-pandas/",
        "all_urls": ["https://realpython.com/python-data-cleaning-numpy-pandas/"],
        "source": "Curated Catalog",
        "summary": "Practical recipes for cleaning messy datasets: handling nulls, string standardizing, deduplication, and datetime parsing.",
        "raw_excerpt": "Step-by-step techniques for dropping irrelevant columns, renaming headers, reindexing, and vectorizing string cleaning with .str methods.",
        "tags": ["python", "pandas", "numpy", "data-cleaning", "etl"],
        "notes": "Directly mirrors take-home data wrangling tests given by mid-tier tech and analytics firms."
    },
    {
        "title": "NumPy Quickstart Tutorial",
        "category": "Technical Learning Materials",
        "sub_category": "Numerical Computing",
        "skill_tag": "python",
        "difficulty_level": "BEGINNER",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 75,
        "canonical_url": "https://numpy.org/doc/stable/user/quickstart.html",
        "primary_url": "https://numpy.org/doc/stable/user/quickstart.html",
        "all_urls": ["https://numpy.org/doc/stable/user/quickstart.html"],
        "source": "Curated Catalog",
        "summary": "Core array operations, ndarray indexing, slicing, broadcasting, and vectorization essentials.",
        "raw_excerpt": "Understanding ndarray attributes (shape, dtype, ndim), universal functions (ufuncs), broadcasting rules, and linear algebra routines.",
        "tags": ["python", "numpy", "vectorization", "math"],
        "notes": "Required for understanding underlying Pandas behavior and performance optimization."
    },
    {
        "title": "FastAPI Official Tutorial: Building High-Performance REST APIs",
        "category": "Technical Learning Materials",
        "sub_category": "Backend Engineering",
        "skill_tag": "fastapi",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 150,
        "canonical_url": "https://fastapi.tiangolo.com/tutorial/",
        "primary_url": "https://fastapi.tiangolo.com/tutorial/",
        "all_urls": ["https://fastapi.tiangolo.com/tutorial/"],
        "source": "Curated Catalog",
        "summary": "Building modern REST APIs in Python using Pydantic schemas, dependency injection, async endpoints, and automated OpenAPI documentation.",
        "raw_excerpt": "Covers path parameters, query params, request bodies, response models, HTTP status codes, and error handling with HTTPException.",
        "tags": ["python", "fastapi", "rest-api", "backend", "pydantic"],
        "notes": "Matches Junior Python Backend Developer requirements at startups and product companies."
    },

    # ----------------- 2. SQL & Relational Database Design -----------------
    {
        "title": "PostgreSQL Tutorial: Essential Querying and Filtering",
        "category": "Technical Learning Materials",
        "sub_category": "SQL Core",
        "skill_tag": "sql",
        "difficulty_level": "BEGINNER",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 90,
        "canonical_url": "https://www.postgresqltutorial.com/postgresql-getting-started/",
        "primary_url": "https://www.postgresqltutorial.com/postgresql-getting-started/",
        "all_urls": ["https://www.postgresqltutorial.com/postgresql-getting-started/"],
        "source": "Curated Catalog",
        "summary": "Relational fundamentals: SELECT statements, WHERE clauses, ORDER BY, GROUP BY, HAVING, and aggregate functions.",
        "raw_excerpt": "Core SQL syntax, logical operators (AND, OR, NOT), NULL handling, pattern matching with LIKE / ILIKE, and column aliasing.",
        "tags": ["sql", "postgres", "queries", "basics"],
        "notes": "High priority: Tested in 100% of data analyst technical screening assessments."
    },
    {
        "title": "Mode Analytics SQL School: The Intermediate & Advanced SQL Guide",
        "category": "Technical Learning Materials",
        "sub_category": "SQL Analytics",
        "skill_tag": "sql",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "INTERACTIVE_TUTORIAL",
        "estimated_minutes": 180,
        "canonical_url": "https://mode.com/sql-tutorial/intermediate-sql-queries/",
        "primary_url": "https://mode.com/sql-tutorial/intermediate-sql-queries/",
        "all_urls": ["https://mode.com/sql-tutorial/intermediate-sql-queries/"],
        "source": "Curated Catalog",
        "summary": "Mastering table joins (INNER, LEFT, RIGHT, FULL, CROSS), subqueries, UNION/UNION ALL, and CASE statements.",
        "raw_excerpt": "In-depth treatment of multi-table joins, self-joins, conditional aggregations, and query optimization patterns for analytics.",
        "tags": ["sql", "joins", "subqueries", "analytics"],
        "notes": "Directly prepares candidates for complex multi-table SQL interview challenges."
    },
    {
        "title": "PostgreSQL & SQLite Window Functions Complete Guide",
        "category": "Technical Learning Materials",
        "sub_category": "SQL Analytics",
        "skill_tag": "sql",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 120,
        "canonical_url": "https://www.sqlite.org/windowfunctions.html",
        "primary_url": "https://www.sqlite.org/windowfunctions.html",
        "all_urls": ["https://www.sqlite.org/windowfunctions.html", "https://www.postgresqltutorial.com/postgresql-window-function/"],
        "source": "Curated Catalog",
        "summary": "Master analytical window functions: ROW_NUMBER(), RANK(), DENSE_RANK(), NTILE(), LEAD(), LAG(), and cumulative SUM() OVER().",
        "raw_excerpt": "PARTITION BY and ORDER BY clauses, frame specifications (ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), and running metrics.",
        "tags": ["sql", "window-functions", "analytics", "ranking"],
        "notes": "Window functions are asked in 9 out of 10 Senior and Junior Data Analyst technical interview rounds."
    },
    {
        "title": "Relational Database Normalization & Star Schema Design",
        "category": "Technical Learning Materials",
        "sub_category": "Data Modeling",
        "skill_tag": "data_modeling",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 90,
        "canonical_url": "https://en.wikipedia.org/wiki/Star_schema",
        "primary_url": "https://en.wikipedia.org/wiki/Star_schema",
        "all_urls": ["https://en.wikipedia.org/wiki/Star_schema"],
        "source": "Curated Catalog",
        "summary": "Dimensional modeling principles: Fact tables, Dimension tables, 1NF/2NF/3NF normalization, surrogate keys, and slowly changing dimensions (SCD).",
        "raw_excerpt": "Comparison between OLTP 3NF normalized structures and OLAP dimensional star/snowflake schemas for business intelligence.",
        "tags": ["sql", "data-modeling", "star-schema", "database-design"],
        "notes": "Crucial for BI Developer, Data Warehouse Engineer, and Senior Analyst roles."
    },
    {
        "title": "Use The Index, Luke! A Guide to Database Performance for Developers",
        "category": "Technical Learning Materials",
        "sub_category": "SQL Optimization",
        "skill_tag": "sql",
        "difficulty_level": "ADVANCED",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 180,
        "canonical_url": "https://use-the-index-luke.com/",
        "primary_url": "https://use-the-index-luke.com/",
        "all_urls": ["https://use-the-index-luke.com/"],
        "source": "Curated Catalog",
        "summary": "Deep dive into B-Tree indexes, index scans vs table scans, composite indexes, query execution plans (EXPLAIN ANALYZE), and sargability.",
        "raw_excerpt": "Explains how database engines execute queries, why function calls break index lookups, and how to write sargable predicates.",
        "tags": ["sql", "indexing", "performance", "query-optimization"],
        "notes": "Differentiates good candidates from top 5% candidates during technical grilling rounds."
    },

    # ----------------- 3. Power BI & Business Intelligence -----------------
    {
        "title": "Microsoft Learn: Get Started with Power BI Desktop",
        "category": "Certifications and Courses",
        "sub_category": "Power BI Fundamentals",
        "skill_tag": "power_bi",
        "difficulty_level": "BEGINNER",
        "resource_type": "ROADMAP",
        "estimated_minutes": 180,
        "canonical_url": "https://learn.microsoft.com/en-us/training/paths/get-started-power-bi/",
        "primary_url": "https://learn.microsoft.com/en-us/training/paths/get-started-power-bi/",
        "all_urls": ["https://learn.microsoft.com/en-us/training/paths/get-started-power-bi/"],
        "source": "Curated Catalog",
        "summary": "Official Microsoft learning path covering Power BI Desktop installation, data source connection, Power Query data transformation, and basic visual reports.",
        "raw_excerpt": "Connecting to Excel, CSV, and SQL databases; using Power Query Editor to shape data; creating bar charts, line graphs, and matrix visuals.",
        "tags": ["power-bi", "microsoft", "bi", "reporting", "beginner"],
        "notes": "Aligned with Microsoft PL-300: Power BI Data Analyst certification syllabus."
    },
    {
        "title": "Microsoft Learn: Model Data in Power BI (Star Schema & Relationships)",
        "category": "Certifications and Courses",
        "sub_category": "Data Modeling",
        "skill_tag": "power_bi",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "ROADMAP",
        "estimated_minutes": 150,
        "canonical_url": "https://learn.microsoft.com/en-us/training/paths/model-power-bi/",
        "primary_url": "https://learn.microsoft.com/en-us/training/paths/model-power-bi/",
        "all_urls": ["https://learn.microsoft.com/en-us/training/paths/model-power-bi/"],
        "source": "Curated Catalog",
        "summary": "Designing semantic models, configuring cardinality (1:*, *:*, 1:1), cross-filter direction, and building star schema models.",
        "raw_excerpt": "Best practices for data relationships, resolving circular dependencies, role-playing dimensions, and managing large datasets.",
        "tags": ["power-bi", "data-modeling", "star-schema", "relationships"],
        "notes": "Core topic in every corporate Power BI interview."
    },
    {
        "title": "DAX Guide: Mastering CALCULATE, FILTER, and Filter Context",
        "category": "Technical Learning Materials",
        "sub_category": "DAX Formulas",
        "skill_tag": "dax",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 120,
        "canonical_url": "https://dax.guide/calculate/",
        "primary_url": "https://dax.guide/calculate/",
        "all_urls": ["https://dax.guide/calculate/", "https://dax.guide/"],
        "source": "Curated Catalog",
        "summary": "Comprehensive breakdown of CALCULATE, context transition, row context vs filter context, and ALL/ALLEXCEPT modifiers.",
        "raw_excerpt": "Explains how CALCULATE evaluates filter expressions, overrides existing filter contexts, and transitions row context to filter context.",
        "tags": ["power-bi", "dax", "calculate", "filter-context"],
        "notes": "CALCULATE and context transition are the #1 most frequently asked DAX questions."
    },
    {
        "title": "Microsoft Learn: Create DAX Calculations in Power BI",
        "category": "Certifications and Courses",
        "sub_category": "DAX Formulas",
        "skill_tag": "dax",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "ROADMAP",
        "estimated_minutes": 140,
        "canonical_url": "https://learn.microsoft.com/en-us/training/paths/dax-power-bi/",
        "primary_url": "https://learn.microsoft.com/en-us/training/paths/dax-power-bi/",
        "all_urls": ["https://learn.microsoft.com/en-us/training/paths/dax-power-bi/"],
        "source": "Curated Catalog",
        "summary": "Calculated columns vs measures, basic aggregation functions (SUM, AVERAGE, COUNTROWS), and Time Intelligence calculations (YTD, MTD, SAMEPERIODLASTYEAR).",
        "raw_excerpt": "Building dynamic business measures, understanding performance impact of calculated columns vs explicit measures, and working with Date tables.",
        "tags": ["power-bi", "dax", "measures", "time-intelligence"],
        "notes": "Essential practical skills for building enterprise dashboard KPIs."
    },
    {
        "title": "Enterprise Power BI Performance Tuning and Best Practices",
        "category": "Technical Learning Materials",
        "sub_category": "BI Optimization",
        "skill_tag": "power_bi",
        "difficulty_level": "ADVANCED",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 100,
        "canonical_url": "https://learn.microsoft.com/en-us/power-bi/guidance/power-bi-optimization",
        "primary_url": "https://learn.microsoft.com/en-us/power-bi/guidance/power-bi-optimization",
        "all_urls": ["https://learn.microsoft.com/en-us/power-bi/guidance/power-bi-optimization"],
        "source": "Curated Catalog",
        "summary": "Using Performance Analyzer in Power BI Desktop to inspect DAX query runtimes, visual display bottlenecks, and data model memory footprint.",
        "raw_excerpt": "Guidance on reducing model size, minimizing cardinality, removing unnecessary columns, and avoiding bidirectional cross filtering.",
        "tags": ["power-bi", "performance", "optimization", "enterprise"],
        "notes": "Distinguishes junior dashboard creators from senior BI architects."
    },

    # ----------------- 4. Data Engineering & Cloud Data -----------------
    {
        "title": "Microsoft Learn: Introduction to Azure Data Factory (ADF)",
        "category": "Certifications and Courses",
        "sub_category": "Cloud ETL",
        "skill_tag": "data_engineering",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "ROADMAP",
        "estimated_minutes": 180,
        "canonical_url": "https://learn.microsoft.com/en-us/training/modules/intro-to-azure-data-factory/",
        "primary_url": "https://learn.microsoft.com/en-us/training/modules/intro-to-azure-data-factory/",
        "all_urls": ["https://learn.microsoft.com/en-us/training/modules/intro-to-azure-data-factory/"],
        "source": "Curated Catalog",
        "summary": "Core Azure Data Factory concepts: Linked Services, Datasets, Pipelines, Copy Activities, and Triggers for cloud ETL orchestration.",
        "raw_excerpt": "Designing hybrid data integration pipelines, connecting on-premise databases to Azure Blob/Data Lake, and monitoring pipeline runs.",
        "tags": ["azure", "adf", "data-factory", "etl", "cloud"],
        "notes": "High demand skill in Indian IT consulting firms (TCS, Infosys, Wipro, Cognizant, Accenture)."
    },
    {
        "title": "Databricks: PySpark DataFrame Tutorial & Architecture",
        "category": "Technical Learning Materials",
        "sub_category": "Big Data & PySpark",
        "skill_tag": "pyspark",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 150,
        "canonical_url": "https://spark.apache.org/docs/latest/api/python/getting_started/quickstart_df.html",
        "primary_url": "https://spark.apache.org/docs/latest/api/python/getting_started/quickstart_df.html",
        "all_urls": ["https://spark.apache.org/docs/latest/api/python/getting_started/quickstart_df.html"],
        "source": "Curated Catalog",
        "summary": "Getting started with PySpark: SparkSession, DataFrame transformations vs actions, lazy evaluation, filtering, and aggregations.",
        "raw_excerpt": "Distributed computing fundamentals, creating DataFrames from Pandas/JSON/Parquet, executing SQL queries via spark.sql(), and writing results.",
        "tags": ["pyspark", "spark", "big-data", "python", "data-engineering"],
        "notes": "Top skill for transitioning from Data Analyst to Junior Data Engineer."
    },
    {
        "title": "Delta Lake Getting Started: ACID Transactions on Data Lakes",
        "category": "Technical Learning Materials",
        "sub_category": "Modern Data Architecture",
        "skill_tag": "data_engineering",
        "difficulty_level": "ADVANCED",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 110,
        "canonical_url": "https://docs.delta.io/latest/delta-intro.html",
        "primary_url": "https://docs.delta.io/latest/delta-intro.html",
        "all_urls": ["https://docs.delta.io/latest/delta-intro.html"],
        "source": "Curated Catalog",
        "summary": "Understanding Delta Lake: Medallion Architecture (Bronze, Silver, Gold), ACID transactions, schema enforcement, and time travel.",
        "raw_excerpt": "How Delta transaction logs guarantee serializability, prevent dirty reads, and enable atomic batch + streaming updates on cloud object stores.",
        "tags": ["delta-lake", "medallion-architecture", "databricks", "acid", "lakehouse"],
        "notes": "Standard architecture pattern in modern cloud data teams."
    },

    # ----------------- 5. Machine Learning & Predictive Analytics -----------------
    {
        "title": "Scikit-Learn Getting Started: Machine Learning in Python",
        "category": "Technical Learning Materials",
        "sub_category": "Machine Learning",
        "skill_tag": "data_analysis",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "DOCUMENTATION",
        "estimated_minutes": 140,
        "canonical_url": "https://scikit-learn.org/stable/getting_started.html",
        "primary_url": "https://scikit-learn.org/stable/getting_started.html",
        "all_urls": ["https://scikit-learn.org/stable/getting_started.html"],
        "source": "Curated Catalog",
        "summary": "Core machine learning workflows: Estimators, fit/predict paradigm, train-test splitting, feature scaling, and model evaluation metrics.",
        "raw_excerpt": "Linear regression, logistic regression, decision trees, cross-validation (KFold), and assembling preprocessing pipelines with ColumnTransformer.",
        "tags": ["python", "machine-learning", "scikit-learn", "analytics"],
        "notes": "Valuable for Data Analyst roles requiring predictive modeling or churn analysis."
    },
    {
        "title": "Kaggle Learn: Data Visualization with Seaborn and Matplotlib",
        "category": "Certifications and Courses",
        "sub_category": "Data Visualization",
        "skill_tag": "data_analysis",
        "difficulty_level": "BEGINNER",
        "resource_type": "INTERACTIVE_TUTORIAL",
        "estimated_minutes": 120,
        "canonical_url": "https://www.kaggle.com/learn/data-visualization",
        "primary_url": "https://www.kaggle.com/learn/data-visualization",
        "all_urls": ["https://www.kaggle.com/learn/data-visualization"],
        "source": "Curated Catalog",
        "summary": "Hands-on data visualization in Python: Line charts, bar charts, scatter plots, heatmaps, and distributions using Seaborn.",
        "raw_excerpt": "Translating analytical findings into visually compelling and informative graphics; adjusting color palettes, titles, and layout styling.",
        "tags": ["python", "visualization", "seaborn", "matplotlib", "kaggle"],
        "notes": "Essential for presenting portfolio projects and take-home case studies."
    },

    # ----------------- 6. Coding Practice, DSA & Assessment Preparation -----------------
    {
        "title": "LeetCode 75 Curated Study Plan: Essential DSA",
        "category": "Coding Practice",
        "sub_category": "Data Structures & Algorithms",
        "skill_tag": "dsa",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "EXERCISE_SET",
        "estimated_minutes": 360,
        "canonical_url": "https://leetcode.com/studyplan/leetcode-75/",
        "primary_url": "https://leetcode.com/studyplan/leetcode-75/",
        "all_urls": ["https://leetcode.com/studyplan/leetcode-75/"],
        "source": "Curated Catalog",
        "summary": "The premier curated collection of 75 essential algorithm problems covering arrays, two-pointers, sliding window, hash maps, trees, and graphs.",
        "raw_excerpt": "Structured problem sets designed to build interview-ready problem-solving instincts without drowning in thousands of questions.",
        "tags": ["leetcode", "dsa", "algorithms", "interview-prep", "coding"],
        "notes": "Target: Solve 1-2 problems daily during the 30-day interview sprint."
    },
    {
        "title": "SQLZoo: Interactive SQL Practice with Instant Feedback",
        "category": "Coding Practice",
        "sub_category": "SQL Practice",
        "skill_tag": "sql",
        "difficulty_level": "BEGINNER",
        "resource_type": "INTERACTIVE_TUTORIAL",
        "estimated_minutes": 120,
        "canonical_url": "https://sqlzoo.net/wiki/SQL_Tutorial",
        "primary_url": "https://sqlzoo.net/wiki/SQL_Tutorial",
        "all_urls": ["https://sqlzoo.net/wiki/SQL_Tutorial"],
        "source": "Curated Catalog",
        "summary": "Interactive in-browser SQL exercises with automatic test case validation covering SELECT, JOINs, nested queries, and window functions.",
        "raw_excerpt": "Real-time query execution environment with immediate error diagnosis and schema inspection across progressive difficulty tiers.",
        "tags": ["sql", "practice", "sqlzoo", "exercises", "interactive"],
        "notes": "Excellent warm-up before taking HackerRank or TestGorilla SQL assessments."
    },
    {
        "title": "NeetCode Roadmap: Visual Data Structures & Algorithms Guide",
        "category": "Coding Practice",
        "sub_category": "DSA Roadmap",
        "skill_tag": "dsa",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "ROADMAP",
        "estimated_minutes": 240,
        "canonical_url": "https://neetcode.io/roadmap",
        "primary_url": "https://neetcode.io/roadmap",
        "all_urls": ["https://neetcode.io/roadmap"],
        "source": "Curated Catalog",
        "summary": "Visual, interactive dependency graph of DSA topics from Arrays & Hashing up to Dynamic Programming and Graphs.",
        "raw_excerpt": "Includes video walkthroughs and clean Python code solutions for each pattern: two pointers, binary search, sliding window, and backtracking.",
        "tags": ["neetcode", "dsa", "roadmap", "python", "interview-prep"],
        "notes": "The single most recommended coding interview preparation roadmap worldwide."
    },

    # ----------------- 7. Interview Preparation & Behavioral Frameworks -----------------
    {
        "title": "STAR Method Behavioral Interview Mastery Framework",
        "category": "Interview Preparation",
        "sub_category": "Behavioral Skills",
        "skill_tag": "data_analysis",
        "difficulty_level": "BEGINNER",
        "resource_type": "CHEAT_SHEET",
        "estimated_minutes": 60,
        "canonical_url": "https://en.wikipedia.org/wiki/Situation,_task,_action_and_result",
        "primary_url": "https://en.wikipedia.org/wiki/Situation,_task,_action_and_result",
        "all_urls": ["https://en.wikipedia.org/wiki/Situation,_task,_action_and_result"],
        "source": "Curated Catalog",
        "summary": "Structuring behavioral answers using Situation, Task, Action, and Result to showcase quantifiable impact and problem solving.",
        "raw_excerpt": "How to answer 'Tell me about a time you handled a difficult stakeholder' or 'Describe a project where data was messy and deadlines were tight'.",
        "tags": ["interview-prep", "behavioral", "star-method", "hr-round"],
        "notes": "Essential preparation for HR and managerial screening rounds."
    },
    {
        "title": "Comprehensive Data Analyst Technical Interview Questions (50 Questions)",
        "category": "Interview Preparation",
        "sub_category": "Technical Interview",
        "skill_tag": "data_analysis",
        "difficulty_level": "INTERMEDIATE",
        "resource_type": "CHEAT_SHEET",
        "estimated_minutes": 150,
        "canonical_url": "https://github.com/alexeygrigorev/data-science-interviews",
        "primary_url": "https://github.com/alexeygrigorev/data-science-interviews",
        "all_urls": ["https://github.com/alexeygrigorev/data-science-interviews"],
        "source": "Curated Catalog",
        "summary": "Curated repository of technical questions on SQL queries, metric definitions, A/B testing basics, business KPIs, and data modeling.",
        "raw_excerpt": "Real interview questions collected from product and enterprise companies: customer retention calculations, churn cohorts, and KPI anomaly root causes.",
        "tags": ["interview-questions", "data-analyst", "kpis", "sql", "business-intelligence"],
        "notes": "Review 24 hours before any technical phone screen or on-site panel."
    },
    {
        "title": "System Design Primer: Scalable Architecture Basics",
        "category": "Technical Learning Materials",
        "sub_category": "Architecture",
        "skill_tag": "fastapi",
        "difficulty_level": "ADVANCED",
        "resource_type": "ROADMAP",
        "estimated_minutes": 240,
        "canonical_url": "https://github.com/donnemartin/system-design-primer",
        "primary_url": "https://github.com/donnemartin/system-design-primer",
        "all_urls": ["https://github.com/donnemartin/system-design-primer"],
        "source": "Curated Catalog",
        "summary": "Learn how to design large-scale systems: caching (Redis), load balancers, asynchronous workers, database sharding, and CAP theorem.",
        "raw_excerpt": "System design fundamentals for software engineers and backend developers, including diagrams, trade-off comparisons, and real-world architectures.",
        "tags": ["system-design", "architecture", "scalability", "backend"],
        "notes": "Essential for junior developers aspiring to progress to mid-level software roles."
    }
]


def seed_curated_learning_resources(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Seed or update curated learning resources idempotently.
    Preserves user completion status and personal notes if they already exist.
    """
    from careerorbit.database.db import get_connection

    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    cursor = conn.cursor()
    inserted_count = 0
    updated_count = 0
    now_utc = datetime.now(timezone.utc).isoformat()

    try:
        for res in CURATED_LEARNING_RESOURCES:
            canonical_url = res["canonical_url"]
            all_urls_json = json.dumps(res.get("all_urls") or [canonical_url])
            tags_json = json.dumps(res.get("tags") or [])

            cursor.execute("SELECT id, is_completed, notes FROM learning_resources WHERE canonical_url = ?", (canonical_url,))
            existing = cursor.fetchone()

            cursor.execute("""
                INSERT INTO learning_resources (
                    title, category, sub_category, canonical_url, primary_url,
                    all_urls, source, source_message_uid, raw_excerpt, summary,
                    tags, saved_at, notes, skill_tag, difficulty_level, resource_type,
                    estimated_minutes, created_at, is_completed, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(canonical_url) DO UPDATE SET
                    title = excluded.title,
                    category = excluded.category,
                    sub_category = excluded.sub_category,
                    primary_url = excluded.primary_url,
                    all_urls = excluded.all_urls,
                    source = excluded.source,
                    raw_excerpt = excluded.raw_excerpt,
                    summary = excluded.summary,
                    tags = excluded.tags,
                    skill_tag = excluded.skill_tag,
                    difficulty_level = excluded.difficulty_level,
                    resource_type = excluded.resource_type,
                    estimated_minutes = excluded.estimated_minutes
            """, (
                res["title"],
                res["category"],
                res.get("sub_category", ""),
                canonical_url,
                res["primary_url"],
                all_urls_json,
                res.get("source", "Curated Catalog"),
                "",
                res.get("raw_excerpt", ""),
                res.get("summary", ""),
                tags_json,
                now_utc,
                res.get("notes", ""),
                res.get("skill_tag", ""),
                res.get("difficulty_level", "BEGINNER"),
                res.get("resource_type", "DOCUMENTATION"),
                res.get("estimated_minutes", 30),
                now_utc
            ))

            if existing is None:
                inserted_count += 1
            else:
                updated_count += 1

        conn.commit()
    finally:
        if should_close:
            conn.close()

    return {
        "status": "SUCCESS",
        "total_curated": len(CURATED_LEARNING_RESOURCES),
        "inserted": inserted_count,
        "updated": updated_count
    }
