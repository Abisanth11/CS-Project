# data/database.py
# SQLite-Datenbank von HypoKompass: Schema, Speichern und Abfragen.
# Tabellen wie im Projektkonzept (Kapitel 4). Die Datei liegt neben diesem Skript.
#
# KI-Hinweis: erstellt mit Claude (Anthropic), 09.10.2026.

import os
import sqlite3

DB_PFAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hypokompass.sqlite")

# SNB-Code (Cube zikrepro, Dimension D1) -> Produktname in der App
# Achtung: Die SNB-Codes sind nicht einheitlich ("11" = 1 Jahr, "9" = 9 Jahre, "HYP_15" = 15 Jahre).
HYPO_PRODUKTE = {
    "11": "FEST_1",
    "20": "FEST_2",
    "30": "FEST_3",
    "40": "FEST_4",
    "50": "FEST_5",
    "60": "FEST_6",
    "70": "FEST_7",
    "80": "FEST_8",
    "9": "FEST_9",
    "10": "FEST_10",
    "HYP_11": "FEST_11",
    "HYP_12": "FEST_12",
    "HYP_13": "FEST_13",
    "HYP_14": "FEST_14",
    "HYP_15": "FEST_15",
    "SARJ03": "SARON_3J",
    "SARJ05": "SARON_5J",
    "SARJOBD": "SARON_UNBEFRISTET",
    "MV": "VARIABEL",
}

# SNB-Cube plimoincha (Immobilienpreise, jährlich), über /dimensions geprüft am 12.10.2026
# D0 = Objekttyp, D1 = Anbieter und Preisart. Werte sind Indexwerte (keine Franken).
IMMO_OBJEKTE = {
    "EW": "Eigentumswohnungen",
    "EH": "Einfamilienhäuser",
    "MH": "Mehrfamilienhäuser",
    "MW": "Mietwohnungen",
    "BF": "Büroflächen",
    "GF": "Gewerbeflächen",
    "VF": "Verkaufsflächen",
}
IMMO_ANBIETER = {
    "TP3": "BFS, Transaktionspreise (ab 2017)",
    "TP1": "Fahrländer Partner, Transaktionspreise",
    "TP2": "IAZI, Transaktionspreise",
    "TP": "Wüest Partner, Transaktionspreise",
    "AP": "Wüest Partner, Angebotspreise",
}


def verbinde(pfad=DB_PFAD):
    """Öffnet die Datenbank (legt sie bei Bedarf an) und stellt sicher, dass alle Tabellen existieren."""
    con = sqlite3.connect(pfad)
    erstelle_tabellen(con)
    return con


