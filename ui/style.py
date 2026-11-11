"""CupSwap design system: global CSS + small HTML components (hero, stepper, KPI cards, pills, callouts)."""
from __future__ import annotations

from html import escape

import streamlit as st

NAVY, BLUE, MUTED, BORDER = "#0F172A", "#2563EB", "#64748B", "#E2E8F0"

CSS = """
<style>
.block-container, [data-testid="stMainBlockContainer"] {padding-top: 4.6rem !important; padding-bottom: 3rem !important;
  max-width: 1400px;}
.cs-kv {display:grid; grid-template-columns: 110px 1fr; gap:6px 10px; font-size:.84rem; margin:6px 0 8px;}
.cs-kv .k {color:#64748B; font-weight:600; font-size:.74rem; text-transform:uppercase; letter-spacing:.05em; padding-top:2px;}
.cs-kv .v {color:#1E293B; line-height:1.4;}
.cs-card.feature {min-height: 236px;}
.stAppDeployButton, [data-testid="stStatusWidget"] {display: none;}
[data-testid="stHeader"] {background: rgba(245,247,251,.85); backdrop-filter: blur(6px);}
div[data-testid="stVerticalBlockBorderWrapper"] > div {border-color: #E2E8F0;}
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > div > .cs-cardmark) {background: #fff;}
.stButton > button[kind="primary"] {box-shadow: 0 1px 2px rgba(37,99,235,.25); font-weight: 600;}
.stButton > button {font-weight: 500;}
[data-testid="stExpander"] details {background: #fff; border-radius: 10px;}
[data-testid="stMetric"] {background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:10px 14px;}

/* hero */
.cs-hero {background: linear-gradient(120deg,#0B1220 0%,#14306B 55%,#2563EB 100%); color:#fff; border-radius:16px;
  padding: 20px 26px 18px; margin: 0 0 14px; box-shadow: 0 10px 28px rgba(15,23,42,.16); position: relative; overflow: hidden;}
.cs-hero:after {content:""; position:absolute; right:-60px; top:-60px; width:240px; height:240px; border-radius:50%;
  background: radial-gradient(circle, rgba(255,255,255,.14), rgba(255,255,255,0) 70%);}
.cs-kicker {font-size:.7rem; letter-spacing:.16em; text-transform:uppercase; color:#93C5FD; font-weight:700;}
.cs-title {font-size:1.7rem; font-weight:800; margin:.15rem 0 .3rem; letter-spacing:-.01em; color:#fff;}
.cs-sub {color:#CBD5E1; font-size:.93rem; max-width:1000px; line-height:1.45;}
.cs-tag {display:inline-block; background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.22); color:#E2E8F0;
  border-radius:999px; padding:2px 10px; font-size:.72rem; margin:10px 6px 0 0; font-weight:500;}

/* stepper */
.cs-stepper {display:flex; align-items:center; background:#fff; border:1px solid #E2E8F0; border-radius:12px;
  padding:11px 14px; margin:2px 0 16px;}
.cs-step {display:flex; align-items:center; gap:8px; font-size:.8rem; color:#64748B; white-space:nowrap;}
.cs-step .dot {width:24px; height:24px; border-radius:50%; display:flex; align-items:center; justify-content:center;
  font-weight:700; font-size:.72rem; background:#E2E8F0; color:#475569; flex-shrink:0;}
.cs-step.done .dot {background:#059669; color:#fff;}
.cs-step.done {color:#065F46;}
.cs-step.active .dot {background:#2563EB; color:#fff; box-shadow:0 0 0 4px rgba(37,99,235,.18);}
.cs-step.active {color:#0F172A; font-weight:700;}
.cs-step.fail .dot {background:#DC2626; color:#fff;}
.cs-step.fail {color:#991B1B; font-weight:600;}
.cs-bar {flex:1; height:2px; background:#E2E8F0; margin:0 10px; min-width:16px;}
.cs-bar.done {background:#059669;}

/* KPI cards */
.cs-kpis {display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin:4px 0 14px;}
.cs-kpi {background:#fff; border:1px solid #E2E8F0; border-radius:12px; padding:12px 14px; border-top:3px solid #CBD5E1;}
.cs-kpi .lbl {font-size:.68rem; text-transform:uppercase; letter-spacing:.07em; color:#64748B; font-weight:700;}
.cs-kpi .val {font-size:1.4rem; font-weight:800; color:#0F172A; margin-top:3px; line-height:1.2;}
.cs-kpi .sub {font-size:.74rem; color:#64748B; margin-top:2px;}
.cs-kpi.blue {border-top-color:#2563EB;} .cs-kpi.green {border-top-color:#059669;}
.cs-kpi.orange {border-top-color:#D97706;} .cs-kpi.red {border-top-color:#DC2626;} .cs-kpi.violet {border-top-color:#7C3AED;}

/* section titles */
.cs-section {margin:20px 0 8px;}
.cs-section .t {font-size:1.05rem; font-weight:800; color:#0F172A; letter-spacing:-.005em;}
.cs-section .s {font-size:.82rem; color:#64748B; margin-top:1px;}
.cs-eyebrow {font-size:.68rem; text-transform:uppercase; letter-spacing:.08em; color:#64748B; font-weight:700;}

/* pills */
.cs-pill {display:inline-block; border-radius:999px; padding:1px 9px; font-size:.71rem; font-weight:600; margin:1px 4px 1px 0;
  border:1px solid transparent; white-space:nowrap; vertical-align:middle;}
.cs-pill.green {background:#ECFDF5; color:#047857; border-color:#A7F3D0;}
.cs-pill.blue {background:#EFF6FF; color:#1D4ED8; border-color:#BFDBFE;}
.cs-pill.orange {background:#FFFBEB; color:#B45309; border-color:#FDE68A;}
.cs-pill.red {background:#FEF2F2; color:#B91C1C; border-color:#FECACA;}
.cs-pill.violet {background:#F5F3FF; color:#6D28D9; border-color:#DDD6FE;}
.cs-pill.gray {background:#F1F5F9; color:#475569; border-color:#E2E8F0;}

/* callouts & cards */
.cs-callout {border:1px solid #E2E8F0; border-left:4px solid #2563EB; background:#fff; border-radius:10px; padding:11px 14px;
  font-size:.86rem; color:#334155; margin:4px 0 10px;}
.cs-callout .h {font-weight:700; color:#0F172A; margin-bottom:3px;}
.cs-callout.green {border-left-color:#059669;} .cs-callout.orange {border-left-color:#D97706;}
.cs-callout.red {border-left-color:#DC2626;} .cs-callout.violet {border-left-color:#7C3AED;}
.cs-card {background:#fff; border:1px solid #E2E8F0; border-radius:14px; padding:16px 18px; height:100%;}
.cs-card .ic {width:38px; height:38px; border-radius:10px; display:flex; align-items:center; justify-content:center;
  font-size:1.2rem; background:#EFF6FF; margin-bottom:8px;}
.cs-card .h {font-weight:800; font-size:1rem; color:#0F172A;}
.cs-card .d {font-size:.84rem; color:#475569; margin:4px 0 8px; line-height:1.45;}
.cs-autonomy {width:100%; border-collapse:separate; border-spacing:0; background:#fff; border:1px solid #E2E8F0;
  border-radius:12px; overflow:hidden; font-size:.84rem;}
.cs-autonomy th {background:#F8FAFC; text-align:left; padding:9px 12px; font-size:.7rem; text-transform:uppercase;
  letter-spacing:.06em; color:#64748B; border-bottom:1px solid #E2E8F0;}
.cs-autonomy td {padding:8px 12px; border-bottom:1px solid #F1F5F9; color:#1E293B;}
.cs-autonomy tr:last-child td {border-bottom:none;}

/* trace timeline */
.cs-step-head {display:flex; align-items:center; gap:8px; margin-bottom:4px;}
.cs-num {background:#0F172A; color:#fff; border-radius:7px; font-size:.7rem; font-weight:700; padding:2px 8px;}
.cs-time {font-size:.72rem; color:#94A3B8;}
.cs-line {font-size:.88rem; margin:5px 0; color:#1E293B; line-height:1.45;}
.cs-k {display:inline-block; min-width:64px; font-size:.66rem; font-weight:800; text-transform:uppercase; letter-spacing:.07em;
  color:#64748B; margin-right:6px;}
.cs-k.think {color:#7C3AED;} .cs-k.act {color:#2563EB;} .cs-k.observe {color:#059669;} .cs-k.guard {color:#D97706;}
.cs-k.human {color:#DC2626;}
.cs-code {font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background:#F1F5F9; border:1px solid #E2E8F0;
  border-radius:6px; padding:0 6px; font-size:.76rem; color:#0F172A; margin-right:4px; white-space:nowrap;}
.cs-think {font-style:italic; color:#4C1D95;}

/* negotiation chat */
.cs-chat {display:flex; flex-direction:column; gap:10px; padding:4px 2px;}
.cs-msg {max-width:80%; border-radius:14px; padding:10px 14px; border:1px solid #E2E8F0; background:#fff; font-size:.88rem;}
.cs-msg.buyer {align-self:flex-end; background:#EFF6FF; border-color:#BFDBFE; border-bottom-right-radius:4px;}
.cs-msg.seller {align-self:flex-start; background:#FFF1F2; border-color:#FECDD3; border-bottom-left-radius:4px;}
.cs-msg.system {align-self:center; background:#F8FAFC; max-width:95%; text-align:center; font-size:.82rem; color:#475569;}
.cs-who {font-size:.68rem; font-weight:800; text-transform:uppercase; letter-spacing:.07em; color:#475569;}
.cs-price {font-size:1.05rem; font-weight:800; color:#0F172A; margin:2px 0;}
.cs-guard {font-size:.74rem; color:#B45309; margin-top:5px;}

/* sidebar */
section[data-testid="stSidebar"] .cs-brand {padding:2px 0 6px;}
.cs-brand .n {font-size:1.3rem; font-weight:800; color:#fff; letter-spacing:-.01em;}
.cs-brand .s {font-size:.74rem; color:#94A3B8;}
.cs-side-label {font-size:.66rem; text-transform:uppercase; letter-spacing:.09em; color:#94A3B8; font-weight:700; margin:10px 0 4px;}
.cs-stats {display:grid; grid-template-columns:1fr 1fr; gap:8px;}
.cs-stat {background:#1E293B; border:1px solid #334155; border-radius:10px; padding:8px 10px;}
.cs-stat .v {font-size:1.1rem; font-weight:800; color:#F8FAFC;}
.cs-stat .l {font-size:.66rem; color:#94A3B8; text-transform:uppercase; letter-spacing:.06em;}
.cs-rail {font-size:.78rem; color:#CBD5E1; margin:3px 0;}
.cs-modebox {background:#1E293B; border:1px solid #334155; border-radius:10px; padding:8px 10px; font-size:.76rem; color:#CBD5E1;}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def hero(kicker: str, title: str, subtitle: str, tags: list[str] | None = None) -> None:
    tag_html = "".join(f'<span class="cs-tag">{escape(t)}</span>' for t in (tags or []))
    _html(f'<div class="cs-hero"><div class="cs-kicker">{escape(kicker)}</div><div class="cs-title">{escape(title)}</div>'
          f'<div class="cs-sub">{escape(subtitle)}</div><div>{tag_html}</div></div>')


def stepper(steps: list[str], states: list[str]) -> None:
    """states per step: done | active | fail | todo."""
    parts = []
    for i, (label, s) in enumerate(zip(steps, states)):
        mark = "✓" if s == "done" else ("!" if s == "fail" else str(i + 1))
        parts.append(f'<div class="cs-step {s}"><div class="dot">{mark}</div>{escape(label)}</div>')
        if i < len(steps) - 1:
            parts.append(f'<div class="cs-bar {"done" if s == "done" else ""}"></div>')
    _html(f'<div class="cs-stepper">{"".join(parts)}</div>')


def progress_states(n: int, current: int, failed: int | None = None) -> list[str]:
    """Steps before `current` are done, `current` is active (current == n means all done)."""
    out = []
    for i in range(n):
        if failed is not None and i == failed:
            out.append("fail")
        elif i < current:
            out.append("done")
        elif i == current:
            out.append("active")
        else:
            out.append("todo")
    return out


def kpis(items: list[tuple]) -> None:
    """items: (label, value, sub, tone)"""
    cards = "".join(f'<div class="cs-kpi {tone}"><div class="lbl">{escape(str(lbl))}</div><div class="val">{escape(str(val))}</div>'
                    f'<div class="sub">{escape(str(sub))}</div></div>' for lbl, val, sub, tone in items)
    _html(f'<div class="cs-kpis">{cards}</div>')


def section(title: str, subtitle: str = "") -> None:
    _html(f'<div class="cs-section"><div class="t">{escape(title)}</div>'
          + (f'<div class="s">{escape(subtitle)}</div>' if subtitle else "") + "</div>")


def pill(text: str, tone: str = "gray") -> str:
    return f'<span class="cs-pill {tone}">{escape(str(text))}</span>'


def callout(body: str, title: str = "", tone: str = "blue", raw: bool = False) -> None:
    b = body if raw else escape(body)
    _html(f'<div class="cs-callout {tone}">' + (f'<div class="h">{escape(title)}</div>' if title else "") + f"{b}</div>")


def html(s: str) -> None:
    _html(s)
