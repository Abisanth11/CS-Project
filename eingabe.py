# Inputs section of the app
# eingabe.py
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
# Uses only Python basics: functions, loops, if/else, lists, dictionaries.
#
# AI notice: console version scaffolded with Claude (Anthropic), 09.10.2026;
#            converted to Streamlit and translated to English with Claude (Anthropic), 15.10.2026.
#
# Run with:  streamlit run eingabe.py

import datetime

import streamlit as st

# The database module is optional: if it is missing, placeholder rates are used,
# so this page also runs on its own (e.g. for testing).
try:
    from data import database
except ImportError:
    database = None

CURRENT_YEAR = datetime.date.today().year

# Mortgage products a strategy is built from
PRODUCTS = {
    "FEST_3": "Fixed-rate mortgage 3 years",
    "FEST_10": "Fixed-rate mortgage 10 years",
    "FEST_15": "Fixed-rate mortgage 15 years",
    "SARON": "SARON mortgage (variable)",
}

# These strategies are always compared. Shares as fractions (0.5 = 50 %).
STANDARD_STRATEGIES = [
    {"name": "All fixed 10 years", "tranches": {"FEST_10": 1.0}},
    {"name": "All SARON", "tranches": {"SARON": 1.0}},
    {"name": "Staggered fixed 3/10/15 years", "tranches": {"FEST_3": 1 / 3, "FEST_10": 1 / 3, "FEST_15": 1 / 3}},
    {"name": "Mix 50 % fixed 10 y. / 50 % SARON", "tranches": {"FEST_10": 0.5, "SARON": 0.5}},
]

# Risk tolerance: how important are predictable interest costs?
RISK_OPTIONS = [
    "Very important – I don't want any surprises with interest rates",
    "Fairly important – some fluctuation is okay",
    "Less important – I accept fluctuations for lower costs",
]
RISK_LEVELS = ["low", "medium", "high"]

# PLACEHOLDER rates in %: only used if the database is empty (python -m data.update_data
# never run). Values from data.snb.ch: fixed-rate mortgages August 2026 (mean "M"),
# SARON as of 02.10.2026.
PLACEHOLDER_RATES = {
    "FEST_3": 1.61,
    "FEST_10": 2.03,
    "FEST_15": 2.34,
    "SARON": -0.04,   # only SARON itself – the bank margin is entered by the user
}
REAL_ESTATE_YEARS = 10              # period for the price development of apartments and rents
PLACEHOLDER_SARON_MORTGAGE = 1.19   # average rate of new SARON mortgages (open-ended), Aug. 2026

# Usual bank rules for equity (used for warnings only)
MIN_EQUITY_SHARE = 0.20        # at least 20 % of the purchase price
MIN_HARD_EQUITY_SHARE = 0.10   # of which at least 10 % not from the pension fund


# --- Helper functions ---

def chf(amount):
    """Formats an amount as CHF with thousands separators, e.g. CHF 1'250'000."""
    return "CHF " + format(round(amount), ",").replace(",", "'")


def tranche_text(tranches):
    """Describes a split as text, e.g. '50 % Fixed-rate mortgage 10 years + 50 % SARON ...'."""
    parts = []
    for product in tranches:
        parts.append(str(round(tranches[product] * 100)) + " % " + PRODUCTS[product])
    return " + ".join(parts)


# --- Market data ---

@st.cache_data(ttl=3600)   # load only once per hour, not on every click
def load_market_data():
    """Returns the current rates per product.

    First from the SQLite database (SNB data). If it is empty or missing, the placeholders
    are used – so the app also runs offline or before the first update.
    """
    current = None
    # Price development over the last 10 years (SNB cube plimoincha, source Wüest Partner):
    # owner-occupied apartments = transaction prices (TP), rental apartments = asking rents (AP).
    # None if the data has not been loaded yet. (Added 12.10.2026, AI notice: Claude)
    real_estate = {"apartments": None, "rents": None}

    if database is not None:
        try:
            # The functions of the database module keep their (German) names
            con = database.verbinde()
            current = database.aktuelle_zinsen(con)
            real_estate = {
                "apartments": database.preisentwicklung(con, "EW", "TP", REAL_ESTATE_YEARS),
                "rents": database.preisentwicklung(con, "MW", "AP", REAL_ESTATE_YEARS),
            }
            con.close()
        except Exception:
            current = None   # e.g. database file missing -> fall back to placeholders

    if current is None:
        return {
            "rates": PLACEHOLDER_RATES,
            "saron_mortgage": PLACEHOLDER_SARON_MORTGAGE,
            "real_estate": real_estate,
            "source": "Placeholder",
        }
    return {
        "rates": current["zinsen"],
        "saron_mortgage": current["saron_hypo"],
        "real_estate": real_estate,
        "source": "SNB, mortgages " + current["stand_hypo"] + ", SARON " + current["stand_saron"],
    }


def average_margin(market):
    """Average margin of new SARON mortgages = their rate minus SARON.

    SARON counts as at least 0 %, because banks do not charge it as negative.
    """
    saron = market["rates"]["SARON"]
    if saron < 0:
        saron = 0
    return market["saron_mortgage"] - saron


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
             "purchase price, of which at least 10 % must not come from the pension fund.")

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

    # For the comparison "buy or rent?" in step 3 (added 12.10.2026, AI notice: Claude)
    rent = st.number_input(
        "What is your current monthly rent incl. utilities? (CHF)",
        min_value=0, max_value=100_000, value=0, step=100,
        help="For the comparison buying vs. renting; 0 = skip.")

    return {
        "purchase_price": purchase_price,
        "equity": equity,
        "pension": pension,
        "income": income,
        "birth_year": int(birth_year),
        "rent": rent,
    }


