# HypoKompass CH – Festhypothek oder SARON?

Gruppenprojekt Fundamentals and Methods of Computer Science (HSG, HS 2026).
Vergleicht Hypothekarstrategien (fest, gestaffelt, SARON, Mix) auf Basis offizieller SNB-Daten.
Keine Finanzierungsberatung.

## Starten

```
pip install -r requirements.txt
python -m data.update_data     # SNB-Daten laden (beim ersten Mal und danach bei Bedarf)
python main.py                 # Konsolen-Version
```

Ohne `update_data` läuft die App mit Platzhalter-Zinsen (Stand Aug./Okt. 2026).

## Aufbau

| Datei | Inhalt |
|---|---|
| `main.py` | Konsolen-Version: Eingabe → Berechnung → Ausgabe |
| `eingabe.py` | Schritt 1: Fragen an die Nutzerin, Strategien, Marktdaten laden |
| `berechnung.py` | Schritt 2: Tragbarkeit (A1–A6) und Kostenvergleich der Strategien (B1–B5) |
| `auswertung.py` | Schritt 3: Kennzahlen, Einschätzung nach Risikobereitschaft, Kaufen vs. Mieten (C1–C5), Ausgabe |
| `data/snb_client.py` | Download und Parsing der SNB-Cubes |
| `data/database.py` | SQLite-Schema, Speichern, Abfragen |
| `data/update_data.py` | Inkrementelles Laden neuer SNB-Daten |

## Datenquellen

SNB-Datenportal (data.snb.ch), Nutzung frei mit Quellenangabe:
`snbgwdzid` (Leitzins, SARON), `zikrepro` (Hypothekarzinsen), `plkopr` (Landesindex der Konsumentenpreise),
`plimoincha` (Immobilienpreise und Mieten, jährlich; die App verwendet die Reihen von Wüest Partner:
Transaktionspreise Eigentumswohnungen und Angebotsmieten).

## Annahmen der Berechnung

- Tragbarkeit nach Schweizer Bankpraxis: kalkulatorischer Zins 5 %, Nebenkosten 1 % des
  Kaufpreises, Wohnkosten höchstens 1/3 des Bruttoeinkommens (bis 38 % gelb, Teamentscheid).
- Eigenmittel mindestens 20 % des Kaufpreises, davon mindestens 10 % hart (nicht aus der Pensionskasse).
- Kaufnebenkosten pauschal 3 % des Kaufpreises (je nach Kanton tiefer oder höher;
  Zürich erhebt z. B. keine Handänderungssteuer). Sie werden zusätzlich zu den 20 % fällig.
- Kaufnebenkosten werden aus harten Eigenmitteln bezahlt: Pensionskassengeld wird direkt an
  Bank oder Verkäufer überwiesen und darf z. B. nicht für Notariatskosten verwendet werden
  (Quelle: Merkblatt WEF-Vorbezug, Bernische Pensionskasse).
- Eine Verpfändung der Pensionskasse wird vereinfacht wie ein Vorbezug behandelt.
- Die 2. Hypothek (Teil über 2/3 des Kaufpreises) wird direkt amortisiert, innert 15 Jahren,
  spätestens bis Alter 65. Die App rechnet deshalb nur für Personen von 18 bis 60 Jahren.
- Der SARON wird für die Hypothek nie unter 0 % gerechnet; der Markt-SARON selbst darf negativ sein.
- In den Szenarien ändern sich SARON und Festzinsen jedes Jahr um gleich viel
  (−0,25 / 0 / +0,25 Prozentpunkte). Läuft eine Festhypothek ab, wird sie zum dann gültigen Zins verlängert.
- Verglichen werden die Zinskosten über 15 Jahre (= längste Festhypothek). Die Amortisation
  ist darin nicht enthalten, sie senkt nur die Schuld.

(Annahmen geprüft und präzisiert von Noel, 09.10.2026.)

## KI-Nutzung

Teile des Codes wurden mit Claude (Anthropic) erstellt; die betroffenen Dateien sind im Kopfkommentar gekennzeichnet.
