"""Console entry point for HypoKompass CH."""
import input_data
import calculation
import evaluation


def main():
    print("=== HypoKompass CH — financing your first home ===")
    print("Disclaimer: this is a model calculation, not financial advice.")
    data = input_data.sample_data() if input_data.ask_yes_no("Use sample data?") else input_data.collect_inputs()
    if data.get("user"):
        input_data.show_summary(data["user"])
    results = calculation.calculate(data)
    assessment = evaluation.evaluate(data, results)
    evaluation.display_evaluation(data, results, assessment)


if __name__ == "__main__":
    main()
