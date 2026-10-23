# data/update_data.py
# Holt neue Werte von der SNB und speichert sie in der SQLite-Datenbank.
# Inkrementell: Es werden nur Daten ab dem neuesten gespeicherten Datum geschrieben.
# Das letzte gespeicherte Datum wird bewusst nochmals überschrieben, falls die SNB es korrigiert hat.
#
# Ausführen im Projektordner (nicht im Ordner data/):
#     python -m data.update_data
#
# KI-Hinweis: erstellt mit Claude (Anthropic), 09.10.2026.

from data import database
from data import snb_client


def ist_neu(datum, letztes):
    """True, wenn 'datum' noch nicht (oder als letzter Eintrag) in der Datenbank ist."""
    return letztes is None or datum >= letztes   # Datumstexte 'YYYY-MM(-DD)' lassen sich so vergleichen


def aktualisiere_tageszinsen(con):
    """SNB-Leitzins und SARON (Cube snbgwdzid) -> Tabelle rates_daily."""
    letztes = database.letztes_datum(con, "rates_daily", "date")
    zeilen = []
    for eintrag in snb_client.lade_cube("snbgwdzid"):
        if eintrag["D0"] in ["LZ", "SARON"] and ist_neu(eintrag["Date"], letztes):
            zeilen.append((eintrag["Date"], eintrag["D0"], eintrag["Value"]))
    return database.speichere_rates_daily(con, zeilen)


def aktualisiere_hypozinsen(con):
    """Hypothekarzinsen nach Produkt (Cube zikrepro) -> Tabelle mortgage_rates."""
    letztes = database.letztes_datum(con, "mortgage_rates", "month")
    zeilen = []
    for eintrag in snb_client.lade_cube("zikrepro"):
        code = eintrag["D1"]
        if code in database.HYPO_PRODUKTE and ist_neu(eintrag["Date"], letztes):
            produkt = database.HYPO_PRODUKTE[code]
            zeilen.append((eintrag["Date"], produkt, eintrag["D0"], eintrag["Value"]))
    return database.speichere_mortgage_rates(con, zeilen)


def aktualisiere_inflation(con):
    """Landesindex der Konsumentenpreise (Cube plkopr) -> Tabelle inflation.

    Die SNB liefert Indexwert und Teuerung als getrennte Zeilen; hier werden sie
    pro Monat zu einer Zeile zusammengeführt.
    """
    letztes = database.letztes_datum(con, "inflation", "month")
    monate = {}   # {"2026-08": {"LD2010100": 101.5, "VVP": 0.8}, ...}
    for eintrag in snb_client.lade_cube("plkopr"):
        if ist_neu(eintrag["Date"], letztes):
            if eintrag["Date"] not in monate:
                monate[eintrag["Date"]] = {}
            monate[eintrag["Date"]][eintrag["D0"]] = eintrag["Value"]

    zeilen = []
    for monat in monate:
        werte = monate[monat]
        index = werte.get("LD2010100")   # .get() gibt None zurück, falls der Wert fehlt
        teuerung = werte.get("VVP")
        zeilen.append((monat, index, teuerung, 0))
    return database.speichere_inflation(con, zeilen)


def aktualisiere_immopreise(con):
    """Immobilienpreise und Mieten (Cube plimoincha, jährlich) -> Tabelle property_prices.

    Hinzugefügt am 12.10.2026 (KI-Hinweis: Claude).
    """
    letztes = database.letztes_datum(con, "property_prices", "year")
    zeilen = []
    for eintrag in snb_client.lade_cube("plimoincha"):
        if ist_neu(eintrag["Date"], letztes):
            zeilen.append((eintrag["Date"], eintrag["D0"], eintrag["D1"], eintrag["Value"]))
    return database.speichere_property_prices(con, zeilen)


def aktualisiere_alles():
    """Aktualisiert alle Tabellen und meldet, wie viele Zeilen geschrieben wurden."""
    con = database.verbinde()
    print("Lade SNB-Daten ... (das kann beim ersten Mal etwas dauern)")
    print("Leitzins & SARON:   ", aktualisiere_tageszinsen(con), "Zeilen")
    print("Hypothekarzinsen:   ", aktualisiere_hypozinsen(con), "Zeilen")
    print("Inflation (LIK):    ", aktualisiere_inflation(con), "Zeilen")
    print("Immobilienpreise:   ", aktualisiere_immopreise(con), "Zeilen")
    con.close()
    print("Fertig. Datenbank:", database.DB_PFAD)


if __name__ == "__main__":
    aktualisiere_alles()
