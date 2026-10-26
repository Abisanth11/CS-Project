"""Interest-rate scenarios from SNB history (basis for the cost distribution and the ML part).

Instead of three straight lines (-0.25 / 0 / +0.25 pp per year) every strategy is calculated
on many rate paths:
  - historical: "what if the next 15 years repeat the rate changes from 1989 to 2003?"
  - simulated: block bootstrap of historical annual changes (1,000 paths)
  - trend: the three existing scenarios from calculation.py, in the same format

A scenario is a dict {"name", "kind", "rates"} where rates[product][t] is the market rate in %
for a new contract in year t (t = 0 is today). Fixed-rate tranches lock in rates[product][0]
and are renewed at rates[product][t]; SARON tranches pay rates["SARON"][t] every year.

Data (annual averages of SNB series):
  - 1976–2008: "VARIABEL" (variable mortgage rate) as a proxy for the general rate level;
    all products move in parallel. After 2008 this series hardly moves any more
    (old variable mortgages are not adjusted), so it is no longer used from then on.
  - from 2008: the real series per product: FEST_3 / FEST_10 / FEST_15 and the SARON.
    These also capture non-parallel moves, e.g. the 2022 shock (SARON -0.7 % -> 1.7 %).
Only the *changes* are taken from history; every path starts at today's rates.
Market floor: 1976–2025 contains a long decline from 7.8 % to 2.6 %. Repeated from today's level
it would push the SARON to about -4 %, so no path goes below the lowest annual average of its
product (SARON about -0.7 %, fixed about 1.2–1.4 %); later rises start from that floor.
On top, the floors for costs (SARON >= 0 %, fixed renewal >= MIN_FIXED_RATE) apply as in
calculation.py.

AI notice: created with Claude (Anthropic), October 2026. Checked by the team: [ ]
"""
import numpy as np

# Reuse the assumptions of the cost comparison, so both files always calculate the same way
from calculation import COMPARISON_YEARS, FIXED_TERMS, MIN_FIXED_RATE, RATE_SCENARIOS

# The database is optional: without it, only the trend scenarios are available
try:
    from data import database as _database
except ImportError:
    _database = None

# Products the app compares (same keys as in input_data.py)
PRODUCTS = ["FIXED_3", "FIXED_10", "FIXED_15", "SARON"]
# Name of each fixed-rate product in the SNB table mortgage_rates
DB_SERIES = {"FIXED_3": "FEST_3", "FIXED_10": "FEST_10", "FIXED_15": "FEST_15"}
# Long series (since 1976) that stands in for all products before the product series exist
PROXY_SERIES = "VARIABEL"
SPLICE_YEAR = 2008            # first year whose change comes from the product series
SIMULATION_RUNS = 1000        # number of simulated paths
BLOCK_YEARS = 3               # bootstrap blocks keep multi-year rate cycles together
RANDOM_SEED = 42              # fixed seed: the same simulation every time the app runs


# --- Historical data ---

def _annual_means(rows):
    """[(period 'YYYY-..', value), ...] -> {year: mean}, only complete calendar years."""
    # Collect all values of the same year in one list: {1990: [7.1, 7.3, ...], ...}
    values = {}
    for period, value in rows:
        year = int(period[:4])                 # 'YYYY-MM' or 'YYYY-MM-DD' -> YYYY
        values.setdefault(year, []).append(value)
    # Average per year; incomplete years (e.g. the current one) are left out,
    # otherwise e.g. Jan–Aug would be compared with a full year
    means = {}
    for year, year_values in values.items():
        if len(year_values) >= 12:
            means[year] = sum(year_values) / len(year_values)
    return means


def load_annual_levels(con):
    """Annual average rate level per series: {"PROXY": {...}, "FIXED_3": {...}, ..., "SARON": {...}}."""
    def monthly(product):
        # Monthly mean values ('M') of one product from the SNB table, oldest first
        return con.execute("SELECT month, value FROM mortgage_rates WHERE product = ? AND stat = 'M' "
                           "ORDER BY month", (product,)).fetchall()

    # Proxy series (variable mortgage, since 1976)
    levels = {"PROXY": _annual_means(monthly(PROXY_SERIES))}
    # Fixed-rate series (since 2007-12)
    for product, series in DB_SERIES.items():
        levels[product] = _annual_means(monthly(series))
    # SARON is stored daily: monthly averages first, so every month weighs the same
    # (months with many trading days would otherwise count more)
    saron_monthly = con.execute("SELECT substr(date, 1, 7), AVG(value) FROM rates_daily "
                                "WHERE series = 'SARON' GROUP BY substr(date, 1, 7)").fetchall()
    levels["SARON"] = _annual_means(saron_monthly)
    return levels


def market_floors(levels):
    """Lowest annual average rate per product (pp), used as lower bound for the paths."""
    # Annual averages instead of daily values: a single extreme day
    # (SARON -1.69 % in January 2015) should not become the floor
    floors = {}
    for product in PRODUCTS:
        if levels.get(product):
            floors[product] = min(levels[product].values())
    return floors


