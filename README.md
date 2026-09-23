# Eva V2 - LiveKit voice agent (browser, local testing)

Eva V2 moves the voice pipeline onto LiveKit for realtime orchestration,
turn detection and barge-in, while keeping Groq as the LLM. TTS is split:

- English / Hindi -> LiveKit Inference TTS (no separate API key)
- Bengali / Tamil / Telugu / Kannada / Malayalam -> Sarvam TTS

## 1. Prerequisites (create these accounts first)

| Service | Used for | Get a key at |
|---|---|---|
| LiveKit Cloud (free tier) | room/media server + Inference TTS | https://cloud.livekit.io |
| Groq | LLM | https://console.groq.com/keys |
| Deepgram | STT | https://console.deepgram.com |
| Sarvam AI | regional TTS | https://dashboard.sarvam.ai |

From your LiveKit Cloud project: **Settings -> API Keys** gives you
`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.

## 2. Set up the project

```bash
mkdir eva-v2 && cd eva-v2
# put agent.py, app.py, requirements.txt, .env.example, templates/index.html here

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

## 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in every key from step 1.

## 4. Sanity-check the pipeline (no browser, no Flask)

This talks to Eva directly through your computer's mic/speakers - the
fastest way to confirm STT/LLM/TTS actually work before touching the web
part:

```bash
python agent.py console
```

Say something in English, then try Hindi, then Tamil/Bengali/etc. and
listen for the voice switching engines (check the terminal log line
`speaking [Tamil] via regional: ...` to confirm routing).

Press `Ctrl+C` to stop.

## 5. Run the full browser flow

Open **two terminals** (both with the venv activated):

**Terminal 1 - the agent worker** (waits to be dispatched into rooms):
```bash
python agent.py dev
```

**Terminal 2 - the Flask app**:
```bash
python app.py
```

Now open **http://localhost:5000**, click **"Talk to Eva"**, allow
microphone access, and start talking. The agent worker in Terminal 1 will
log when it joins the room.

## 6. How the language routing works

Eva's system prompt tells the LLM to always reply in the caller's language,
in native script (never romanized). `agent.py` then scans each sentence of
the LLM's reply with the same Unicode-script regexes Eva V1 used:

- Devanagari script -> Hindi -> LiveKit Inference TTS
- Bengali/Tamil/Telugu/Kannada/Malayalam script -> that language -> Sarvam TTS
- Anything else (Latin script) -> English -> LiveKit Inference TTS

This routes off what the model actually said, not off Deepgram's guess at
the input language - so it stays correct even if STT mishears a word.

## 7. Customizing

- **Eva's personality / instructions**: `EVA_INSTRUCTIONS` in `agent.py`.
- **Groq model**: `GROQ_MODEL` in `.env`.
- **English/Hindi voice**: `GLOBAL_TTS_MODEL` / `GLOBAL_TTS_VOICE` in `.env`
  (any LiveKit Inference TTS model that supports both languages works -
  check https://docs.livekit.io/agents/models/tts for options).
- **Regional voice**: `SARVAM_SPEAKER` / `SARVAM_TTS_MODEL` in `.env`.
- **Interruption sensitivity**: `min_interruption_duration` in
  `agent.py`'s `AgentSession(...)` call - lower = more sensitive barge-in.

## 8. Troubleshooting

- **Agent never joins the room**: `AGENT_NAME` must be identical in `.env`
  (used by both `app.py`'s token and `agent.py`'s `@server.rtc_session`).
  Make sure `agent.py dev` is actually running.
- **"turn_detection" / "TurnHandlingOptions" errors on start**: LiveKit's
  API has shifted this option around between SDK versions. If
  `turn_detection=MultilingualModel()` on `AgentSession` raises a
  `TypeError`, replace it with:
```python
  from livekit.agents import TurnHandlingOptions
  ...
  turn_handling=TurnHandlingOptions(turn_detection=MultilingualModel()),
```
- **No sound in the browser**: check the browser console for autoplay
  errors - clicking "Talk to Eva" counts as a user gesture so this
  shouldn't normally happen, but some browsers are stricter.
- **"model not enabled" from LiveKit Inference**: check
  **your LiveKit Cloud project -> Settings -> Inference** and enable the
  model you configured in `GLOBAL_TTS_MODEL`.

## 9. Not included yet (out of scope for this local test build)

Phone calls (Twilio/VaniSetu/VoiceLink), CRM tools, and meeting booking
from Eva V1 aren't ported over here - this is a clean browser-only MVP to
validate the LiveKit pipeline first, per your original migration plan.
Once this is solid, SIP trunking can be added on top the same way LiveKit
docs describe for telephony agents.