# Akustik-Messsystem

Dieses Projekt ist ein Python-Programm zur akustischen Messung in einem 1D-Schallkanal.  
Es dient zur Aufnahme und Analyse von Mikrofonsignalen, zur FFT-Auswertung und zur Zerlegung der gemessenen Schalldrücke in hinlaufende und rücklaufende Wellen.

## Ziel des Projekts

Das Ziel ist die automatisierte Messung akustischer Signale im Schallkanal.

Dabei werden drei Mikrofone verwendet, um die komplexen Schalldruck-Amplituden

- `P1`
- `P2`
- `P3`

bei einer Messfrequenz `f0` zu bestimmen.

Aus diesen drei komplexen Werten werden anschließend berechnet:

- `A`: hinlaufende Welle
- `B`: rücklaufende / reflektierte Welle
- `|B| / |A|`: Reflexionsfaktor-Betrag
- Residuum als Qualitätsmaß der Wellenzerlegung

Die automatische Regelung passt die Generator-Spannung so an, dass der Betrag der hinlaufenden Welle `|A|` konstant bleibt.

## Projektstruktur

```text
.
├── gui.py
├── focusrite_interface.py
├── generator_interface.py
├── estimation.py
├── automation.py
├── compensation.py
└── metrics.py

python3 "/Users/alaa/Library/Mobile Documents/com~apple~CloudDocs/MASTER/Sensorik/py/acoustic_rohr_project/src/acoustics/gui.py"


_build_ui()          → baut die Oberfläche
_connect_signals()   → verbindet Buttons mit Funktionen
record_for_time()    → nimmt 1 Sekunde auf und startet Auswertung
_get_f0()            → liefert die Messfrequenz
compute_fft...       → berechnet Frequenzspektrum
measure_at_frequency → berechnet Amplitude und Phase bei f0
SignalPlotDialog     → öffnet großen Plot
LogDialog            → öffnet großes Log-Fenster

cd "/Users/alaa/Library/Mobile Documents/com~apple~CloudDocs/MASTER/Sensorik/py"