def annual_changes(levels):
    """Spliced annual rate changes in pp: [(year, {product: change}), ...], sorted by year.

    The change of year Y is level(Y) - level(Y-1). Up to SPLICE_YEAR - 1 all products take
    the change of the proxy series, from SPLICE_YEAR on each product its own change. If a
    product series is not complete yet (fixed rates start 2007-12, SARON 2009-08), the proxy
    change is used for that year, so there is no gap in the history.
    """
    def change(series, year):
        # Change from the previous year, or None if one of the two years is missing
        if year in levels[series] and year - 1 in levels[series]:
            return levels[series][year] - levels[series][year - 1]
        return None

    changes = []
    for year in sorted(levels["PROXY"]):
        proxy = change("PROXY", year)
        if proxy is None:
            continue                           # first year of the data: no previous year
        if year < SPLICE_YEAR:
            # Before 2008: all products move by the same amount as the proxy series
            row = {product: proxy for product in PRODUCTS}
        else:
            # From 2008: each product its own change; if its series is still missing
            # for this year, fall back to the proxy
            row = {}
            for product in PRODUCTS:
                own = change(product, year)
                row[product] = proxy if own is None else own
        changes.append((year, row))
    return changes


# --- Scenario generation ---

def _path_from_changes(current_rates, change_rows, years, floors):
    """Start at today's rates, then add the changes year by year, never below the floor."""
    # Year 0 = today's market rates
    rates = {product: [current_rates[product]] for product in PRODUCTS}
    # Years 1 .. years-1: add one change per year
    for row in change_rows[:years - 1]:
        for product in PRODUCTS:
            # If today's rate is already below the historical floor (possible for new data),
            # the floor is today's rate, so the path never jumps up in year 1
            floor = min(floors.get(product, float("-inf")), current_rates[product])
            new_rate = rates[product][-1] + row[product]
            # The floor is applied to the path itself: a later rise starts from the floor
            rates[product].append(max(floor, new_rate))
    return rates


def trend_scenarios(current_rates, years=COMPARISON_YEARS):
    """The three scenarios of calculation.py (constant change per year) in scenario format."""
    scenarios = []
    for name, change in RATE_SCENARIOS.items():
        # Straight line: rate in year t = today + change * t (no floor, exactly as in calculation.py)
        rates = {p: [current_rates[p] + change * t for t in range(years)] for p in PRODUCTS}
        scenarios.append({"name": f"Trend {name}", "kind": "trend", "rates": rates})
    return scenarios


def historical_scenarios(current_rates, changes, floors, years=COMPARISON_YEARS):
    """One scenario per historical start year in which a full window of changes exists."""
    scenarios = []
    # A path of 15 years needs 14 changes; slide that window over the history
    # (1978–1991, 1979–1992, ...) -> one scenario per window
    for start in range(len(changes) - (years - 1) + 1):
        window = changes[start:start + years - 1]
        first, last = window[0][0], window[-1][0]
        rows = [row for _, row in window]      # drop the year, keep {product: change}
        scenarios.append({"name": f"History {first - 1}–{last}", "kind": "historical",
                          "rates": _path_from_changes(current_rates, rows, years, floors)})
    return scenarios


def simulated_scenarios(current_rates, changes, floors, runs=SIMULATION_RUNS, years=COMPARISON_YEARS,
                        block=BLOCK_YEARS, seed=RANDOM_SEED):
    """Block bootstrap: glue random blocks of consecutive historical years together.

    The changes are demeaned first: 1976–2025 rates fell on average (about -0.06 pp per year),
    which the simulation should not simply continue. All products of a year are drawn together,
    so their correlation is kept.
    """
    rows = [row for _, row in changes]
    # Subtract the average change per product -> on average the simulation neither rises nor falls
    means = {p: sum(row[p] for row in rows) / len(rows) for p in PRODUCTS}
    rows = [{p: row[p] - means[p] for p in PRODUCTS} for row in rows]
    rng = np.random.default_rng(seed)
    scenarios = []
    for run in range(runs):
        drawn = []
        # Draw random start years and take 3 consecutive years each time, until there are
        # enough changes for 15 years (a block keeps e.g. a 3-year rate rise together)
        while len(drawn) < years - 1:
            start = rng.integers(0, len(rows) - block + 1)
            drawn.extend(rows[start:start + block])
        scenarios.append({"name": f"Simulation {run + 1}", "kind": "simulated",
                          "rates": _path_from_changes(current_rates, drawn, years, floors)})
    return scenarios


