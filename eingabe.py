"""Input collection for HypoKompass CH (console version)."""
import datetime

try:
    from data import database as _database
except ImportError:
    _database = None

CURRENT_YEAR = datetime.date.today().year
PRODUCTS = {
    "FIXED_3": "3-year fixed-rate mortgage",
    "FIXED_10": "10-year fixed-rate mortgage",
    "FIXED_15": "15-year fixed-rate mortgage",
    "SARON": "SARON mortgage (variable)",
}
STANDARD_STRATEGIES = [
    {"name": "All fixed for 10 years", "tranches": {"FIXED_10": 1.0}},
    {"name": "All SARON", "tranches": {"SARON": 1.0}},
    {"name": "Staggered fixed 3/10/15 years", "tranches": {"FIXED_3": 1/3, "FIXED_10": 1/3, "FIXED_15": 1/3}},
    {"name": "50% fixed for 10 years / 50% SARON", "tranches": {"FIXED_10": 0.5, "SARON": 0.5}},
]
RISK_OPTIONS = {
    "1": ("low", "Low — minimise fluctuations in interest costs"),
    "2": ("medium", "Medium — balance costs and predictability"),
    "3": ("high", "High — accept fluctuations in pursuit of lower costs"),
}
PLACEHOLDER_RATES = {"FIXED_3": 1.61, "FIXED_10": 2.03, "FIXED_15": 2.34, "SARON": -0.04}
PLACEHOLDER_SARON_MORTGAGE = 1.19
REAL_ESTATE_YEARS = 10
MIN_EQUITY_SHARE = 0.20
MIN_HARD_EQUITY_SHARE = 0.10


def format_chf(amount):
    """Format a value as CHF 1'250'000."""
    return "CHF " + format(round(amount), ",").replace(",", "'")


def describe_tranches(tranches):
    parts = [f"{round(share * 100)}% {PRODUCTS[product]}" for product, share in tranches.items() if product in PRODUCTS and share > 0]
    return " + ".join(parts) if parts else "No mortgage tranche specified"


def _copy_strategies(strategies=STANDARD_STRATEGIES):
    return [{"name": item["name"], "tranches": dict(item["tranches"])} for item in strategies]


def load_market_data():
    """Load market data through the existing database adapter, or use fallbacks.

    The internal adapter currently has German function names; the data exposed to
    the rest of this application uses English keys.
    """
    current = None
    real_estate = {"apartments": None, "rents": None}
    connection = None
    if _database is not None:
        try:
            connection = _database.verbinde()
            current = _database.aktuelle_zinsen(connection)
            real_estate = {
                "apartments": _database.preisentwicklung(connection, "EW", "TP", REAL_ESTATE_YEARS),
                "rents": _database.preisentwicklung(connection, "MW", "AP", REAL_ESTATE_YEARS),
            }
        except Exception:
            current = None
            real_estate = {"apartments": None, "rents": None}
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
    if current is None:
        return {"rates": dict(PLACEHOLDER_RATES), "saron_mortgage_rate": PLACEHOLDER_SARON_MORTGAGE,
                "source": "Placeholder values (SNB database unavailable)", "real_estate": real_estate}
    rates = dict(PLACEHOLDER_RATES)
    rates.update({"FIXED_3": current.get("zinsen", {}).get("FEST_3", PLACEHOLDER_RATES["FIXED_3"]),
                  "FIXED_10": current.get("zinsen", {}).get("FEST_10", PLACEHOLDER_RATES["FIXED_10"]),
                  "FIXED_15": current.get("zinsen", {}).get("FEST_15", PLACEHOLDER_RATES["FIXED_15"]),
                  "SARON": current.get("zinsen", {}).get("SARON", PLACEHOLDER_RATES["SARON"])})
    return {"rates": rates, "saron_mortgage_rate": current.get("saron_hypo", PLACEHOLDER_SARON_MORTGAGE),
            "source": f"SNB: mortgages {current.get('stand_hypo', 'unknown')}, SARON {current.get('stand_saron', 'unknown')}",
            "real_estate": real_estate}


def average_saron_margin(market):
    saron = max(0, market["rates"].get("SARON", 0.0))
    return market["saron_mortgage_rate"] - saron


def ask_yes_no(question):
    while True:
        answer = input(f"{question} (y/n): ").strip().lower()
        if answer in ("y", "yes", "1"):
            return True
        if answer in ("n", "no", "0"):
            return False
        print("Please answer 'y' or 'n'.")


def _ask_integer(question, default, minimum=None, maximum=None):
    while True:
        raw = input(f"{question} [default: {default}]: ").strip()
        if not raw:
            value = default
        else:
            try:
                value = int(raw.replace("'", "").replace("’", "").replace(" ", ""))
            except ValueError:
                print("Please enter a whole number, e.g. 850000.")
                continue
        if minimum is not None and value < minimum:
            print(f"The value must be at least {minimum}.")
            continue
        if maximum is not None and value > maximum:
            print(f"The value must be at most {maximum}.")
            continue
        return value


