"""Read-only Streamlit dashboard for saved Spread ranking and practice evidence.

Run from the repository root with: python -m streamlit run dashboard.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
RANKING_DIR = ROOT / "evidence" / "ranking_current"
SWEEP_DIR = ROOT / "evidence" / "sweeps"

st.set_page_config(page_title="Spread results", page_icon="📊", layout="wide")


@st.cache_data(ttl=30)
def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as source:
        return json.load(source)


def ranking_files() -> list[Path]:
    return sorted(RANKING_DIR.glob("season*.json"), reverse=True)


@st.cache_data(ttl=30)
def sweep_files() -> list[str]:
    files = []
    for path in sorted(SWEEP_DIR.glob("*.json"), reverse=True):
        try:
            data = read_json(str(path))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data.get("rows"), list) and data["rows"]:
            files.append(path.name)
    return files


def money(cents: int | float) -> str:
    return f"€{cents / 100:,.2f}"


def ranking_frame(data: dict) -> pd.DataFrame:
    rows = []
    for run in data.get("runs", []):
        score = run.get("score", {})
        rows.append({
            "Level": int(run["level"]),
            "Week": int(run["week"]),
            "Margin (€)": score.get("marginCents", 0) / 100,
            "On time (%)": score.get("onTimeShare", 0) * 100,
            "Won orders": score.get("wonOrders", 0),
            "Ranked": bool(score.get("ranked", False)),
        })
    return pd.DataFrame(rows)


def show_rankings() -> None:
    files = ranking_files()
    if not files:
        st.info("No saved ranking seasons were found in evidence/ranking_current/.")
        return

    selected = st.selectbox("Ranking season", files, format_func=lambda path: path.stem.replace("season", "Season "))
    data = read_json(str(selected))
    runs = ranking_frame(data)
    if runs.empty:
        st.info("This ranking file has no completed runs yet.")
        return

    levels = sorted(runs["Level"].unique().tolist())
    chosen = st.multiselect("Levels", levels, default=levels)
    view = runs[runs["Level"].isin(chosen)]
    if view.empty:
        st.info("Select at least one level to see its results.")
        return

    total_margin = view["Margin (€)"].sum()
    won = int(view["Won orders"].sum())
    on_time = ((view["On time (%)"] * view["Won orders"]).sum() / won) if won else 0
    ranked = int(view["Ranked"].sum())
    a, b, c, d = st.columns(4)
    a.metric("Total margin", money(total_margin * 100))
    b.metric("Weighted on time", f"{on_time:.2f}%")
    c.metric("Won orders", f"{won:,}")
    d.metric("Ranked weeks", f"{ranked}/{len(view)}")

    by_level = (view.groupby("Level", as_index=False)
                .agg(**{"Margin (€)": ("Margin (€)", "sum"), "Weeks": ("Week", "count")}))
    st.subheader("Margin by level")
    st.bar_chart(by_level, x="Level", y="Margin (€)", horizontal=True, sort=False,
                 alt="Total ranking margin in euros for each selected level")

    ranks = data.get("levelsResult", {})
    display = view.copy()
    display["Board rank"] = display["Level"].map(
        lambda level: ranks.get(str(level), {}).get("rank")
    )
    display["Margin"] = display["Margin (€)"].map(lambda value: f"€{value:,.2f}")
    display["On time"] = display["On time (%)"].map(lambda value: f"{value:.2f}%")
    st.subheader("Week-by-week results")
    st.dataframe(display[["Level", "Week", "Board rank", "Margin", "On time", "Won orders", "Ranked"]],
                 hide_index=True, width="stretch")
    st.caption(f"Season {data.get('season', 'unknown')} · {data.get('board', 'ranking board')} · saved evidence only")


def short_setting(setting: str, index: int) -> str:
    values = dict(re.findall(r"([A-Za-z_][A-Za-z_0-9]*)=([^\s]+)", setting))
    keys = ("fee_open", "fee_cap", "price_mult", "max_drive_h", "min_slack_h", "open_order_cap", "options")
    detail = " · ".join(f"{key} {values[key]}" for key in keys if key in values)
    return f"Arm {index + 1}" + (f" · {detail}" if detail else "")


def sweep_frame(data: dict) -> pd.DataFrame:
    rows = []
    for row in data.get("rows", []):
        score = row.get("score")
        if not score:
            continue
        rows.append({
            "Setting": row.get("setting", "unknown"),
            "Seed": row.get("seed", "unknown"),
            "Level": row.get("level", data.get("level")),
            "Margin (€)": score.get("marginCents", 0) / 100,
            "On time (%)": score.get("onTimeShare", 0) * 100,
            "Won orders": score.get("wonOrders", 0),
            "Ranked": bool(score.get("ranked", False)),
        })
    return pd.DataFrame(rows)


def show_sweeps() -> None:
    files = sweep_files()
    if not files:
        st.info("No saved practice sweeps were found in evidence/sweeps/.")
        return

    selected = st.selectbox("Practice sweep", files, format_func=lambda name: Path(name).stem.replace("_", " "))
    data = read_json(str(SWEEP_DIR / selected))
    runs = sweep_frame(data)
    if runs.empty:
        st.info("This sweep has no successful run results.")
        return

    settings = runs["Setting"].drop_duplicates().tolist()
    selected_settings = st.multiselect("Settings to compare", settings, default=settings)
    view = runs[runs["Setting"].isin(selected_settings)]
    if view.empty:
        st.info("Select at least one setting to see results.")
        return

    summaries = []
    for index, (setting, group) in enumerate(view.groupby("Setting", sort=False)):
        summaries.append({
            "Arm": short_setting(setting, settings.index(setting)),
            "Parameters": setting,
            "Runs": len(group),
            "Mean margin (€)": group["Margin (€)"].mean(),
            "Lowest margin (€)": group["Margin (€)"].min(),
            "Mean on time (%)": group["On time (%)"].mean(),
            "Lowest on time (%)": group["On time (%)"].min(),
            "Mean won orders": group["Won orders"].mean(),
        })
    summary = pd.DataFrame(summaries).sort_values("Mean margin (€)", ascending=False)

    a, b, c, d = st.columns(4)
    a.metric("Mean margin", money(view["Margin (€)"].mean() * 100))
    b.metric("Mean on time", f"{view['On time (%)'].mean():.2f}%")
    c.metric("Lowest on time", f"{view['On time (%)'].min():.2f}%")
    d.metric("Practice runs", f"{len(view)}")

    st.subheader("Average margin by setting")
    st.bar_chart(summary, x="Arm", y="Mean margin (€)", horizontal=True, sort="-Mean margin (€)",
                 alt="Average practice margin in euros by setting")
    st.subheader("Setting comparison")
    display = summary.copy()
    for column in ("Mean margin (€)", "Lowest margin (€)"):
        display[column] = display[column].map(lambda value: f"€{value:,.2f}")
    for column in ("Mean on time (%)", "Lowest on time (%)"):
        display[column] = display[column].map(lambda value: f"{value:.2f}%")
    display["Mean won orders"] = display["Mean won orders"].map(lambda value: f"{value:.1f}")
    st.dataframe(display, hide_index=True, width="stretch")

    with st.expander("Individual seed results"):
        detail = view.copy()
        detail["Margin"] = detail["Margin (€)"].map(lambda value: f"€{value:,.2f}")
        detail["On time"] = detail["On time (%)"].map(lambda value: f"{value:.2f}%")
        st.dataframe(detail[["Setting", "Seed", "Level", "Margin", "On time", "Won orders", "Ranked"]],
                     hide_index=True, width="stretch")
    st.caption(f"{data.get('name', Path(selected).stem)} · {data.get('level', 'multiple')} level · saved practice evidence only")


st.title("Spread performance")
st.caption("Explore saved ranking weeks and paired practice sweeps. Historical ranking scores are separate from practice results.")

with st.sidebar:
    st.header("Data")
    mode = st.radio("View", ("Ranked weeks", "Practice sweeps"), label_visibility="collapsed")
    if st.button("Refresh evidence"):
        st.cache_data.clear()
        st.rerun()

if mode == "Ranked weeks":
    show_rankings()
else:
    show_sweeps()
