# data/snb_client.py
# Lädt Datensätze ("Cubes") vom SNB-Datenportal (data.snb.ch): frei, ohne API-Key.
#
# Aufbau einer Antwort (CSV, Semikolon-getrennt), geprüft am 09.10.2026:
#   "CubeId";"snbgwdzid"
#   "PublishingDate";"2026-10-05 10:00"
#                                       <- Leerzeile
#   "Date";"D0";"Value"                 <- Kopfzeile der eigentlichen Tabelle
#   "2026-10-02";"SARON";"-0.04"
#   "2004-05-03";"LZ";                  <- leerer Wert = an diesem Datum keine Daten
#
# Verwendete Cubes und Codes (über /dimensions geprüft):
#   snbgwdzid  täglich   D0: LZ = SNB-Leitzins, SARON = SARON Fixing Handelsschluss
#   zikrepro   monatlich D0: M, 025Q, 05Q (Median), 075Q
#                        D1: Festhypotheken 11=1 J., 20=2 J., 30=3 J., ... 10=10 J., HYP_15=15 J.
#                            SARON-Hypotheken SARJ03, SARJ05, SARJOBD (unbefristet), MV = variabel
#   plkopr     monatlich D0: LD2010100 = Indexwert (Dezember 2025 = 100),
#                            VVP = Veränderung gegenüber Vorjahresmonat in %
#   plimoincha jährlich  D0: EW = Eigentumswohnungen, EH = Einfamilienhäuser, MW = Mietwohnungen, ...
#                        D1: TP = Wüest Partner Transaktionspreis, AP = Wüest Partner Angebotspreis,
#                            TP1 = Fahrländer, TP2 = IAZI, TP3 = BFS (ab 2017)   (geprüft 12.10.2026)
#
# KI-Hinweis: erstellt mit Claude (Anthropic), 09.10.2026.

import requests

BASIS_URL = "https://data.snb.ch/api/cube/"


def zerlege_zeile(zeile):
    """Teilt eine CSV-Zeile am Semikolon und entfernt die Anführungszeichen.

    '"2026-10-02";"SARON";"-0.04"' -> ["2026-10-02", "SARON", "-0.04"]
    """
    teile = []
    for teil in zeile.split(";"):
        teile.append(teil.strip().strip('"'))
    return teile


def lade_cube(cube_id):
    """Lädt einen Cube und gibt die Datenzeilen als Liste von Dictionaries zurück.

    Beispiel: [{"Date": "2026-10-02", "D0": "SARON", "Value": -0.04}, ...]
    Zeilen ohne Wert werden weggelassen, "Value" ist bereits eine Zahl (float).
    """
    antwort = requests.get(BASIS_URL + cube_id + "/data/csv/de", timeout=60)
    antwort.raise_for_status()                     # Fehler, falls die SNB nicht antwortet
    text = antwort.content.decode("utf-8-sig")     # utf-8-sig entfernt das BOM am Dateianfang
    zeilen = text.splitlines()

    # Die Tabelle beginnt bei der Zeile, die mit "Date" anfängt (davor stehen Metadaten)
    start = -1
    for i in range(len(zeilen)):
        if zeilen[i].startswith('"Date"'):
            start = i
            break
    if start == -1:
        raise ValueError("Unerwartetes Format bei Cube " + cube_id + ": keine Kopfzeile gefunden.")

    spalten = zerlege_zeile(zeilen[start])
    daten = []
    for zeile in zeilen[start + 1:]:
        if zeile.strip() == "":
            continue
        werte = zerlege_zeile(zeile)
        if werte[-1] == "":
            continue                               # kein Wert für dieses Datum
        eintrag = {}
        for j in range(len(spalten)):
            eintrag[spalten[j]] = werte[j]
        eintrag["Value"] = float(eintrag["Value"])
        daten.append(eintrag)
    return daten


def lade_dimensionen(cube_id):
    """Gibt die Codes und Bezeichnungen eines Cubes zurück (verschachteltes Dictionary aus JSON)."""
    antwort = requests.get(BASIS_URL + cube_id + "/dimensions/de", timeout=60)
    antwort.raise_for_status()
    antwort.encoding = "utf-8"                     # sonst werden Umlaute falsch dargestellt
    return antwort.json()
