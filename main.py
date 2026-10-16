# main.py
# Konsolen-Version von HypoKompass CH. Aufbau in drei Schritten:
#   1. Eingabedaten  (eingabe.py)
#   2. Berechnung    (berechnung.py)
#   3. Auswertung    (auswertung.py)
# Wird später durch die Streamlit-App (app.py) ersetzt.
#
# KI-Hinweis: Grundgerüst erstellt mit Claude (Anthropic), 09.10.2026.

import eingabe
import berechnung
import auswertung


def main():
    print("=== HypoKompass CH – dein erstes Eigenheim finanzieren ===")
    print("Hinweis: Keine Finanzierungsberatung. Zinsen: Durchschnittswerte der SNB.")

    # --- 1. Eingabedaten ---
    if eingabe.frage_ja_nein("Beispieldaten verwenden?"):
        daten = eingabe.beispiel_daten()
        eingabe.zeige_zusammenfassung(daten["nutzer"])
    else:
        daten = eingabe.erfasse_daten()

    # --- 2. Berechnung ---
    resultate = berechnung.berechne(daten)

    # --- 3. Auswertung ---
    ergebnis = auswertung.werte_aus(daten, resultate)
    auswertung.zeige_auswertung(daten, resultate, ergebnis)


if __name__ == "__main__":
    main()
