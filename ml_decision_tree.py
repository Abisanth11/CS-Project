"""Decision tree: which mortgage strategy suits which user? (ML part of HypoKompass CH)

Idea (after the feedback of our lecturer): we do NOT forecast interest rates. Instead
  1. we create many synthetic users (age, horizon, risk tolerance, income change, ...),
  2. calculate every strategy for each of them on all rate scenarios of scenarios.py
     (35 historical + 1,000 simulated paths) and pick the most suitable one -> label,
  3. train a small decision tree on (user features -> best strategy).
The tree learns from our own simulation, so it does not "know" more than the simulation.
Its value is explainability: it turns 1,000 scenarios into a few readable rules, e.g.
"horizon <= 6 years and risk tolerance high -> All SARON", and shows which user
characteristics drive the decision (feature importance).

Which strategy is "the most suitable" (the label):
  - costs = interest over the user's horizon (+ early repayment penalty if the user sells
    while a fixed-rate tranche is still running)
  - score = (1 - w) * average costs + w * average of the worst 10 % of the scenarios (CVaR 90 %)
    with w depending on the risk tolerance (low: mostly the bad case counts, high: the average)
  - budget stress: share of scenarios in which the actual housing costs (interest +
    amortisation + maintenance) exceed 1/3 of the income in at least one year.
    Strategies above the limit of the risk profile are not eligible.
  - best strategy = lowest score among the eligible strategies

AI notice: created with Claude (Anthropic), October 2026. Checked by the team: [ ]
"""
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier, export_text

from calculation import COMPARISON_YEARS, FIXED_TERMS, MAINTENANCE_RATE, calculate_affordability, \
    compare_strategies, mortgage_balance_path
from evaluation import calculate_metrics, recommend_strategy
from input_data import CURRENT_YEAR, STANDARD_STRATEGIES, average_saron_margin, load_market_data
from scenarios import PRODUCTS, build_scenarios, tranche_rate_path

# --- Assumptions for the label ---
SCENARIO_KINDS = ("historical", "simulated")   # the trend lines are not used for training
RISK_LEVELS = ["low", "medium", "high"]        # same values as RISK_OPTIONS in input_data.py
# Weight of the bad case (CVaR) in the score: low risk tolerance -> the bad case counts most
RISK_WEIGHTS = {"low": 0.8, "medium": 0.5, "high": 0.1}
# Max. share of scenarios with budget stress that a user of this profile accepts
MAX_STRESS = {"low": 0.02, "medium": 0.05, "high": 0.10}
CVAR_LEVEL = 90                                # "bad case" = the worst 10 % of the scenarios
STRESS_RATIO = 1 / 3                           # actual housing costs > 1/3 of income = stress
INCOME_CHANGE_YEARS = 5                        # the expected income change happens within 5 years

# --- Synthetic users (ranges of the random profiles) ---
N_PROFILES = 3000
HORIZONS = [3, 5, 7, 10, 15]                   # years until the user plans to sell / refinance
AGE_RANGE = (25, 55)
PRICE_RANGE = (500_000, 2_000_000)
EQUITY_SHARE_RANGE = (0.20, 0.45)              # equity after purchase costs, share of the price
AFFORDABILITY_RANGE = (0.20, 0.38)             # imputed cost ratio: green and yellow light only
INCOME_CHANGE_RANGE = (-0.30, 0.30)            # e.g. -30 % (part-time, children) to +30 % (career)
MARGIN_RANGE = (0.60, 1.40)                    # SARON margin of the bank in pp
RANDOM_SEED = 42

# --- Decision tree ---
MAX_DEPTH = 4                                  # deeper trees fit better but are hard to read
MIN_SAMPLES_LEAF = 30                          # a rule must hold for at least 30 users
TEST_SHARE = 0.25

# Columns of the feature matrix, in this order
FEATURES = ["horizon_years", "risk_tolerance", "income_change_pct", "affordability_ratio",
            "loan_to_value", "saron_margin", "age"]
FEATURE_LABELS = {"horizon_years": "horizon (years)", "risk_tolerance": "risk tolerance",
                  "income_change_pct": "expected income change (%)",
                  "affordability_ratio": "imputed cost ratio (%)", "loan_to_value": "loan-to-value (%)",
                  "saron_margin": "SARON margin (pp)", "age": "age"}


# --- Step 1: prepare the scenarios once (the same for all users) ---

