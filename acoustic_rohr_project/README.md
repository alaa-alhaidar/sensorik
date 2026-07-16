# Akustisches Messsystem zur Bestimmung der hin- und rücklaufenden Welle

## Übersicht

Dieses Projekt dient zur Messung und Analyse von Schallwellen in einem Impedanzrohr mit drei Mikrofonen. Ziel ist die Bestimmung der hinlaufenden und rücklaufenden Welle sowie die automatische Regelung der Generatoramplitude, sodass über einen gesamten Frequenzbereich eine konstante Schalldruckamplitude der hinlaufenden Welle erreicht wird.

Das Programm bietet folgende Funktionen:

- Aufnahme von Audiosignalen über ein Focusrite Scarlett Audio-Interface
- Steuerung eines Agilent 33120A Funktionsgenerators
- Simulation der Messhardware für Tests ohne Laboraufbau
- Berechnung komplexer Schalldruckamplituden der Mikrofone
- Bestimmung der hinlaufenden und rücklaufenden Welle
- Automatische Frequenzmessungen
- Automatische Pegelregelung
- Grafische Darstellung aller Messergebnisse
- Speicherung der Messdaten

---

# Projektstruktur

```
gui.py
│
├── generator_hdw_panel.py
│      Steuerung des Agilent 33120A
│
├── simulated_generator.py
│      Simulation des Funktionsgenerators
│
├── focusrite_interface.py
│      Aufnahme über Focusrite Scarlett
│
├── signal_process.py
│      Signalverarbeitung
│
├── estimation.py
│      Berechnung der Wellen A und B
│
├── automation.py
│      Automatische Regelung und Frequenz-Sweep
│
├── compensation.py
│      Kompensationsfunktionen
│
├── metrics.py
│      Hilfsfunktionen
│
└── Testprogramme
```

---

# Programmablauf

## 1. Programm starten

Das Programm wird über

```bash
python gui.py
```

gestartet.

Die grafische Benutzeroberfläche bildet den zentralen Einstiegspunkt und verbindet alle Projektmodule.

---

## 2. Auswahl der Signalquelle

Das System unterstützt zwei Betriebsarten.

### Simulation

Es werden künstliche Mikrofonsignale erzeugt.

```
SimulatedGenerator
```

Diese Betriebsart eignet sich zur Entwicklung und zum Testen ohne Laborhardware.

### Hardware

Im Labor werden verwendet:

- Agilent 33120A Funktionsgenerator
- Focusrite Scarlett Audio-Interface
- drei Mikrofone

---

## 3. Verbindung mit dem Generator

Nach dem Start wird der Generator verbunden.

```
Generator verbinden
        │
        ▼
Agilent33120A.connect()
        │
        ▼
Geräte-ID lesen
```

Danach können

- Frequenz
- Ausgangsspannung
- Signalform (Sinus)

eingestellt werden.

---

## 4. Aufnahme des Messsignals

Während einer Messung läuft folgender Ablauf ab:

```
Generator erzeugt Sinus
          │
          ▼
Focusrite nimmt Signal auf
          │
          ▼
Drei Mikrofonkanäle werden gespeichert
```

Standardparameter:

- Abtastrate: 48 kHz
- Messdauer: 1 s

---

## 5. Signalvorverarbeitung

Vor der eigentlichen Auswertung werden die aufgenommenen Signale überprüft.

Dabei erfolgt

- Kontrolle der Kanalanzahl
- Anwendung der Mikrofonkalibrierung
- Umwandlung in NumPy-Arrays
- Prüfung auf Clipping

---

## 6. Berechnung der komplexen Schalldrücke

Für jedes Mikrofon wird die komplexe Schalldruckamplitude berechnet.

Für jedes Mikrofon werden bestimmt:

```
P₁
P₂
P₃
```

sowie

- Betrag
- Phase
- RMS-Wert

---

## 7. Berechnung der hin- und rücklaufenden Welle

Aus den drei komplexen Mikrofonwerten

```
P₁
P₂
P₃
```

werden mittels Least-Squares die beiden Wellen bestimmt.

```
A
```

Hinlaufende Welle

```
B
```

Rücklaufende Welle

Hierzu wird das lineare Gleichungssystem gelöst

```text
P = M · [A B]ᵀ
```

wobei

- **P** den Messvektor der Mikrofone beschreibt,
- **M** die Ausbreitungsmatrix darstellt,
- **A** die hinlaufende Welle ist,
- **B** die rücklaufende Welle ist.

