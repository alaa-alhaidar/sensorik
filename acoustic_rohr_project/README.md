Die gesamte Reihenfolge ist so:

## 1. Start in der GUI

Du hast zwei getrennte Abläufe:

### Frequenzschleife

* Frequenzen werden nacheinander durchlaufen.
* Die Generator-Spannung bleibt konstant.
* Jede Frequenz wird genau einmal gemessen.
* Es gibt keine Anpassung auf (60,\mu V).

### Automation

* Frequenzen werden ebenfalls nacheinander durchlaufen.
* Bei jeder Frequenz wird die Generator-Spannung angepasst.
* Ziel ist:

[
|A| = 60,\mu V
]

* Danach wird die gefundene Spannung für diese Frequenz gespeichert.

---

# 2. Generator setzt Frequenz und Spannung

Für jeden Frequenzpunkt wird ausgeführt:

```python
generator.set_output(f0, voltage)
```

Das bedeutet:

[
f_0 \rightarrow \text{Generatorfrequenz}
]

[
U \rightarrow \text{Generatorspannung}
]

Bei der normalen Frequenzschleife bleibt (U) gleich.

Bei der Automation wird (U) mehrfach verändert, bis (|A|) im Toleranzbereich liegt. 

---

# 3. Signalaufnahme

Danach werden die drei Mikrofonsignale aufgenommen:

[
p_1(t),\quad p_2(t),\quad p_3(t)
]

Bei der echten Messung kommen diese Signale von der Focusrite.

Bei der Simulation werden sie künstlich erzeugt.

Die Aufnahme hat die Form:

```python
signal.shape = (samples, 3)
```

Also:

```text
Zeitpunkt 1: M1, M2, M3
Zeitpunkt 2: M1, M2, M3
Zeitpunkt 3: M1, M2, M3
...
```

---

# 4. Kalibrierung

Jeder Mikrofonkanal wird mit seinem Kalibrierfaktor multipliziert:

```python
signal[:, ch] *= CALIBRATION[ch + 1]
```

Dadurch werden die aufgenommenen digitalen Werte auf die verwendete Spannungsskalierung gebracht. 

---

# 5. Bekannte Messfrequenz (f_0)

Beim Sweep und bei der Automation ist (f_0) bereits bekannt.

Beispiel:

```text
300 Hz
350 Hz
400 Hz
...
1950 Hz
```

Die FFT muss die Frequenz dann nicht erst suchen.

Sie dient hauptsächlich zur Kontrolle:

* liegt der Peak tatsächlich bei (f_0)?
* gibt es Rauschen?
* gibt es Oberwellen?

---

# 6. Komplexe Amplitude jedes Mikrofons

Aus jedem Zeitsignal wird die komplexe Amplitude genau bei (f_0) bestimmt:

[
P_i(f_0)
========

\frac{2}{\sum w[n]}
\sum_n p_i[n],w[n],e^{-j2\pi f_0n/f_s}
]

Damit erhältst du:

[
P_1,\quad P_2,\quad P_3
]

Jeder Wert ist komplex:

[
P_i = \operatorname{Re}(P_i)+j\operatorname{Im}(P_i)
]

Daraus folgen:

[
|P_i|
]

und

[
\varphi_i=\arg(P_i)
]

Das ist wichtig, weil für die Wellenzerlegung nicht nur der Betrag, sondern auch die Phase gebraucht wird. 

---

# 7. FFT

Parallel wird aus dem Zeitsignal die FFT berechnet:

[
p_i(t)\rightarrow P_i(f)
]

Die FFT liefert für viele Frequenz-Bins komplexe Werte.

Für den Plot wird meistens nur der Betrag beziehungsweise der Pegel gezeigt:

[
20\log_{10}
\left(
\frac{|P_i(f)|_\mathrm{RMS}}{1,\mu V}
\right)
]

Beim Sweep ist diese FFT nicht die Grundlage für (A) und (B), sondern vor allem eine Kontrolle.

---

# 8. Wellenmodell im Rohr

Für jedes Mikrofon gilt:

[
P(x)=Ae^{-jkx}+Be^{jkx}
]

Dabei ist:

* (A): hinlaufende Welle
* (B): rücklaufende Welle
* (k): Wellenzahl

[
k=\frac{2\pi f_0}{c}
]

