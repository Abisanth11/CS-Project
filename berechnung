# berechnung.py
# Schritt 2 von 3: Berechnung (Hauptprozess).
#
# Bekommt die Eingabedaten aus Schritt 1 (eingabe.py) und gibt alle Resultate
# als Dictionary an Schritt 3 (Auswertung) weiter. Hier gibt es kein input() und kein print().
#
#   Teil A: Tragbarkeit      – kann ich mir das Eigenheim leisten?      (A1 bis A6)
#   Teil B: Kostenvergleich  – was kostet jede Strategie pro Szenario?  (B1 bis B5)
#
# KI-Hinweis: erstellt mit Claude (Anthropic), Oktober 2026. Formeln vom Team geprüft: [ ]
# Korrekturen nach Prüfung durch Noel (09.10.2026):
#   1. Kaufnebenkosten gehen von den harten Eigenmitteln ab (A6-Prüfung)
#   2. SARON-Untergrenze verschiebt den Zinsverlauf nicht mehr (B1)
#   3. Vergleich über 15 statt 10 Jahre, damit die Festhypothek 15 Jahre fair verglichen wird

from eingabe import AKTUELLES_JAHR

# --- Annahmen Tragbarkeit (Schweizer Bankpraxis) ---
KALK_ZINS = 0.05               # kalkulatorischer Zins 5 % (nicht der echte Zins)
NEBENKOSTEN_SATZ = 0.01        # Unterhalt: 1 % des Kaufpreises pro Jahr
KAUFNEBENKOSTEN_SATZ = 0.03    # Notar, Grundbuch, Handänderungssteuer: einmalig ca. 3 %
MAX_TRAGBARKEIT = 1 / 3        # Wohnkosten max. 1/3 des Bruttoeinkommens
GELB_GRENZE = 0.38             # Teamentscheid: bis 38 % = knapp (gelbe Ampel)
MAX_BELEHNUNG = 0.80           # Hypothek max. 80 % des Kaufpreises
MIN_HARTE_EIGENMITTEL = 0.10   # mind. 10 % des Kaufpreises nicht aus der Pensionskasse
GRENZE_1_HYPO = 2 / 3          # 1. Hypothek bis 2/3 des Kaufpreises
AMORTISATION_JAHRE = 15        # 2. Hypothek in 15 Jahren abzahlen ...
PENSIONSALTER = 65             # ... aber spätestens bis zur Pensionierung

# --- Annahmen Kostenvergleich ---
VERGLEICH_JAHRE = 15           # Zeitraum des Vergleichs in Jahren (= längste Laufzeit, FEST_15)

# Änderung der Zinsen in Prozentpunkten pro Jahr je Szenario
SZENARIEN = {
    "sinken": -0.25,
    "stabil": 0.0,
    "steigen": 0.25,
}

# Laufzeit der Festhypotheken in Jahren
LAUFZEITEN = {
    "FEST_3": 3,
    "FEST_10": 10,
    "FEST_15": 15,
}


# =====================================================================
# Teil A: Tragbarkeit
# =====================================================================

def berechne_kaufnebenkosten(kaufpreis):
    """A1: Einmalige Kaufnebenkosten, sie werden aus den Eigenmitteln bezahlt."""
    return kaufpreis * KAUFNEBENKOSTEN_SATZ


def berechne_hypothek(kaufpreis, eigenmittel_fuer_kauf):
    """A2: Hypothek = Kaufpreis minus Eigenmittel, dazu die Belehnung in Prozent des Kaufpreises."""
    hypothek = kaufpreis - eigenmittel_fuer_kauf
    if hypothek < 0:
        hypothek = 0
    belehnung = hypothek / kaufpreis
    return hypothek, belehnung


def teile_hypothek_auf(kaufpreis, hypothek):
    """A3: Bis 2/3 des Kaufpreises ist es die 1. Hypothek, der Rest ist die 2. Hypothek."""
    grenze = kaufpreis * GRENZE_1_HYPO
    if hypothek <= grenze:
        erste = hypothek
        zweite = 0
    else:
        erste = grenze
        zweite = hypothek - grenze
    return erste, zweite


