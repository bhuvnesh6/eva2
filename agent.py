"""
Eva V2 - LiveKit agent worker (Sarvam removed - English/Hindi only).

Pipeline:
    Browser mic --(LiveKit WebRTC)--> Deepgram STT --> Groq LLM --> TTS
                                                                       |
                                                English / Hindi   -> LiveKit Inference TTS (no extra key)

Turn detection (MultilingualModel), voice activity detection (Silero) and
adaptive interruption/barge-in are handled natively by AgentSession - this
replaces all the manual barge-in / volume-threshold code from Eva V1.

Run:
    python agent.py console   # talk to Eva right in your terminal (mic/speaker) - no browser needed
    python agent.py dev       # connects to LiveKit Cloud, waits to be dispatched into rooms (used by app.py)
    python agent.py start     # production mode
"""

import logging
import os
import re
from typing import AsyncIterable

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    ModelSettings,
    RoomOutputOptions,
    cli,
    inference,
)
from livekit.plugins import deepgram, groq, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eva-agent")

AGENT_NAME = os.environ.get("AGENT_NAME", "eva-agent")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

GLOBAL_TTS_MODEL = os.environ.get("GLOBAL_TTS_MODEL", "inworld/inworld-tts-2")
GLOBAL_TTS_VOICE = os.environ.get("GLOBAL_TTS_VOICE", "Ashley")

# ---------------- language detection (by Unicode script - same idea as Eva V1) ----------------
# Regional scripts (Bengali/Tamil/Telugu/Kannada/Malayalam) removed along with Sarvam.
# Only English/Hindi are detected now; anything else falls back to English.
SENTENCE_END_RE = re.compile(r"([.!?।\n])")
HINDI_RE = re.compile(r"[\u0900-\u097F]")
LANG_NAMES = {"en": "English", "hi": "Hindi"}

EVA_INSTRUCTIONS = (
    "You are Eva, a warm and concise voice assistant. "
    "Keep replies short and conversational (1-3 sentences) - this is a live "
    "voice call, not a chat window. "
    "Reply in the SAME language the caller is speaking - English or Hindi "
    "(in Devanagari script, never romanized/transliterated). "
    "If you can't tell, or if the caller speaks another language, default "
    "to English. "
    "Never use emojis, asterisks or markdown - everything you write is spoken aloud."
)


def _detect_lang(text: str) -> str:
    """Runs on the LLM's OUTPUT text (not the input audio) - same approach
    Eva V1 used. This is what decides which language the TTS speaks a
    sentence in."""
    if HINDI_RE.search(text):
        return "hi"
    return "en"


class EvaAgent(Agent):
    """Overrides tts_node() to set the right TTS language per sentence."""

    def __init__(self, global_tts: inference.TTS):
        super().__init__(instructions=EVA_INSTRUCTIONS)
        self._global_tts = global_tts

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Greet the caller warmly as Eva and ask how you can help today."
        )

    async def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings):
        buffer = ""
        async for chunk in text:
            buffer += chunk
            parts = SENTENCE_END_RE.split(buffer)
            complete, i = "", 0
            while i + 1 < len(parts):
                complete += parts[i] + parts[i + 1]
                i += 2
            buffer = parts[i] if i < len(parts) else ""

            sentence = complete.strip()
            if sentence:
                async for frame in self._speak(sentence):
                    yield frame

        tail = buffer.strip()
        if tail:
            async for frame in self._speak(tail):
                yield frame

    async def _speak(self, sentence: str):
        lang = _detect_lang(sentence)
        self._global_tts.update_options(language=lang)

        logger.info("speaking [%s]: %s", LANG_NAMES.get(lang, lang), sentence[:60])
        async for audio in self._global_tts.synthesize(sentence):
            yield audio.frame


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server = AgentServer()
server.setup_fnc = prewarm


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    global_tts = inference.TTS(
        model=GLOBAL_TTS_MODEL,
        voice=GLOBAL_TTS_VOICE,
        language="en",
    )

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=groq.LLM(model=GROQ_MODEL),
        tts=global_tts,  # default/fallback; EvaAgent.tts_node sets language per sentence
        turn_detection=MultilingualModel(),
        allow_interruptions=True,
        min_interruption_duration=0.5,
    )

    async def log_usage():
        for usage in session.usage.model_usage:
            logger.info("usage %s/%s: %s", usage.provider, usage.model, usage)

    ctx.add_shutdown_callback(log_usage)

    agent = EvaAgent(global_tts=global_tts)

    await session.start(
        agent=agent,
        room=ctx.room,
        room_output_options=RoomOutputOptions(transcription_enabled=True),
    )


if __name__ == "__main__":
    cli.run_app(server)