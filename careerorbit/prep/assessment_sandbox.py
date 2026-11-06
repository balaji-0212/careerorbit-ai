"""Phase 4 — Technical Assessment Sandbox & Evaluator.

Provides safe in-memory SQLite query execution and deterministic conceptual evaluation
for SQL, Python, Data Engineering, and ML screening challenges.
Zero host execution of arbitrary untrusted shell or system scripts.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from careerorbit.database.db import (
    get_connection,
    get_assessment_challenge,
    save_assessment_challenge,
    save_assessment_submission
)

FORBIDDEN_SQL_PATTERNS = [
    r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b",
    r"\bALTER\b", r"\bCREATE\b", r"\bATTACH\b", r"\bDETACH\b",
    r"\bPRAGMA\b", r"\bEXEC\b", r"\bREINDEX\b", r"\bVACUUM\b"
]


CURATED_ASSESSMENT_CHALLENGES: List[Dict[str, Any]] = [
    # ----------------- SQL CHALLENGES -----------------
    {
        "challenge_uid": "sql-window-top-salaries",
        "title": "Top 2 Salaries in Each Department",
        "category": "SQL",
        "difficulty": "MEDIUM",
        "question_type": "QUERY",
        "prompt_markdown": (
            "Write an SQL query to find the top 2 highest-paid employees in each department. "
            "If there is a tie in salary, both employees should share the same rank using `DENSE_RANK()`. "
            "Return `department`, `employee_name`, `salary`, and `salary_rank` ordered by `department` ASC, `salary_rank` ASC."
        ),
        "initial_code": "-- Write your SQL query below\nSELECT \n    department,\n    employee_name,\n    salary,\n    DENSE_RANK() OVER (PARTITION BY department ORDER BY salary DESC) as salary_rank\nFROM employees;\n",
        "test_fixtures": {
            "schema_sql": """
                CREATE TABLE employees (
                    id INTEGER PRIMARY KEY,
                    employee_name TEXT,
                    department TEXT,
                    salary INTEGER
                );
            """,
            "seed_sql": """
                INSERT INTO employees VALUES (1, 'Aarav', 'Engineering', 95000);
                INSERT INTO employees VALUES (2, 'Diya', 'Engineering', 95000);
                INSERT INTO employees VALUES (3, 'Karthik', 'Engineering', 85000);
                INSERT INTO employees VALUES (4, 'Priya', 'Engineering', 70000);
                INSERT INTO employees VALUES (5, 'Rohan', 'Analytics', 80000);
                INSERT INTO employees VALUES (6, 'Sneha', 'Analytics', 75000);
                INSERT INTO employees VALUES (7, 'Vikram', 'Analytics', 60000);
            """
        },
        "expected_output": [
            {"department": "Analytics", "employee_name": "Rohan", "salary": 80000, "salary_rank": 1},
            {"department": "Analytics", "employee_name": "Sneha", "salary": 75000, "salary_rank": 2},
            {"department": "Engineering", "employee_name": "Aarav", "salary": 95000, "salary_rank": 1},
            {"department": "Engineering", "employee_name": "Diya", "salary": 95000, "salary_rank": 1},
            {"department": "Engineering", "employee_name": "Karthik", "salary": 85000, "salary_rank": 2}
        ],
        "explanation": "DENSE_RANK() assigns consecutive ranks without gaps when ties occur. Filtering salary_rank <= 2 in a CTE or subquery yields top 2 ranks per department.",
        "time_limit_minutes": 25
    },
    {
        "challenge_uid": "sql-customer-repeat-orders",
        "title": "High-Value Repeat Customers",
        "category": "SQL",
        "difficulty": "EASY",
        "question_type": "QUERY",
        "prompt_markdown": (
            "Write an SQL query to identify repeat customers who have placed at least 3 orders and have spent a cumulative total of at least 1000. "
            "Return `customer_id`, `total_orders`, and `total_spend` ordered by `total_spend` DESC."
        ),
        "initial_code": "-- Return customer_id, count of orders, sum of amount\nSELECT customer_id, COUNT(*) as total_orders, SUM(order_amount) as total_spend\nFROM orders\nGROUP BY customer_id\nHAVING total_orders >= 3 AND total_spend >= 1000\nORDER BY total_spend DESC;\n",
        "test_fixtures": {
            "schema_sql": """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER,
                    order_amount REAL,
                    order_date TEXT
                );
            """,
            "seed_sql": """
                INSERT INTO orders VALUES (1, 101, 350.0, '2026-01-10');
                INSERT INTO orders VALUES (2, 101, 450.0, '2026-01-15');
                INSERT INTO orders VALUES (3, 101, 300.0, '2026-02-01');
                INSERT INTO orders VALUES (4, 102, 800.0, '2026-01-11');
                INSERT INTO orders VALUES (5, 102, 100.0, '2026-02-05');
                INSERT INTO orders VALUES (6, 103, 500.0, '2026-01-05');
                INSERT INTO orders VALUES (7, 103, 600.0, '2026-01-20');
                INSERT INTO orders VALUES (8, 103, 700.0, '2026-02-12');
                INSERT INTO orders VALUES (9, 104, 1200.0, '2026-02-15');
            """
        },
        "expected_output": [
            {"customer_id": 103, "total_orders": 3, "total_spend": 1800.0},
            {"customer_id": 101, "total_orders": 3, "total_spend": 1100.0}
        ],
        "explanation": "GROUP BY customer_id with HAVING COUNT(*) >= 3 AND SUM(order_amount) >= 1000 correctly filters aggregated groups.",
        "time_limit_minutes": 15
    },
    {
        "challenge_uid": "sql-churned-accounts",
        "title": "Dormant Users Without Recent Orders",
        "category": "SQL",
        "difficulty": "EASY",
        "question_type": "QUERY",
        "prompt_markdown": (
            "Write an SQL query to find all users registered in the database who have never placed an order. "
            "Return `user_id` and `user_name` ordered by `user_id` ASC."
        ),
        "initial_code": "-- Use LEFT JOIN to detect users with zero orders\nSELECT u.id as user_id, u.name as user_name\nFROM users u\nLEFT JOIN orders o ON u.id = o.user_id\nWHERE o.id IS NULL\nORDER BY u.id ASC;\n",
        "test_fixtures": {
            "schema_sql": """
                CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL);
            """,
            "seed_sql": """
                INSERT INTO users VALUES (1, 'Alice');
                INSERT INTO users VALUES (2, 'Bob');
                INSERT INTO users VALUES (3, 'Charlie');
                INSERT INTO users VALUES (4, 'David');
                INSERT INTO orders VALUES (101, 1, 99.0);
                INSERT INTO orders VALUES (102, 3, 149.0);
            """
        },
        "expected_output": [
            {"user_id": 2, "user_name": "Bob"},
            {"user_id": 4, "user_name": "David"}
        ],
        "explanation": "A LEFT JOIN with WHERE foreign_key IS NULL is the canonical method for anti-join exclusion.",
        "time_limit_minutes": 15
    },
    {
        "challenge_uid": "sql-monthly-running-total",
        "title": "Monthly Cumulative Revenue Running Total",
        "category": "SQL",
        "difficulty": "MEDIUM",
        "question_type": "QUERY",
        "prompt_markdown": (
            "Write an SQL query to compute the cumulative running total of revenue month by month. "
            "Return `month`, `monthly_revenue`, and `running_total` ordered by `month` ASC."
        ),
        "initial_code": "SELECT \n    month,\n    revenue as monthly_revenue,\n    SUM(revenue) OVER (ORDER BY month ASC) as running_total\nFROM monthly_sales\nORDER BY month ASC;\n",
        "test_fixtures": {
            "schema_sql": """
                CREATE TABLE monthly_sales (
                    month TEXT PRIMARY KEY,
                    revenue INTEGER
                );
            """,
            "seed_sql": """
                INSERT INTO monthly_sales VALUES ('2026-01', 12000);
                INSERT INTO monthly_sales VALUES ('2026-02', 15000);
                INSERT INTO monthly_sales VALUES ('2026-03', 18000);
                INSERT INTO monthly_sales VALUES ('2026-04', 21000);
            """
        },
        "expected_output": [
            {"month": "2026-01", "monthly_revenue": 12000, "running_total": 12000},
            {"month": "2026-02", "monthly_revenue": 15000, "running_total": 27000},
            {"month": "2026-03", "monthly_revenue": 18000, "running_total": 45000},
            {"month": "2026-04", "monthly_revenue": 21000, "running_total": 66000}
        ],
        "explanation": "SUM(revenue) OVER (ORDER BY month ASC) creates an unbounded preceding running total across ordered monthly periods.",
        "time_limit_minutes": 20
    },
    {
        "challenge_uid": "sql-mom-growth-rate",
        "title": "Month-Over-Month Revenue Growth Percentage",
        "category": "SQL",
        "difficulty": "HARD",
        "question_type": "QUERY",
        "prompt_markdown": (
            "Write an SQL query using `LAG()` to calculate the percentage revenue change compared to the previous month. "
            "For the first month (where prior revenue is NULL), growth_pct should be NULL. "
            "Round `growth_pct` to 1 decimal place. Return `month`, `revenue`, `prev_revenue`, and `growth_pct` ordered by `month` ASC."
        ),
        "initial_code": "WITH monthly_rev AS (\n    SELECT \n        month, \n        revenue,\n        LAG(revenue, 1) OVER (ORDER BY month) as prev_revenue\n    FROM monthly_sales\n)\nSELECT \n    month,\n    revenue,\n    prev_revenue,\n    ROUND(((revenue - prev_revenue) * 100.0 / prev_revenue), 1) as growth_pct\nFROM monthly_rev\nORDER BY month ASC;\n",
        "test_fixtures": {
            "schema_sql": """
                CREATE TABLE monthly_sales (month TEXT PRIMARY KEY, revenue REAL);
            """,
            "seed_sql": """
                INSERT INTO monthly_sales VALUES ('2026-01', 10000.0);
                INSERT INTO monthly_sales VALUES ('2026-02', 12500.0);
                INSERT INTO monthly_sales VALUES ('2026-03', 15000.0);
            """
        },
        "expected_output": [
            {"month": "2026-01", "revenue": 10000.0, "prev_revenue": None, "growth_pct": None},
            {"month": "2026-02", "revenue": 12500.0, "prev_revenue": 10000.0, "growth_pct": 25.0},
            {"month": "2026-03", "revenue": 15000.0, "prev_revenue": 12500.0, "growth_pct": 20.0}
        ],
        "explanation": "LAG(revenue, 1) retrieves preceding row value. (current - prev) * 100.0 / prev computes accurate MoM growth.",
        "time_limit_minutes": 30
    },

    # ----------------- PYTHON & DATA ANALYSIS -----------------
    {
        "challenge_uid": "py-pandas-missing-data-strategy",
        "title": "Handling Missing Values in Continuous Sensor Data",
        "category": "PYTHON",
        "difficulty": "MEDIUM",
        "question_type": "MULTIPLE_CHOICE",
        "prompt_markdown": (
            "You have a time-series dataset of hourly machine temperature readings with occasional missing intervals of 1-2 hours due to network blips. "
            "Which imputation technique is most appropriate to preserve the physical properties of the signal without introducing lookahead bias?"
        ),
        "initial_code": "",
        "options": [
            {"key": "A", "text": "Replace all NaNs with the overall column mean."},
            {"key": "B", "text": "Forward fill (`ffill()` or linear interpolation with limit=2)."},
            {"key": "C", "text": "Drop all rows with missing values (`dropna()`)."},
            {"key": "D", "text": "Replace with zero."}
        ],
        "expected_output": "B",
        "explanation": "For continuous time-series data with small gaps, forward-fill or linear interpolation preserves temporal continuity without leaking future data.",
        "time_limit_minutes": 10
    },
    {
        "challenge_uid": "py-dsa-lookup-complexity",
        "title": "Lookup Time Complexity: Hash Set vs Python List",
        "category": "PYTHON",
        "difficulty": "EASY",
        "question_type": "MULTIPLE_CHOICE",
        "prompt_markdown": (
            "When checking whether an element exists in a collection of N items (`x in collection`), "
            "what are the average-case time complexities for a Python `list` versus a Python `set`?"
        ),
        "initial_code": "",
        "options": [
            {"key": "A", "text": "List: O(1), Set: O(N)"},
            {"key": "B", "text": "List: O(log N), Set: O(1)"},
            {"key": "C", "text": "List: O(N), Set: O(1)"},
            {"key": "D", "text": "List: O(N), Set: O(log N)"}
        ],
        "expected_output": "C",
        "explanation": "A Python list requires linear scanning O(N), while a set uses a hash table providing average-case O(1) constant time lookup.",
        "time_limit_minutes": 10
    },
    {
        "challenge_uid": "py-pandas-groupby-multiindex",
        "title": "Flattening Hierarchical Column Indexes after GroupBy",
        "category": "PYTHON",
        "difficulty": "MEDIUM",
        "question_type": "MULTIPLE_CHOICE",
        "prompt_markdown": (
            "After running `df.groupby('dept').agg({'salary': ['mean', 'max'], 'bonus': 'sum'})`, the resulting DataFrame has a MultiIndex on columns. "
            "What is the most idiomatic way in modern Pandas to flatten the columns into single-level strings like `salary_mean`?"
        ),
        "initial_code": "",
        "options": [
            {"key": "A", "text": "df.columns = ['_'.join(c).strip('_') for c in df.columns]"},
            {"key": "B", "text": "df.unstack(level=0)"},
            {"key": "C", "text": "df.reset_index(inplace=True)"},
            {"key": "D", "text": "df.pivot_table(index='dept')"}
        ],
        "expected_output": "A",
        "explanation": "List comprehension joining tuple elements with '_' is the standard and robust method to flatten multi-level column names in Pandas.",
        "time_limit_minutes": 15
    },

    # ----------------- CLOUD DATA ENGINEERING -----------------
    {
        "challenge_uid": "de-medallion-architecture-layers",
        "title": "Medallion Architecture Layer Separation",
        "category": "DATA_ENGINEERING",
        "difficulty": "MEDIUM",
        "question_type": "MULTIPLE_CHOICE",
        "prompt_markdown": (
            "In modern lakehouse design (Databricks / Delta Lake), what is the primary role of the **Silver** layer compared to Bronze and Gold?"
        ),
        "initial_code": "",
        "options": [
            {"key": "A", "text": "Stores raw, unaltered payloads directly as appended from source systems."},
            {"key": "B", "text": "Provides pre-aggregated, business-level star schemas for executive dashboards."},
            {"key": "C", "text": "Provides cleaned, cleansed, enriched, and validated enterprise tables (conformed view)."},
            {"key": "D", "text": "Serves as cold storage archive for regulatory compliance."}
        ],
        "expected_output": "C",
        "explanation": "Bronze is raw ingest, Silver is cleaned/conformed/enriched, and Gold is aggregated business-level data models.",
        "time_limit_minutes": 10
    },
    {
        "challenge_uid": "de-pyspark-data-skew",
        "title": "Mitigating Join Skew in Distributed Processing",
        "category": "DATA_ENGINEERING",
        "difficulty": "HARD",
        "question_type": "MULTIPLE_CHOICE",
        "prompt_markdown": (
            "In Apache Spark / PySpark, when joining a large 500M row transaction table with a small 20K row lookup table, "
            "one executor runs out of memory (OOM) due to partition skew. What is the most effective solution?"
        ),
        "initial_code": "",
        "options": [
            {"key": "A", "text": "Increase spark.executor.cores from 4 to 8."},
            {"key": "B", "text": "Use a Broadcast Join (`broadcast(small_df)`) to replicate the small table to all executors."},
            {"key": "C", "text": "Sort the large table by transaction date before joining."},
            {"key": "D", "text": "Repartition the small table into 1,000 partitions."}
        ],
        "expected_output": "B",
        "explanation": "Broadcasting the lookup table avoids the network shuffle entirely, eliminating data skew on the join key.",
        "time_limit_minutes": 15
    },
    {
        "challenge_uid": "de-pipeline-idempotency",
        "title": "Ensuring Idempotent Batch Pipeline Ingestion",
        "category": "DATA_ENGINEERING",
        "difficulty": "MEDIUM",
        "question_type": "MULTIPLE_CHOICE",
        "prompt_markdown": (
            "An Azure Data Factory (ADF) pipeline failed midway through its nightly load. "
            "Which pattern guarantees that retrying the entire daily run will not produce duplicate records in the destination data warehouse?"
        ),
        "initial_code": "",
        "options": [
            {"key": "A", "text": "Append-only insert without primary key checks."},
            {"key": "B", "text": "Partition overwrite (or pre-delete by `date = @pipeline().parameters.date`) before insertion."},
            {"key": "C", "text": "Run a post-load deduplication query every 7 days."},
            {"key": "D", "text": "Ignore failures and wait for tomorrow's run."}
        ],
        "expected_output": "B",
        "explanation": "Partition replacement or atomic merge on target partitions ensures idempotency: running the same job multiple times produces identical state.",
        "time_limit_minutes": 15
    },

    # ----------------- MACHINE LEARNING FUNDAMENTALS -----------------
    {
        "challenge_uid": "ml-precision-vs-recall-imbalance",
        "title": "Metric Choice for High-Imbalance Fraud Detection",
        "category": "MACHINE_LEARNING",
        "difficulty": "MEDIUM",
        "question_type": "MULTIPLE_CHOICE",
        "prompt_markdown": (
            "In credit card fraud detection where only 0.1% of transactions are fraudulent, "
            "a model predicting 'Not Fraud' 100% of the time achieves 99.9% Accuracy. "
            "Which metric should the team optimize to ensure fraudulent transactions are actively caught?"
        ),
        "initial_code": "",
        "options": [
            {"key": "A", "text": "Accuracy"},
            {"key": "B", "text": "Recall (Sensitivity) and PR-AUC"},
            {"key": "C", "text": "Mean Squared Error (MSE)"},
            {"key": "D", "text": "R-Squared Score"}
        ],
        "expected_output": "B",
        "explanation": "High recall minimizes false negatives (missed frauds). PR-AUC (Precision-Recall Area Under Curve) evaluates performance without distortion from majority true negatives.",
        "time_limit_minutes": 10
    },
    {
        "challenge_uid": "ml-l1-vs-l2-regularization",
        "title": "L1 (Lasso) vs L2 (Ridge) Regularization Effects",
        "category": "MACHINE_LEARNING",
        "difficulty": "EASY",
        "question_type": "MULTIPLE_CHOICE",
        "prompt_markdown": (
            "When dealing with a high-dimensional tabular dataset with 200 collinear features, "
            "why is L1 (Lasso) regularization preferred when feature selection is required?"
        ),
        "initial_code": "",
        "options": [
            {"key": "A", "text": "L1 drives non-informative feature weights strictly to zero, effectively performing sparse feature selection."},
            {"key": "B", "text": "L1 keeps all weights non-zero but shrinks them proportionally."},
            {"key": "C", "text": "L1 cannot be used on regression tasks."},
            {"key": "D", "text": "L1 doubles the number of model parameters."}
        ],
        "expected_output": "A",
        "explanation": "Due to the geometry of the L1 penalty (|w|), solutions frequently intersect at the axes, forcing less significant coefficients strictly to zero.",
        "time_limit_minutes": 10
    },
    {
        "challenge_uid": "ml-data-leakage-prevention",
        "title": "Preventing Preprocessing Data Leakage",
        "category": "MACHINE_LEARNING",
        "difficulty": "MEDIUM",
        "question_type": "MULTIPLE_CHOICE",
        "prompt_markdown": (
            "Which of the following practices represents a serious **data leakage** error during model training?"
        ),
        "initial_code": "",
        "options": [
            {"key": "A", "text": "Fitting `StandardScaler` only on the training set and using `transform()` on the test set."},
            {"key": "B", "text": "Performing mean imputation and feature scaling on the entire dataset before splitting into train/test."},
            {"key": "C", "text": "Using cross-validation within the training split."},
            {"key": "D", "text": "Encoding categorical variables using only categories observed in the training split."}
        ],
        "expected_output": "B",
        "explanation": "Computing scaling parameters or statistics across the entire dataset leaks distribution knowledge from the test set into training.",
        "time_limit_minutes": 10
    }
]


def seed_assessment_challenges(conn: Optional[sqlite3.Connection] = None) -> int:
    """Idempotently seed the curated technical assessment challenge bank."""
    close_at_end = False
    if conn is None:
        conn = get_connection()
        close_at_end = True

    count = 0
    try:
        for c in CURATED_ASSESSMENT_CHALLENGES:
            save_assessment_challenge(c)
            count += 1
    finally:
        if close_at_end:
            conn.close()

    return count


def evaluate_sql_submission(challenge: Dict[str, Any], query: str) -> Dict[str, Any]:
    """Execute SQL query safely inside an isolated in-memory SQLite sandbox with strict validation."""
    clean_query = (query or "").strip()
    if not clean_query:
        return {
            "is_passed": False,
            "tests_passed": 0,
            "total_tests": 1,
            "score": 0.0,
            "feedback_notes": "Submission was empty. Please provide a valid SQL query.",
            "output": [],
            "execution_time_ms": 0
        }

    # Security check: disallow multiple statements
    statements = [s.strip() for s in clean_query.split(";") if s.strip()]
    if len(statements) > 1:
        return {
            "is_passed": False,
            "tests_passed": 0,
            "total_tests": 1,
            "score": 0.0,
            "feedback_notes": "Security Rule: Multiple SQL statements are not permitted in the assessment sandbox.",
            "output": [],
            "execution_time_ms": 0
        }

    # Query must start with SELECT or WITH
    primary_stmt = statements[0] if statements else clean_query
    if not re.match(r"^(SELECT|WITH)\b", primary_stmt, re.IGNORECASE):
        return {
            "is_passed": False,
            "tests_passed": 0,
            "total_tests": 1,
            "score": 0.0,
            "feedback_notes": "Security Rule: Only read-only SELECT or WITH queries are permitted in the sandbox.",
            "output": [],
            "execution_time_ms": 0
        }

    # Check forbidden DDL/DML keywords
    for pattern in FORBIDDEN_SQL_PATTERNS:
        if re.search(pattern, primary_stmt, re.IGNORECASE):
            return {
                "is_passed": False,
                "tests_passed": 0,
                "total_tests": 1,
                "score": 0.0,
                "feedback_notes": f"Security Rule: Forbidden statement '{pattern.strip(r'b\\')}' detected.",
                "output": [],
                "execution_time_ms": 0
            }

    # Execute in clean in-memory database
    start_time = time.perf_counter()
    mem_conn = sqlite3.connect(":memory:")
    mem_conn.row_factory = sqlite3.Row
    cursor = mem_conn.cursor()

    try:
        fixtures = challenge.get("test_fixtures", {})
        schema_sql = fixtures.get("schema_sql", "")
        seed_sql = fixtures.get("seed_sql", "")

        if schema_sql:
            cursor.executescript(schema_sql)
        if seed_sql:
            cursor.executescript(seed_sql)

        # Execute candidate query with strict limit
        cursor.execute(primary_stmt)
        rows = cursor.fetchmany(50)
        output_data = [dict(r) for r in rows]

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # Compare outputs with expected output
        expected = challenge.get("expected_output", [])
        is_match, feedback = _compare_sql_outputs(output_data, expected)

        return {
            "is_passed": is_match,
            "tests_passed": 1 if is_match else 0,
            "total_tests": 1,
            "score": 100.0 if is_match else 0.0,
            "feedback_notes": feedback,
            "output": output_data,
            "execution_time_ms": elapsed_ms
        }
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return {
            "is_passed": False,
            "tests_passed": 0,
            "total_tests": 1,
            "score": 0.0,
            "feedback_notes": f"SQL Execution Error: {str(e)}",
            "output": [],
            "execution_time_ms": elapsed_ms
        }
    finally:
        mem_conn.close()


def _compare_sql_outputs(actual: List[Dict[str, Any]], expected: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Compare normalized SQL output rows against deterministic expected result."""
    if not isinstance(expected, list):
        return False, "Malformed challenge expectation."

    if len(actual) != len(expected):
        return False, f"Row count mismatch: expected {len(expected)} rows, but query returned {len(actual)} rows."

    for idx, (act_row, exp_row) in enumerate(zip(actual, expected)):
        # Normalize column key names to lowercase
        act_norm = {k.lower(): v for k, v in act_row.items()}
        exp_norm = {k.lower(): v for k, v in exp_row.items()}

        for k, exp_val in exp_norm.items():
            if k not in act_norm:
                return False, f"Missing required column '{k}' in row {idx + 1}."
            act_val = act_norm[k]
            # Handle float rounding
            if isinstance(exp_val, float) and isinstance(act_val, (int, float)):
                if round(exp_val, 2) != round(float(act_val), 2):
                    return False, f"Value mismatch in column '{k}' at row {idx + 1}: expected {exp_val}, received {act_val}."
            elif act_val != exp_val:
                return False, f"Value mismatch in column '{k}' at row {idx + 1}: expected '{exp_val}', received '{act_val}'."

    return True, "All test fixtures passed! Output matches expected benchmark."


