# Built from the repo root (see docker-compose.yml) so the ml/ package is in the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"


RUN python -m venv /opt/venv

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY ml ./ml

# Whisper is large, so real transcription is opt-in: build with INSTALL_SPEECH=1.
# Without it, /api/transcribe returns stub data.
ARG INSTALL_SPEECH=0
RUN if [ "$INSTALL_SPEECH" = "1" ] && [ -f ml/speech/requirements.txt ]; then \
        pip install -r ml/speech/requirements.txt; \
    fi

COPY backend/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
