# auswertung.py
# Schritt 3 von 3: Auswertung und Einschätzung.
#
# Bekommt die Eingabedaten aus Schritt 1 und die Resultate aus Schritt 2.
#   Teil C: Auswerten  (C1 bis C5) – nur vergleichen und rechnen, kein print()
#   Teil D: Anzeigen               – gibt alles übersichtlich in der Konsole aus
# Die spätere Streamlit-App kann die Werte aus Teil C direkt anzeigen; Teil D braucht es dann nicht mehr.
#
# Wichtig: Die App gibt eine Einschätzung nach transparenten Regeln, keine Finanzberatung.
#
# KI-Hinweis: erstellt mit Claude (Anthropic), 12.10.2026. Regeln vom Team geprüft: [ ]

from eingabe import chf
from berechnung import NEBENKOSTEN_SATZ

SZENARIO_NAMEN = ["sinken", "stabil", "steigen"]

# Welche Kennzahl entscheidet, je nach Risikobereitschaft aus Schritt 1?
#   tief:   kleinste Spannweite            -> die Kosten schwanken am wenigsten
#   mittel: günstigste bei steigenden Zinsen -> gut abgesichert für den schlechten Fall
#   hoch:   günstigste bei stabilen Zinsen   -> tiefste erwartete Kosten
REGELN = {
    "tief": ("spannweite",
             "Dir ist Planbarkeit wichtig. Darum zählt die Strategie, deren Kosten am wenigsten schwanken."),
    "mittel": ("steigen",
               "Du suchst ein Gleichgewicht. Darum zählt die Strategie, die auch bei steigenden Zinsen am günstigsten ist."),
    "hoch": ("stabil",
             "Du nimmst Schwankungen in Kauf. Darum zählt die Strategie mit den tiefsten Kosten bei gleichbleibenden Zinsen."),
}


# =====================================================================
# Teil C: Auswerten
# =====================================================================

def berechne_kennzahlen(vergleich, jahre):
    """C1: Kennzahlen pro Strategie: Kosten je Szenario, Spannweite und Kosten pro Monat.

    Spannweite = Kosten bei steigenden minus Kosten bei sinkenden Zinsen = unser Mass für das Zinsrisiko.
    """
    kennzahlen = {}
    for name in vergleich:
        kosten = vergleich[name]
        kennzahlen[name] = {
            "sinken": kosten["sinken"],
            "stabil": kosten["stabil"],
            "steigen": kosten["steigen"],
            "spannweite": kosten["steigen"] - kosten["sinken"],
            "pro_monat": kosten["stabil"] / (jahre * 12),   # Durchschnitt bei stabilen Zinsen
        }
    return kennzahlen


def finde_beste(kennzahlen, kennzahl):
    """C2: Name der Strategie mit dem kleinsten Wert einer Kennzahl (z. B. "stabil" oder "spannweite")."""
    beste = ""
    bester_wert = 0
    for name in kennzahlen:
        wert = kennzahlen[name][kennzahl]
        if beste == "" or wert < bester_wert:
            beste = name
            bester_wert = wert
    return beste


def empfehle(kennzahlen, risiko):
    """C3: Strategie passend zur Risikobereitschaft, dazu die Begründung als Text."""
    kennzahl, begruendung = REGELN[risiko]
    return finde_beste(kennzahlen, kennzahl), begruendung


def ist_ueberall_guenstigst(kennzahlen, name):
    """C4: True, wenn die Strategie in allen drei Szenarien am wenigsten kostet."""
    for szenario in SZENARIO_NAMEN:
        for andere in kennzahlen:
            if kennzahlen[andere][szenario] < kennzahlen[name][szenario]:
                return False
    return True