def berechne_amortisation(zweite_hypothek, alter):
    """A4: Die 2. Hypothek wird in 15 Jahren abbezahlt, aber höchstens bis Alter 65."""
    jahre = AMORTISATION_JAHRE
    if PENSIONSALTER - alter < jahre:
        jahre = PENSIONSALTER - alter
    if jahre < 1:
        jahre = 1   # damit nie durch 0 geteilt wird
    pro_jahr = zweite_hypothek / jahre
    return pro_jahr, jahre


def berechne_kalk_kosten(hypothek, amortisation, kaufpreis):
    """A5: Kalkulatorische Kosten pro Jahr = Zins 5 % + Amortisation + Nebenkosten 1 %."""
    zinskosten = hypothek * KALK_ZINS
    nebenkosten = kaufpreis * NEBENKOSTEN_SATZ
    return zinskosten + amortisation + nebenkosten


def bestimme_ampel(belehnung, harte_eigenmittel, kaufpreis, quote):
    """A6: Ampel. Zuerst die Eigenmittel prüfen, dann die Tragbarkeit (Reihenfolge ist wichtig)."""
    if belehnung > MAX_BELEHNUNG:
        return "rot", "Zu wenig Eigenmittel: nach den Kaufnebenkosten braucht es mind. 20 % des Kaufpreises."
    elif harte_eigenmittel < kaufpreis * MIN_HARTE_EIGENMITTEL:
        return "rot", ("Zu wenig harte Eigenmittel: Nach den Kaufnebenkosten müssen mind. 10 % "
                       "des Kaufpreises aus eigenem Geld stammen, nicht aus der Pensionskasse.")
    elif quote <= MAX_TRAGBARKEIT:
        return "grün", "Tragbar."
    elif quote <= GELB_GRENZE:
        return "gelb", "Knapp: liegt leicht über 1/3 des Einkommens."
    else:
        return "rot", "Nicht tragbar: Wohnkosten über 1/3 des Einkommens."


def berechne_tragbarkeit(nutzer, alter):
    """Teil A komplett: führt A1 bis A6 nacheinander aus und sammelt alles in einem Dictionary."""
    kaufpreis = nutzer["kaufpreis"]

    kaufnebenkosten = berechne_kaufnebenkosten(kaufpreis)                       # A1
    eigenmittel_fuer_kauf = nutzer["eigenmittel"] - kaufnebenkosten
    # Die Kaufnebenkosten gehen von den harten Eigenmitteln ab: Pensionskassengeld wird
    # direkt an Bank oder Verkäufer überwiesen und darf z. B. nicht für Notariatskosten
    # verwendet werden (Quelle: Merkblatt WEF-Vorbezug der Bernischen Pensionskasse).
    harte_eigenmittel = nutzer["eigenmittel"] - nutzer["pk_bezug"] - kaufnebenkosten

    hypothek, belehnung = berechne_hypothek(kaufpreis, eigenmittel_fuer_kauf)  # A2
    erste, zweite = teile_hypothek_auf(kaufpreis, hypothek)                     # A3
    amortisation, amort_jahre = berechne_amortisation(zweite, alter)           # A4
    kosten_jahr = berechne_kalk_kosten(hypothek, amortisation, kaufpreis)      # A5
    quote = kosten_jahr / nutzer["einkommen"]
    ampel, meldung = bestimme_ampel(belehnung, harte_eigenmittel, kaufpreis, quote)  # A6

    return {
        "kaufnebenkosten": kaufnebenkosten,
        "harte_eigenmittel": harte_eigenmittel,
        "hypothek": hypothek,
        "belehnung": belehnung,
        "erste_hypothek": erste,
        "zweite_hypothek": zweite,
        "amortisation": amortisation,
        "amortisations_jahre": amort_jahre,
        "kosten_jahr": kosten_jahr,
        "kosten_monat": kosten_jahr / 12,
        "quote": quote,
        "ampel": ampel,
        "meldung": meldung,
    }


# =====================================================================
# Teil B: Kostenvergleich der Strategien
# =====================================================================