---

## 8. Darstellung der Ergebnisse

Die grafische Oberfläche zeigt

- Zeitverlauf
- FFT
- komplexe Mikrofonwerte
- Wellenzerlegung
- Schalldruckpegel
- Ortsverlauf im Rohr
- RMS-Pegel in dBµV

---

# Automatische Regelung

Die wichtigste Funktion des Projekts ist die automatische Regelung.

Ziel ist:

> Für jede Frequenz soll die hinlaufende Welle dieselbe Schalldruckamplitude besitzen.

---

## Ablauf

Für jede Frequenz wird folgender Regelkreis ausgeführt.

```
Generator starten
        │
        ▼
Signal aufnehmen
        │
        ▼
Amplitude |A| berechnen
        │
        ▼
Soll-Ist-Vergleich
        │
        ▼
Generator-Spannung anpassen
        │
        ▼
Neue Messung
```

Dieser Vorgang wird wiederholt, bis die gewünschte Toleranz erreicht wird.

---

## Berechnung der neuen Spannung

Die Generator-Spannung wird nach jedem Messschritt proportional angepasst.

```text
U_neu = U_alt · ( |A_Soll| / |A_Mess| )
```

Dabei gilt:

- **U_neu** : neue Generator-Spannung
- **U_alt** : bisherige Generator-Spannung
- **|A_Soll|** : gewünschte Amplitude
- **|A_Mess|** : gemessene Amplitude

Ist die gemessene Amplitude kleiner als der Sollwert, wird die Generator-Spannung erhöht.

Ist sie größer, wird die Spannung reduziert.

---

## Abbruchbedingungen

Die automatische Regelung endet, wenn

- die Zielamplitude erreicht wurde,
- die maximale Schrittzahl erreicht wurde,
- die maximale Generator-Spannung erreicht wurde,
- die minimale Generator-Spannung erreicht wurde,
- Clipping erkannt wurde.

---

# Automatischer Frequenz-Sweep

Der Frequenz-Sweep läuft beispielsweise über

```
350 Hz

↓

400 Hz

↓

450 Hz

↓

...

↓

2050 Hz
```

Für jede Frequenz wird die vollständige Messung einschließlich der automatischen Regelung durchgeführt.

Für jede Frequenz werden gespeichert:

- Generator-Spannung vor der Regelung
- Generator-Spannung nach der Regelung
- Amplitude vor der Regelung
- Amplitude nach der Regelung
- relativer Fehler
- Anzahl der Regelschritte

---

# Ausgabe

Während der Messung werden fortlaufend aktualisiert:

- Live-Plots
- FFT
- Tabellen
- Log-Dateien

Nach Abschluss können sämtliche Messergebnisse gespeichert werden.

---

# Gesamter Messablauf

```
Programm starten
        │
        ▼
Generator verbinden
        │
        ▼
Focusrite verbinden
        │
        ▼
Messparameter einstellen
        │
        ▼
Generator erzeugt Sinussignal
        │
        ▼
Signalaufnahme
        │
        ▼
Signalvorverarbeitung
        │
        ▼
FFT-Berechnung
        │
        ▼
Berechnung von P₁, P₂ und P₃
        │
        ▼
Least-Squares-Schätzung
        │
        ▼
Berechnung von A und B
        │
        ▼
Soll-Ist-Vergleich
        │
        ▼
Automatische Spannungsregelung
        │
        ▼
Messung wiederholen
        │
        ▼
Ergebnisse darstellen
        │
        ▼
Messdaten speichern
```

---

# Verwendete Hardware

- Agilent 33120A Funktionsgenerator
- Focusrite Scarlett Audio-Interface
- drei Kondensatormikrofone
- Impedanzrohr

---

# Verwendete Software

- Python 3
- NumPy
- PySide6
- PyQtGraph
- SoundDevice
- PyVISA

---

# Ziel des Projekts

Das entwickelte Messsystem ermöglicht die reproduzierbare Untersuchung von Schallfeldern in einem Impedanzrohr. Durch die automatische Regelung der Generatoramplitude wird über einen gesamten Frequenzbereich eine konstante Amplitude der hinlaufenden Welle eingestellt. Die Signalverarbeitung ist vollständig von der grafischen Benutzeroberfläche getrennt und unterstützt sowohl reale Messhardware als auch einen vollständigen Simulationsbetrieb. Dadurch eignet sich das System sowohl für Laborversuche als auch für die Weiterentwicklung neuer Messverfahren.