FROM python:3.11-slim

WORKDIR /app

# System deps some livekit/audio plugins need at build time
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download turn-detector / VAD model weights at build time,
# not at container start — avoids first-request stalls or failures
# if the VPS has restricted runtime egress.
RUN python agent.py download-files

EXPOSE 5030

# AUTO_START_AGENT=true (set in .env) makes app.py launch agent.py
# as a subprocess, same as your local setup.
CMD ["python", "app.py"]