import numpy as np
import sounddevice as sd

from focusrite_interface import FocusriteInterface
from signal_process import measure_at_frequency_by_f0


SAMPLE_RATE = 48000
DURATION = 2.0
DEVICE_INDEX = 36     # bei dir laut GUI: Index 2
CHANNELS = 8          # erstmal alle 8 lesen
F0 = 203.12           # oder Generatorfrequenz, z.B. 1000.0


def main():
    print("=== Audio-Geräte ===")
    devices = sd.query_devices()

    for idx, dev in enumerate(devices):
        print(
            f"Index {idx}: "
            f"name='{dev['name']}', "
            f"inputs={dev['max_input_channels']}, "
            f"outputs={dev['max_output_channels']}, "
            f"default_samplerate={dev['default_samplerate']}"
        )

    print("\n=== Aufnahme ===")
    print(
        f"Device={DEVICE_INDEX}, "
        f"Kanäle={CHANNELS}, "
        f"fs={SAMPLE_RATE}, "
        f"Dauer={DURATION}s"
    )

    interface = FocusriteInterface(
        sample_rate=SAMPLE_RATE,
        device=DEVICE_INDEX,
        channels=CHANNELS,
    )

    audio = interface.record_input(DURATION)

    print("\nSignal shape:", audio.shape)
    print("Bedeutung: (Samples, Kanäle)")

    print("\n=== Kanal-Analyse ===")

    for ch in range(audio.shape[1]):
        x = audio[:, ch]

        rms = np.sqrt(np.mean(x ** 2))
        peak = np.max(np.abs(x))
        dbfs = 20.0 * np.log10(peak + 1e-12)

        P, amp_f0, phase, rms2 = measure_at_frequency_by_f0(
            x,
            f0=F0,
            sample_rate=SAMPLE_RATE,
        )

        print(
            f"Kanal {ch + 1}: "
            f"RMS={rms:.6e}, "
            f"Peak={peak:.6e}, "
            f"Peak={dbfs:.2f} dBFS, "
            f"|P(f0)|={amp_f0:.6e}, "
            f"Phase={phase:.3f} rad"
        )

        if peak > 0.707:
            print("  WARNUNG: über -3 dBFS, Clipping-Gefahr.")

    print("\nFertig.")


if __name__ == "__main__":
    main()