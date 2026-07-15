
# Akustisches Messsystem zur Bestimmung der hin- und rücklaufenden Welle

## Übersicht

Dieses Projekt dient zur Messung und Analyse von Schallwellen in einem Impedanzrohr mit drei Mikrofonen.

Das Programm kann

* Audiosignale über ein Focusrite Scarlett Audio-Interface aufnehmen,
* einen Agilent 33120A Funktionsgenerator automatisch steuern,
* komplexe Schalldruckamplituden der Mikrofone berechnen,
* die hinlaufende und rücklaufende Welle bestimmen,
* automatische Frequenzmessungen durchführen,
* die Generator-Spannung automatisch nachregeln, um eine konstante Schalldruckamplitude der hinlaufenden Welle zu erzeugen,
* sämtliche Ergebnisse grafisch darstellen und speichern.

Das System kann sowohl mit echter Hardware als auch vollständig simuliert betrieben werden.

---

# Projektstruktur

```
gui.py
│
├── generator_hdw_panel.py
│      Steuerung des Agilent 33120A
│
├── simulated_generator.py
│      Generator für Simulation
│
├── focusrite_interface.py
│      Aufnahme über Focusrite Scarlett
│
├── signal_process.py
│      Signalverarbeitung
│
├── estimation.py
│      Berechnung von A und B
│
├── automation.py
│      automatische Regelung
│
├── compensation.py
│      Verstärkung/Kompensation
│
├── metrics.py
│      Hilfsfunktionen
│
└── Testprogramme
```

---

# Programmablauf

## 1. Programmstart

Das Projekt wird über

```bash
python gui.py
```

gestartet.

Die GUI ist der zentrale Einstiegspunkt und verbindet alle Module.

---

# 2. Auswahl der Signalquelle

Es stehen zwei Betriebsarten zur Verfügung.

### Simulation

Es werden künstliche Mikrofonsignale erzeugt.

```
SimulatedGenerator
```

Diese Betriebsart dient zur Entwicklung ohne Laborhardware.

---

### Hardware

Im Labor werden verwendet

* Agilent 33120A
* Focusrite Scarlett
* drei Mikrofone

---

# 3. Verbindung mit dem Generator

Beim Start wird der Generator verbunden.

```
Generator verbinden
        │
        ▼
Agilent33120A.connect()
        │
        ▼
ID des Gerätes lesen
```

Danach können

* Frequenz
* Spannung
* Sinusform

eingestellt werden.

---

# 4. Aufnahme des Signals

Nach dem Start einer Messung erfolgt

```
Generator erzeugt Sinus
          │
          ▼
Focusrite nimmt auf
          │
          ▼
3 Kanäle werden gespeichert
```

Die Aufnahme erfolgt typischerweise mit

* 48 kHz
* 1 s Messdauer

---

# 5. Signalvorbereitung

Vor der eigentlichen Berechnung werden die Signale geprüft.

Dabei erfolgt

* Prüfung der Kanalanzahl
* Kalibrierung
* Umwandlung in NumPy
* Clippingkontrolle

---

# 6. Berechnung der komplexen Schalldrücke

Für jedes Mikrofon wird die komplexe Schalldruckamplitude berechnet.

Für jedes Mikrofon entstehen

```
P1
P2
P3
```

sowie

* Betrag
* Phase
* RMS

---

# 7. Berechnung der Wellen

Aus

```
P1
P2
P3
```

wird mittels Least-Squares

```
A
```

(hinlaufende Welle)

und

```
B
```

(rücklaufende Welle)

berechnet.

Hierzu wird das lineare Gleichungssystem

[
P=M\cdot
\begin{bmatrix}
A\
B
\end{bmatrix}
]

gelöst.

---

# 8. Darstellung

Die GUI zeigt anschließend

* Zeitverlauf
* FFT
* komplexe Mikrofonwerte
* Wellenzerlegung
* Pegel
* Ortsverlauf
* dBµV-Darstellung

---

# Automatische Regelung

Die wichtigste Funktion des Projekts ist die automatische Regelung.

Ziel ist

> Für jede Frequenz soll die hinlaufende Welle dieselbe Amplitude besitzen.

---

## Ablauf

Für jede Frequenz erfolgt

```
Generator starten
        │
        ▼
Messung
        │
        ▼
Berechnung von |A|
        │
        ▼
Vergleich mit Sollwert
        │
        ▼
Generator-Spannung anpassen
        │
        ▼
erneut messen
```

Dies wird solange wiederholt, bis

```
|A|
```

innerhalb der Toleranz liegt.

---

## Berechnung der neuen Spannung

Die neue Spannung wird berechnet als

[
U_{neu}
=======

U_{alt}
\cdot
\frac{|A_{Soll}|}
{|A_{Mess}|}
]

Dadurch wird die Generatoramplitude automatisch angepasst.

---

## Abbruchbedingungen

Die Regelung endet wenn

* Ziel erreicht
* maximale Schrittzahl erreicht
* Generator-Maximalspannung erreicht
* Mindestspannung erreicht
* Clipping erkannt

---

# Automatischer Frequenz-Sweep

Der Sweep läuft beispielsweise

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

Für jede Frequenz wird die komplette Regelung erneut durchgeführt.

Am Ende erhält man

* Generator-Spannung
* Amplitude vor Regelung
* Amplitude nach Regelung
* Fehler
* Anzahl der Regelschritte

---

# Ausgabe

Während der Messung werden

* Live-Plots
* Tabellen
* Log-Dateien

aktualisiert.

Nach Abschluss können sämtliche Ergebnisse gespeichert werden.

---

# Messablauf (Gesamtübersicht)

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
Generator erzeugt Sinus
        │
        ▼
Signalaufnahme
        │
        ▼
Signalverarbeitung
        │
        ▼
FFT
        │
        ▼
P1 P2 P3 berechnen
        │
        ▼
Least-Squares
        │
        ▼
A und B bestimmen
        │
        ▼
Soll-Ist-Vergleich
        │
        ▼
Generator nachregeln
        │
        ▼
Messung wiederholen
        │
        ▼
Ergebnisse darstellen
        │
        ▼
Speichern
```

---

# Verwendete Hardware

* Agilent 33120A Funktionsgenerator
* Focusrite Scarlett Audio Interface
* drei Kondensatormikrofone
* Messrohr
* Raspberry Pi Pico (für spätere Erweiterungen möglich)

---

# Verwendete Bibliotheken

* Python 3
* NumPy
* PySide6
* PyQtGraph
* SoundDevice
* PyVISA

---

# Ziel des Projekts

Das System ermöglicht die automatische Erzeugung einer konstanten Schalldruckamplitude der hinlaufenden Welle über einen gesamten Frequenzbereich. Dadurch können frequenzabhängige Eigenschaften eines Messobjekts reproduzierbar untersucht werden. Die Software trennt die Signalverarbeitung konsequent von der grafischen Benutzeroberfläche, unterstützt sowohl reale Messhardware als auch Simulationen und bietet eine automatische Pegelregelung zur Verbesserung der Messgenauigkeit. Diese Beschreibung basiert auf der Struktur und den Funktionen der bereitgestellten Projektdateien.    
