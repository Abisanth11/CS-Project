"""Interpret results and display a console report."""
from input_data import format_chf
from calculation import MAINTENANCE_RATE

SCENARIOS = ["falling", "stable", "rising"]
RISK_RULES = {
    "low": ("spread", "Predictability matters to you, so the preferred strategy minimises fluctuations in interest costs."),
    "medium": ("rising", "You want a balance, so the preferred strategy has the lowest costs when interest rates rise."),
    "high": ("stable", "You accept fluctuations, so the preferred strategy has the lowest costs when rates remain stable."),
}


def calculate_metrics(comparison, years):
    metrics = {}
    for name, costs in comparison.items():
        metrics[name] = {"falling": costs["falling"], "stable": costs["stable"], "rising": costs["rising"],
                         "spread": costs["rising"] - costs["falling"], "monthly_average": costs["stable"] / (years * 12)}
    return metrics


def find_best(metrics, metric):
    return min(metrics, key=lambda name: metrics[name][metric]) if metrics else ""


def recommend_strategy(metrics, risk_tolerance):
    metric, explanation = RISK_RULES[risk_tolerance]
    return find_best(metrics, metric), explanation


def is_cheapest_in_every_scenario(metrics, name):
    return all(metrics[name][scenario] <= metrics[other][scenario] for scenario in SCENARIOS for other in metrics)


def compare_with_rent(user, metric, affordability):
    if user["monthly_rent"] <= 0:
        return None
    monthly_interest = metric["monthly_average"]
    monthly_maintenance = user["purchase_price"] * MAINTENANCE_RATE / 12
    ownership_cost = monthly_interest + monthly_maintenance
    return {"rent": user["monthly_rent"], "monthly_interest": monthly_interest,
            "monthly_maintenance": monthly_maintenance, "ownership_cost": ownership_cost,
            "difference": user["monthly_rent"] - ownership_cost,
            "monthly_amortisation": affordability["annual_amortisation"] / 12}


def evaluate(data, results):
    user = data["user"]
    metrics = calculate_metrics(results["strategy_comparison"], results["years"])
    cheapest = find_best(metrics, "stable")
    safest = find_best(metrics, "spread")
    recommendation, explanation = recommend_strategy(metrics, user["risk_tolerance"])
    return {"metrics": metrics, "cheapest_strategy": cheapest, "lowest_risk_strategy": safest,
            "cost_of_safety": metrics[safest]["stable"] - metrics[cheapest]["stable"],
            "recommended_strategy": recommendation, "recommendation_explanation": explanation,
            "dominates": is_cheapest_in_every_scenario(metrics, cheapest),
            "affordable": results["affordability"]["traffic_light"] != "red",
            "rent_comparison": compare_with_rent(user, metrics[recommendation], results["affordability"])}


def _display_affordability(result):
    print("\n=== 1. Can you afford it? ===")
    print("Purchase costs:       ", format_chf(result["purchase_costs"]), "(one-off)")
    print("Mortgage:             ", format_chf(result["mortgage"]), f"(loan-to-value {result['mortgage_ratio']:.1%})")
    print("Annual amortisation:  ", format_chf(result["annual_amortisation"]), "over", result["amortisation_years"], "years")
    print("Imputed monthly costs:", format_chf(result["imputed_monthly_costs"]))
    print("Share of gross income:", f"{result['affordability_ratio']:.1%}")
    print("Assessment:           ", result["traffic_light"].upper(), "—", result["message"])


def _display_strategies(metrics, recommendation, years, source):
    print(f"\n=== 2. Strategy cost comparison over {years} years (source: {source}) ===")
    for name, values in metrics.items():
        marker = "  <-- recommended" if name == recommendation else ""
        print(f"\n{name}{marker}")
        print("  Costs if rates stay stable:", format_chf(values["stable"]), "(average", format_chf(values["monthly_average"]), "/month)")
        print("  Range:                   ", format_chf(values["falling"]), "to", format_chf(values["rising"]))
        print("  Interest-rate risk:      ", format_chf(values["spread"]))


def _display_assessment(assessment, risk, saron_rate):
    print("\n=== 3. Assessment ===")
    if not assessment["affordable"]:
        print("Warning: this financing is not affordable under the model assumptions. Review your equity or purchase price first.")
    print("Risk tolerance:", risk)
    print(assessment["recommendation_explanation"])
    print("Recommended strategy:", assessment["recommended_strategy"])
    if assessment["dominates"]:
        print(f"'{assessment['cheapest_strategy']}' is cheapest in all three interest-rate scenarios.")
    else:
        print("Cheapest with stable rates:", assessment["cheapest_strategy"])
    if assessment["lowest_risk_strategy"] != assessment["cheapest_strategy"]:
        print("Lowest fluctuation:", assessment["lowest_risk_strategy"])
        print("Additional cost of this lower risk with stable rates:", format_chf(assessment["cost_of_safety"]))
    if saron_rate <= 0:
        print("Note: SARON is at or below 0% and is floored at 0% in the model.")


def _display_trend(label, trend):
    if not trend:
        print(label + ": no data available (update the SNB data first).")
        return
    change = trend.get("change_pct", trend.get("aenderung_pct"))
    annual = trend.get("per_year_pct", trend.get("pro_jahr_pct"))
    start = trend.get("from", trend.get("von", "?"))
    end = trend.get("to", trend.get("bis", "?"))
    print(f"{label}: {start}–{end}: {change:+.1f}% ({annual:.1f}% per year)")


def _display_buy_vs_rent(comparison, recommendation, real_estate):
    print("\n=== 4. Buy or rent? ===")
    if comparison:
        print(f"As a homeowner using '{recommendation}' (stable rates):")
        print("  Average interest:", format_chf(comparison["monthly_interest"]), "+ maintenance", format_chf(comparison["monthly_maintenance"]), "=", format_chf(comparison["ownership_cost"]), "per month")
        print("  Current rent:     ", format_chf(comparison["rent"]), "per month")
        if comparison["difference"] >= 0:
            print("  Home ownership is approximately", format_chf(comparison["difference"]), "cheaper per month.")
        else:
            print("  Home ownership is approximately", format_chf(-comparison["difference"]), "more expensive per month.")
        if comparison["monthly_amortisation"] > 0:
            print("  Amortisation adds", format_chf(comparison["monthly_amortisation"]), "per month; this builds equity rather than being a pure expense.")
        print("  Excludes foregone returns on equity and possible property appreciation.")
    else:
        print("No rent provided; skipping the direct comparison.")
    print("\nMarket context (SNB / Wüest Partner):")
    _display_trend("  Owner-occupied apartment prices", real_estate.get("apartments"))
    _display_trend("  Asking rents", real_estate.get("rents"))


def display_evaluation(data, results, assessment):
    market = data["market"]
    _display_affordability(results["affordability"])
    _display_strategies(assessment["metrics"], assessment["recommended_strategy"], results["years"], market["source"])
    _display_assessment(assessment, data["user"]["risk_tolerance"], market["rates"]["SARON"])
    _display_buy_vs_rent(assessment["rent_comparison"], assessment["recommended_strategy"], market["real_estate"])
    print("\nNot financial advice: this is a model based on historical SNB data and simplified scenarios.")
