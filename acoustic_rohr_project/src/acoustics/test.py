import sounddevice as sd
import numpy as np

device = 2      # MacBook Air Microphone
fs = 48000
duration = 3
channels = 1

x = sd.rec(
    int(duration * fs),
    samplerate=fs,
    channels=channels,
    device=device,
    dtype="float32",
    blocking=True,
)
sd.wait()

print("max =", np.max(np.abs(x)))
print("rms =", np.sqrt(np.mean(x**2)))