"""Streamlit view of distributor quality, variance, and root cause.

Launch from the project root:

    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import common  # noqa: E402

SCORE_COLUMNS = [
    "distributor_id",
    "completeness",
    "uniqueness",
    "validity",
    "timeliness",
    "overall",
]


def load_frames(distributor: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read the scorecard, the variance totals, root causes, and a line sample."""
    cfg = common.load_config()
    conn = common.connect(common.resolve(cfg["paths"]["database"]))
    try:
        scorecard = pd.read_sql_query(
            f"SELECT {', '.join(SCORE_COLUMNS)} FROM dq_scorecard ORDER BY distributor_id",
            conn,
        )
        total_sql = """
            SELECT
                SUM(ABS(variance_before)) AS absolute_before,
                SUM(ABS(variance)) AS absolute_after
            FROM reconciliation
        """
        cause_sql = """
            SELECT root_cause, COUNT(*) AS lines, SUM(ABS(variance)) AS absolute_liters
            FROM reconciliation
            WHERE flagged = 1
        """
        sample_sql = """
            SELECT distributor_id, sku_id, week, internal_volume, feed_volume,
                   variance, variance_pct, root_cause
            FROM reconciliation
            WHERE flagged = 1
        """
        params: list[str] = []
        if distributor != "All":
            total_sql += " WHERE distributor_id = ?"
            cause_sql += " AND distributor_id = ?"
            sample_sql += " AND distributor_id = ?"
            params = [distributor]
        cause_sql += " GROUP BY root_cause ORDER BY lines DESC"
        sample_sql += " ORDER BY ABS(variance) DESC LIMIT 200"
        totals = pd.read_sql_query(total_sql, conn, params=params)
        causes = pd.read_sql_query(cause_sql, conn, params=params)
        sample = pd.read_sql_query(sample_sql, conn, params=params)
    finally:
        conn.close()
    return scorecard, totals, causes, sample


def waterfall(totals: pd.DataFrame) -> go.Figure:
    """Show absolute liter variance before cleaning, the drop, and the result."""
    before = float(totals.loc[0, "absolute_before"])
    after = float(totals.loc[0, "absolute_after"])
    figure = go.Figure(
        go.Waterfall(
            x=["Before cleaning", "Removed by cleaning", "After cleaning"],
            y=[before, after - before, after],
            measure=["absolute", "relative", "total"],
            text=[f"{before:,.0f}", f"{after - before:,.0f}", f"{after:,.0f}"],
            textposition="outside",
            connector={"line": {"color": "#9AA0A6"}},
        )
    )
    figure.update_layout(
        title="Absolute variance, liters",
        yaxis_title="Liters",
        waterfallgroupgap=0.3,
        margin={"t": 60, "b": 40},
    )
    return figure


def main() -> None:
    """Render the scorecard, waterfall, and root-cause drill-down."""
    st.set_page_config(page_title="Trade data quality", layout="wide")
    st.title("Trade data quality")
    st.caption("Iowa Data Hub annual exports compared with the simulated distributor feeds.")

    preview = load_frames("All")
    distributors = ["All", *preview[0]["distributor_id"].tolist()]
    distributor = st.selectbox("Distributor", distributors)
    scorecard, totals, causes, sample = preview if distributor == "All" else load_frames(distributor)

    st.header("Distributor Health Scorecard")
    shown = scorecard if distributor == "All" else scorecard[scorecard["distributor_id"] == distributor]
    st.dataframe(shown, width="stretch", hide_index=True)

    st.header("Variance waterfall")
    st.caption("Sum of absolute liter gaps before cleaning, the amount cleaning removed, and the gap that remains.")
    st.plotly_chart(waterfall(totals), width="stretch")

    st.header("Line-item root cause")
    if causes.empty:
        st.info("No flagged lines for this distributor.")
        return
    st.bar_chart(causes.set_index("root_cause")["lines"])
    st.dataframe(sample, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
else:
    main()
