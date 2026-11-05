"""
Text-to-SQL engine.
Converts a natural language business question into a SQL query,
runs it against the local SQLite sales database, and returns results.
"""

import os
import sqlite3
import pandas as pd
from groq import Groq
from dotenv import load_dotenv

load_dotenv()  # reads GROQ_API_KEY from a .env file if present

# ---- Configuration ----
DB_PATH = "sales.db"
MODEL = "openai/gpt-oss-120b"  # Groq deprecated llama-3.3-70b-versatile in June 2026; this is their recommended replacement

# The schema description fed to the LLM as context.
# This is the single most important piece for accuracy -- the LLM can only
# write correct SQL if it knows exactly what columns exist and what they mean.
SCHEMA_DESCRIPTION = """
Table: sales

Columns:
- order_id (TEXT): unique order identifier
- order_date (TEXT, format YYYY-MM-DD): date the order was placed
- product_id (TEXT): product identifier
- product_name (TEXT): name of the product, e.g. "Wireless Mouse"
- category (TEXT): one of "Electronics", "Accessories", "Furniture", "Stationery"
- quantity (INTEGER): number of units ordered
- unit_price (INTEGER): price per unit in INR
- revenue (INTEGER): quantity * unit_price, total revenue for that order line
- customer_id (TEXT): customer identifier
- region (TEXT): one of "North", "South", "East", "West", "Central"

Notes:
- Today's date for "last N months" style questions should be treated as the
  MAX(order_date) in the table, since this is a static historical dataset.
- Always use SQLite-compatible syntax (e.g. date() functions, not MySQL/Postgres ones).
"""

SYSTEM_PROMPT = f"""You are a SQL generator for a SQLite database. Given a business
question in natural language, output ONLY a single valid SQLite SQL query that
answers it. Do not include explanations, markdown formatting, or code fences --
output raw SQL only.

{SCHEMA_DESCRIPTION}
"""

CLARIFY_SYSTEM_PROMPT = f"""You check whether a business question about a sales
database is answerable as a single unambiguous SQL query, given this schema:

{SCHEMA_DESCRIPTION}

A question is AMBIGUOUS if it's missing information needed to write one correct
query -- for example, unclear metric ("best" could mean highest total revenue,
highest single order, or most units sold), unclear grouping (by product? by
region? by month?), or unclear time window ("recently" -- how recent?).

A question is CLEAR if a competent analyst could write exactly one SQL query
for it without guessing.

Respond in EXACTLY this format, nothing else:
AMBIGUOUS: <one short clarifying question to ask the user>
or
CLEAR: no clarification needed
"""


def get_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        # Fall back to Streamlit Cloud secrets when running as a deployed app
        try:
            import streamlit as st
            api_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            pass
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not set. Get a free key at https://console.groq.com "
            "and set it in your .env file (local) or Streamlit Secrets (deployed)."
        )
    return Groq(api_key=api_key)


def question_to_sql(question: str) -> str:
    """Send the question + schema to Groq, get back a raw SQL query."""
    client = get_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0,  # deterministic SQL generation
    )
    sql = response.choices[0].message.content.strip()

    # Defensive cleanup in case the model wraps output in code fences anyway
    if sql.startswith("```"):
        sql = sql.strip("`")
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip()

    return sql


def check_ambiguity(question: str):
    """
    Ask the LLM whether the question is answerable as one clear SQL query.
    Returns None if clear, or a clarifying question (str) if ambiguous.
    """
    client = get_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CLARIFY_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0,
    )
    result = response.choices[0].message.content.strip()

    if result.upper().startswith("AMBIGUOUS:"):
        return result.split(":", 1)[1].strip()
    return None  # CLEAR, or unrecognized format -- proceed either way


def run_sql(sql: str) -> pd.DataFrame:
    """Execute SQL against the local database and return a DataFrame."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(sql, conn)
    finally:
        conn.close()
    return df


def ask(question: str, skip_clarification: bool = False):
    """
    Full pipeline: ambiguity check -> question -> SQL -> results.
    Returns (sql, dataframe, error_or_none, clarification_or_none).

    If the question is ambiguous, sql/dataframe/error are all None and
    clarification holds a follow-up question to show the user instead.
    Set skip_clarification=True to force execution anyway (e.g. after the
    user has already answered the clarifying question).
    """
    if not skip_clarification:
        try:
            clarification = check_ambiguity(question)
        except Exception as e:
            clarification = None  # if the check itself fails, just proceed
        if clarification:
            return None, None, None, clarification

    try:
        sql = question_to_sql(question)
    except Exception as e:
        return None, None, f"Error generating SQL: {e}", None

    try:
        df = run_sql(sql)
    except Exception as e:
        return sql, None, f"Error running SQL: {e}", None

    return sql, df, None, None


if __name__ == "__main__":
    # Quick manual test from the command line
    q = "What was the best revenue we generated?"  # deliberately ambiguous
    sql, df, err, clarification = ask(q)
    print("Question:", q)
    if clarification:
        print("Clarification needed:", clarification)
    elif err:
        print("Error:", err)
    else:
        print("Generated SQL:", sql)
        print(df)