def vergleiche_mit_miete(nutzer, kennzahl, tragbarkeit):
    """C5: Monatliche Wohnkosten als Eigentümer vs. heutige Miete (None, wenn keine Miete angegeben).

    Eigentum = durchschnittliche Zinsen (Szenario stabil) + Unterhalt 1 % des Kaufpreises pro Jahr.
    Die Amortisation zählt nicht als Kosten, sie ist Sparen (die Schuld sinkt).
    Nicht eingerechnet: entgangene Rendite auf den Eigenmitteln und eine mögliche Wertsteigerung.
    """
    if nutzer["miete"] <= 0:
        return None
    zinsen = kennzahl["pro_monat"]
    unterhalt = nutzer["kaufpreis"] * NEBENKOSTEN_SATZ / 12
    eigentum = zinsen + unterhalt
    return {
        "miete": nutzer["miete"],
        "zinsen": zinsen,
        "unterhalt": unterhalt,
        "eigentum": eigentum,
        "differenz": nutzer["miete"] - eigentum,   # positiv = Eigentum ist günstiger
        "amortisation": tragbarkeit["amortisation"] / 12,
    }


def werte_aus(daten, resultate):
    """Hauptfunktion von Teil C: führt C1 bis C5 aus und sammelt alles in einem Dictionary."""
    nutzer = daten["nutzer"]
    kennzahlen = berechne_kennzahlen(resultate["vergleich"], resultate["jahre"])     # C1

    guenstigste = finde_beste(kennzahlen, "stabil")                                  # C2
    sicherste = finde_beste(kennzahlen, "spannweite")
    empfehlung, begruendung = empfehle(kennzahlen, nutzer["risiko"])                 # C3

    return {
        "kennzahlen": kennzahlen,
        "guenstigste": guenstigste,
        "sicherste": sicherste,
        # Was die Sicherheit kostet: Mehrkosten der sichersten gegenüber der günstigsten (Zinsen stabil)
        "preis_sicherheit": kennzahlen[sicherste]["stabil"] - kennzahlen[guenstigste]["stabil"],
        "empfehlung": empfehlung,
        "begruendung": begruendung,
        "dominiert": ist_ueberall_guenstigst(kennzahlen, guenstigste),               # C4
        "tragbar": resultate["tragbarkeit"]["ampel"] != "rot",
        "wohnen": vergleiche_mit_miete(nutzer, kennzahlen[empfehlung],              # C5
                                       resultate["tragbarkeit"]),
    }


# =====================================================================
# Teil D: Anzeigen
# =====================================================================

def zeige_tragbarkeit(t):
    """Tragbarkeit mit Ampel."""
    print("\n=== 1. Kannst du dir das leisten? ===")
    print("Kaufnebenkosten: ", chf(t["kaufnebenkosten"]), "(einmalig, aus eigenem Geld)")
    print("Hypothek:        ", chf(t["hypothek"]), "(Belehnung", round(t["belehnung"] * 100, 1), "%)")
    print("Amortisation:    ", chf(t["amortisation"]), "pro Jahr über", t["amortisations_jahre"], "Jahre")
    print("Kosten pro Monat:", chf(t["kosten_monat"]), "(kalkulatorisch, wie die Bank rechnet)")
    print("Tragbarkeit:     ", round(t["quote"] * 100, 1), "% des Einkommens")
    print("Ampel:           ", t["ampel"].upper(), "-", t["meldung"])


def zeige_strategien(kennzahlen, empfehlung, jahre, quelle):
    """Zinskosten jeder Strategie mit Bandbreite und Spannweite."""
    print("\n=== 2. Was kostet dich welche Strategie? ===")
    print("Zinskosten über", jahre, "Jahre (Quelle:", quelle + ")")
    for name in kennzahlen:
        k = kennzahlen[name]
        markierung = ""
        if name == empfehlung:
            markierung = "   <-- passt zu dir"
        print("\n" + name + markierung)
        print("   Zinsen bleiben gleich:", chf(k["stabil"]), "(im Schnitt", chf(k["pro_monat"]), "pro Monat)")
        print("   Bandbreite:           ", chf(k["sinken"]), "bis", chf(k["steigen"]))
        print("   Zinsrisiko:           ", chf(k["spannweite"]), "(Spannweite)")


