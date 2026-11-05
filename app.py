import streamlit as st
from nl_to_sql import ask

st.set_page_config(page_title="Text-to-SQL Assistant", page_icon="📊", layout="centered")

st.title("📊 Text-to-SQL Business Assistant")
st.caption("Ask a business question in plain English — it gets converted to SQL and run against a sales database.")

with st.expander("💡 Example questions"):
    st.markdown("""
    **Clear questions (answered directly):**
    - What was the total revenue in the last 12 months?
    - Show me the top 5 customers by total spend.
    - What is the average order value by region?

    **Ambiguous questions (it will ask you to clarify first):**
    - What was the best revenue we generated?
    - Show me the top products.
    """)

if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
if "clarification" not in st.session_state:
    st.session_state.clarification = None

question = st.text_input(
    "Ask a question about the sales data:",
    placeholder="e.g. What was the total revenue last quarter?",
)

if st.button("Ask", type="primary") and question:
    with st.spinner("Checking your question and generating SQL..."):
        sql, df, err, clarification = ask(question)

    if clarification:
        st.session_state.pending_question = question
        st.session_state.clarification = clarification
    else:
        st.session_state.pending_question = None
        st.session_state.clarification = None
        if err:
            st.error(err)
            if sql:
                st.code(sql, language="sql")
        else:
            st.subheader("Generated SQL")
            st.code(sql, language="sql")
            st.subheader("Results")
            if df is not None and not df.empty:
                st.dataframe(df, use_container_width=True)
                if df.shape[0] == 1 and df.shape[1] == 1:
                    st.metric(label=df.columns[0], value=df.iloc[0, 0])
            else:
                st.info("Query ran successfully but returned no rows.")

# --- Clarification follow-up flow ---
if st.session_state.clarification:
    st.warning(f"🤔 **Clarifying question:** {st.session_state.clarification}")
    followup = st.text_input("Your answer:", key="followup")
    if st.button("Submit clarification") and followup:
        combined_question = f"{st.session_state.pending_question} ({followup})"
        with st.spinner("Generating SQL and running query..."):
            sql, df, err, _ = ask(combined_question, skip_clarification=True)

        st.session_state.clarification = None
        st.session_state.pending_question = None

        if err:
            st.error(err)
            if sql:
                st.code(sql, language="sql")
        else:
            st.subheader("Generated SQL")
            st.code(sql, language="sql")
            st.subheader("Results")
            if df is not None and not df.empty:
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Query ran successfully but returned no rows.")

st.divider()
st.caption("Built with Groq (GPT-OSS 120B) + SQLite + Streamlit — free-tier stack, no hosting cost.")