
import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# -------------------- CONFIGURATION --------------------

st.set_page_config(
    page_title="GridForge | AI Security",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULT_API_URL = "http://127.0.0.1:8000"

st.markdown(
    """
    <style>
    .stApp {
        background-color: #0b1120;
        color: #e5e7eb;
    }
    [data-testid="stSidebar"] {
        background-color: #111827;
    }
    div[data-testid="stMetric"] {
        background: #151f32;
        border: 1px solid #29364d;
        padding: 18px;
        border-radius: 12px;
    }
    div[data-testid="stMetricLabel"] {
        color: #9ca3af;
    }
    h1, h2, h3 {
        color: #f3f4f6;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------- SIDEBAR --------------------

st.sidebar.title("🛡️ GridForge")
st.sidebar.caption("AI Agent Governance & Runtime Security")
st.sidebar.divider()

api_url = st.sidebar.text_input(
    "Backend API URL",
    value=DEFAULT_API_URL,
).strip().rstrip("/")

reviewer_key = st.sidebar.text_input(
    "Reviewer key",
    type="password",
    help="Enter the local reviewer key configured for your FastAPI backend.",
)

if st.sidebar.button("🔄 Refresh dashboard", use_container_width=True):
    st.rerun()

st.sidebar.divider()
st.sidebar.caption("Local development dashboard")
st.sidebar.caption("No real financial transactions are performed.")

# -------------------- API HELPERS --------------------

def api_get(path, reviewer=False):
    headers = {}
    if reviewer and reviewer_key:
        headers["X-Reviewer-Key"] = reviewer_key

    try:
        response = requests.get(
            f"{api_url}{path}",
            headers=headers,
            timeout=5,
        )
        if response.ok:
            return response.json(), None

        if response.status_code == 503 and reviewer:
            return None, "Reviewer authentication is not configured in the backend."
        if response.status_code == 401 and reviewer:
            return None, "Reviewer key is missing or incorrect."
        return None, f"API returned HTTP {response.status_code}: {response.text[:200]}"
    except requests.RequestException as exc:
        return None, f"Cannot connect to the backend: {exc}"


def api_post(path, payload, reviewer=False):
    headers = {"Content-Type": "application/json"}
    if reviewer and reviewer_key:
        headers["X-Reviewer-Key"] = reviewer_key

    try:
        response = requests.post(
            f"{api_url}{path}",
            json=payload,
            headers=headers,
            timeout=10,
        )
        if response.ok:
            return response.json(), None
        return None, f"API returned HTTP {response.status_code}: {response.text[:300]}"
    except requests.RequestException as exc:
        return None, f"Request failed: {exc}"


def as_records(data):
    """Accept common API response shapes and return a list of dictionaries."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "results", "logs", "audit_logs", "tools", "approvals"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def field(row, *names, default="—"):
    for name in names:
        if isinstance(row, dict) and row.get(name) is not None:
            return row[name]
    return default


def normalize_decision(value):
    return str(value).upper().replace(" ", "_")


# -------------------- HEADER --------------------

st.title("🛡️ GridForge")
st.markdown(
    "### AI Agent Governance & Runtime Security Platform"
)
st.caption(
    "Monitor tool calls, inspect security decisions, review high-risk actions, "
    "and examine the audit trail."
)

# -------------------- FETCH DATA --------------------

health_data, health_error = api_get("/health")
tools_data, tools_error = api_get("/api/v1/tools")
audit_data, audit_error = api_get("/api/v1/audit-logs")

tools = as_records(tools_data) if tools_data is not None else []
audit_logs = as_records(audit_data) if audit_data is not None else []

approvals_data, approvals_error = api_get(
    "/api/v1/approvals?status=PENDING",
    reviewer=True,
)
pending_approvals = (
    as_records(approvals_data) if approvals_data is not None else []
)

# Normalize event decisions for counting and filtering.
def get_decision(log):
    return normalize_decision(
        field(log, "decision", "status", "action", default="")
    )


denied_logs = [
    log for log in audit_logs
    if get_decision(log) in {"DENY", "DENIED", "BLOCKED"}
]
approval_logs = [
    log for log in audit_logs
    if "APPROVAL" in get_decision(log)
]
approved_logs = [
    log for log in audit_logs
    if get_decision(log) in {"APPROVED", "EXECUTED"}
]

unique_agent_ids = {
    str(field(log, "agent_id", default=""))
    for log in audit_logs
    if field(log, "agent_id", default="") != "—"
}

# -------------------- STATUS STRIP --------------------

status_col1, status_col2 = st.columns([1, 3])

with status_col1:
    if health_error:
        st.error("Backend unavailable")
    else:
        st.success("Backend connected")

with status_col2:
    st.caption(f"API endpoint: {api_url}")

st.divider()

# -------------------- NAVIGATION --------------------

overview_tab, agents_tab, security_tab, approvals_tab, audit_tab = st.tabs(
    [
        "🏠 Overview",
        "🤖 Agents & Tools",
        "🚨 Security Monitor",
        "📝 Approval Center",
        "📜 Audit Trail",
    ]
)

# -------------------- OVERVIEW --------------------

with overview_tab:
    st.subheader("Security Overview")
    st.caption("Metrics are calculated from the audit events returned by your API.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tools returned", len(tools))
    m2.metric("Agents seen in audit logs", len(unique_agent_ids))
    m3.metric("Denied / blocked events", len(denied_logs))
    m4.metric("Pending approvals", len(pending_approvals))

    st.divider()

    left, right = st.columns([1.4, 1])

    with left:
        st.subheader("Recent Security Events")
        if audit_error:
            st.warning(audit_error)
        elif audit_logs:
            recent = audit_logs[:10]
            table_rows = []
            for log in recent:
                table_rows.append({
                    "Event ID": field(log, "id", "audit_log_id"),
                    "Agent ID": field(log, "agent_id"),
                    "Tool": field(log, "tool_name", "tool"),
                    "Decision": get_decision(log),
                    "Risk": field(log, "risk_score"),
                    "Reason": field(log, "reason", "message"),
                })
            st.dataframe(
                pd.DataFrame(table_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No audit events were returned by the backend.")

    with right:
        st.subheader("Decision Summary")
        st.metric("Approval-related events", len(approval_logs))
        st.metric("Approved / executed events", len(approved_logs))

        if audit_logs:
            decision_counts = {}
            for log in audit_logs:
                decision = get_decision(log) or "UNKNOWN"
                decision_counts[decision] = decision_counts.get(decision, 0) + 1

            st.bar_chart(
                pd.DataFrame(
                    {
                        "Decision": list(decision_counts.keys()),
                        "Events": list(decision_counts.values()),
                    }
                ).set_index("Decision")
            )
        else:
            st.info("Decision statistics will appear when audit events are available.")

# -------------------- AGENTS & TOOLS --------------------

with agents_tab:
    st.subheader("Registered Tools")

    if tools_error:
        st.error(tools_error)
    elif tools:
        tool_rows = []
        for tool in tools:
            tool_rows.append({
                "ID": field(tool, "id"),
                "Name": field(tool, "name"),
                "Description": field(tool, "description"),
                "Active": field(tool, "is_active", "active"),
            })
        st.dataframe(
            pd.DataFrame(tool_rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No tools were returned by the API.")

    st.divider()
    st.subheader("Agents Observed in Audit Logs")
    st.caption(
        "This list is derived from audit events. It is not a complete registry "
        "of every registered agent."
    )

    if audit_logs:
        agent_rows = {}
        for log in audit_logs:
            agent_id = field(log, "agent_id", default=None)
            if agent_id is not None:
                key = str(agent_id)
                agent_rows.setdefault(key, {
                    "Agent ID": key,
                    "Observed events": 0,
                })
                agent_rows[key]["Observed events"] += 1

        if agent_rows:
            st.dataframe(
                pd.DataFrame(list(agent_rows.values())),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No agent IDs were found in the returned audit events.")
    else:
        st.info("No audit events are available to identify agents.")

# -------------------- SECURITY MONITOR --------------------

with security_tab:
    st.subheader("Security Monitor")
    st.caption("Inspect denied actions and tool calls requiring approval.")

    security_events = [
        log for log in audit_logs
        if get_decision(log) in {
            "DENY", "DENIED", "BLOCKED",
            "REQUIRE_APPROVAL", "REQUIRES_APPROVAL",
        }
    ]

    if security_events:
        security_rows = []
        for log in security_events:
            security_rows.append({
                "Event ID": field(log, "id", "audit_log_id"),
                "Request ID": field(log, "request_id"),
                "Agent ID": field(log, "agent_id"),
                "Tool": field(log, "tool_name", "tool"),
                "Decision": get_decision(log),
                "Risk Score": field(log, "risk_score"),
                "Reason": field(log, "reason", "message"),
            })
        st.dataframe(
            pd.DataFrame(security_rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No denied or approval-required events were found in the returned logs.")

    st.info(
        "GridForge's current policy engine uses deterministic rules. "
        "These events demonstrate policy enforcement, not a trained ML detector."
    )

# -------------------- APPROVAL CENTER --------------------

with approvals_tab:
    st.subheader("Human Approval Center")
    st.caption("Review pending high-risk actions. Only approve actions you understand.")

    if not reviewer_key:
        st.warning(
            "Enter your reviewer key in the sidebar to load and review approvals."
        )
    elif approvals_error:
        st.error(approvals_error)
        st.caption(
            "If the error is HTTP 503, configure GRIDFORGE_REVIEWER_KEY "
            "in the backend terminal. If it is HTTP 401, check that both "
            "terminals are using the same key."
        )
    elif not pending_approvals:
        st.success("There are no pending approvals returned by the backend.")
    else:
        st.write(f"Pending approvals returned: **{len(pending_approvals)}**")

        for approval in pending_approvals:
            approval_id = field(approval, "id", "approval_id")
            tool_name = field(approval, "tool_name")
            agent_id = field(approval, "agent_id")
            risk_score = field(approval, "risk_score")
            arguments = field(approval, "arguments", default={})
            reason = field(approval, "reason", "policy_reason")

            with st.container(border=True):
                st.markdown(
                    f"**Approval #{approval_id} — {tool_name}**"
                )
                a1, a2, a3 = st.columns(3)
                a1.write(f"**Agent:** {agent_id}")
                a2.write(f"**Risk score:** {risk_score}")
                a3.write(
                    f"**Status:** {field(approval, 'status', default='PENDING')}"
                )

                st.write("**Arguments**")
                st.json(arguments)
                st.write(f"**Reason:** {reason}")

                col_approve, col_reject = st.columns(2)

                with col_approve:
                    if st.button(
                        "Approve",
                        key=f"approve_{approval_id}",
                        use_container_width=True,
                    ):
                        result, error = api_post(
                            f"/api/v1/approvals/{approval_id}/review",
                            {
                                "decision": "APPROVED",
                                "reviewed_by": "dashboard_reviewer",
                                "reason": "Reviewed in GridForge dashboard",
                            },
                            reviewer=True,
                        )
                        if error:
                            st.error(error)
                        else:
                            st.success(f"Approval #{approval_id} approved.")
                            st.rerun()

                with col_reject:
                    if st.button(
                        "Reject",
                        key=f"reject_{approval_id}",
                        use_container_width=True,
                    ):
                        result, error = api_post(
                            f"/api/v1/approvals/{approval_id}/review",
                            {
                                "decision": "REJECTED",
                                "reviewed_by": "dashboard_reviewer",
                                "reason": "Rejected in GridForge dashboard",
                            },
                            reviewer=True,
                        )
                        if error:
                            st.error(error)
                        else:
                            st.success(f"Approval #{approval_id} rejected.")
                            st.rerun()

    st.warning(
        "Approving an item changes its approval status only. "
        "It does not execute the tool. Execution is a separate API action."
    )

# -------------------- AUDIT TRAIL --------------------

with audit_tab:
    st.subheader("Audit Trail")
    st.caption("Review events returned by the backend audit endpoint.")

    if audit_error:
        st.error(audit_error)
    elif audit_logs:
        all_decisions = sorted({
            get_decision(log) or "UNKNOWN"
            for log in audit_logs
        })

        selected_decisions = st.multiselect(
            "Filter by decision",
            options=all_decisions,
            default=all_decisions,
        )

        filtered_logs = [
            log for log in audit_logs
            if (get_decision(log) or "UNKNOWN") in selected_decisions
        ]

        audit_rows = []
        for log in filtered_logs:
            audit_rows.append({
                "Event ID": field(log, "id", "audit_log_id"),
                "Request ID": field(log, "request_id"),
                "Agent ID": field(log, "agent_id"),
                "Tool": field(log, "tool_name", "tool"),
                "Decision": get_decision(log),
                "Risk Score": field(log, "risk_score"),
                "Reason": field(log, "reason", "message"),
                "Timestamp": field(
                    log, "created_at", "timestamp", "created_on"
                ),
            })

        st.write(f"Showing **{len(filtered_logs)}** events.")
        st.dataframe(
            pd.DataFrame(audit_rows),
            use_container_width=True,
            hide_index=True,
        )

        csv_data = pd.DataFrame(audit_rows).to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Export filtered audit events as CSV",
            data=csv_data,
            file_name="gridforge_audit_trail.csv",
            mime="text/csv",
        )
    else:
        st.info("No audit events were returned by the backend.")

# -------------------- FOOTER --------------------

st.divider()
st.caption(
    "GridForge prototype • FastAPI backend + Streamlit dashboard • "
    "Demo data only; no real financial actions"
)