def zeige_einschaetzung(a, risiko, saron):
    """Einschätzung nach den Regeln in REGELN."""
    print("\n=== 3. Unsere Einschätzung ===")
    if not a["tragbar"]:
        print("Achtung: So ist die Finanzierung nicht tragbar (Ampel rot).")
        print("Kläre zuerst Eigenmittel oder Kaufpreis. Der Vergleich dient nur zur Orientierung.\n")

    print("Deine Risikobereitschaft:", risiko)
    print(a["begruendung"])
    print("-> Passende Strategie:", a["empfehlung"])

    print()
    if a["dominiert"]:
        print("'" + a["guenstigste"] + "' ist in allen drei Zinsszenarien am günstigsten.")
    else:
        print("Am günstigsten bei gleichbleibenden Zinsen:", a["guenstigste"])
    if a["sicherste"] != a["guenstigste"]:
        print("Am wenigsten Schwankung hat:", a["sicherste"] + ".")
        print("Diese Sicherheit kostet dich bei gleichbleibenden Zinsen", chf(a["preis_sicherheit"]), "mehr.")

    if saron <= 0:
        print("\nHinweis: Der SARON steht bei 0 % oder tiefer und wird nicht unter 0 % gerechnet.")
        print("Darum sind 'sinken' und 'stabil' beim SARON gleich.")


def zeige_entwicklung(text, entwicklung):
    """Eine Zeile zur Preisentwicklung, z. B. 'Eigentumswohnungen 2015–2025: +35.9 % (3.1 % pro Jahr)'."""
    if not entwicklung:   # None zählt in einer Bedingung als False (Unit 2)
        print(text + ": keine Daten (python -m data.update_data ausführen)")
        return
    vorzeichen = ""
    if entwicklung["aenderung_pct"] >= 0:
        vorzeichen = "+"
    print(text, entwicklung["von"] + "–" + entwicklung["bis"] + ":",
          vorzeichen + str(round(entwicklung["aenderung_pct"], 1)), "%",
          "(" + str(round(entwicklung["pro_jahr_pct"], 1)), "% pro Jahr)")


def zeige_kaufen_mieten(wohnen, empfehlung, immo):
    """Vergleich mit der heutigen Miete und Preisentwicklung (SNB-Cube plimoincha, Wüest Partner)."""
    print("\n=== 4. Kaufen oder mieten? ===")
    if wohnen:
        print("Als Eigentümer/in mit '" + empfehlung + "' (Zinsen bleiben gleich):")
        print("   Zinsen im Schnitt:", chf(wohnen["zinsen"]), "+ Unterhalt", chf(wohnen["unterhalt"]),
              "=", chf(wohnen["eigentum"]), "pro Monat")
        print("   Deine heutige Miete:", chf(wohnen["miete"]), "pro Monat")
        if wohnen["differenz"] >= 0:
            print("   -> Wohneigentum ist rund", chf(wohnen["differenz"]), "pro Monat günstiger.")
        else:
            print("   -> Wohneigentum ist rund", chf(-wohnen["differenz"]), "pro Monat teurer.")
        if wohnen["amortisation"] > 0:
            print("   Dazu kommt die Amortisation von", chf(wohnen["amortisation"]),
                  "pro Monat – das ist Sparen, kein Verlust.")
        print("   Nicht eingerechnet: entgangene Rendite auf deinen Eigenmitteln und eine mögliche Wertsteigerung.")
    else:
        print("Keine Miete angegeben – der direkte Vergleich wird übersprungen.")

    print("\nMarktumfeld (Quelle: SNB / Wüest Partner):")
    zeige_entwicklung("   Preise Eigentumswohnungen", immo["wohnungen"])
    zeige_entwicklung("   Angebotsmieten           ", immo["mieten"])


def zeige_auswertung(daten, resultate, a):
    """Hauptfunktion von Teil D: zeigt die ganze Auswertung an."""
    markt = daten["markt"]
    zeige_tragbarkeit(resultate["tragbarkeit"])
    zeige_strategien(a["kennzahlen"], a["empfehlung"], resultate["jahre"], markt["quelle"])
    zeige_einschaetzung(a, daten["nutzer"]["risiko"], markt["zinsen"]["SARON"])
    zeige_kaufen_mieten(a["wohnen"], a["empfehlung"], markt["immo"])
    print("\nKeine Finanzierungsberatung: Modellrechnung auf Basis historischer SNB-Daten und einfacher Szenarien.")
