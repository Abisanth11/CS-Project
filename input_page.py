# input_page.py
# Step 1 of 3: collect the input data (Streamlit version).
#
# Target group: young graduates financing their first home (primary residence) who want
# to compare how to split their mortgage:
#   - everything in one fixed-rate mortgage,
#   - staggered across several fixed-rate mortgages (3 / 10 / 15 years),
#   - or a mix with a SARON mortgage (linked to the SARON reference rate).
#
# Layout inspired by the Comparis mortgage calculator: one question after another,
# short help texts, summary at the end.
#
# Provides a dictionary with two parts (also stored in st.session_state["inputs"]):
#   "user":   the person's details incl. the strategies to compare
#   "market": rates per product from the SQLite database (SNB data), otherwise placeholders
# The keys are the same as in input_data.py, so the result can go directly to calculation.py.
# Shared parts (products, strategies, market data, CHF formatting) come from input_data.py,
# so console and web version always use the same values.
#
# AI notice: console version scaffolded with Claude (Anthropic), 09.10.2026;
#            converted to Streamlit and translated to English by Denis with Claude (Anthropic), 15.10.2026;
#            adapted to the names of input_data.py / calculation.py by Noel with Claude (Anthropic), 16.10.2026
#            (file renamed from eingabe.py; equity warnings now include the purchase costs);
#            block C "Your plans" (horizon, income change) for the decision tree
#            added by Denis with Claude (Anthropic), 26.10.2026.
#
# Run with:  streamlit run input_page.py

import streamlit as st

from input_data import (
    CURRENT_YEAR,
    PRODUCTS,
    STANDARD_STRATEGIES,
    MIN_EQUITY_SHARE,
    MIN_HARD_EQUITY_SHARE,
    PURCHASE_COST_RATE,
    MIN_HORIZON_YEARS,
    MAX_HORIZON_YEARS,
    DEFAULT_HORIZON_YEARS,
    MIN_INCOME_CHANGE,
    MAX_INCOME_CHANGE,
    DEFAULT_INCOME_CHANGE,
    load_market_data,
    average_saron_margin,
    format_chf,
    describe_tranches,
    sample_data,   # noqa: F401  (re-exported, e.g. for app.py tests)
)

# Risk tolerance: how important are predictable interest costs?
RISK_OPTIONS = [
    "Very important – I don't want any surprises with interest rates",
    "Fairly important – some fluctuation is okay",
    "Less important – I accept fluctuations for lower costs",
]
RISK_LEVELS = ["low", "medium", "high"]


# --- Market data ---

@st.cache_data(ttl=3600)   # load only once per hour, not on every click
def load_market_data_cached():
    """Market data from input_data.load_market_data() (SNB database or placeholders), cached."""
    return load_market_data()


# --- Block A: Your home and your finances ---

def capture_financing():
    """Asks for purchase price, equity, pension fund share, income, birth year and rent."""
    st.header("A) Your home and your finances")
    st.write("The app calculates for your first home that you live in yourself (primary residence).")

    # Note: the maximum values are fixed on purpose. If they depended on other inputs,
    # Streamlit would reset the field every time those inputs change.
    purchase_price = st.number_input(
        "How much does the apartment or house cost? (CHF)",
        min_value=1, max_value=100_000_000, value=850_000, step=10_000)

    equity = st.number_input(
        "How much equity do you bring? (CHF)",
        min_value=0, max_value=100_000_000, value=200_000, step=5_000,
        help="Savings, pillar 3a, pension fund, gifts. Banks require at least 20 % of the "
             "purchase price after purchase costs, of which at least 10 % must not come from the pension fund.")

    pension = st.number_input(
        "How much of it comes from the pension fund? (CHF)",
        min_value=0, max_value=100_000_000, value=0, step=5_000,
        help="Advance withdrawal or pledge of the 2nd pillar; 0 if none.")

    income = st.number_input(
        "What is your gross annual income? (CHF)",
        min_value=1, max_value=100_000_000, value=150_000, step=5_000,
        help="If you buy as a couple, enter your combined income.")

    # Maximum age 60 (suggestion Noel, 09.10.2026): the app targets young buyers.
    # From 65 on, the 2nd mortgage would have to be repaid within a single year,
    # so the result would not be meaningful.
    birth_year = st.number_input(
        "In which year were you born?",
        min_value=CURRENT_YEAR - 60, max_value=CURRENT_YEAR - 18, value=CURRENT_YEAR - 28, step=1,
        help="Needed to calculate the repayment until retirement; the app works for ages 18 to 60.")

    # For the comparison "buy or rent?" in step 3
    rent = st.number_input(
        "What is your current monthly rent incl. utilities? (CHF)",
        min_value=0, max_value=100_000, value=0, step=100,
        help="For the comparison buying vs. renting; 0 = skip.")

    return {
        "purchase_price": purchase_price,
        "equity": equity,
        "pension_fund_withdrawal": pension,
        "gross_annual_income": income,
        "birth_year": int(birth_year),
        "monthly_rent": rent,
    }