def prepare_engine(market, strategies=STANDARD_STRATEGIES, scenarios=None):
    """Turn the scenarios into numpy arrays, so one user takes milliseconds instead of seconds."""
    if scenarios is None:
        scenarios = build_scenarios(market["rates"])
    # Only historical and simulated paths; the 3 trend lines are no probability distribution
    scenarios = [s for s in scenarios if s["kind"] in SCENARIO_KINDS]
    years = COMPARISON_YEARS
    # Market rates as matrix per product: one row per scenario, one column per year
    market_rates = {p: np.array([s["rates"][p] for s in scenarios]) for p in PRODUCTS}
    prepared = []
    for strategy in strategies:
        # Rate actually paid per scenario and year, still WITHOUT the SARON margin:
        # the margin is added later per user (it is just "+ share * margin")
        rate = np.zeros((len(scenarios), years))
        locked = {}                            # fixed tranches: rate locked in each year
        for product, share in strategy["tranches"].items():
            path = np.array([tranche_rate_path(product, s["rates"][product], 0.0, years) for s in scenarios])
            rate += share * path
            if product != "SARON":
                locked[product] = path
        prepared.append({"name": strategy["name"], "tranches": strategy["tranches"], "rate": rate,
                         "saron_share": strategy["tranches"].get("SARON", 0.0),
                         "penalty": _penalty_rates(strategy["tranches"], locked, market_rates, years)})
    return {"strategies": prepared, "market": market, "n_scenarios": len(scenarios)}


def _penalty_rates(tranches, locked, market_rates, years):
    """Early repayment penalty in % of the debt, if the user sells after h years (h = 1 .. years-1).

    Swiss banks charge roughly: remaining years of the contract * (contract rate - today's
    market rate), if positive. If rates have risen since the contract, there is no penalty.
    Simplification: the market rate of the same product is used for the comparison.
    """
    n_scenarios = len(market_rates["SARON"])
    penalty = {}
    for h in range(1, years):
        total = np.zeros(n_scenarios)          # strategies without fixed tranches: no penalty
        for product, path in locked.items():
            term = FIXED_TERMS[product]
            if h % term == 0:
                continue                       # the contract ends exactly now: no penalty
            remaining = term - h % term        # years left until the contract would end
            contract_rate = path[:, h - 1]     # rate of the running contract
            market_now = market_rates[product][:, h]
            total += tranches[product] * np.maximum(0, contract_rate - market_now) * remaining
        penalty[h] = total
    return penalty


# --- Step 2: evaluate all strategies for one user ---

def user_cash_flows(profile):
    """Debt, amortisation, maintenance and income per year of one user (lists of 15 values)."""
    age = profile["age"]
    user = {"purchase_price": profile["purchase_price"], "equity": profile["equity"],
            "pension_fund_withdrawal": 0, "gross_annual_income": profile["income"]}
    # Mortgage, 1st/2nd mortgage and amortisation from the existing calculation (calculation.py)
    affordability = calculate_affordability(user, age)
    balances = mortgage_balance_path(affordability["mortgage"], affordability["annual_amortisation"],
                                     affordability["first_mortgage"], COMPARISON_YEARS)
    # Amortisation actually paid each year: stops when only the 1st mortgage is left
    floor = affordability["first_mortgage"]
    amortisation = [min(affordability["annual_amortisation"], b - floor) for b in balances]
    # Income grows / shrinks linearly over INCOME_CHANGE_YEARS, then stays at the new level
    income = [profile["income"] * (1 + profile["income_change"] * min(t, INCOME_CHANGE_YEARS) / INCOME_CHANGE_YEARS)
              for t in range(COMPARISON_YEARS)]
    return {"affordability": affordability, "balances": np.array(balances),
            "amortisation": np.array(amortisation), "income": np.array(income),
            "maintenance": profile["purchase_price"] * MAINTENANCE_RATE}


def evaluate_strategies(engine, profile):
    """Score, costs and budget stress of every strategy for one user."""
    flows = user_cash_flows(profile)
    h = profile["horizon"]
    balances = flows["balances"]
    results = []
    for strategy in engine["strategies"]:
        # Rate per scenario and year incl. the user's SARON margin
        rate = strategy["rate"] + strategy["saron_share"] * profile["saron_margin"]
        # Interest per scenario and year, only for the years the user keeps the mortgage
        interest = rate[:, :h] * balances[:h] / 100
        total = interest.sum(axis=1)
        # Selling before the end of the comparison: early repayment penalty on the remaining debt
        if h < COMPARISON_YEARS:
            total = total + strategy["penalty"][h] * balances[h] / 100
        # Budget stress: actual housing costs above 1/3 of the income in at least one year
        housing = interest + flows["amortisation"][:h] + flows["maintenance"]
        stressed = (housing > STRESS_RATIO * flows["income"][:h]).any(axis=1)
        # CVaR 90 %: average of the most expensive 10 % of the scenarios
        bad_case = total[total >= np.percentile(total, CVAR_LEVEL)].mean()
        w = RISK_WEIGHTS[profile["risk_tolerance"]]
        results.append({"name": strategy["name"], "mean": float(total.mean()), "cvar": float(bad_case),
                        "score": float((1 - w) * total.mean() + w * bad_case),
                        "stress": float(stressed.mean())})
    return results


