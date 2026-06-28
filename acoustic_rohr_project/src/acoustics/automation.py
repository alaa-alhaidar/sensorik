import numpy as np


def mean_microphone_amplitude(m):
    return (m["amp1"] + m["amp2"] + m["amp3"]) / 3.0


def update_voltage_from_amplitude(
    voltage,
    target_amp,
    measured_amp,
    min_voltage=0.01,
    max_voltage=1.0, # 1V ist die maximale Spannung, die der Generator liefern kann
):
    correction = target_amp / (measured_amp + 1e-12) # Ziel-Amplitude geteilt durch gemessene Amplitude
    new_voltage = voltage * correction # neue Spannung berechnen
    return max(min_voltage, min(new_voltage, max_voltage)) # neue Spannung auf erlaubten Bereich beschränken


def amplitude_reached_target(measured_amp, target_amp, tolerance):
    relative_error = (target_amp - measured_amp) / target_amp # relativer Fehler berechnen
    return abs(relative_error) <= tolerance, relative_error


def is_clipping_error(error):
    return "Clipping-Gefahr" in str(error)


def run_auto_measurement_steps(
    generator,
    f0,
    start_voltage,
    target_amp,
    tolerance,
    max_steps,
    min_voltage,
    max_voltage,
    duration,
    measure_once,
    compute_wave,
):
    """
    Führt automatische Messung für eine Frequenz aus.

    Diese Funktion kennt keine GUI:
    - kein QMessageBox
    - kein Plot
    - kein PySide6
    """

    voltage = float(start_voltage)
    results = []

    generator.set_sine()
    generator.output_on()

    for step in range(1, max_steps + 1):
        generator.set_output(f0, voltage)

        try:
            measurement_result = measure_once(duration, f0)
        except ValueError as error:
            if is_clipping_error(error) and results:
                last_valid = results[-1]
                last_valid["voltage_after_regulation"] = last_valid["voltage"]
                last_valid["ok"] = False
                last_valid["clipping_stopped"] = True
                last_valid["clipping_message"] = str(error)
                break
            if is_clipping_error(error) and voltage > min_voltage:
                voltage = min_voltage
                continue
            raise

        if measurement_result is None:
            raise RuntimeError("Messung fehlgeschlagen.")

        m = measurement_result["m"]
        wave = compute_wave(m, f0)

        measured_A_abs = wave["A_abs"]

        ok, relative_error = amplitude_reached_target(
            measured_A_abs,
            target_amp,
            tolerance,
        )

        step_result = {
            "step": step,
            "frequency": f0,
            "voltage": voltage,
            "voltage_before_regulation": voltage,
            "measurement_result": measurement_result,
            "m": m,
            "wave": wave,
            "measured_A_abs": measured_A_abs,
            "ok": ok,
            "relative_error": relative_error,
        }

        if ok:
            step_result["voltage_after_regulation"] = voltage
            results.append(step_result)
            break

        new_voltage = update_voltage_from_amplitude(
            voltage,
            target_amp,
            measured_A_abs,
            min_voltage,
            max_voltage,
        )

        if step >= max_steps:
            step_result["voltage_after_regulation"] = voltage
            results.append(step_result)
            break

        step_result["voltage_after_regulation"] = new_voltage
        results.append(step_result)

        # Wenn |A| zu groß ist und die berechnete Spannung unter das Minimum fällt,
        # dann nicht sofort abbrechen, sondern einmal mit Minimalspannung neu messen.
        if new_voltage <= min_voltage and measured_A_abs > target_amp:
            if voltage <= min_voltage:
                break
            voltage = min_voltage
            continue

        # Wenn |A| zu klein ist und die berechnete Spannung am Maximum liegt,
        # kann die Zielamplitude nicht erreicht werden.
        if new_voltage >= max_voltage and measured_A_abs < target_amp:
            if voltage >= max_voltage:
                break
            voltage = max_voltage
            continue

        voltage = new_voltage

    return results


