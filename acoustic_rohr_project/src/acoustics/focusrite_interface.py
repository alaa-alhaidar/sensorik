import queue
import numpy as np
import sounddevice as sd


class FocusriteInterface:
    def __init__(
        self,
        sample_rate=48000,
        device=None,
        dtype="float32",
        channels=3,
    ):
        self.sample_rate = int(sample_rate)
        self.device = device
        self.dtype = dtype
        self.channels = int(channels)

        # Kleiner Block für Live-Plot.
        # 2048 Samples bei 48 kHz ≈ 42,7 ms
        self.blocksize = 2048

        self.stream = None
        self.audio_queue = queue.Queue()

    def list_focusrite_input_devices(self):
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        result = []

        print("=" * 80)
        print("ALLE AUDIO-GERÄTE:")
        for idx, dev in enumerate(devices):
            hostapi_name = hostapis[dev["hostapi"]]["name"]
            input_channels = int(dev["max_input_channels"])
            output_channels = int(dev["max_output_channels"])

            print(
                f"{idx}: {dev['name']} | "
                f"HostAPI={hostapi_name} | "
                f"Inputs={input_channels} | Outputs={output_channels}"
            )

            if input_channels > 0:
                result.append((idx, f"{dev['name']} [{hostapi_name}]", input_channels))

        print("=" * 80)

        return result

    def _get_device(self):
        """
        Gibt das ausgewählte Eingabegerät zurück.
        Es werden jetzt alle Eingabegeräte erlaubt.
        """
        if self.device is not None:
            dev_info = sd.query_devices(self.device, "input")
            max_inputs = int(dev_info["max_input_channels"])

            if max_inputs < self.channels:
                raise ValueError(
                    f"Das ausgewählte Gerät hat nur {max_inputs} Eingangskanäle. "
                    f"Benötigt werden {self.channels}."
                )

            return self.device

        devices = self.list_focusrite_input_devices()

        if not devices:
            raise ValueError("Kein Eingabegerät gefunden.")

        device_index, _, input_channels = devices[0]

        if input_channels < self.channels:
            raise ValueError(
                f"Das gefundene Eingabegerät hat nur {input_channels} Eingangskanäle. "
                f"Benötigt werden {self.channels}."
            )

        return device_index

    def record_input(self, duration=1.0):
        """
        Nimmt duration Sekunden mit mehreren Kanälen auf.
        Rückgabe-Form: (samples, channels)
        """
        device_to_use = self._get_device()

        if duration is None or isinstance(duration, bool):
            duration = 1.0

        duration = float(duration)

        if duration <= 0:
            duration = 1.0

        num_samples = int(round(self.sample_rate * duration))

        if num_samples < 2:
            raise ValueError(
                f"Aufnahme zu kurz: duration={duration}, num_samples={num_samples}"
            )

        audio = sd.rec(
            frames=num_samples,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            device=device_to_use,
            blocking=True,
        )

        audio = np.asarray(audio, dtype=np.float64)

        if audio.size == 0:
            raise ValueError("Das Eingabegerät hat keine Samples geliefert.")

        return audio

    def start_input_stream(self):
        """
        Startet Live-Stream mit mehreren Kanälen.
        """
        device_to_use = self._get_device()

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            device=device_to_use,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
        )

        self.stream.start()
        return device_to_use

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self.audio_queue.put(("status", str(status)))

        chunk = indata[:, :self.channels].copy()
        self.audio_queue.put(("audio", chunk))

    def stop_input_stream(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None