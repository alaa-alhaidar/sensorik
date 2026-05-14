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