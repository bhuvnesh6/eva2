FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python agent.py download-files

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 5030

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]