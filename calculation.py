"""Mortgage affordability and interest-cost calculations (step 2 of 3).

Part A: affordability – can I afford the home? (traffic light)
Part B: cost comparison – what does each strategy cost in each interest-rate scenario?
No input() and no print() here, so this file works for the console and for Streamlit.

AI notice: created with Claude (Anthropic), October 2026 (German version);
English version: [team: add whether/which AI tool was used for the translation].
Formulas checked by the team: [ ]

Corrections after review by Noel:
  1. Purchase costs are deducted from the hard equity (affordability check)       (09.10.2026)
  2. The SARON floor of 0 % does not shift the rate path                            (09.10.2026)
  3. Comparison over 15 instead of 10 years, so the 15-year fixed rate is
     compared fairly                                                                (09.10.2026)
  4. A fixed-rate mortgage is never renewed below MIN_FIXED_RATE (1 %) instead
     of 0 %                                                                         (16.10.2026)
"""
from input_data import CURRENT_YEAR

# --- Assumptions affordability (Swiss bank practice) ---
CALCULATED_INTEREST_RATE = 0.05    # imputed interest rate 5 % (not the real rate)
MAINTENANCE_RATE = 0.01            # maintenance: 1 % of the purchase price per year
PURCHASE_COST_RATE = 0.03          # notary, land registry, transfer tax: one-off approx. 3 %
MAX_AFFORDABILITY_RATIO = 1 / 3    # housing costs max. 1/3 of gross income
WARNING_AFFORDABILITY_RATIO = 0.38 # team decision: up to 38 % = borderline (yellow light)
MAX_MORTGAGE_RATIO = 0.80          # mortgage max. 80 % of the purchase price
MIN_HARD_EQUITY_RATIO = 0.10       # at least 10 % of the price not from the pension fund
FIRST_MORTGAGE_LIMIT = 2 / 3       # 1st mortgage up to 2/3 of the purchase price
REPAYMENT_YEARS = 15               # 2nd mortgage repaid within 15 years ...
RETIREMENT_AGE = 65                # ... but at the latest by retirement

# --- Assumptions cost comparison ---
COMPARISON_YEARS = 15              # = longest fixed term (FIXED_15)
RATE_SCENARIOS = {"falling": -0.25, "stable": 0.0, "rising": 0.25}   # change in percentage points per year
FIXED_TERMS = {"FIXED_3": 3, "FIXED_10": 10, "FIXED_15": 15}

# Floor for fixed-rate mortgages at renewal (in %): even if rates fall sharply, the bank always
# charges its margin. Even in the negative-rate period 2019–2021 the SNB average for new
# fixed-rate mortgages never fell below about 1.1 % (5 years) / 1.27 % (10 years).
MIN_FIXED_RATE = 1.0


def calculate_purchase_costs(purchase_price):
    return purchase_price * PURCHASE_COST_RATE


def calculate_mortgage(purchase_price, equity_for_purchase):
    mortgage = max(0, purchase_price - equity_for_purchase)
    return mortgage, mortgage / purchase_price


def split_mortgage(purchase_price, mortgage):
    first_mortgage = min(mortgage, purchase_price * FIRST_MORTGAGE_LIMIT)
    return first_mortgage, max(0, mortgage - first_mortgage)


def calculate_amortisation(second_mortgage, age):
    years = max(1, min(REPAYMENT_YEARS, RETIREMENT_AGE - age))
    return second_mortgage / years, years


def calculate_imputed_annual_costs(mortgage, amortisation, purchase_price):
    return mortgage * CALCULATED_INTEREST_RATE + amortisation + purchase_price * MAINTENANCE_RATE


def determine_affordability(mortgage_ratio, hard_equity, purchase_price, cost_ratio):
    if mortgage_ratio > MAX_MORTGAGE_RATIO:
        return "red", "Insufficient equity: after purchase costs, at least 20% of the purchase price is usually required."
    if hard_equity < purchase_price * MIN_HARD_EQUITY_RATIO:
        return "red", "Insufficient non-pension-fund equity: at least 10% of the purchase price is usually required after purchase costs."
    if cost_ratio <= MAX_AFFORDABILITY_RATIO:
        return "green", "Affordable under the model assumptions."
    if cost_ratio <= WARNING_AFFORDABILITY_RATIO:
        return "yellow", "Borderline: housing costs are slightly above one third of gross income."
    return "red", "Not affordable under the model assumptions: housing costs exceed one third of gross income."