def check_financing(user):
    """Shows errors/warnings for implausible inputs. Returns True if the inputs are usable.

    The warnings use the same rules as the traffic light in calculation.py:
    the purchase costs are paid first, from own (non-pension-fund) money.
    """
    valid = True
    if user["equity"] > user["purchase_price"]:
        st.error("Your equity is higher than the purchase price.")
        valid = False
    if user["pension_fund_withdrawal"] > user["equity"]:
        st.error("The pension fund amount cannot be higher than your total equity.")
        valid = False

    if valid:
        purchase_costs = user["purchase_price"] * PURCHASE_COST_RATE
        equity_share = (user["equity"] - purchase_costs) / user["purchase_price"]
        hard_share = (user["equity"] - user["pension_fund_withdrawal"] - purchase_costs) / user["purchase_price"]
        if equity_share < MIN_EQUITY_SHARE:
            st.warning(f"After purchase costs, your equity covers {equity_share:.0%} of the price – "
                       "banks usually require at least 20 %.")
        if hard_share < MIN_HARD_EQUITY_SHARE:
            st.warning(f"After purchase costs, only {hard_share:.0%} of the price comes from outside "
                       "the pension fund – banks usually require at least 10 %.")
    return valid


# --- Block B: Strategies and risk ---

def capture_own_strategy():
    """Lets the user split the mortgage across the products (total = 100 %).

    The last product (SARON) automatically gets the rest, so the total always adds up.
    Returns None if the shares add up to more than 100 %.
    """
    st.write("Split your mortgage across the products (in %). The last product gets the rest.")
    keys = list(PRODUCTS)
    tranches = {}
    total = 0

    for product in keys[:-1]:   # all products except the last one
        share = st.slider(PRODUCTS[product] + " (%)", min_value=0, max_value=100, value=0, step=5)
        if share > 0:
            tranches[product] = share / 100
        total = total + share

    rest = 100 - total
    last = keys[-1]
    if rest < 0:
        st.error(f"Your shares add up to {total} % – please reduce them to at most 100 %.")
        return None

    st.write(f"{PRODUCTS[last]}: rest = **{rest} %**")
    if rest > 0:
        tranches[last] = rest / 100
    return {"name": "Custom allocation", "tranches": tranches}


def capture_strategies_and_risk(market):
    """Shows the standard strategies, asks for own allocation, SARON margin and risk.

    market: result of load_market_data(), for the hint about the average margin.
    """
    st.header("B) How do you want to split your mortgage?")
    st.write("We compare these strategies for you:")
    for strategy in STANDARD_STRATEGIES:
        st.write("- **" + strategy["name"] + "**: " + describe_tranches(strategy["tranches"]))

    # copy, so the template stays unchanged
    strategies = [{"name": s["name"], "tranches": dict(s["tranches"])} for s in STANDARD_STRATEGIES]
    if st.checkbox("I would also like to compare my own allocation"):
        own = capture_own_strategy()
        if own is not None:
            strategies.append(own)

    margin = st.number_input(
        "What margin does the bank charge on the SARON mortgage? (in %)",
        min_value=0.0, max_value=3.0, value=0.8, step=0.05,
        help="Your rate = SARON + margin. Average for new SARON mortgages according to the SNB: approx. "
             + str(round(average_saron_margin(market), 2)) + " %, good offers are lower.")

    risk_choice = st.radio("How important is it to you that your interest costs stay predictable?",
                           RISK_OPTIONS)
    risk = RISK_LEVELS[RISK_OPTIONS.index(risk_choice)]

    return {
        "strategies": strategies,
        "saron_margin": margin,
        "risk_tolerance": risk,
    }


