import numpy as np


def mean_microphone_amplitude(m):
    return (m["amp1"] + m["amp2"] + m["amp3"]) / 3.0


def update_voltage_from_amplitude(
    voltage,
    target_amp,
    measured_amp,
    min_voltage=0.01,
    max_voltage=1.0,
):
    correction = target_amp / (measured_amp + 1e-12)
    new_voltage = voltage * correction
    return max(min_voltage, min(new_voltage, max_voltage))


def amplitude_reached_target(measured_amp, target_amp, tolerance):
    relative_error = (target_amp - measured_amp) / target_amp
    return abs(relative_error) <= tolerance, relative_error


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

        measurement_result = measure_once(duration, f0)
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
            "measurement_result": measurement_result,
            "m": m,
            "wave": wave,
            "measured_A_abs": measured_A_abs,
            "ok": ok,
            "relative_error": relative_error,
        }

        results.append(step_result)

        if ok:
            break

        if voltage >= max_voltage:
            break

        voltage = update_voltage_from_amplitude(
            voltage,
            target_amp,
            measured_A_abs,
            min_voltage,
            max_voltage,
        )

    return results


def run_frequency_sweep_steps(
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
):
    """
    Führt Frequenzschleife aus.

    Auch diese Funktion kennt keine GUI.
    Sie gibt nur Daten zurück.
    """

    sweep_results = []

    generator.set_sine()
    generator.output_on()

    for f0 in frequencies:
        step_results = run_auto_measurement_steps(
            generator=generator,
            f0=f0,
            start_voltage=start_voltage,
            target_amp=target_amp,
            tolerance=tolerance,
            max_steps=max_steps,
            min_voltage=min_voltage,
            max_voltage=max_voltage,
            duration=duration,
            measure_once=measure_once,
            compute_wave=compute_wave,
        )

        last = step_results[-1]
        wave = last["wave"]

        sweep_results.append({
            "frequency": f0,
            "voltage": last["voltage"],
            "A_abs": wave["A_abs"],
            "B_abs": wave["B_abs"],
            "B_over_A": wave["B_over_A"],
            "reflection_energy": wave["reflection_energy"],
            "dissipation_percent": wave["dissipation_percent"],
            "residual": wave["residual"],
            "step_results": step_results,
        })

    return sweep_results