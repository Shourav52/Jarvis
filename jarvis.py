"""
Jarvis - Dhap 1: Voice -> Whisper -> LLM -> Voice reply
Enter chapo, kotha bolo, thamle Jarvis uttor dibe.
(Wake word pore add hobe.)
"""
import asyncio
import os
import tempfile
import time
import re
import edge_tts
import numpy as np
import pygame
import sounddevice as sd
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from openai import OpenAI
from scipy.io import wavfile

load_dotenv()

# ---------- Settings ----------
SAMPLE_RATE = 16000
CHUNK_SEC = 0.1
SILENCE_THRESHOLD = 0.008   # mic khub sensitive/kom hole eta change korov
SILENCE_END_SEC = 2.0       # eto sec chup thakle recording shesh
WAIT_START_SEC = 10         # eto sec er moddhe kotha na bolle cancel
MAX_RECORD_SEC = 30

WHISPER_MODEL = "small"     # kom power e "base", valo accuracy te "medium"
LANGUAGE = "en"
VOICES = {"bn": "bn-BD-NabanitaNeural", "en": "en-US-AriaNeural"}

SYSTEM_PROMPT = """You are Jarvis, a personal voice assistant of Shorov, a software
engineering student and MERN/Next.js developer.
- Reply in the same language the user spoke. If Bangla, write in Bangla script.
- Keep replies short (1-3 sentences) because they are spoken aloud.
- No markdown, no bullet points, no emojis.
- If the request is unclear, ask ONE short clarifying question first.
- Explain things simply with a small example."""

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
)
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

print("Whisper model load hocche (prothom bar ektu somoy lagbe)...")
stt = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
pygame.mixer.init()

history = [{"role": "system", "content": SYSTEM_PROMPT}]


def record_until_silence():
    """Mic theke kotha record kore, chup hole thame. Kotha na bolle None."""
    chunk = int(SAMPLE_RATE * CHUNK_SEC)
    frames, started, silent = [], False, 0
    t0 = time.time()
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                        dtype="float32", blocksize=chunk) as stream:
        while True:
            data, _ = stream.read(chunk)
            rms = float(np.sqrt(np.mean(data ** 2)))
            if rms > SILENCE_THRESHOLD:
                started, silent = True, 0
                frames.append(data)
            elif started:
                frames.append(data)
                silent += 1
                if silent * CHUNK_SEC >= SILENCE_END_SEC:
                    break
            elif time.time() - t0 > WAIT_START_SEC:
                return None
            if time.time() - t0 > MAX_RECORD_SEC:
                break
    return np.concatenate(frames) if frames else None


def transcribe(audio):
    """Audio -> (text, language code)."""
    samples = audio.flatten().astype(np.float32)
    segments, info = stt.transcribe(samples, beam_size=1, vad_filter=True, language=LANGUAGE)
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, info.language


def ask_llm(user_text):
    history.append({"role": "user", "content": user_text})
    resp = client.chat.completions.create(model=LLM_MODEL, messages=history)
    reply = resp.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    return reply



def speak(text, lang):
    voice = VOICES.get(lang, VOICES["en"])
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        path = f.name
    asyncio.run(edge_tts.Communicate(text, voice).save(path))
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)
    pygame.mixer.music.unload()
    os.remove(path)

END_WORDS = {"bye", "goodbye", "stop", "exit" ,"stop jarvis","quit", "shesh", "bondho", "thik ache", "thik aache", "thik achhe", "thik aachhe"}
def is_echo(text, last_reply):
    """Jarvis er nijer kotha mic e dhukle ota ignore kore."""
    if not last_reply:
        return False
    a = set(re.sub(r"[^a-z' ]", "", text.lower()).split())
    b = set(re.sub(r"[^a-z' ]", "", last_reply.lower()).split())
    return len(a) >= 2 and len(a & b) / len(a) >= 0.6


def is_end_command(text):
    cleaned = re.sub(r"[^a-z' ]", "", text.lower()).strip()
    words = cleaned.split()
    return cleaned == "thats all" or (len(words) <= 10 and any(w in END_WORDS for w in words))
def main():
    print("Jarvis ready. Enter chepe shuru koro. Bondho korte Ctrl+C.\n")
    while True:
        input("[Enter chapo] ")
        print("Conversation shuru. 'bye' bolle ba 10 sec chup thakle shesh hobe.\n")
        last_reply = ""
        while True:
            print("Shunchi...")
            audio = record_until_silence()
            if audio is None:
                print("Kono kotha shunini, conversation shesh.\n")
                break
            text, lang = transcribe(audio)
            if not text:
                continue
            print(f"Tumi ({lang}): {text}")
            if is_end_command(text):
                speak("Okay, bye!", "en")
                break
            if is_echo(text, last_reply):
                continue
            try:
                reply = ask_llm(text)
            except Exception as e:
                print(f"LLM error: {e}\n")
                continue
            print(f"Jarvis: {reply}\n")
            last_reply = reply
            speak(reply, lang if lang in VOICES else "en")
            time.sleep(1.2)  # wait before next recording
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye!")
