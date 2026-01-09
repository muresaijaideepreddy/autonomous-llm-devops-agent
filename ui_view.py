import streamlit as st
import time
from ui_controller import (
    trigger_pipeline_run,
    get_available_runs,
    get_run_data,
    risk_badge,
    status_badge
)

st.set_page_config(
    page_title="Autonomous LLM CI Dashboard",
    layout="wide"
)

# --------------------------------
# SIDEBAR
# --------------------------------

st.sidebar.title("🧠 Autonomous CI System")
st.sidebar.caption("LLM‑Driven DevOps Pipeline")

if st.sidebar.button("▶ Run Pipeline"):
    with st.spinner("Running Autonomous CI Pipeline..."):
        progress = st.progress(0)
        progress.progress(20)
        time.sleep(0.4)

        trigger_pipeline_run()

        progress.progress(100)
        st.success("Pipeline completed")
        time.sleep(1)
        st.rerun()

# --------------------------------
# LOAD RUN DATA
# --------------------------------

runs = get_available_runs()

if not runs:
    st.warning("No pipeline runs found. Click **Run Pipeline**.")
    st.stop()

selected_run = st.sidebar.selectbox(
    "Select Pipeline Run",
    runs,
    index=len(runs) - 1
)

run_data = get_run_data(selected_run)

planner = run_data.get("planner_output", {})
tester = run_data.get("tester_output", {})
executor = run_data.get("executor_output", {})

# --------------------------------
# MAIN DASHBOARD
# --------------------------------

st.title("🚀 Autonomous LLM CI Dashboard")
st.caption(f"Run ID: `{run_data.get('run_id')}`")

c1, c2, c3, c4 = st.columns(4)

c1.metric("🧠 Risk", risk_badge(planner.get("risk_level")))
c2.metric("📦 Modules", ", ".join(planner.get("modules_to_test", [])))
c3.metric("🧪 Tests", tester.get("num_tests_generated", 0))
c4.metric("⚙️ Status", status_badge(executor.get("status")))

st.divider()

# --------------------------------
# WHY RISK
# --------------------------------

st.subheader("❓ Why this risk?")
st.info(planner.get("reason", "No explanation provided"))

# --------------------------------
# PIPELINE FLOW
# --------------------------------

st.subheader("🔄 Pipeline Flow")

f1, f2, f3 = st.columns(3)

with f1:
    st.success("🧠 Planner Agent")
    st.json(planner)

with f2:
    st.info("🧪 Tester Agent")
    st.json(tester)

with f3:
    st.warning("⚙️ Executor Agent")
    st.json({
        "status": executor.get("status"),
        "failed_tests": executor.get("failed_tests", [])
    })

# --------------------------------
# TIMELINE
# --------------------------------

st.subheader("⏱ Timeline")

t1, t2, t3 = st.columns(3)
t1.metric("Start Time", run_data.get("start_time"))
t2.metric("End Time", run_data.get("end_time"))
t3.metric("Execution Time", f"{executor.get('execution_time_ms', 0)} ms")

# --------------------------------
# LOGS
# --------------------------------

with st.expander("📄 Execution Logs"):
    st.code(executor.get("logs", ""), language="text")

st.caption("Autonomous LLM DevOps System | Fully UI‑Driven")