def best_strategy(results, risk_tolerance):
    """Index of the most suitable strategy: lowest score among those within the stress limit."""
    eligible = [i for i, r in enumerate(results) if r["stress"] <= MAX_STRESS[risk_tolerance]]
    if eligible:
        return min(eligible, key=lambda i: results[i]["score"])
    # No strategy is within the limit: take the one with the least budget stress
    return min(range(len(results)), key=lambda i: (results[i]["stress"], results[i]["score"]))


# --- Step 3: synthetic users and training data ---

def random_profiles(n=N_PROFILES, seed=RANDOM_SEED):
    """n random but realistic users (only green or yellow affordability light)."""
    rng = np.random.default_rng(seed)
    profiles = []
    for _ in range(n):
        price = rng.uniform(*PRICE_RANGE)
        # Equity = share of the price + 3 % purchase costs (paid on top, see calculation.py)
        equity = price * (rng.uniform(*EQUITY_SHARE_RANGE) + 0.03)
        profile = {"age": int(rng.integers(AGE_RANGE[0], AGE_RANGE[1] + 1)), "purchase_price": price,
                   "equity": equity, "horizon": int(rng.choice(HORIZONS)),
                   "risk_tolerance": str(rng.choice(RISK_LEVELS)),
                   "income_change": rng.uniform(*INCOME_CHANGE_RANGE),
                   "saron_margin": rng.uniform(*MARGIN_RANGE)}
        # Income is chosen so that the imputed cost ratio (5 % rate) lies in the target range
        affordability = calculate_affordability({**profile, "gross_annual_income": 1,
                                                 "pension_fund_withdrawal": 0}, profile["age"])
        profile["income"] = affordability["imputed_annual_costs"] / rng.uniform(*AFFORDABILITY_RANGE)
        profiles.append(profile)
    return profiles


def features(profile):
    """One row of the feature matrix (same order as FEATURES)."""
    affordability = calculate_affordability({"purchase_price": profile["purchase_price"],
                                             "equity": profile["equity"], "pension_fund_withdrawal": 0,
                                             "gross_annual_income": profile["income"]}, profile["age"])
    return [profile["horizon"], RISK_LEVELS.index(profile["risk_tolerance"]),
            profile["income_change"] * 100, affordability["affordability_ratio"] * 100,
            affordability["mortgage_ratio"] * 100, profile["saron_margin"], profile["age"]]


def build_training_data(engine, profiles):
    """Feature matrix X, labels y (strategy index) and all scores (for the evaluation)."""
    X, y, scores, stress = [], [], [], []
    for profile in profiles:
        results = evaluate_strategies(engine, profile)
        X.append(features(profile))
        y.append(best_strategy(results, profile["risk_tolerance"]))
        scores.append([r["score"] for r in results])
        stress.append([r["stress"] > MAX_STRESS[profile["risk_tolerance"]] for r in results])
    return np.array(X), np.array(y), np.array(scores), np.array(stress)


# --- Step 4: train and evaluate the tree ---

def old_rule_choice(engine, profile):
    """Baseline: what the app recommends today (RISK_RULES in evaluation.py, 3 trend lines, 15 years)."""
    flows = user_cash_flows(profile)
    strategies = [{"name": s["name"], "tranches": s["tranches"]} for s in engine["strategies"]]
    comparison = compare_strategies(strategies, list(flows["balances"]), engine["market"]["rates"],
                                    profile["saron_margin"])
    name, _ = recommend_strategy(calculate_metrics(comparison, COMPARISON_YEARS), profile["risk_tolerance"])
    return [s["name"] for s in strategies].index(name)


def regret(choices, scores):
    """Average extra score in CHF compared with the best strategy (0 = always the best one)."""
    rows = np.arange(len(choices))
    return float((scores[rows, choices] - scores.min(axis=1)).mean())