def evaluate_conceptual_submission(challenge: Dict[str, Any], answer: str) -> Dict[str, Any]:
    """Deterministic evaluation for multiple choice and conceptual questions."""
    clean_ans = (answer or "").strip().upper()
    expected = str(challenge.get("expected_output", "")).strip().upper()

    is_correct = (clean_ans == expected)
    feedback = (
        "Correct! Outstanding work."
        if is_correct
        else f"Incorrect. Your answer was '{clean_ans}', but the correct answer is '{expected}'."
    )

    return {
        "is_passed": is_correct,
        "tests_passed": 1 if is_correct else 0,
        "total_tests": 1,
        "score": 100.0 if is_correct else 0.0,
        "feedback_notes": feedback,
        "output": [{"submitted_answer": clean_ans, "correct_answer": expected}],
        "execution_time_ms": 5
    }


def evaluate_submission(challenge_id: int, submitted_code: str) -> Dict[str, Any]:
    """Universal evaluation router that executes assessment safely and records attempt history."""
    challenge = get_assessment_challenge(challenge_id, include_solution=True)
    if not challenge:
        raise ValueError(f"Challenge with id {challenge_id} does not exist.")

    q_type = challenge.get("question_type", "QUERY")

    if q_type == "QUERY":
        eval_result = evaluate_sql_submission(challenge, submitted_code)
    else:
        eval_result = evaluate_conceptual_submission(challenge, submitted_code)

    # Save to database
    submission_record = {
        "challenge_id": challenge_id,
        "submitted_code": submitted_code,
        "is_passed": eval_result["is_passed"],
        "execution_time_ms": eval_result.get("execution_time_ms", 0),
        "tests_passed": eval_result.get("tests_passed", 0),
        "total_tests": eval_result.get("total_tests", 1),
        "score": eval_result.get("score", 0.0),
        "feedback_notes": eval_result.get("feedback_notes", ""),
        "output": eval_result.get("output", [])
    }
    sub_id = save_assessment_submission(submission_record)

    eval_result["id"] = sub_id
    eval_result["challenge_id"] = challenge_id
    eval_result["submitted_code"] = submitted_code
    eval_result["explanation"] = challenge.get("explanation", "")
    eval_result["expected_output"] = challenge.get("expected_output")

    return eval_result