Für drei Mikrofone entsteht:

[
\begin{bmatrix}
P_1\
P_2\
P_3
\end{bmatrix}
=============

\begin{bmatrix}
e^{-jkx_1} & e^{jkx_1}\
e^{-jkx_2} & e^{jkx_2}\
e^{-jkx_3} & e^{jkx_3}
\end{bmatrix}
\begin{bmatrix}
A\
B
\end{bmatrix}
]

---

# 9. Least-Squares-Wellenzerlegung

Du hast drei Messungen, aber nur zwei Unbekannte:

[
A,\quad B
]

Deshalb ist das System überbestimmt.

NumPy löst es mit:

```python
solution, residuals, _, _ = np.linalg.lstsq(M, b, rcond=None)
```

Das Ergebnis ist:

```python
A = solution[0]
B = solution[1]
```

Also komplexe Werte:

[
A=|A|e^{j\varphi_A}
]

[
B=|B|e^{j\varphi_B}
]



---

# 10. Beträge von (A) und (B)

Aus den komplexen Werten werden die Beträge berechnet:

[
|A|=\sqrt{\operatorname{Re}(A)^2+\operatorname{Im}(A)^2}
]

[
|B|=\sqrt{\operatorname{Re}(B)^2+\operatorname{Im}(B)^2}
]

Diese Werte erscheinen im Graphen:

```text
A und B über Frequenz
```

Wichtig:

[
|A|,\ |B|
]

sind Amplituden.

Die Leistung beziehungsweise Energie ist proportional zum Quadrat:

[
E_A\propto |A|^2
]

[
E_B\propto |B|^2
]

---

# 11. Reflexion und Dissipation

Der komplexe Reflexionsfaktor ist:

[
r=\frac{B}{A}
]

Der Amplitudenreflexionsfaktor ist:

[
|r|=\frac{|B|}{|A|}
]

Der reflektierte Energieanteil ist:

[
R=|r|^2
]

Die Dissipation ist:

[
D=1-R
]

Also:

```text
A, B
→ r = B/A
→ R = |r|²
→ D = 1 - R
```



---

# 12. Automation

Bei der Automation wird nach jeder Messung geprüft:

[
\text{Fehler}
=============

\frac{A_\text{Ziel}-A_\text{gemessen}}
{A_\text{Ziel}}
]

Dann wird die Spannung korrigiert:

[
U_\text{neu}
============

U_\text{alt}
\cdot
\frac{A_\text{Ziel}}
{A_\text{gemessen}}
]

Beispiel:

[
A_\text{Ziel}=60,\mu V
]

[
A_\text{gemessen}=40,\mu V
]

Dann:

[
U_\text{neu}
============

# U_\text{alt}\cdot\frac{60}{40}

1.5U_\text{alt}
]

Danach wird erneut gemessen.

Das wird wiederholt, bis:

[
57,\mu V\le |A|\le63,\mu V
]

bei (5%) Toleranz.

---

# 13. Automation-Graph

Oben:

* X-Achse: Frequenz
* Y-Achse: (|A|) und (|B|)
* Ziel-Linie bei (60,\mu V)
* untere Toleranz bei (57,\mu V)
* obere Toleranz bei (63,\mu V)

Unten:

* X-Achse: Frequenz
* Y-Achse: benötigte Generator-Spannung

Also:

[
f\rightarrow U_\text{passend}
]

---

# 14. Normale Frequenzschleife

Bei der normalen Frequenzschleife gibt es keine Spannungsanpassung.

Die Reihenfolge ist nur:

```text
Frequenz setzen
→ Signal aufnehmen
→ P1, P2, P3 berechnen
→ A, B berechnen
→ R, D berechnen
→ nächsten Frequenzpunkt messen
```

Die Spannung bleibt dabei immer gleich.

---

## Gesamte Kette

[
\boxed{
f_0,U
\rightarrow
p_1(t),p_2(t),p_3(t)
\rightarrow
P_1(f_0),P_2(f_0),P_3(f_0)
\rightarrow
A(f_0),B(f_0)
\rightarrow
|A|,|B|
\rightarrow
R,D
}
]

Bei der Automation kommt danach noch:

[
|A|\text{ prüfen}
\rightarrow
U\text{ anpassen}
\rightarrow
erneut messen
]

bis der Zielbereich erreicht ist.