def train_model(market=None, n_profiles=N_PROFILES, max_depth=MAX_DEPTH, seed=RANDOM_SEED):
    """Train the tree and evaluate it on test users it has never seen. Returns a 'bundle' dict."""
    market = market or load_market_data()
    engine = prepare_engine(market)
    profiles = random_profiles(n_profiles, seed)
    X, y, scores, stress = build_training_data(engine, profiles)
    # Split the users: 75 % for training, 25 % only for testing
    idx_train, idx_test = train_test_split(np.arange(len(y)), test_size=TEST_SHARE, random_state=seed)
    tree = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=MIN_SAMPLES_LEAF, random_state=seed)
    tree.fit(X[idx_train], y[idx_train])
    predicted = tree.predict(X[idx_test])
    # Baselines: always the most frequent strategy, and the current rule of the app
    majority = np.full(len(idx_test), np.bincount(y[idx_train]).argmax())
    old_rule = np.array([old_rule_choice(engine, profiles[i]) for i in idx_test])
    names = [s["name"] for s in engine["strategies"]]

    def report(choices):
        rows = np.arange(len(idx_test))
        return {"accuracy": float((choices == y[idx_test]).mean()),
                "regret_chf": regret(choices, scores[idx_test]),
                "over_stress_limit": float(stress[idx_test][rows, choices].mean())}

    metrics = {"tree": report(predicted), "majority": report(majority), "old_rule": report(old_rule),
               "label_share": {names[k]: float((y == k).mean()) for k in range(len(names))},
               "feature_importance": dict(zip(FEATURES, tree.feature_importances_.round(3).tolist())),
               "n_train": len(idx_train), "n_test": len(idx_test), "n_scenarios": engine["n_scenarios"]}
    return {"tree": tree, "engine": engine, "names": names, "metrics": metrics,
            "data": {"X": X, "y": y, "scores": scores, "stress": stress, "train": idx_train, "test": idx_test}}


def depth_table(bundle, depths=range(1, 9)):
    """Test accuracy and regret for different tree depths (to justify MAX_DEPTH)."""
    d = bundle["data"]
    rows = []
    for depth in depths:
        tree = DecisionTreeClassifier(max_depth=depth, min_samples_leaf=MIN_SAMPLES_LEAF, random_state=RANDOM_SEED)
        tree.fit(d["X"][d["train"]], d["y"][d["train"]])
        predicted = tree.predict(d["X"][d["test"]])
        rows.append({"depth": depth, "leaves": int(tree.get_n_leaves()),
                     "accuracy": float((predicted == d["y"][d["test"]]).mean()),
                     "regret_chf": regret(predicted, d["scores"][d["test"]])})
    return rows


# --- Step 5: recommendation and explanation for a real user ---

def profile_from_user(user, horizon=None, income_change=None):
    """Convert the user dict of input_data.py / input_page.py into a profile for the tree.

    Horizon and income change come from block C of the input ("horizon_years",
    "income_change"); they can be overridden here, e.g. to compare two horizons.
    """
    if horizon is None:
        horizon = user.get("horizon_years", COMPARISON_YEARS)     # older inputs: whole comparison
    if income_change is None:
        income_change = user.get("income_change", 0.0)            # older inputs: no change
    return {"age": CURRENT_YEAR - user["birth_year"], "purchase_price": user["purchase_price"],
            "equity": user["equity"], "income": user["gross_annual_income"], "horizon": int(horizon),
            "risk_tolerance": user["risk_tolerance"], "income_change": income_change,
            "saron_margin": user["saron_margin"]}


def _condition_text(feature, threshold, goes_left):
    """One tree split as readable text, e.g. 'horizon (years) <= 6'."""
    if feature == "risk_tolerance":
        # The tree splits the coded values 0/1/2 at 0.5 or 1.5
        if threshold < 1:
            return "risk tolerance is low" if goes_left else "risk tolerance is medium or high"
        return "risk tolerance is low or medium" if goes_left else "risk tolerance is high"
    sign = "<=" if goes_left else ">"
    return f"{FEATURE_LABELS[feature]} {sign} {threshold:.1f}"


def _decided_nodes(tree):
    """Nodes below which every leaf predicts the same strategy.

    sklearn sometimes splits a node although both sides end with the same strategy (the split
    only makes the leaves "purer"). For the explanation such splits are useless, so we stop there.
    """
    t = tree.tree_
    classes = {}                               # node -> set of strategies predicted below it

    def collect(node):
        if t.children_left[node] == t.children_right[node]:
            classes[node] = {int(np.argmax(t.value[node]))}      # leaf: its own prediction
        else:
            classes[node] = collect(t.children_left[node]) | collect(t.children_right[node])
        return classes[node]

    collect(0)                                 # 0 = root of the tree
    return {node for node, found in classes.items() if len(found) == 1}


