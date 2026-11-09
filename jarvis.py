"""
Jarvis - Dhap 2: Voice conversation + Web research tool
Mic -> Whisper -> LLM (web_search tool) -> Voice reply
"""
import asyncio
import json
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import edge_tts
import numpy as np
import pygame
import requests
import sounddevice as sd
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from openai import OpenAI

load_dotenv()

# ---------- Settings ----------
SAMPLE_RATE = 16000
CHUNK_SEC = 0.1
SILENCE_THRESHOLD = 0.015   # mic khub sensitive/kom hole eta change koro
SILENCE_END_SEC = 1.3       # eto sec chup thakle recording shesh
WAIT_START_SEC = 10         # eto sec er moddhe kotha na bolle conversation shesh
MAX_RECORD_SEC = 30

WHISPER_MODEL = "small"     # kom power e "base", valo accuracy te "medium"
LANGUAGE = "en"             # Bangla bolle "bn", auto-detect chaile None
VOICES = {"bn": "bn-BD-NabanitaNeural", "en": "en-US-AriaNeural"}
END_WORDS = {"bye", "goodbye", "stop", "exit"}
MAX_TOOL_ROUNDS = 4         # ek proshne max koto bar tool chalabe
REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "low")  # gpt-oss: low = druto

SYSTEM_PROMPT = (
    "You are Jarvis, a personal voice assistant of Shorov, a software "
    "engineering student and MERN/Next.js developer.\n"
    f"Today's date is {date.today().isoformat()}.\n"
    "- Reply in the same language the user spoke. If Bangla, write in Bangla script.\n"
    "- Keep replies short (1-3 sentences) because they are spoken aloud.\n"
    "- No markdown, no bullet points, no emojis, never read out URLs.\n"
    "- If the request is unclear, ask ONE short clarifying question first.\n"
    "- Explain things simply with a small example.\n"
    "- You have a web_search tool. Use it for news, latest versions, prices, "
    "recent events, or any fact you are not sure about. After searching, answer "
    "briefly from the results and say if results are unclear.\n"
    "- For news, give at most 3 items in one short paragraph, no lists."
)

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
)
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

TOOLS = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Short search query"}
            },
            "required": ["query"],
        },
    },
}]

print("Whisper model load hocche (prothom bar ektu somoy lagbe)...")
stt = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
pygame.mixer.init()

history = [{"role": "system", "content": SYSTEM_PROMPT}]


# ---------- Tools ----------
def web_search(query):
    """Tavily diye web search, LLM er jonno chhoto text result ferot dey."""
    if not TAVILY_API_KEY:
        return "Web search unavailable: TAVILY_API_KEY is not set."
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
            json={"query": query, "max_results": 5, "include_answer": True},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return f"Search failed: {e}"

    parts = []
    if data.get("answer"):
        parts.append("Summary: " + data["answer"])
    for item in data.get("results", [])[:5]:
        content = (item.get("content") or "")[:400]
        parts.append(f"- {item.get('title', '')} ({item.get('url', '')}): {content}")
    return "\n".join(parts) or "No results found."


def run_tool(name, args):
    if name == "web_search":
        query = args.get("query", "")
        print(f"[Searching: {query}]")
        return web_search(query)
    return f"Unknown tool: {name}"


# ---------- Audio ----------
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
    segments, info = stt.transcribe(
        samples, beam_size=1, vad_filter=True, language=LANGUAGE
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, info.language


_tts_pool = ThreadPoolExecutor(max_workers=3)


def _synth(text, voice):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        path = f.name
    asyncio.run(edge_tts.Communicate(text, voice).save(path))
    return path


def split_sentences(text):
    parts = re.split(r"(?<=[.!?\u0964])\s+", text.strip())
    return [p for p in parts if p.strip()]


def speak(text, lang):
    """Bangla okkhor thakle Bangla voice. Prothom sentence ager bajay,
    baki gulo oi shomoy toiri hoy, tai wait kom."""
    voice = VOICES["bn"] if re.search(r"[\u0980-\u09FF]", text) else VOICES["en"]
    sentences = split_sentences(text) or [text]
    futures = [_tts_pool.submit(_synth, sent, voice) for sent in sentences]
    for fut in futures:
        path = fut.result()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.music.unload()
        os.remove(path)


# ---------- Brain ----------
def ask_llm(user_text):
    history.append({"role": "user", "content": user_text})
    extra = {"tools": TOOLS} if TAVILY_API_KEY else {}
    if LLM_MODEL.startswith("openai/gpt-oss"):
        extra["extra_body"] = {"reasoning_effort": REASONING_EFFORT}

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=LLM_MODEL, messages=history, **extra
        )
        msg = resp.choices[0].message

        if msg.tool_calls:
            history.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [{
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                } for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(tc.function.name, args)
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            continue

        reply = (msg.content or "").strip()
        history.append({"role": "assistant", "content": reply})
        return reply

    return "Sorry, I could not finish that. Please try again."


def is_end_command(text):
    cleaned = re.sub(r"[^a-z' ]", "", text.lower()).strip()
    words = cleaned.split()
    return cleaned == "thats all" or (
        len(words) <= 10 and any(w in END_WORDS for w in words)
    )


def is_echo(text, last_reply):
    """Jarvis er nijer kotha mic e dhukle ota ignore kore."""
    if not last_reply:
        return False
    a = set(re.sub(r"[^a-z' ]", "", text.lower()).split())
    b = set(re.sub(r"[^a-z' ]", "", last_reply.lower()).split())
    return len(a) >= 2 and len(a & b) / len(a) >= 0.6


def main():
    if not TAVILY_API_KEY:
        print("Note: TAVILY_API_KEY nei, web search off thakbe.\n")
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
            t1 = time.time()
            text, lang = transcribe(audio)
            t_stt = time.time() - t1
            if not text:
                continue
            print(f"Tumi ({lang}): {text}")
            if is_end_command(text):
                speak("Okay, bye!", "en")
                break
            if is_echo(text, last_reply):
                continue
            try:
                t2 = time.time()
                reply = ask_llm(text)
                t_llm = time.time() - t2
            except Exception as e:
                print(f"LLM error: {e}\n")
                continue
            print(f"Jarvis: {reply}")
            print(f"[time: stt {t_stt:.1f}s | llm {t_llm:.1f}s]\n")
            last_reply = reply
            speak(reply, lang if lang in VOICES else "en")
            time.sleep(1.2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye!")