def calculate_affordability(user, age):
    price = user["purchase_price"]
    purchase_costs = calculate_purchase_costs(price)
    equity_for_purchase = user["equity"] - purchase_costs
    # Purchase costs are deducted from the hard equity: pension fund money is paid directly to
    # the bank or seller and may not be used e.g. for notary fees
    # (source: fact sheet on WEF advance withdrawal, Bernische Pensionskasse).
    hard_equity = user["equity"] - user["pension_fund_withdrawal"] - purchase_costs
    mortgage, mortgage_ratio = calculate_mortgage(price, equity_for_purchase)
    first_mortgage, second_mortgage = split_mortgage(price, mortgage)
    amortisation, amortisation_years = calculate_amortisation(second_mortgage, age)
    annual_costs = calculate_imputed_annual_costs(mortgage, amortisation, price)
    cost_ratio = annual_costs / user["gross_annual_income"]
    traffic_light, message = determine_affordability(mortgage_ratio, hard_equity, price, cost_ratio)
    return {"purchase_costs": purchase_costs, "hard_equity": hard_equity, "mortgage": mortgage,
            "mortgage_ratio": mortgage_ratio, "first_mortgage": first_mortgage, "second_mortgage": second_mortgage,
            "annual_amortisation": amortisation, "amortisation_years": amortisation_years,
            "imputed_annual_costs": annual_costs, "imputed_monthly_costs": annual_costs / 12,
            "affordability_ratio": cost_ratio, "traffic_light": traffic_light, "message": message}


def saron_rate_path(start_rate, annual_change, years):
    # The 0 % floor only applies to the value written into the path, not to the path itself:
    # starting at -0.04 %, "rising" gives 0, 0.21, 0.46 ... (not 0, 0.25, 0.50).
    path, rate = [], start_rate
    for _ in range(years):
        path.append(max(0, rate))
        rate += annual_change
    return path


def fixed_rate_path(start_rate, term, annual_change, years):
    path, rate = [], start_rate
    for year in range(years):
        if year > 0 and year % term == 0:
            # renewal at the new market rate, but never below MIN_FIXED_RATE
            rate = max(MIN_FIXED_RATE, start_rate + annual_change * year)
        path.append(rate)
    return path


def mortgage_balance_path(mortgage, amortisation, floor, years):
    path, balance = [], mortgage
    for _ in range(years):
        path.append(balance)
        balance = max(floor, balance - amortisation)
    return path


def strategy_interest_costs(balances, tranches, rates, saron_margin, annual_change):
    years = len(balances)
    costs = [0.0] * years
    for product, share in tranches.items():
        if product == "SARON":
            path = saron_rate_path(rates["SARON"], annual_change, years)
            margin = saron_margin
        else:
            path = fixed_rate_path(rates[product], FIXED_TERMS[product], annual_change, years)
            margin = 0
        for year in range(years):
            costs[year] += balances[year] * share * (path[year] + margin) / 100
    return costs


def compare_strategies(strategies, balances, rates, saron_margin):
    comparison = {}
    for strategy in strategies:
        comparison[strategy["name"]] = {
            scenario: sum(strategy_interest_costs(balances, strategy["tranches"], rates, saron_margin, change))
            for scenario, change in RATE_SCENARIOS.items()
        }
    return comparison


def calculate(data):
    user = data["user"]
    age = CURRENT_YEAR - user["birth_year"]
    affordability = calculate_affordability(user, age)
    balances = mortgage_balance_path(affordability["mortgage"], affordability["annual_amortisation"],
                                     affordability["first_mortgage"], COMPARISON_YEARS)
    comparison = compare_strategies(user["strategies"], balances, data["market"]["rates"], user["saron_margin"])
    return {"affordability": affordability, "strategy_comparison": comparison, "years": COMPARISON_YEARS}
