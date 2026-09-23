"""
Eva V2 - Flask front-end.

Serves the browser widget (templates/index.html), issues LiveKit tokens,
AND (by default) launches the agent worker (agent.py) as a subprocess so
you only need to run ONE command and see ALL logs - Flask's HTTP logs and
the agent's STT/LLM/TTS pipeline logs - in the same terminal.

Run:
    python app.py
Then open http://localhost:5000

Set AUTO_START_AGENT=false in .env if you'd rather run `python agent.py dev`
yourself in a second terminal (e.g. so you can restart the agent without
restarting Flask).
"""

import atexit
import logging
import os
import subprocess
import sys
import threading
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from livekit import api

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("eva-app")

LIVEKIT_URL = os.environ["LIVEKIT_URL"]
LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]
AGENT_NAME = os.environ.get("AGENT_NAME", "eva-agent")
ROOM_PREFIX = os.environ.get("EVA_ROOM_PREFIX", "eva-room")
FLASK_PORT = int(os.environ.get("FLASK_PORT", 5000))
AUTO_START_AGENT = os.environ.get("AUTO_START_AGENT", "true").lower() == "true"

app = Flask(__name__)

# ---------------- agent.py subprocess management ----------------
_agent_process = None


def _stream_output(pipe, prefix):
    """Reads the agent subprocess's output line-by-line and reprints it
    here, prefixed, so it shows up live in this same terminal."""
    for line in iter(pipe.readline, ""):
        if not line:
            break
        print(f"{prefix} {line}", end="")
    pipe.close()


def start_agent_worker():
    global _agent_process
    logger.info("Launching agent worker: python agent.py dev")

    child_env = os.environ.copy()
    child_env["PYTHONUNBUFFERED"] = "1"  # force real-time output, no pipe buffering

    _agent_process = subprocess.Popen(
        [sys.executable, "-u", "agent.py", "dev"],  # -u = unbuffered stdout/stderr
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=child_env,
    )
    threading.Thread(
        target=_stream_output, args=(_agent_process.stdout, "[agent]"), daemon=True
    ).start()


def stop_agent_worker():
    if _agent_process and _agent_process.poll() is None:
        logger.info("Stopping agent worker subprocess...")
        _agent_process.terminate()
        try:
            _agent_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _agent_process.kill()


atexit.register(stop_agent_worker)

# ---------------- routes ----------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/token", methods=["GET", "POST"])
def api_token():
    identity = f"user-{uuid.uuid4().hex[:8]}"
    room_name = f"{ROOM_PREFIX}-{uuid.uuid4().hex[:8]}"

    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .with_room_config(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)],
            )
        )
        .to_jwt()
    )

    logger.info("Issued token: identity=%s room=%s", identity, room_name)

    return jsonify(
        {
            "url": LIVEKIT_URL,
            "token": token,
            "room": room_name,
            "identity": identity,
        }
    )


@app.route("/health")
def health():
    agent_alive = _agent_process is not None and _agent_process.poll() is None
    return jsonify({"status": "ok", "agent_running": agent_alive})


if __name__ == "__main__":
    logger.info("LiveKit URL: %s", LIVEKIT_URL)
    logger.info("Agent name: %s", AGENT_NAME)
    # AUTO_START_AGENT / subprocess launch removed — supervisord runs
    # agent.py as its own process in production now.
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=True, use_reloader=False)