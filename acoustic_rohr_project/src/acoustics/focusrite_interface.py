import queue
import numpy as np
import sounddevice as sd

# https://python-sounddevice.readthedocs.io/en/0.5.3/usage.html#recording
class FocusriteInterface:
    def __init__(self, sample_rate=48000, device=None, dtype="float32", channels=3):
        self.sample_rate = int(sample_rate)
        self.device = device
        self.dtype = dtype
        self.channels = int(channels)
        self.blocksize = self.sample_rate
        self.stream = None
        self.audio_queue = queue.Queue()

    def list_focusrite_input_devices(self):
        devices = sd.query_devices()
        result = []

        for idx, dev in enumerate(devices):
            name = dev["name"].lower()
            input_channels = int(dev["max_input_channels"])

            if input_channels > 0:
                result.append((idx, dev["name"], input_channels))

        return result

    def _get_device(self):
        if self.device is not None:
            dev_info = sd.query_devices(self.device, "input")
            name = dev_info["name"].lower()
            max_inputs = int(dev_info["max_input_channels"])

            if max_inputs < self.channels:
                raise ValueError(
                    f"Das Gerät hat nur {max_inputs} Eingangskanäle. "
                    f"Benötigt werden {self.channels}."
                )

            return self.device

        devices = self.list_focusrite_input_devices()
        if not devices:
            raise ValueError("Kein Eingabegerät gefunden.")

        device_index, _, input_channels = devices[0]

        if input_channels < self.channels:
            raise ValueError(
                f"Das gefundene Focusrite hat nur {input_channels} Eingangskanäle. "
                f"Benötigt werden {self.channels}."
            )

        return device_index

    def record_input(self, duration):
        """
        Nimmt duration Sekunden mit mehreren Kanälen auf:
        Rückgabe (samples, channels).
        """
        if duration is None or duration <= 0:
            duration = 1.0
        duration = float(duration)
        device_to_use = self._get_device()
        num_samples = int(round(self.sample_rate * duration))

        audio = sd.rec(
            frames=num_samples,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            device=device_to_use,
            blocking=True,
        )
        sd.wait()

        audio = np.asarray(audio, dtype=np.float64)
        print(f"Aufnahme abgeschlossen: {audio.shape[0]} Samples, {audio.shape[1]} Kanäle.")
        return audio

    def start_input_stream(self):
        """Startet Live-Stream mit 3 Kanälen."""
        device_to_use = self._get_device()

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=2048,
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

        chunk = indata[:, : self.channels].copy()
        self.audio_queue.put(("audio", chunk))

    def stop_input_stream(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
