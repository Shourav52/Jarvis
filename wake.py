"""Wake word 'Hey Jarvis' (openWakeWord). Local e cholay: internet ba API lagbe na.

Audio Groq e shudhu 'Hey Jarvis' shonar PORE jay; ager shob kichu Mac er bhitor e thake.
Prothom bar 3ta chhoto model file (~ kichu MB) download hoy; tarpor offline-i cholbe.
"""
import os
import subprocess
import urllib.request

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
FRAME = 1280                                            # 80 ms, openWakeWord er pochondo
THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.5"))   # kom = beshi sensitive
DEBUG = os.getenv("WAKE_DEBUG") == "1"                  # score dekhte: WAKE_DEBUG=1

MODEL_FILES = ["melspectrogram.onnx", "embedding_model.onnx", "hey_jarvis_v0.1.onnx"]
URLS = [
    "https://github.com/dscripka/openWakeWord/raw/main/openwakeword/resources/models/{f}",
    "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/{f}",
]


def models_dir():
    import openwakeword
    return os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")


def _fetch(url, dest):
    """curl diye, na hole Python diye download. (ok, error)"""
    tmp = dest + ".part"
    ok, err = False, ""
    try:
        r = subprocess.run(["curl", "-L", "--fail", "--silent", "--show-error",
                            "--connect-timeout", "10", "--max-time", "120", "-o", tmp, url],
                           capture_output=True, text=True)
        ok = r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 10000
        err = r.stderr.strip()
    except Exception as e:
        err = str(e)
    if not ok:
        try:
            urllib.request.urlretrieve(url, tmp)
            ok = os.path.getsize(tmp) > 10000
        except Exception as e:
            err = str(e)
    if ok:
        os.replace(tmp, dest)
        return True, ""
    if os.path.exists(tmp):
        os.remove(tmp)
    return False, err


def ensure_models():
    folder = models_dir()
    os.makedirs(folder, exist_ok=True)
    for f in MODEL_FILES:
        dest = os.path.join(folder, f)
        if os.path.exists(dest):
            continue
        print(f"Wake word file download hocche: {f}")
        err = ""
        for url in URLS:
            ok, err = _fetch(url.format(f=f), dest)
            if ok:
                break
        else:
            links = "\n  ".join(URLS[0].format(f=x) for x in MODEL_FILES)
            raise RuntimeError(
                f"{f} download hoyni ({err}).\n"
                f"Browser e ei 3ta file download kore ei folder e rakho:\n  {folder}\nLinks:\n  {links}")


class WakeWord:
    def __init__(self):
        ensure_models()
        from openwakeword.model import Model

        explicit = os.path.join(models_dir(), "hey_jarvis_v0.1.onnx")
        self.model, last_err = None, None
        for name in (explicit, "hey_jarvis", "hey_jarvis_v0.1"):
            try:
                self.model = Model(wakeword_models=[name], inference_framework="onnx")
                break
            except Exception as e:
                last_err = e
        if self.model is None:
            raise RuntimeError(f"hey_jarvis model load hoyni: {last_err}")

    def wait(self):
        """'Hey Jarvis' na shona porjonto opekkha kore. Ctrl+C dile KeyboardInterrupt."""
        try:
            self.model.reset()
        except Exception:
            pass
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=FRAME) as stream:
            while True:
                data, _ = stream.read(FRAME)
                scores = self.model.predict(np.asarray(data).flatten())
                best = max(scores.values()) if scores else 0.0
                if DEBUG and best > 0.2:
                    
                    print(f"(wake score {best:.2f})")
                if best >= THRESHOLD:
                    return True
                