def erstelle_tabellen(con):
    """Legt alle Tabellen an, falls sie noch nicht existieren.

    Die PRIMARY KEYs verhindern doppelte Einträge: Wird derselbe Monat nochmals geladen,
    ersetzt INSERT OR REPLACE den alten Wert (z. B. wenn die SNB eine Zahl korrigiert).
    """
    con.executescript("""
        CREATE TABLE IF NOT EXISTS rates_daily (
            date   TEXT,          -- 'YYYY-MM-DD'
            series TEXT,          -- 'LZ' (Leitzins) oder 'SARON'
            value  REAL,          -- in %
            PRIMARY KEY (date, series)
        );
        CREATE TABLE IF NOT EXISTS mortgage_rates (
            month   TEXT,         -- 'YYYY-MM'
            product TEXT,         -- z. B. 'FEST_10', 'SARON_UNBEFRISTET' (siehe HYPO_PRODUKTE)
            stat    TEXT,         -- 'M' (Mittelwert), '025Q', '05Q' (Median), '075Q'
            value   REAL,         -- in %
            PRIMARY KEY (month, product, stat)
        );
        CREATE TABLE IF NOT EXISTS inflation (
            month         TEXT PRIMARY KEY,
            lik_index     REAL,             -- Landesindex der Konsumentenpreise
            change_pct    REAL,             -- Teuerung gegenüber Vorjahresmonat in %
            forecast_flag INTEGER DEFAULT 0 -- 1 = SNB-Prognose statt Messwert
        );
        CREATE TABLE IF NOT EXISTS property_prices (
            year        TEXT,             -- 'YYYY'
            object_type TEXT,             -- 'EW', 'MW', ... (siehe IMMO_OBJEKTE)
            provider    TEXT,             -- 'TP', 'AP', 'TP3', ... (siehe IMMO_ANBIETER)
            value       REAL,             -- Indexwert
            PRIMARY KEY (year, object_type, provider)
        );
        CREATE TABLE IF NOT EXISTS predictions (
            month         TEXT,
            product       TEXT,
            horizon       INTEGER,          -- Prognosehorizont in Monaten (3, 6, 12)
            value_pred    REAL,
            model_version TEXT,
            PRIMARY KEY (month, product, horizon, model_version)
        );
        CREATE TABLE IF NOT EXISTS scenarios (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user         TEXT,
            price        REAL,
            equity       REAL,
            income       REAL,
            term         INTEGER,
            saron_margin REAL,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()


def letztes_datum(con, tabelle, spalte):
    """Neuestes Datum in einer Tabelle, z. B. '2026-08' (None, wenn die Tabelle leer ist).

    tabelle/spalte kommen nur aus unserem eigenen Code, nie aus einer Nutzereingabe.
    Deshalb ist das Zusammensetzen des SQL-Texts hier unproblematisch.
    """
    return con.execute("SELECT MAX(" + spalte + ") FROM " + tabelle).fetchone()[0]


# --- Speichern ---

def speichere_rates_daily(con, zeilen):
    """zeilen: Liste von (date, series, value). Gibt die Anzahl gespeicherter Zeilen zurück."""
    con.executemany("INSERT OR REPLACE INTO rates_daily VALUES (?, ?, ?)", zeilen)
    con.commit()
    return len(zeilen)


def speichere_mortgage_rates(con, zeilen):
    """zeilen: Liste von (month, product, stat, value)."""
    con.executemany("INSERT OR REPLACE INTO mortgage_rates VALUES (?, ?, ?, ?)", zeilen)
    con.commit()
    return len(zeilen)


def speichere_inflation(con, zeilen):
    """zeilen: Liste von (month, lik_index, change_pct, forecast_flag)."""
    con.executemany("INSERT OR REPLACE INTO inflation VALUES (?, ?, ?, ?)", zeilen)
    con.commit()
    return len(zeilen)


def speichere_property_prices(con, zeilen):
    """zeilen: Liste von (year, object_type, provider, value)."""
    con.executemany("INSERT OR REPLACE INTO property_prices VALUES (?, ?, ?, ?)", zeilen)
    con.commit()
    return len(zeilen)


def speichere_szenario(con, user, price, equity, income, term, saron_margin):
    """Speichert ein Nutzer-Szenario und gibt seine id zurück."""
    cursor = con.execute(
        "INSERT INTO scenarios (user, price, equity, income, term, saron_margin) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user, price, equity, income, term, saron_margin))
    con.commit()
    return cursor.lastrowid


# --- Abfragen ---

def lade_szenarien(con, user):
    """Alle gespeicherten Szenarien einer Person, neueste zuerst (Liste von Tupeln)."""
    return con.execute(
        "SELECT id, price, equity, income, term, saron_margin, created_at "
        "FROM scenarios WHERE user = ? ORDER BY id DESC", (user,)).fetchall()


def letzter_hypozins(con, produkt, stat="M"):
    """Neuester Hypothekarzins eines Produkts: (wert, monat) oder None."""
    return con.execute(
        "SELECT value, month FROM mortgage_rates WHERE product = ? AND stat = ? "
        "ORDER BY month DESC LIMIT 1", (produkt, stat)).fetchone()


def letzter_tageszins(con, series):
    """Neuester Wert von 'SARON' oder 'LZ': (wert, datum) oder None."""
    return con.execute(
        "SELECT value, date FROM rates_daily WHERE series = ? "
        "ORDER BY date DESC LIMIT 1", (series,)).fetchone()


def immo_index(con, objekt, anbieter, jahr):
    """Indexwert eines Jahres, z. B. immo_index(con, "EW", "TP", "2025"), oder None."""
    zeile = con.execute(
        "SELECT value FROM property_prices WHERE object_type = ? AND provider = ? AND year = ?",
        (objekt, anbieter, jahr)).fetchone()
    if zeile is None:
        return None
    return zeile[0]


def preisentwicklung(con, objekt, anbieter, jahre=10):
    """Veränderung eines Immobilienindex über die letzten 'jahre' Jahre, oder None.

    Rückgabe z. B. {"von": "2015", "bis": "2025", "aenderung_pct": 45.2, "pro_jahr_pct": 3.8}
    pro_jahr_pct ist die durchschnittliche jährliche Veränderung (mit Zinseszins gerechnet).
    """
    bis = con.execute(
        "SELECT MAX(year) FROM property_prices WHERE object_type = ? AND provider = ?",
        (objekt, anbieter)).fetchone()[0]
    if bis is None:
        return None
    von = str(int(bis) - jahre)
    wert_alt = immo_index(con, objekt, anbieter, von)
    wert_neu = immo_index(con, objekt, anbieter, bis)
    if wert_alt is None or wert_neu is None:
        return None

    faktor = wert_neu / wert_alt
    return {
        "von": von,
        "bis": bis,
        "aenderung_pct": (faktor - 1) * 100,
        "pro_jahr_pct": (faktor ** (1 / jahre) - 1) * 100,
    }


def aktuelle_zinsen(con):
    """Aktuelle Zinsen für die Produkte der App, oder None, wenn Daten fehlen.

    Rückgabe: {"zinsen": {"FEST_3": ..., "FEST_10": ..., "FEST_15": ..., "SARON": ...},
               "saron_hypo": Durchschnittszins neuer SARON-Hypotheken (unbefristet),
               "stand_hypo": "YYYY-MM", "stand_saron": "YYYY-MM-DD"}
    """
    fest_3 = letzter_hypozins(con, "FEST_3")
    fest_10 = letzter_hypozins(con, "FEST_10")
    fest_15 = letzter_hypozins(con, "FEST_15")
    saron_hypo = letzter_hypozins(con, "SARON_UNBEFRISTET")
    saron = letzter_tageszins(con, "SARON")
    if fest_3 is None or fest_10 is None or fest_15 is None or saron_hypo is None or saron is None:
        return None

    return {
        "zinsen": {
            "FEST_3": fest_3[0],
            "FEST_10": fest_10[0],
            "FEST_15": fest_15[0],
            "SARON": saron[0],
        },
        "saron_hypo": saron_hypo[0],
        "stand_hypo": fest_10[1],
        "stand_saron": saron[1],
    }