def saron_pfad(start_saron, aenderung, jahre):
    """B1: Liste mit dem SARON (in %) für jedes Jahr. Der SARON wird nie unter 0 % gerechnet.

    Die Untergrenze gilt nur für den eingetragenen Wert, nicht für den Verlauf selbst:
    Startet der SARON bei -0.04 %, ergibt "steigen" 0, 0.21, 0.46 ... (nicht 0, 0.25, 0.5).
    """
    pfad = []
    saron = start_saron
    for jahr in range(jahre):
        if saron < 0:
            pfad.append(0)
        else:
            pfad.append(saron)
        saron = saron + aenderung
    return pfad


def fest_zins_pfad(start_zins, laufzeit, aenderung, jahre):
    """B2: Liste mit dem Zins einer Festhypothek für jedes Jahr.

    Während der Laufzeit bleibt der Zins gleich. Läuft sie ab (z. B. 3 Jahre),
    wird sie zum neuen Marktzins verlängert: Startzins + Änderung bis zu diesem Jahr.
    """
    pfad = []
    zins = start_zins
    for jahr in range(jahre):
        if jahr > 0 and jahr % laufzeit == 0:
            zins = start_zins + aenderung * jahr
            if zins < 0:
                zins = 0
        pfad.append(zins)
    return pfad


def schuld_pfad(hypothek, amortisation, untergrenze, jahre):
    """B3: Liste mit der Hypothekarschuld für jedes Jahr.

    Die Schuld sinkt jedes Jahr um die Amortisation, aber nie unter die 1. Hypothek.
    """
    pfad = []
    schuld = hypothek
    for jahr in range(jahre):
        pfad.append(schuld)
        schuld = schuld - amortisation
        if schuld < untergrenze:
            schuld = untergrenze
    return pfad


def kosten_strategie(schulden, tranchen, zinsen, marge, aenderung):
    """B4: Zinskosten pro Jahr für eine Strategie, z. B. tranchen = {"FEST_10": 0.5, "SARON": 0.5}."""
    jahre = len(schulden)
    kosten = []
    for jahr in range(jahre):
        kosten.append(0)

    for produkt in tranchen:
        # passenden Zinspfad holen: SARON (+ Marge der Bank) oder Festhypothek
        if produkt == "SARON":
            pfad = saron_pfad(zinsen["SARON"], aenderung, jahre)
            zuschlag = marge
        else:
            pfad = fest_zins_pfad(zinsen[produkt], LAUFZEITEN[produkt], aenderung, jahre)
            zuschlag = 0   # bei der Festhypothek ist die Marge schon im Zins enthalten

        for jahr in range(jahre):
            betrag = schulden[jahr] * tranchen[produkt]
            kosten[jahr] = kosten[jahr] + betrag * (pfad[jahr] + zuschlag) / 100
    return kosten


def vergleiche_strategien(strategien, schulden, zinsen, marge):
    """B5: Gesamte Zinskosten jeder Strategie in jedem Szenario.

    Ergebnis z. B. {"Alles SARON": {"sinken": 74965, "stabil": 74965, "steigen": 230395}, ...}
    """
    vergleich = {}
    for strategie in strategien:
        name = strategie["name"]
        vergleich[name] = {}
        for szenario in SZENARIEN:
            kosten = kosten_strategie(schulden, strategie["tranchen"], zinsen, marge,
                                      SZENARIEN[szenario])
            vergleich[name][szenario] = sum(kosten)
    return vergleich


# =====================================================================
# Schnittstelle: Schritt 1 -> Schritt 2 -> Schritt 3
# =====================================================================

def berechne(daten):
    """Hauptfunktion von Schritt 2: rechnet Teil A und Teil B und gibt alle Resultate zurück."""
    nutzer = daten["nutzer"]
    zinsen = daten["markt"]["zinsen"]
    alter = AKTUELLES_JAHR - nutzer["geburtsjahr"]

    # Teil A
    tragbarkeit = berechne_tragbarkeit(nutzer, alter)

    # Teil B
    schulden = schuld_pfad(tragbarkeit["hypothek"], tragbarkeit["amortisation"],
                           tragbarkeit["erste_hypothek"], VERGLEICH_JAHRE)
    vergleich = vergleiche_strategien(nutzer["strategien"], schulden, zinsen, nutzer["marge"])

    return {
        "tragbarkeit": tragbarkeit,
        "vergleich": vergleich,
        "jahre": VERGLEICH_JAHRE,
    }