def _ask_percentage(question, default, minimum=0.0, maximum=3.0):
    while True:
        raw = input(f"{question} [default: {default:.2f}%]: ").strip()
        try:
            value = float(raw.replace(",", ".").replace("%", "").strip()) if raw else float(default)
        except ValueError:
            print("Please enter a number, e.g. 0.80.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"Please enter a value between {minimum:.2f}% and {maximum:.2f}%.")


def _collect_financing():
    print("\n=== A) Your home and finances ===")
    print("This model is intended for a home you will live in yourself.")
    purchase_price = _ask_integer("Purchase price (CHF)", 850_000, minimum=1)
    while True:
        equity = _ask_integer("How much equity do you have (CHF)?", 200_000, minimum=0)
        if equity <= purchase_price:
            break
        print("Equity cannot exceed the purchase price in this model.")
    while True:
        pension_fund = _ask_integer("How much of your equity comes from your pension fund (CHF)?", 0, minimum=0)
        if pension_fund <= equity:
            break
        print("The pension fund amount cannot exceed your total equity.")
    income = _ask_integer("Gross annual income (CHF)", 150_000, minimum=1)
    birth_year = _ask_integer("Year of birth", CURRENT_YEAR - 28, minimum=CURRENT_YEAR - 60, maximum=CURRENT_YEAR - 18)
    rent = _ask_integer("Current monthly rent including utilities (CHF; 0 to skip)", 0, minimum=0)
    user = {"purchase_price": purchase_price, "equity": equity, "pension_fund_withdrawal": pension_fund,
            "gross_annual_income": income, "birth_year": birth_year, "monthly_rent": rent}
    purchase_costs = purchase_price * 0.03
    hard_equity = equity - pension_fund - purchase_costs
    if equity / purchase_price < MIN_EQUITY_SHARE:
        print("Note: your equity is below 20% of the purchase price.")
    if hard_equity / purchase_price < MIN_HARD_EQUITY_SHARE:
        print("Note: after purchase costs, less than 10% of the price comes from non-pension-fund equity.")
    if equity - purchase_costs < 0:
        print("Note: your equity does not cover the assumed purchase costs.")
    return user


def _collect_custom_strategy():
    print("\nCustom strategy: enter the shares of the first three products as percentages.")
    print("Any remaining share will be allocated to the SARON mortgage.")
    while True:
        fixed_3 = _ask_integer("3-year fixed mortgage (%)", 0, 0, 100)
        fixed_10 = _ask_integer("10-year fixed mortgage (%)", 0, 0, 100)
        fixed_15 = _ask_integer("15-year fixed mortgage (%)", 0, 0, 100)
        total = fixed_3 + fixed_10 + fixed_15
        if total <= 100:
            break
        print(f"Shares total {total}%. Please enter a total of at most 100%.")
    saron = 100 - total
    tranches = {key: share / 100 for key, share in (("FIXED_3", fixed_3), ("FIXED_10", fixed_10), ("FIXED_15", fixed_15), ("SARON", saron)) if share > 0}
    return {"name": "Custom allocation", "tranches": tranches}


def _collect_strategies_and_risk(market):
    print("\n=== B) How to split your mortgage ===")
    strategies = _copy_strategies()
    for strategy in strategies:
        print(f"  - {strategy['name']}: {describe_tranches(strategy['tranches'])}")
    if ask_yes_no("Would you also like to compare a custom allocation?"):
        strategies.append(_collect_custom_strategy())
    print(f"Estimated average bank margin for SARON mortgages: {average_saron_margin(market):.2f}%.")
    margin = _ask_percentage("What margin does your bank charge on the SARON mortgage?", 0.80)
    print("\nHow important is it that your interest costs remain predictable?")
    for number, (_, description) in RISK_OPTIONS.items():
        print(f"  {number}. {description}")
    while True:
        choice = input("Enter 1, 2 or 3 [default: 2]: ").strip() or "2"
        if choice in RISK_OPTIONS:
            risk = RISK_OPTIONS[choice][0]
            break
        print("Invalid selection. Please enter 1, 2 or 3.")
    return {"strategies": strategies, "saron_margin": margin, "risk_tolerance": risk}


def show_summary(user):
    print("\n=== Summary of your details ===")
    print("Purchase price:          ", format_chf(user["purchase_price"]))
    equity_share = user["equity"] / user["purchase_price"] * 100
    print("Equity:                  ", format_chf(user["equity"]), f"({equity_share:.1f}%)")
    print("Of which pension fund:   ", format_chf(user["pension_fund_withdrawal"]))
    print("Gross annual income:     ", format_chf(user["gross_annual_income"]))
    print("Age:                     ", CURRENT_YEAR - user["birth_year"])
    if user["monthly_rent"] > 0:
        print("Current monthly rent:    ", format_chf(user["monthly_rent"]))
    if "saron_margin" in user:
        print("SARON bank margin:        ", f"{user['saron_margin']:.2f}%")
    if "risk_tolerance" in user:
        print("Risk tolerance:           ", user["risk_tolerance"])
    if "strategies" in user:
        print("Strategies:")
        for strategy in user["strategies"]:
            print(f"  - {strategy['name']}: {describe_tranches(strategy['tranches'])}")


def collect_inputs():
    print("\n=== HypoKompass CH — financing your first home ===")
    print("Disclaimer: this is a model calculation, not financial advice.")
    market = load_market_data()
    print(f"\nData source: {market['source']}")
    print("Starting interest rates:")
    for product, label in PRODUCTS.items():
        print(f"  - {label}: {market['rates'][product]:.2f}%")
    if market["source"].startswith("Placeholder"):
        print("Note: placeholder rates are being used because the SNB database is unavailable.")
    user = _collect_financing()
    user.update(_collect_strategies_and_risk(market))
    show_summary(user)
    return {"user": user, "market": market}


def sample_data():
    user = {"purchase_price": 850_000, "equity": 200_000, "pension_fund_withdrawal": 0,
            "gross_annual_income": 150_000, "birth_year": CURRENT_YEAR - 28, "monthly_rent": 2_200,
            "strategies": _copy_strategies(), "saron_margin": 0.8, "risk_tolerance": "medium"}
    return {"user": user, "market": load_market_data()}


if __name__ == "__main__":
    data = sample_data() if ask_yes_no("Use sample data?") else collect_inputs()
    show_summary(data["user"])
