FROM python:3.12-slim

# ffmpeg: ses/kare/klip işlemleri; nodejs: Claude Code CLI
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && npm cache clean --force \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY auditor ./auditor
COPY config ./config

# Claude CLI root olarak çalışmayı sevmez; ayrı kullanıcı
RUN useradd -m -u 1000 app && mkdir -p /data && chown -R app:app /data /app
USER app

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    CONFIG_DIR=/app/config \
    HF_HOME=/data/models

EXPOSE 8000 8765
CMD ["uvicorn", "auditor.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