def build_scenarios(current_rates, con=None, runs=SIMULATION_RUNS, years=COMPARISON_YEARS):
    """All scenarios. Without database only the trend scenarios are returned."""
    # The trend scenarios always work, even without data
    scenarios = trend_scenarios(current_rates, years)
    # Open the database ourselves if no connection was passed in
    close_connection = False
    if con is None and _database is not None:
        try:
            con, close_connection = _database.verbinde(), True
        except Exception:
            con = None
    if con is None:
        return scenarios
    # Read the history; close the connection again only if we opened it here
    try:
        levels = load_annual_levels(con)
    finally:
        if close_connection:
            con.close()
    changes, floors = annual_changes(levels), market_floors(levels)
    # Too little history (e.g. empty database): no historical / simulated paths
    if len(changes) < years:
        return scenarios
    historical = historical_scenarios(current_rates, changes, floors, years)
    simulated = simulated_scenarios(current_rates, changes, floors, runs, years)
    return scenarios + historical + simulated


# --- Costs on a rate path ---

def tranche_rate_path(product, market, saron_margin, years):
    """Rate in % that one tranche actually pays in each year (same rules as calculation.py)."""
    if product == "SARON":
        # SARON mortgage: market SARON of each year (never below 0 %) plus the bank's margin
        return [max(0, market[t]) + saron_margin for t in range(years)]
    # Fixed-rate mortgage: today's rate stays fixed for the whole term ...
    term, rate, path = FIXED_TERMS[product], market[0], []
    for t in range(years):
        # ... and is renewed at the market rate of that year when the term ends,
        # never below MIN_FIXED_RATE (the bank always charges its margin)
        if t > 0 and t % term == 0:
            rate = max(MIN_FIXED_RATE, market[t])
        path.append(rate)
    return path


def interest_costs_on_path(balances, tranches, scenario_rates, saron_margin):
    """Interest costs per year of one strategy on one scenario (same rules as calculation.py)."""
    years = len(balances)
    costs = [0.0] * years
    # A strategy consists of tranches, e.g. {"FIXED_10": 0.5, "SARON": 0.5}
    for product, share in tranches.items():
        path = tranche_rate_path(product, scenario_rates[product], saron_margin, years)
        # Interest of this tranche = remaining debt * share of the tranche * rate
        for t in range(years):
            costs[t] += balances[t] * share * path[t] / 100
    return costs


def cost_distribution(strategies, balances, scenarios, saron_margin):
    """Total interest costs: {strategy name: np.array with one value per scenario}."""
    distribution = {}
    for strategy in strategies:
        totals = []
        for scenario in scenarios:
            # Interest over all years of this scenario, summed up to one number
            yearly = interest_costs_on_path(balances, strategy["tranches"], scenario["rates"], saron_margin)
            totals.append(sum(yearly))
        distribution[strategy["name"]] = np.array(totals)
    return distribution


def summarize(costs):
    """Key figures of a cost distribution (CHF): typical, bad case and worst case."""
    return {"mean": float(np.mean(costs)),             # average over all scenarios
            "median": float(np.median(costs)),         # typical case: half of the scenarios are cheaper
            "p90": float(np.percentile(costs, 90)),    # bad case: only 10 % of the scenarios are worse
            "worst": float(np.max(costs)),             # most expensive scenario
            "best": float(np.min(costs)),              # cheapest scenario
            "std": float(np.std(costs))}               # spread = how uncertain the costs are


if __name__ == "__main__":
    # Demo with Lea from the project idea: python scenarios.py
    from calculation import calculate_affordability, mortgage_balance_path
    from input_data import CURRENT_YEAR, STANDARD_STRATEGIES, average_saron_margin, format_chf, load_market_data

    # Today's rates from the SNB database (or placeholders)
    market = load_market_data()
    lea = {"purchase_price": 850_000, "equity": 200_000, "pension_fund_withdrawal": 0,
           "gross_annual_income": 150_000, "birth_year": CURRENT_YEAR - 28}
    # Mortgage amount and amortisation from the existing affordability calculation
    affordability = calculate_affordability(lea, 28)
    # Remaining debt per year (falls with amortisation down to the 1st mortgage)
    balances = mortgage_balance_path(affordability["mortgage"], affordability["annual_amortisation"],
                                     affordability["first_mortgage"], COMPARISON_YEARS)
    scenarios = build_scenarios(market["rates"])
    margin = average_saron_margin(market)
    print(f"{market['source']} · {len(scenarios)} scenarios · SARON margin {margin:.2f} %\n")
    # One table for the historical and one for the simulated paths
    for kind in ("historical", "simulated"):
        subset = [s for s in scenarios if s["kind"] == kind]
        print(f"{kind.capitalize()} ({len(subset)} paths): interest costs over {COMPARISON_YEARS} years")
        for name, costs in cost_distribution(STANDARD_STRATEGIES, balances, subset, margin).items():
            k = summarize(costs)
            print(f"  {name:36} median {format_chf(k['median']):>13}   90 % {format_chf(k['p90']):>13}"
                  f"   worst {format_chf(k['worst']):>13}")
        print()
