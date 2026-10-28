"""HypoKompass CH - interactive Streamlit interface.

The UI uses the existing calculation.py / evaluation.py mortgage model. It is a
model calculation for educational comparison, not personalized financial advice.
Run with: streamlit run app.py

Decision tree (ml_decision_tree.py) added by Denis with Claude (Anthropic), 26.10.2026:
new inputs "Your plans" (horizon, income change); the recommendation on the results page
comes from the tree and is explained with its rules. If the ML part fails, the app falls
back to the old rule of evaluation.py.
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
from calculation import calculate
from evaluation import evaluate
from input_data import (
    CURRENT_YEAR,
    DEFAULT_HORIZON_YEARS,
    DEFAULT_INCOME_CHANGE,
    MAX_HORIZON_YEARS,
    MAX_INCOME_CHANGE,
    MIN_HORIZON_YEARS,
    MIN_INCOME_CHANGE,
    STANDARD_STRATEGIES,
    average_saron_margin,
    format_chf,
    load_market_data,
)
from ml_decision_tree import profile_from_user, recommend, train_model


# -----------------------------------------------------------------------------
# Page setup and theme
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "assets" / "hypokompass_logo.png"

with open(LOGO_PATH, "rb") as f:
    LOGO_BASE64 = base64.b64encode(f.read()).decode("utf-8")

st.set_page_config(
    page_title="HypoKompass CH | Your first home",
    page_icon=str(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="collapsed",
)

NAVY = "#103f4b"
INK = "#172b32"
MUTED = "#687980"
PAPER = "#f5f3ee"
LINE = "#e5e0d6"
ORANGE = "#e28b43"
TEAL = "#75a79a"
BLUE = "#347b96"

# Theme mode: follow the device by default, with a manual three-state toggle.
# CSS media queries handle system preference because Streamlit's Python runtime
# cannot directly read the browser's prefers-color-scheme setting.
if "theme_mode" not in st.session_state:
    # Migrate the earlier boolean preference if this app is being upgraded in-place.
    old_preference = st.session_state.pop("dark_mode", None)
    st.session_state["theme_mode"] = "dark" if old_preference is True else "system"
THEME_MODE = st.session_state["theme_mode"]
DARK = THEME_MODE == "dark"
BG = "#111a1e" if DARK else PAPER
SURFACE = "#1b292f" if DARK else "#fffdf9"
CARD = "#202f35" if DARK else "#ffffff"
TEXT = "#edf3f4" if DARK else INK
SUBTEXT = "#b4c2c6" if DARK else MUTED
BORDER = "#35464d" if DARK else LINE

st.markdown(
    f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
      :root {{
        --hypo-navy: {NAVY}; --hypo-ink: {INK}; --hypo-muted: {MUTED};
        --hypo-paper: {BG}; --hypo-line: {BORDER}; --hypo-orange: {ORANGE};
        --hypo-surface: {SURFACE}; --hypo-card: {CARD}; --hypo-text: {TEXT}; --hypo-subtext: {SUBTEXT};
      }}
      html, body, [class*="css"], [data-testid="stAppViewContainer"] {{ font-family: 'DM Sans', sans-serif; color: var(--hypo-text); }}
      .stApp, [data-testid="stAppViewContainer"] {{ background: var(--hypo-paper); color:var(--hypo-text); }}
      [data-testid="stHeader"] {{ background: var(--hypo-paper); }}
      [data-testid="stToolbar"] {{ right: 1rem; }}
      .st-key-theme_toggle {{ position:fixed !important; top:.55rem !important; right:1rem !important; z-index:999999 !important; width:2.8rem !important; }}
      .st-key-theme_toggle button {{ width:2.6rem !important; min-width:2.6rem !important; max-width:2.6rem !important; height:2.6rem !important; min-height:2.6rem !important; padding:0 !important; box-shadow:0 2px 10px rgba(0,0,0,.12); }}
      .block-container {{ max-width: 1420px; padding-top: 1.2rem; padding-bottom: 3rem; }}
      h1, h2, h3, h4, h5, h6, [data-testid="stMarkdownContainer"] h1, [data-testid="stMarkdownContainer"] h2, [data-testid="stMarkdownContainer"] h3 {{ font-family: 'Manrope', sans-serif !important; color: var(--hypo-text) !important; letter-spacing: -0.025em; }}
      h1 {{ font-size: clamp(2rem, 3.6vw, 3.15rem) !important; line-height: 1.08 !important; font-weight: 800 !important; }}
      h2 {{ font-size: 1.45rem !important; font-weight: 800 !important; }}
      h3 {{ font-size: 1.08rem !important; font-weight: 800 !important; }}
      p, label, [data-testid="stWidgetLabel"], [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] {{ color: var(--hypo-text); }}
      [data-testid="stCaptionContainer"], .muted, .tip, .intro-copy, .section-kicker, .eyebrow, .metric-label, .metric-small, .chart-note {{ color: var(--hypo-subtext) !important; }}
      [data-testid="stRadio"] label, [data-testid="stCheckbox"] label, [data-testid="stSelectbox"] label {{ color:var(--hypo-text) !important; }}
      [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{ background:var(--hypo-card); color:var(--hypo-text); border-color:var(--hypo-line); }}
      [data-testid="stNumberInput"] button {{ color:var(--hypo-text); background:var(--hypo-card); }}

      [data-testid="stMarkdownContainer"] p {{ line-height: 1.55; }}
      [data-testid="stNumberInput"] input, [data-testid="stTextInput"] input {{
        background: var(--hypo-card); border: 1px solid var(--hypo-line); border-radius: 12px;
        min-height: 3.15rem; font-size: 1.05rem; color: var(--hypo-text);
      }}
      [data-testid="stNumberInput"] input:focus {{ border-color: var(--hypo-navy); box-shadow: 0 0 0 1px var(--hypo-navy); }}
      [data-testid="stRadio"] > div {{ gap: .6rem; }}
      [data-testid="stRadio"] label {{
        border: 1px solid var(--hypo-line); border-radius: 13px; background: var(--hypo-card); color:var(--hypo-text);
        padding: .85rem 1rem; min-height: 3.45rem; align-items: center;
      }}
      [data-testid="stRadio"] label:has(input:checked) {{ border: 2px solid var(--hypo-navy); background: var(--hypo-card); }}
      [data-testid="stRadio"] label p {{ font-weight: 600; margin: 0; }}
      [data-testid="stCheckbox"] label p {{ font-weight: 600; }}
      [data-testid="stExpander"] {{ border: 1px solid var(--hypo-line); border-radius: 12px; background: var(--hypo-card); }}
      .stButton > button {{
        border-radius: 12px; min-height: 3.1rem; font-weight: 800; letter-spacing: .01em;
        border: 1px solid var(--hypo-navy); transition: transform .12s ease, box-shadow .12s ease;
      }}
      .stButton > button[kind="primary"] {{ background: var(--hypo-navy); color: #ffffff !important; -webkit-text-fill-color:#ffffff !important; }}
      .stButton > button[kind="primary"] *, .stButton > button[kind="primary"] p, .stButton > button[kind="primary"] span {{ color:#ffffff !important; -webkit-text-fill-color:#ffffff !important; }}
      .stButton > button[kind="primary"]:hover {{ background: #0a3340; border-color: #0a3340; transform: translateY(-1px); box-shadow: 0 8px 18px rgba(16,63,75,.15); }}
      .stButton > button[kind="secondary"] {{ background: rgba(255,255,255,.72); color: var(--hypo-navy); }}
      [data-testid="stAlert"] {{ border-radius: 12px; }}
      hr {{ border-color: var(--hypo-line); }}
      .topbar {{ display:flex; align-items:center; justify-content:space-between; gap:1.2rem; padding:.25rem 0 1.15rem; margin-bottom:1.5rem; border-bottom:1px solid var(--hypo-line); }}
      .brand {{ display:flex; align-items:center; gap:.7rem; font-family:'Manrope',sans-serif; font-size:1.28rem; font-weight:800; letter-spacing:-.035em; color:var(--hypo-text); white-space:nowrap; }}
      .brand-mark {{ height:2.25rem; width:2.25rem; display:inline-flex; align-items:center; justify-content:center; border:2px solid var(--hypo-navy); border-radius:50%; color:var(--hypo-orange); font-size:1.15rem; background:var(--hypo-card); }}
      .eyebrow {{ font-size:.76rem; letter-spacing:.13em; text-transform:uppercase; font-weight:800; color:#738187; margin:0 0 .45rem; }}
      .intro-copy {{ color:var(--hypo-subtext); font-size:1.08rem; max-width:42rem; margin-top:.6rem; }}
      .section-kicker {{ color:var(--hypo-subtext); font-size:.83rem; text-transform:uppercase; letter-spacing:.1em; font-weight:800; margin-bottom:.35rem; }}
      .soft-card {{ background:var(--hypo-card); border:1px solid var(--hypo-line); border-radius:17px; padding:1.25rem 1.35rem; }}
      [data-testid="stVerticalBlockBorderWrapper"] {{ background:var(--hypo-card); border:1px solid var(--hypo-line) !important; border-radius:17px !important; padding:1.15rem 1.25rem !important; }}
      .soft-card h3 {{ margin:.15rem 0 .55rem; }}
      .summary-card {{ background:var(--hypo-card); border:1px solid var(--hypo-line); border-radius:17px; padding:1.3rem 1.4rem; }}
      .muted {{ color:var(--hypo-subtext); }}
      .metric-label {{ color:var(--hypo-subtext); font-size:.87rem; margin-bottom:.2rem; }}
      .metric-value {{ color:var(--hypo-ink); font-family:'Manrope',sans-serif; font-size:1.38rem; font-weight:800; letter-spacing:-.025em; }}
      .metric-small {{ color:var(--hypo-subtext); font-size:.82rem; margin-top:.2rem; }}
      .summary-row {{ display:flex; justify-content:space-between; align-items:baseline; gap:1rem; padding:.68rem 0; border-bottom:1px solid #eeeae2; }}
      .summary-row:last-child {{ border-bottom:0; }}
      .summary-row .label {{ color:var(--hypo-subtext); }}
      .summary-row .value {{ color:var(--hypo-text); font-weight:800; text-align:right; }}
      .status-strip {{ display:flex; align-items:center; gap:.7rem; border-radius:12px; padding:.85rem 1rem; font-weight:800; margin:.8rem 0; }}
      .status-dot {{ width:.65rem; height:.65rem; border-radius:50%; flex-shrink:0; }}
      .status-green {{ background:#e5f1e9; color:#214b37; }} .status-green .status-dot {{ background:#328558; }}
      .status-yellow {{ background:#fff2d8; color:#714a11; }} .status-yellow .status-dot {{ background:#d99a35; }}
      .status-red {{ background:#fbe7e3; color:#842f25; }} .status-red .status-dot {{ background:#bc4a3b; }}
      .tip {{ font-size:.84rem; line-height:1.5; color:var(--hypo-subtext); margin-top:.7rem; }}
      .hero-result {{ background:var(--hypo-navy); color:white; border-radius:19px; padding:1.55rem 1.8rem; margin-bottom:1.35rem; display:flex; align-items:center; justify-content:space-between; gap:1.3rem; }}
      .hero-result .overline {{ font-size:.85rem; color:#d2e0e2; margin-bottom:.45rem; }}
      .hero-result .recommendation {{ font-family:'Manrope',sans-serif; color:white; font-size:clamp(1.6rem,2.5vw,2.35rem); font-weight:800; line-height:1.1; letter-spacing:-.035em; }}
      .hero-result .explain {{ color:#e0e9e9; margin-top:.55rem; max-width:43rem; }}
      .hero-result .risk-cost-label {{ color:#d2e0e2; font-size:.85rem; text-align:right; }}
      .hero-result .risk-cost {{ color:white; font-family:'Manrope',sans-serif; font-size:clamp(1.5rem,2.5vw,2.15rem); font-weight:800; text-align:right; white-space:nowrap; }}
      .comparison-card {{ background:var(--hypo-card); border:1px solid var(--hypo-line); border-radius:17px; padding:1.4rem 1.45rem 1.25rem; }}
      .chart-head {{ display:flex; flex-wrap:wrap; justify-content:space-between; gap:.5rem 1rem; align-items:baseline; margin-bottom:.8rem; }}
      .chart-note {{ color:var(--hypo-subtext); font-size:.8rem; }}
      .axis-row {{ display:grid; grid-template-columns:minmax(125px, 1fr) minmax(180px, 2.2fr) minmax(100px,.72fr); gap:1rem; align-items:end; margin:.9rem 0 .25rem; color:var(--hypo-subtext); font-size:.77rem; }}
      .axis-labels {{ display:flex; justify-content:space-between; gap:.35rem; }}
      .cost-row {{ display:grid; grid-template-columns:minmax(125px, 1fr) minmax(180px, 2.2fr) minmax(100px,.72fr); gap:1rem; align-items:center; padding:1.03rem 0; border-top:1px solid #efebe4; }}
      .cost-name {{ font-weight:700; font-size:.93rem; }} .cost-name.recommended::after {{ content:'  RECOMMENDED'; display:inline-block; color:#287354; background:#e5f1e9; font-size:.61rem; padding:.2rem .35rem; border-radius:4px; vertical-align:middle; margin-left:.3rem; letter-spacing:.04em; }}
      .cost-track {{ height:14px; background:var(--hypo-line); border-radius:99px; position:relative; overflow:visible; }}
      .cost-range {{ position:absolute; height:14px; top:0; border-radius:99px; min-width:3px; }}
      .cost-marker {{ position:absolute; top:-4px; width:4px; height:22px; border-radius:5px; background:var(--hypo-orange); transform:translateX(-50%); box-shadow:0 0 0 1px rgba(255,255,255,.2); }}
      .cost-total {{ text-align:right; font-weight:800; white-space:nowrap; font-variant-numeric:tabular-nums; }}
      .rate-pill {{ display:inline-block; padding:.35rem .55rem; border-radius:8px; background:#f1efe9; font-weight:700; color:var(--hypo-ink); font-size:.82rem; }}
      .footer-note {{ color:var(--hypo-subtext); border-top:1px solid var(--hypo-line); padding-top:1rem; margin-top:2rem; font-size:.8rem; display:flex; justify-content:space-between; gap:1rem; flex-wrap:wrap; }}
      .tiny-tag {{ display:inline-block; color:#66787e; font-size:.74rem; font-weight:800; text-transform:uppercase; letter-spacing:.1em; }}
      .stApp, .stApp p, .stApp label, .stApp [data-testid="stMarkdownContainer"] {{ color:var(--hypo-text); }}
      .soft-card, .summary-card, .comparison-card, [data-testid="stVerticalBlockBorderWrapper"] {{ color:var(--hypo-text); }}
      .summary-row {{ border-bottom-color:var(--hypo-line); }}
      .cost-row {{ border-top-color:var(--hypo-line); }}
      .rate-pill {{ background:var(--hypo-line); color:var(--hypo-text); }}
      .stButton > button[kind="secondary"] {{ background:var(--hypo-card); color:var(--hypo-text); border-color:var(--hypo-line); }}
      [data-testid="stExpander"] {{ background:var(--hypo-card); border-color:var(--hypo-line); }}
      {"""@media (prefers-color-scheme: dark) {
        :root {
          --hypo-navy:#347b88; --hypo-ink:#edf3f4; --hypo-muted:#b4c2c6;
          --hypo-paper:#111a1e; --hypo-line:#35464d; --hypo-surface:#1b292f;
          --hypo-card:#202f35; --hypo-text:#edf3f4; --hypo-subtext:#b4c2c6;
        }
        .stApp, [data-testid="stAppViewContainer"] { color:#edf3f4; }
        .metric-value { color:var(--hypo-text) !important; }
        .summary-row { border-bottom-color:var(--hypo-line); }
        .cost-row { border-top-color:var(--hypo-line); }
        .rate-pill { background:var(--hypo-line); color:var(--hypo-text); }
        .stButton > button[kind="primary"] { background:#347b88; border-color:#347b88; }
      }""" if THEME_MODE == "system" else ""}
      [data-testid="stHorizontalBlock"]:has(.st-key-theme_toggle) {{ flex-wrap:nowrap !important; gap:.5rem !important; }}
      [data-testid="stHorizontalBlock"]:has(.st-key-theme_toggle) > [data-testid="column"] {{ min-width:0 !important; flex:initial !important; }}
      @media (max-width: 800px) {{
        .block-container {{ padding:1rem .8rem 2rem; }}
        .topbar {{ gap:.6rem; margin-bottom:1rem; }}
        .brand {{ font-size:1.08rem; white-space:normal; }}
        .hero-result {{ align-items:flex-start; flex-direction:column; padding:1.1rem; }} .hero-result .risk-cost-label,.hero-result .risk-cost {{ text-align:left; white-space:normal; }}
        .axis-row, .cost-row {{ grid-template-columns:minmax(0,1fr); gap:.45rem; }} .axis-row > div:first-child, .axis-row > div:last-child {{ display:none; }} .cost-total {{ text-align:left; }}
        [data-testid="stHorizontalBlock"] {{ flex-wrap:wrap; gap:.75rem; }}
        [data-testid="stHorizontalBlock"] > [data-testid="column"] {{ min-width:min(100%, 250px); flex:1 1 250px; }}
        .soft-card, .summary-card, .comparison-card {{ padding:1rem; }}
      }}
      @media (max-width: 480px) {{
        h1 {{ font-size:1.9rem !important; }} h2 {{ font-size:1.25rem !important; }}
        .block-container {{ padding-left:.65rem; padding-right:.65rem; }}
        .stButton > button {{ width:100%; }}
        .metric-value {{ font-size:1.2rem; }}
      }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600)
def get_market_data() -> dict[str, Any]:
    """Market data from the project's SNB adapter, or its documented fallbacks."""
    return load_market_data()


@st.cache_resource(show_spinner="Training the decision tree on 1,000+ interest-rate scenarios ...")
def get_decision_tree(_market: dict[str, Any], source: str) -> dict[str, Any]:
    """Train the decision tree once (about 3 seconds) and keep it for all users and clicks.

    The underscore in _market tells Streamlit not to hash the dict; the cache key is the
    data source string instead, so the tree is retrained when new SNB data is loaded.
    """
    return train_model(_market)


def ml_recommendation(user: dict[str, Any], market: dict[str, Any]) -> dict[str, Any] | None:
    """Recommendation + explanation of the decision tree, or None if the ML part fails."""
    try:
        bundle = get_decision_tree(market, market["source"])
        return recommend(bundle, profile_from_user(user))
    except Exception:
        # Keep the app usable: without ML the old rule of evaluation.py is shown
        return None


def money(value: float | int) -> str:
    return format_chf(value)


def pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def strategy_label(name: str) -> str:
    """Translate model strategy labels for the English-language interface."""
    labels = {
        "Staggered fixed 3/10/15 years": "Staggered 3 / 10 / 15",
        "All fixed for 10 years": "Fixed for 10 years",
        "50% fixed for 10 years / 50% SARON": "50 / 50 mix",
        "All SARON": "All SARON",
        "Custom allocation": "Custom allocation",
    }
    return labels.get(name, name)


def risk_label(risk: str) -> str:
    return {"low": "Conservative", "medium": "Balanced", "high": "Flexible"}.get(risk, "Balanced")


def status_info(traffic_light: str) -> tuple[str, str]:
    labels = {
        "green": ("green", "Affordable"),
        "yellow": ("yellow", "Borderline affordable"),
        "red": ("red", "Not currently affordable"),
    }
    return labels.get(traffic_light, ("yellow", "Please review"))



def render_header(active_step: int) -> None:
    """Compact responsive header with an icon-only theme toggle."""
    brand_col, theme_col = st.columns(
        [8, 1],
        vertical_alignment="center",
    )

    with brand_col:
        st.markdown(
            f"""
            <div class="brand">
                <img
                    src="data:image/png;base64,{LOGO_BASE64}"
                    class="brand-logo"
                    alt="HypoKompass logo"
                />
                <span>HypoKompass CH</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with theme_col:
        mode = st.session_state.get("theme_mode", "system")
        icons = {"system": "🌓", "light": "🌙", "dark": "☀️"}
        help_texts = {
            "system": "Theme: follow device setting (tap to force dark mode)",
            "dark": "Theme: dark (tap to force light mode)",
            "light": "Theme: light (tap to follow device setting)",
        }
        if st.button(icons.get(mode, "🌓"), key="theme_toggle", help=help_texts.get(mode, "Change theme"), type="secondary"):
            st.session_state["theme_mode"] = {"system": "dark", "dark": "light", "light": "system"}[mode]
            st.rerun()
    st.markdown('<div class="topbar-divider"></div>', unsafe_allow_html=True)

def render_status(traffic_light: str, title: str, detail: str) -> None:
    state, _ = status_info(traffic_light)
    st.markdown(
        f'<div class="status-strip status-{state}"><span class="status-dot"></span>'
        f'<span>{html.escape(title)}</span></div>'
        f'<div class="tip" style="margin-top:-.25rem">{html.escape(detail)}</div>',
        unsafe_allow_html=True,
    )


def equity_readiness(user: dict[str, Any]) -> tuple[float, float, float]:
    purchase_costs = user["purchase_price"] * 0.03
    net_equity = user["equity"] - purchase_costs
    equity_share = net_equity / user["purchase_price"]
    hard_share = (user["equity"] - user["pension_fund_withdrawal"] - purchase_costs) / user["purchase_price"]
    return net_equity, equity_share, hard_share


def build_custom_strategy() -> dict[str, Any] | None:
    st.markdown("**Custom allocation**")
    st.caption("Split your mortgage into fixed-rate portions. The remaining share will automatically be assigned to SARON.")
    fixed3 = st.slider("3-year fixed-rate share (%)", 0, 100, 0, 5, key="custom_fixed3")
    fixed10 = st.slider("10-year fixed-rate share (%)", 0, 100, 0, 5, key="custom_fixed10")
    fixed15 = st.slider("15-year fixed-rate share (%)", 0, 100, 0, 5, key="custom_fixed15")
    fixed_total = fixed3 + fixed10 + fixed15
    if fixed_total > 100:
        st.error(f"The fixed-rate portions add up to {fixed_total}%. Please reduce the total to 100% or less.")
        return None
    saron = 100 - fixed_total
    st.markdown(f'<span class="rate-pill">SARON share: {saron}%</span>', unsafe_allow_html=True)
    tranches: dict[str, float] = {}
    for key, share in (("FIXED_3", fixed3), ("FIXED_10", fixed10), ("FIXED_15", fixed15), ("SARON", saron)):
        if share > 0:
            tranches[key] = share / 100
    return {"name": "Custom allocation", "tranches": tranches}


def render_input_page(market: dict[str, Any]) -> None:
    render_header(1)
    st.markdown('<div class="eyebrow">Your path to home ownership · Step 1 of 3</div>', unsafe_allow_html=True)
    st.title("Your first home")
    st.markdown('<div class="intro-copy">Fixed, staggered or SARON? Start with your numbers. We compare interest costs and show which strategy best matches your risk tolerance.</div>', unsafe_allow_html=True)
    st.write("")

    main_col, preview_col = st.columns([1.55, 0.9], gap="large")
    with main_col:
        st.markdown('<div class="section-kicker">01 · Your finances</div>', unsafe_allow_html=True)
        st.markdown("### What will your home cost?")
        price_col, equity_col = st.columns(2, gap="medium")
        with price_col:
            purchase_price = st.number_input(
                "Purchase price (CHF)", min_value=100_000, max_value=20_000_000,
                value=850_000, step=10_000,
                key="purchase_price", help="The total purchase price of the property.",
            )
        with equity_col:
            equity = st.number_input(
                "Equity (CHF)", min_value=0, max_value=10_000_000,
                value=200_000, step=5_000,
                key="equity", help="Savings, pillar 3a assets and, where applicable, pension-fund assets.",
            )
        income = st.number_input(
            "Annual gross household income (CHF)", min_value=1, max_value=5_000_000,
            value=150_000, step=5_000, key="income",
            help="If buying together, enter the combined income of the household.",
        )

        with st.expander("Additional details for a more accurate calculation", expanded=False):
            other_col1, other_col2 = st.columns(2, gap="medium")
            with other_col1:
                pension = st.number_input(
                    "Of which from pension fund (CHF)", min_value=0, max_value=10_000_000,
                    value=0, step=5_000, key="pension",
                    help="Withdrawal or pledge of second-pillar pension assets.",
                )
                birth_year = st.number_input(
                    "Year of birth", min_value=CURRENT_YEAR - 60, max_value=CURRENT_YEAR - 18,
                    value=CURRENT_YEAR - 28, step=1, key="birth_year",
                    help="Used to calculate amortisation of the second mortgage up to retirement.",
                )
            with other_col2:
                monthly_rent = st.number_input(
                    "Current monthly rent including utilities (CHF)", min_value=0, max_value=100_000,
                    value=0, step=100, key="monthly_rent",
                    help="Optional; enables a basic comparison with buying.",
                )
                saron_margin = st.number_input(
                    "SARON bank margin (%)", min_value=0.0, max_value=3.0,
                    value=0.8, step=0.05, format="%.2f", key="saron_margin",
                    help=f"The mortgage interest rate is SARON plus the margin. The approximate margin based on SNB data is {average_saron_margin(market):.2f}%.",
                )

        user = {
            "purchase_price": int(purchase_price),
            "equity": int(equity),
            "pension_fund_withdrawal": int(st.session_state.get("pension", 0)),
            "gross_annual_income": int(income),
            "birth_year": int(st.session_state.get("birth_year", CURRENT_YEAR - 28)),
            "monthly_rent": int(st.session_state.get("monthly_rent", 0)),
            "saron_margin": float(st.session_state.get("saron_margin", 0.8)),
        }

        st.markdown('<div class="section-kicker" style="margin-top:1.3rem">02 · Your interest-rate comfort level</div>', unsafe_allow_html=True)
        st.markdown("### How much interest-rate risk are you comfortable with?")
        risk_ui = st.radio(
            "Choose the option that best describes you",
            options=["Conservative", "Balanced", "Flexible"],
            index=1,
            horizontal=True,
            label_visibility="collapsed",
            key="risk_ui",
        )
        user["risk_tolerance"] = {"Conservative": "low", "Balanced": "medium", "Flexible": "high"}[risk_ui]

        # New section for the decision tree: how long the user keeps the mortgage and how
        # the income develops. The horizon is the most important feature of the tree.
        st.markdown('<div class="section-kicker" style="margin-top:1.3rem">03 · Your plans</div>', unsafe_allow_html=True)
        st.markdown("### How long will you keep this home?")
        plan_col1, plan_col2 = st.columns(2, gap="medium")
        with plan_col1:
            horizon = st.slider(
                "Planned horizon (years)", min_value=MIN_HORIZON_YEARS, max_value=MAX_HORIZON_YEARS,
                value=DEFAULT_HORIZON_YEARS, step=1, key="horizon_years",
                help="Until you expect to sell, move or refinance. Selling before a fixed-rate "
                     "mortgage ends usually costs an early repayment penalty.",
            )
        with plan_col2:
            income_change = st.slider(
                "Expected income change in the next 5 years (%)", min_value=MIN_INCOME_CHANGE,
                max_value=MAX_INCOME_CHANGE, value=DEFAULT_INCOME_CHANGE, step=5, key="income_change",
                help="E.g. -20% for part-time work because of children, +15% for a promotion.",
            )
        user["horizon_years"] = int(horizon)
        user["income_change"] = income_change / 100    # stored as a share, like all rates in the code

        with st.expander("Customize your strategy", expanded=False):
            st.caption("The four standard strategies are always compared. You can optionally add your own allocation.")
            add_custom = st.checkbox("Also compare my custom allocation", key="add_custom")
            custom_strategy = build_custom_strategy() if add_custom else None

        # Affordability preview and robust validation before the core model runs.
        if user["equity"] > user["purchase_price"]:
            st.error("Your equity cannot exceed the purchase price.")
            valid = False
        elif user["pension_fund_withdrawal"] > user["equity"]:
            st.error("The amount from your pension fund cannot exceed your total equity.")
            valid = False
        else:
            valid = True
        if st.session_state.get("add_custom") and custom_strategy is None:
            valid = False

        strategies = [{"name": item["name"], "tranches": dict(item["tranches"])} for item in STANDARD_STRATEGIES]
        if st.session_state.get("add_custom") and custom_strategy is not None:
            strategies.append(custom_strategy)
        user["strategies"] = strategies

        net_equity, equity_share, hard_share = equity_readiness(user)
        if equity_share < 0.20:
            st.warning(f"After estimated purchase costs of {money(purchase_price * 0.03)}, your equity represents {pct(equity_share)} of the purchase price. A common guideline is at least 20%.")
        if hard_share < 0.10:
            st.warning(f"After purchase costs, non-pension-fund equity represents {pct(hard_share)} of the purchase price. A common guideline is at least 10%.")

    with preview_col:
        with st.container(border=True):
            st.markdown('<div class="section-kicker">Your overview</div>', unsafe_allow_html=True)
            st.markdown("### At a glance")
            mortgage_estimate = max(0, int(purchase_price - net_equity))
            for label, value in (
                ("Purchase price", money(purchase_price)),
                ("Equity before purchase costs", money(equity)),
                ("Annual income", money(income)),
            ):
                st.markdown(f'<div class="summary-row"><span class="label">{html.escape(label)}</span><span class="value">{html.escape(value)}</span></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="summary-row"><span class="label">Estimated mortgage</span><span class="value">{html.escape(money(mortgage_estimate))}</span></div>', unsafe_allow_html=True)
            equity_color = "green" if equity_share >= .20 and hard_share >= .10 else "yellow"
            label = "Equity meets guideline" if equity_color == "green" else "Please review your equity"
            st.markdown(f'<div class="status-strip status-{equity_color}"><span class="status-dot"></span><span>{label} · {pct(max(0, equity_share))}</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="tip">Purchase costs are estimated at a flat 3%. Pension-fund assets cannot be used to cover these costs.</div>', unsafe_allow_html=True)

        st.write("")
        st.markdown('<div class="soft-card"><div class="section-kicker">What we compare</div><h3>4 mortgage strategies</h3><p class="muted">Fixed for 10 years, staggered 3 / 10 / 15, a fixed/SARON mix, and all SARON.</p><div class="tip">Interest costs are compared over 15 years under falling, stable and rising rate scenarios. A decision tree trained on 1,000+ historical and simulated rate paths picks the strategy that fits your plans and risk tolerance.</div></div>', unsafe_allow_html=True)
        if market["source"].startswith("Placeholder"):
            st.markdown('<div class="tip">Market data: placeholder values are being used because an SNB database is not currently available.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="tip">Data source: {html.escape(market["source"])}</div>', unsafe_allow_html=True)

    st.write("")
    action_col, help_col = st.columns([1.45, 1], gap="large")
    with action_col:
        if st.button("Compare strategies  →", type="primary", use_container_width=True, disabled=not valid):
            data = {"user": user, "market": market}
            try:
                results = calculate(data)
                assessment = evaluate(data, results)
                # Decision tree: recommendation for this profile (None if the ML part fails)
                assessment["ml"] = ml_recommendation(user, market)
            except Exception as exc:  # keep UI usable if the provided project model rejects an edge case
                st.error(f"The calculation could not be completed with these inputs: {exc}")
            else:
                st.session_state["result_data"] = data
                st.session_state["result_results"] = results
                st.session_state["result_assessment"] = assessment
                st.session_state["step"] = 3
                st.session_state["scroll_to_top"] = True
                st.rerun()
    with help_col:
        st.markdown('<div class="tip" style="padding:.65rem 0">The results are illustrative calculations using simplified interest-rate scenarios, not mortgage or financial advice.</div>', unsafe_allow_html=True)

    render_footer(market)


def render_cost_chart(metrics: dict[str, Any], recommendation: str) -> None:
    colors = {
        "Staggered fixed 3/10/15 years": NAVY,
        "All fixed for 10 years": BLUE,
        "50% fixed for 10 years / 50% SARON": TEAL,
        "All SARON": "#b9652c",
        "Custom allocation": "#7c7e9b",
    }
    ordered = sorted(metrics.items(), key=lambda item: (item[0] != recommendation, item[1]["stable"]))
    all_costs = [v[scenario] for _, v in ordered for scenario in ("falling", "stable", "rising")]
    low_axis = max(0, int((min(all_costs) // 50_000) * 50_000))
    high_axis = max(low_axis + 50_000, int(((max(all_costs) + 49_999) // 50_000) * 50_000))
    # Add one small pad on either side, then keep readable CHF 50k ticks.
    low_axis = max(0, low_axis - 50_000)
    high_axis += 50_000
    span = max(1, high_axis - low_axis)
    ticks = list(range(low_axis, high_axis + 1, max(50_000, int(((span / 4) // 50_000) * 50_000) or 50_000)))
    if ticks[-1] != high_axis:
        ticks.append(high_axis)
    axis_html = " ".join(f"<span>{int(t / 1000)}</span>" for t in ticks)
    with st.container(border=True):
        st.markdown(
            f'<div class="chart-head"><h3 style="margin:0">Interest costs over 15 years</h3><span class="chart-note">in CHF 1\'000 · range = rate scenarios · marker = stable rates</span></div>'
            f'<div class="axis-row"><div></div><div class="axis-labels">{axis_html}</div><div style="text-align:right">Range</div></div>',
            unsafe_allow_html=True,
        )
        for name, values in ordered:
            scenario_values = [values["falling"], values["stable"], values["rising"]]
            min_cost, max_cost = min(scenario_values), max(scenario_values)
            left = max(0.0, min(100.0, (min_cost - low_axis) / span * 100))
            right = max(0.0, min(100.0, (max_cost - low_axis) / span * 100))
            stable = max(0.0, min(100.0, (values["stable"] - low_axis) / span * 100))
            width = max(.7, right - left)
            label = html.escape(strategy_label(name))
            is_recommended = name == recommendation
            color = colors.get(name, "#7c7e9b")
            st.markdown(
                f'<div class="cost-row"><div class="cost-name {"recommended" if is_recommended else ""}">{label}</div>'
                f'<div class="cost-track"><div class="cost-range" style="left:{left:.2f}%;width:{width:.2f}%;background:{color}"></div>'
                f'<div class="cost-marker" style="left:{stable:.2f}%"></div></div>'
                f'<div class="cost-total">{html.escape(money(values["stable"]))}</div></div>',
                unsafe_allow_html=True,
            )
    st.caption("The range shows modeled costs from falling to rising interest rates. It is not a forecast of actual rate movements.")


def render_results_page() -> None:
    data = st.session_state.get("result_data")
    results = st.session_state.get("result_results")
    assessment = st.session_state.get("result_assessment")
    if not data or not results or not assessment:
        st.session_state["step"] = 1
        st.rerun()
        return

    user = data["user"]
    affordability = results["affordability"]
    metrics = assessment["metrics"]
    ml = assessment.get("ml")
    # The decision tree decides; the old rule of evaluation.py is only the fallback
    recommendation = ml["strategy"] if ml else assessment["recommended_strategy"]
    rec_metric = metrics[recommendation]
    market = data["market"]

    render_header(3)
    st.markdown('<div class="eyebrow">Your results · Step 3 of 3</div>', unsafe_allow_html=True)
    st.title("Your mortgage strategy")
    st.markdown('<div class="intro-copy">Compare estimated interest costs, affordability and the risk of the different mortgage allocations.</div>', unsafe_allow_html=True)
    st.write("")

    if ml:
        # Explanation from the tree: the rules on the way to this user's leaf
        rationale = "Because " + " and ".join(ml["rules"]) + "." if ml["rules"] else "This strategy fits all profiles in our model."
    else:
        rationale = {
            "low": "You prefer predictable interest costs, so the recommendation prioritizes minimizing fluctuations.",
            "medium": "You want to balance security and potential savings. The recommendation gives particular weight to the rising-rate scenario.",
            "high": "You are more comfortable with rate fluctuations if they could lower costs. The recommendation is based on the stable-rate scenario.",
        }.get(user["risk_tolerance"], "The recommendation is based on your risk tolerance.")
    st.markdown(
        f'<div class="hero-result"><div><div class="overline">Recommended for your profile · {risk_label(user["risk_tolerance"])}</div>'
        f'<div class="recommendation">{html.escape(strategy_label(recommendation))}</div>'
        f'<div class="explain">{html.escape(rationale)}</div></div>'
        f'<div><div class="risk-cost-label">Interest costs with stable rates</div>'
        f'<div class="risk-cost">{html.escape(money(rec_metric["stable"]))}</div></div></div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([.85, 1.55], gap="large")
    with left:
        with st.container(border=True):
            st.markdown('<div class="section-kicker">Your profile</div>', unsafe_allow_html=True)
            st.markdown("### Key figures")
            summary = [
                ("Purchase price", money(user["purchase_price"])),
                ("Equity", f'{money(user["equity"])} ({pct(user["equity"] / user["purchase_price"])})'),
                ("Income", money(user["gross_annual_income"]) + " / year"),
                ("Mortgage", money(affordability["mortgage"])),
            ]
            for label, value in summary:
                st.markdown(f'<div class="summary-row"><span class="label">{html.escape(label)}</span><span class="value">{html.escape(value)}</span></div>', unsafe_allow_html=True)
        st.write("")
        state, state_label = status_info(affordability["traffic_light"])
        with st.container(border=True):
            st.markdown('<div class="section-kicker">Affordability</div>', unsafe_allow_html=True)
            render_status(affordability["traffic_light"], state_label, affordability["message"])
            st.markdown(
                f'<div class="summary-row"><span class="label">Loan-to-value</span><span class="value">{pct(affordability["mortgage_ratio"])}</span></div>'
                f'<div class="summary-row"><span class="label">One-time purchase costs</span><span class="value">{html.escape(money(affordability["purchase_costs"]))}</span></div>'
                f'<div class="summary-row"><span class="label">Imputed monthly housing costs</span><span class="value">{html.escape(money(affordability["imputed_monthly_costs"]))} / month</span></div>'
                f'<div class="summary-row"><span class="label">Share of gross income</span><span class="value">{pct(affordability["affordability_ratio"])}</span></div>'
                f'<div class="tip">Affordability is assessed conservatively using a 5% imputed interest rate, 1% maintenance and amortisation.</div>',
                unsafe_allow_html=True,
            )

    with right:
        render_cost_chart(metrics, recommendation)
        st.write("")
        if ml:
            render_ml_card(ml, recommendation, user)
            st.write("")
        with st.container(border=True):
            st.markdown('<div class="section-kicker">Interest-rate scenarios</div>', unsafe_allow_html=True)
            st.markdown("### What could change?")
            scenario_col1, scenario_col2, scenario_col3 = st.columns(3, gap="small")
            with scenario_col1:
                st.markdown(f'<div class="metric-label">Rates fall</div><div class="metric-value">{html.escape(money(rec_metric["falling"]))}</div><div class="metric-small">−0.25 percentage points/year</div>', unsafe_allow_html=True)
            with scenario_col2:
                st.markdown(f'<div class="metric-label">Rates stay stable</div><div class="metric-value">{html.escape(money(rec_metric["stable"]))}</div><div class="metric-small">±0.00 percentage points/year</div>', unsafe_allow_html=True)
            with scenario_col3:
                st.markdown(f'<div class="metric-label">Rates rise</div><div class="metric-value">{html.escape(money(rec_metric["rising"]))}</div><div class="metric-small">+0.25 percentage points/year</div>', unsafe_allow_html=True)

    if assessment.get("rent_comparison"):
        rent = assessment["rent_comparison"]
        st.write("")
        with st.container(border=True):
            st.markdown('<div class="section-kicker">Optional comparison</div>', unsafe_allow_html=True)
            st.markdown("### Buy or rent?")
            rent_cols = st.columns(3, gap="medium")
            with rent_cols[0]:
                st.markdown(f'<div class="metric-label">Current monthly rent</div><div class="metric-value">{html.escape(money(rent["rent"]))}</div>', unsafe_allow_html=True)
            with rent_cols[1]:
                st.markdown(f'<div class="metric-label">Estimated interest + maintenance</div><div class="metric-value">{html.escape(money(rent["ownership_cost"]))}</div><div class="metric-small">excluding amortisation</div>', unsafe_allow_html=True)
            with rent_cols[2]:
                difference = rent["difference"]
                detail = "less than rent" if difference >= 0 else "more than rent"
                st.markdown(f'<div class="metric-label">Monthly difference</div><div class="metric-value">{html.escape(money(abs(difference)))}</div><div class="metric-small">{detail}</div>', unsafe_allow_html=True)
            st.markdown('<div class="tip">Simplified comparison: excludes the potential returns forgone on equity and changes in property value. Amortisation builds equity, so it is not treated as a pure expense.</div>', unsafe_allow_html=True)

    with st.expander("Interest-rate data and model assumptions"):
        st.markdown(f"**Data source:** {market['source']}")
        st.markdown("**Starting interest rates in the model**")
        rate_cols = st.columns(4, gap="small")
        rate_display = [("Fixed for 3 years", "FIXED_3"), ("Fixed for 10 years", "FIXED_10"), ("Fixed for 15 years", "FIXED_15"), ("SARON", "SARON")]
        for col, (label, key) in zip(rate_cols, rate_display):
            with col:
                st.markdown(f'<div class="metric-label">{label}</div><div class="metric-value">{market["rates"][key]:.2f}%</div>', unsafe_allow_html=True)
        st.markdown("**Assumptions:** 15-year period; interest-rate scenarios of −0.25 / 0 / +0.25 percentage points per year; modeled SARON rate does not fall below 0%; one-time purchase costs estimated at 3%; affordability assessed using a 5% imputed interest rate plus 1% maintenance. Interest costs exclude principal repayments.")

    st.write("")
    button_col, second_col = st.columns([1, 1], gap="medium")
    with button_col:
        if st.button("← Edit inputs", use_container_width=True):
            st.session_state["step"] = 1
            st.session_state["scroll_to_top"] = True
            st.rerun()
    with second_col:
        if st.button("Start a new calculation", type="primary", use_container_width=True):
            st.session_state["step"] = 1
            st.session_state.pop("result_data", None)
            st.session_state.pop("result_results", None)
            st.session_state.pop("result_assessment", None)
            st.session_state["scroll_to_top"] = True
            st.rerun()
    render_footer(market)


def render_ml_card(ml: dict[str, Any], recommendation: str, user: dict[str, Any]) -> None:
    """Card 'Why this strategy?': rules of the tree and key figures over all scenarios."""
    with st.container(border=True):
        st.markdown('<div class="section-kicker">Decision tree · 1,000+ rate scenarios</div>', unsafe_allow_html=True)
        st.markdown("### Why this strategy?")
        # 1. The rules of the tree as a list
        for rule in ml["rules"]:
            st.markdown(f"- {html.escape(rule[0].upper() + rule[1:])}")
        # 2. Key figures of every strategy over the user's horizon
        horizon = user.get("horizon_years", DEFAULT_HORIZON_YEARS)
        st.markdown(
            f'<div class="tip">Interest costs over your horizon of {horizon} years across all historical '
            f'and simulated scenarios (incl. early repayment penalty if you sell before a fixed term ends).</div>',
            unsafe_allow_html=True,
        )
        header = ('<div class="summary-row"><span class="label"><b>Strategy</b></span>'
                  '<span class="label" style="text-align:right"><b>Average · worst 10% · budget stress</b></span></div>')
        rows = [header]
        for item in ml["details"]:
            name = html.escape(strategy_label(item["name"]))
            if item["name"] == recommendation:
                name = f"<b>{name}</b>"            # highlight the recommended strategy
            rows.append(
                f'<div class="summary-row"><span class="label">{name}</span><span class="value">'
                f'{html.escape(money(item["mean"]))} · {html.escape(money(item["cvar"]))} · {item["stress"]:.0%}</span></div>'
            )
        st.markdown("".join(rows), unsafe_allow_html=True)
        st.markdown(
            '<div class="tip">Budget stress = share of scenarios in which your actual housing costs exceed '
            'one third of your income in at least one year.</div>',
            unsafe_allow_html=True,
        )
        # 3. Honest note if the small tree and the exact simulation disagree for this user
        if ml["exact_strategy"] != ml["strategy"]:
            st.info(f"For your exact profile, the full simulation would slightly prefer "
                    f"**{strategy_label(ml['exact_strategy'])}**. The tree keeps its rules simple, "
                    f"so it can differ in borderline cases.")


def render_footer(market: dict[str, Any]) -> None:
    source = market.get("source", "").replace("<", "&lt;").replace(">", "&gt;")
    st.markdown(
        f'<div class="footer-note"><span>Illustrative model calculation, not financial advice</span><span>Source: {source}</span></div>',
        unsafe_allow_html=True,
    )


def scroll_to_top() -> None:
    """Scroll the parent Streamlit page to its top anchor after navigation."""
    components.html(
        """<script>
        (() => {
          let attempts = 0;
          const goTop = () => {
            try {
              const doc = window.parent.document;
              const anchor = doc.getElementById('hypo-page-top');
              if (anchor) anchor.scrollIntoView({block: 'start', behavior: 'auto'});
              const candidates = [
                doc.querySelector('[data-testid="stMain"]'),
                doc.querySelector('[data-testid="stAppViewContainer"]'),
                doc.querySelector('section.main'),
                doc.scrollingElement,
                doc.documentElement,
                doc.body
              ].filter(Boolean);
              candidates.forEach((el) => {
                try { el.scrollTop = 0; } catch (_) {}
                try { if (el.scrollTo) el.scrollTo({top: 0, left: 0, behavior: 'auto'}); } catch (_) {}
              });
              try { window.parent.scrollTo({top: 0, left: 0, behavior: 'auto'}); } catch (_) {}
            } catch (_) { /* embedded component sandbox may restrict parent access */ }
            attempts += 1;
            if (attempts < 25) window.setTimeout(goTop, 120);
          };
          window.requestAnimationFrame(goTop);
        })();
        </script>""",
        height=1,
        scrolling=False,
    )

def main() -> None:
    if "theme_mode" not in st.session_state:
        old_preference = st.session_state.pop("dark_mode", None)
        st.session_state["theme_mode"] = "dark" if old_preference is True else "system"
    st.markdown('<div id="hypo-page-top"></div>', unsafe_allow_html=True)
    if "step" not in st.session_state:
        st.session_state["step"] = 1
    if st.session_state.pop("scroll_to_top", False):
        scroll_to_top()
    market = get_market_data()
    if st.session_state["step"] == 3:
        render_results_page()
    else:
        render_input_page(market)


if __name__ == "__main__":
    main()
