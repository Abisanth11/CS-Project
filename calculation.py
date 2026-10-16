"""Mortgage affordability and interest-cost calculations."""
from input_data import CURRENT_YEAR

CALCULATED_INTEREST_RATE = 0.05
MAINTENANCE_RATE = 0.01
PURCHASE_COST_RATE = 0.03
MAX_AFFORDABILITY_RATIO = 1 / 3
WARNING_AFFORDABILITY_RATIO = 0.38
MAX_MORTGAGE_RATIO = 0.80
MIN_HARD_EQUITY_RATIO = 0.10
FIRST_MORTGAGE_LIMIT = 2 / 3
REPAYMENT_YEARS = 15
RETIREMENT_AGE = 65
COMPARISON_YEARS = 15
RATE_SCENARIOS = {"falling": -0.25, "stable": 0.0, "rising": 0.25}
FIXED_TERMS = {"FIXED_3": 3, "FIXED_10": 10, "FIXED_15": 15}


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
    path, rate = [], start_rate
    for _ in range(years):
        path.append(max(0, rate))
        rate += annual_change
    return path


def fixed_rate_path(start_rate, term, annual_change, years):
    path, rate = [], start_rate
    for year in range(years):
        if year > 0 and year % term == 0:
            rate = max(0, start_rate + annual_change * year)
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
