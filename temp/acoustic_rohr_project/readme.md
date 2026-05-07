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

rm -rf .git
rm -rf acoustic_rohr_project/.git

cat > .gitignore << 'EOF'
venv/
__pycache__/
*.pyc
.DS_Store
EOF

git init
git branch -M main

git add .
git commit -m "Initial commit"

git remote add origin https://github.com/alaa-alhaidar/sensorik.git
git push -u origin main --force