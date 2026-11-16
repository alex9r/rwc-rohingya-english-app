# Built from the repo root (see docker-compose.yml) so the ml/ package is in the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf

# The virtualenv lives outside /app so the source bind mount never hides it
# (and a Windows .venv on the host never collides with the Linux one).
RUN python -m venv /opt/venv \
    && useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /opt/hf && chown app /opt/hf

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY ml ./ml

# Whisper is large, so real transcription is opt-in: build with INSTALL_SPEECH=1.
# Without it, /api/transcribe and /api/pronunciation/score return stub data. The model
# is downloaded at build time so tasks start warm and never need internet access at
# runtime. ml/pronunciation/requirements.txt includes ml/speech's, plus rapidfuzz, so
# scores match what the ml tests see (without it the scorer falls back to difflib).
ARG INSTALL_SPEECH=0
ARG RWC_WHISPER_MODEL=small
ENV RWC_WHISPER_MODEL=${RWC_WHISPER_MODEL}
RUN if [ "$INSTALL_SPEECH" = "1" ] && [ -f ml/pronunciation/requirements.txt ]; then \
        pip install -r ml/pronunciation/requirements.txt \
        && python -c "from faster_whisper import WhisperModel; WhisperModel('$RWC_WHISPER_MODEL', device='cpu', compute_type='int8')" \
        && chown -R app /opt/hf; \
    fi

COPY backend/app ./app

USER app
EXPOSE 8000
# Request logging comes from app.observability (no query strings), so uvicorn's is off.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