def run_frequency_sweep_steps(
    generator,
    frequencies,
    voltage,
    duration,
    measure_once,
    compute_wave,
    on_frequency_result=None,
    should_cancel=None,
):
    """
    Führt eine Frequenzschleife ohne Amplitudenregelung aus.

    Für jede Frequenz:
    - gleiche Generator-Spannung
    - genau eine Messung
    - keine Anpassung an TARGET_AMP
    """

    sweep_results = []
    voltage = float(voltage)

    generator.set_sine()
    generator.output_on()

    for f0 in frequencies:
        if should_cancel is not None and should_cancel():
            break

        f0 = float(f0)
        generator.set_output(f0, voltage)

        measurement_result = measure_once(duration, f0)
        if measurement_result is None:
            raise RuntimeError(f"Messung bei {f0:.1f} Hz fehlgeschlagen.")

        m = measurement_result["m"]
        wave = compute_wave(m, f0)

        step_result = {
            "step": 1,
            "frequency": f0,
            "voltage": voltage,
            "voltage_before_regulation": voltage,
            "voltage_after_regulation": voltage,
            "measurement_result": measurement_result,
            "m": m,
            "wave": wave,
            "measured_A_abs": wave["A_abs"],
            "ok": True,
            "relative_error": 0.0,
        }

        frequency_result = {
            "frequency": f0,
            "voltage": voltage,
            "A_abs": wave["A_abs"],
            "B_abs": wave["B_abs"],
            "B_over_A": wave["B_over_A"],
            "reflection_energy": wave["reflection_energy"],
            "dissipation": wave["dissipation"],
            "dissipation_percent": wave["dissipation_percent"],
            "residual": wave["residual"],
            "wave": wave,
            "step_results": [step_result],
        }

        sweep_results.append(frequency_result)

        if on_frequency_result is not None:
            on_frequency_result(frequency_result, list(sweep_results))

        if should_cancel is not None and should_cancel():
            break

    return sweep_results

def run_automatic_frequency_sweep_steps(
    generator,
    frequencies,
    start_voltage,
    target_amp,
    tolerance,
    max_steps,
    min_voltage,
    max_voltage,
    duration,
    measure_once,
    compute_wave,
    on_frequency_result=None,
    should_cancel=None,
):
    """
    Automatischer Frequenz-Sweep mit Amplitudenregelung.

    Für jede Frequenz wird run_auto_measurement_steps() ausgeführt,
    bis |A| innerhalb der Toleranz am TARGET_AMP liegt.
    Die zuletzt gefundene Spannung wird als Startwert für die nächste
    Frequenz verwendet.
    """

    sweep_results = []
    voltage = float(start_voltage)

    generator.set_sine()
    generator.output_on()

    for f0 in frequencies:
        if should_cancel is not None and should_cancel():
            break

        f0 = float(f0)

        try:
            step_results = run_auto_measurement_steps(
                generator=generator,
                f0=f0,
                start_voltage=voltage,
                target_amp=target_amp,
                tolerance=tolerance,
                max_steps=max_steps,
                min_voltage=min_voltage,
                max_voltage=max_voltage,
                duration=duration,
                measure_once=measure_once,
                compute_wave=compute_wave,
            )
        except ValueError as error:
            if is_clipping_error(error):
                voltage = float(min_voltage)
                continue
            raise

        if not step_results:
            continue

        last = step_results[-1]
        first = step_results[0]
        wave = last["wave"]

        # Gefundene Spannung als Startwert für nächste Frequenz übernehmen.
        voltage = float(last.get("voltage_after_regulation", last["voltage"]))

        frequency_result = {
            "frequency": f0,
            "voltage": voltage,
            "voltage_before_regulation": float(first.get("voltage_before_regulation", first["voltage"])),
            "voltage_after_regulation": float(last.get("voltage_after_regulation", last.get("voltage", voltage))),
            "A_abs_before_regulation": float(first.get("measured_A_abs", first["wave"]["A_abs"])),
            "A_abs_after_regulation": float(last.get("measured_A_abs", wave["A_abs"])),
            "A_abs": wave["A_abs"],
            "B_abs": wave["B_abs"],
            "B_over_A": wave["B_over_A"],
            "reflection_energy": wave["reflection_energy"],
            "dissipation": wave["dissipation"],
            "dissipation_percent": wave["dissipation_percent"],
            "residual": wave["residual"],
            "wave": wave,
            "step_results": step_results,
            "regulation_enabled": True,
            "target_reached": bool(last["ok"]),
        }

        sweep_results.append(frequency_result)

        if on_frequency_result is not None:
            on_frequency_result(frequency_result, list(sweep_results))

        if should_cancel is not None and should_cancel():
            break

    return sweep_results