# --- Block C: Your plans ---

def capture_plans():
    """Asks how long the user keeps the home and how their income will change.

    Both answers go into the decision tree (ml_decision_tree.py): the horizon is the most
    important feature of the tree, the income change decides about budget stress.
    """
    st.header("C) Your plans")

    # Horizon: selling before a fixed-rate mortgage ends costs an early repayment penalty,
    # so short horizons favour SARON, long horizons favour fixed or staggered mortgages
    horizon = st.slider(
        "For how many years do you plan to keep this home and mortgage?",
        min_value=MIN_HORIZON_YEARS, max_value=MAX_HORIZON_YEARS, value=DEFAULT_HORIZON_YEARS, step=1,
        help="Until you expect to sell, move or refinance. If you sell before a fixed-rate "
             "mortgage ends, the bank usually charges an early repayment penalty.")

    # Income change: a lower income makes rising interest rates more dangerous for the budget
    income_change = st.slider(
        "How do you expect your income to change over the next 5 years? (%)",
        min_value=MIN_INCOME_CHANGE, max_value=MAX_INCOME_CHANGE, value=DEFAULT_INCOME_CHANGE, step=5,
        help="Examples: -20 % for part-time work because of children, +15 % for a promotion, "
             "0 % if you expect no change.")

    return {
        "horizon_years": horizon,
        "income_change": income_change / 100,   # stored as a share (e.g. -0.2), like all rates in the code
    }


# --- Summary ---

def show_summary(user):
    """Shows all details again in a clear overview."""
    st.header("Your details")
    equity_share = round(user["equity"] / user["purchase_price"] * 100, 1)

    st.write("**Purchase price:**", format_chf(user["purchase_price"]))
    st.write("**Equity:**", format_chf(user["equity"]), f"({equity_share} %)")
    st.write("**of which pension fund:**", format_chf(user["pension_fund_withdrawal"]))
    st.write("**Gross income:**", format_chf(user["gross_annual_income"]))
    st.write("**Age:**", CURRENT_YEAR - user["birth_year"], "years")
    if user["monthly_rent"] > 0:
        st.write("**Current rent:**", format_chf(user["monthly_rent"]), "per month")
    st.write("**SARON margin:**", user["saron_margin"], "%")
    st.write("**Risk tolerance:**", user["risk_tolerance"])
    st.write("**Planned horizon:**", user["horizon_years"], "years")
    st.write("**Expected income change:**", f"{user['income_change']:+.0%}")
    st.write("**Strategies:**")
    for strategy in user["strategies"]:
        st.write("- **" + strategy["name"] + "**: " + describe_tranches(strategy["tranches"]))


# --- Interface to step 2 ---

def capture_inputs():
    """Shows the whole input page and returns {"user": ..., "market": ...}.

    Unlike the console version, no "are the details correct?" loop is needed:
    in Streamlit the user simply changes a field and everything updates.
    """
    st.title("🏠 HypoKompass CH")
    st.write("Can I afford my first home – and how should I split the mortgage?")

    market = load_market_data_cached()   # first, so the margin question can show the SNB average
    if market["source"].startswith("Placeholder"):
        st.info("No SNB data in the database yet – placeholder rates are used. "
                "Load data with: python -m data.update_data")

    user = capture_financing()
    valid = check_financing(user)
    user.update(capture_strategies_and_risk(market))   # merge both blocks
    user.update(capture_plans())                       # horizon and income change (decision tree)
    show_summary(user)

    data = {"user": user, "market": market}
    # Store for the other pages (agreed team interface)
    st.session_state["inputs"] = data
    st.session_state["inputs_valid"] = valid
    return data


# Show the page only when this file is started directly (streamlit run input_page.py),
# not when another file imports it (e.g. app.py).
if __name__ == "__main__":
    capture_inputs()