def check_financing(user):
    """Shows errors/warnings for implausible inputs. Returns True if the inputs are usable."""
    valid = True
    if user["equity"] > user["purchase_price"]:
        st.error("Your equity is higher than the purchase price.")
        valid = False
    if user["pension"] > user["equity"]:
        st.error("The pension fund amount cannot be higher than your total equity.")
        valid = False

    if valid:
        equity_share = user["equity"] / user["purchase_price"]
        hard_share = (user["equity"] - user["pension"]) / user["purchase_price"]
        if equity_share < MIN_EQUITY_SHARE:
            st.warning(f"Your equity covers {equity_share:.0%} of the price – "
                       "banks usually require at least 20 %.")
        if hard_share < MIN_HARD_EQUITY_SHARE:
            st.warning(f"Only {hard_share:.0%} of the price comes from outside the pension fund – "
                       "banks usually require at least 10 %.")
    return valid


# --- Block B: Strategies and risk ---

def capture_own_strategy():
    """Lets the user split the mortgage across the products (total = 100 %).

    The last product automatically gets the rest, so the total always adds up.
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
    return {"name": "Own allocation", "tranches": tranches}


def capture_strategies_and_risk(market):
    """Shows the standard strategies, asks for own allocation, SARON margin and risk.

    market: result of load_market_data(), for the hint about the average margin.
    """
    st.header("B) How do you want to split your mortgage?")
    st.write("We compare these strategies for you:")
    for strategy in STANDARD_STRATEGIES:
        st.write("- **" + strategy["name"] + "**: " + tranche_text(strategy["tranches"]))

    strategies = list(STANDARD_STRATEGIES)   # copy, so the template stays unchanged
    if st.checkbox("I would also like to compare my own allocation"):
        own = capture_own_strategy()
        if own is not None:
            strategies.append(own)

    margin = st.number_input(
        "What margin does the bank charge on the SARON mortgage? (in %)",
        min_value=0.0, max_value=3.0, value=0.8, step=0.05,
        help="Your rate = SARON + margin. Average for new SARON mortgages according to the SNB: approx. "
             + str(round(average_margin(market), 2)) + " %, good offers are lower.")

    risk_choice = st.radio("How important is it to you that your interest costs stay predictable?",
                           RISK_OPTIONS)
    risk = RISK_LEVELS[RISK_OPTIONS.index(risk_choice)]

    return {
        "strategies": strategies,
        "margin": margin,
        "risk": risk,
    }


# --- Summary ---

def show_summary(user):
    """Shows all details again in a clear overview."""
    st.header("Your details")
    equity_share = round(user["equity"] / user["purchase_price"] * 100, 1)

    st.write("**Purchase price:**", chf(user["purchase_price"]))
    st.write("**Equity:**", chf(user["equity"]), f"({equity_share} %)")
    st.write("**of which pension fund:**", chf(user["pension"]))
    st.write("**Gross income:**", chf(user["income"]))
    st.write("**Age:**", CURRENT_YEAR - user["birth_year"], "years")
    if user["rent"] > 0:
        st.write("**Current rent:**", chf(user["rent"]), "per month")
    st.write("**SARON margin:**", user["margin"], "%")
    st.write("**Risk tolerance:**", user["risk"])
    st.write("**Strategies:**")
    for strategy in user["strategies"]:
        st.write("- **" + strategy["name"] + "**: " + tranche_text(strategy["tranches"]))


# --- Interface to step 2 ---

def capture_inputs():
    """Shows the whole input page and returns {"user": ..., "market": ...}.

    Unlike the console version, no "are the details correct?" loop is needed:
    in Streamlit the user simply changes a field and everything updates.
    """
    st.title("🏠 HypoKompass CH")
    st.write("Can I afford my first home – and how should I split the mortgage?")

    market = load_market_data()   # first, so the margin question can show the SNB average
    if market["source"] == "Placeholder":
        st.info("No SNB data in the database yet – placeholder rates are used. "
                "Load data with: python -m data.update_data")

    user = capture_financing()
    valid = check_financing(user)
    user.update(capture_strategies_and_risk(market))   # merge both blocks
    show_summary(user)

    data = {"user": user, "market": market}
    # Store for the other pages (agreed team interface)
    st.session_state["inputs"] = data
    st.session_state["inputs_valid"] = valid
    return data


def sample_data():
    """Fixed test data: graduate, 28, buys an apartment for CHF 850'000.

    Equity 200'000: after 3 % purchase costs (25'500), 174'500 remain, i.e. just over 20 %.
    """
    user = {
        "purchase_price": 850_000,
        "equity": 200_000,
        "pension": 0,
        "income": 150_000,
        "birth_year": 1998,
        "rent": 2_200,
        "strategies": list(STANDARD_STRATEGIES),   # copy, so the template stays unchanged
        "margin": 0.8,
        "risk": "medium",
    }
    return {"user": user, "market": load_market_data()}


# Show the page only when this file is started directly (streamlit run eingabe.py),
# not when another file imports it (e.g. to use sample_data()).
if __name__ == "__main__":
    capture_inputs()
    