def explain(bundle, profile):
    """The rules on the way from the root of the tree to the leaf of this user."""
    tree = bundle["tree"].tree_
    decided = _decided_nodes(bundle["tree"])
    x = np.array([features(profile)])
    rules = []
    # decision_path: the nodes that this user passes through, from the root downwards
    for node in bundle["tree"].decision_path(x).indices:
        if node in decided:
            break                              # the strategy is already fixed: no more rules needed
        feature = FEATURES[tree.feature[node]]
        threshold = tree.threshold[node]
        rules.append(_condition_text(feature, threshold, x[0, tree.feature[node]] <= threshold))
    return rules


def recommend(bundle, profile):
    """Tree recommendation + probabilities + explanation, and the exact simulation result."""
    x = np.array([features(profile)])
    probabilities = bundle["tree"].predict_proba(x)[0]
    classes = bundle["tree"].classes_          # strategies that occur in the training labels
    results = evaluate_strategies(bundle["engine"], profile)
    exact = best_strategy(results, profile["risk_tolerance"])
    return {"strategy": bundle["names"][int(bundle["tree"].predict(x)[0])],
            "probabilities": {bundle["names"][c]: float(p) for c, p in zip(classes, probabilities)},
            "rules": explain(bundle, profile),
            "exact_strategy": bundle["names"][exact], "details": results}


def tree_as_text(bundle, full=False):
    """The tree as indented text (e.g. for the README or the presentation).

    By default, splits after which the strategy no longer changes are left out (see
    _decided_nodes); full=True shows the original sklearn output.
    """
    if full:
        text = export_text(bundle["tree"], feature_names=FEATURES)
        # Leaves show 'class: 2'; replace the number by the strategy name
        for k, name in enumerate(bundle["names"]):
            text = text.replace(f"class: {k}\n", f"class: {name}\n")
        return text
    t = bundle["tree"].tree_
    decided = _decided_nodes(bundle["tree"])
    lines = []

    def write(node, depth):
        indent = "|   " * depth
        if node in decided:
            # Same strategy everywhere below: print it as one leaf, with the number of training users
            lines.append(f"{indent}--> {bundle['names'][int(np.argmax(t.value[node]))]}"
                         f"  ({int(t.n_node_samples[node])} users)")
            return
        feature = FEATURES[t.feature[node]]
        for child, goes_left in ((t.children_left[node], True), (t.children_right[node], False)):
            lines.append(f"{indent}if {_condition_text(feature, t.threshold[node], goes_left)}:")
            write(child, depth + 1)

    write(0, 0)
    return "\n".join(lines)


if __name__ == "__main__":
    # Demo: python ml_decision_tree.py
    market = load_market_data()
    bundle = train_model(market)
    m = bundle["metrics"]
    print(f"{market['source']} · {m['n_scenarios']} scenarios · {m['n_train']} training / {m['n_test']} test users\n")
    print("Labels (share of users per best strategy):")
    for name, share in m["label_share"].items():
        print(f"  {name:36} {share:6.1%}")
    print("\nTest users              accuracy   regret (CHF)   above stress limit")
    for key, label in (("tree", "Decision tree"), ("old_rule", "Current app rule"), ("majority", "Always most frequent")):
        r = m[key]
        print(f"  {label:22} {r['accuracy']:7.1%}   {r['regret_chf']:12,.0f}   {r['over_stress_limit']:8.1%}")
    print("\nTree depth   leaves   accuracy   regret (CHF)")
    for row in depth_table(bundle):
        print(f"  {row['depth']:5}   {row['leaves']:6}   {row['accuracy']:8.1%}   {row['regret_chf']:12,.0f}")
    print("\nFeature importance:")
    for name, value in sorted(m["feature_importance"].items(), key=lambda item: -item[1]):
        print(f"  {FEATURE_LABELS[name]:30} {value:.3f}")
    print("\n" + tree_as_text(bundle))
    # Lea from the project idea, once with a long and once with a short horizon
    lea = {"purchase_price": 850_000, "equity": 200_000, "gross_annual_income": 150_000,
           "birth_year": CURRENT_YEAR - 28, "risk_tolerance": "medium",
           "saron_margin": average_saron_margin(market)}
    for horizon in (15, 5):
        result = recommend(bundle, profile_from_user(lea, horizon=horizon))
        print(f"Lea, horizon {horizon} years: tree -> {result['strategy']} (exact simulation: {result['exact_strategy']})")
        for rule in result["rules"]:
            print(f"   because {rule}")

