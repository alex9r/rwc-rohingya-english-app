# Built from the repo root (see docker-compose.yml) so the ml/ package is in the image.
# The same image runs locally (docker compose) and on AWS Lambda.
FROM python:3.12-slim

# AWS Lambda Web Adapter: on Lambda it turns API Gateway events into plain HTTP
# requests to uvicorn on port 8000 (AWS_LWA_PORT), so the FastAPI app runs unchanged.
# It's a Lambda extension, so outside Lambda (docker compose) it never starts.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter

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
# chmod: Lambda ignores USER and runs the image as its own unprivileged user, so the
# model files must be readable by anyone (Hugging Face saves downloads owner-only).
ARG INSTALL_SPEECH=0
ARG RWC_WHISPER_MODEL=small
ENV RWC_WHISPER_MODEL=${RWC_WHISPER_MODEL}
RUN if [ "$INSTALL_SPEECH" = "1" ] && [ -f ml/pronunciation/requirements.txt ]; then \
        pip install -r ml/pronunciation/requirements.txt \
        && python -c "from faster_whisper import WhisperModel; WhisperModel('$RWC_WHISPER_MODEL', device='cpu', compute_type='int8')" \
        && chown -R app /opt/hf \
        && chmod -R a+rX /opt/hf; \
    fi

COPY backend/app ./app

# Local runs use this user. On Lambda the filesystem is read-only except /tmp, and the
# function's environment points TMPDIR and XDG_CACHE_HOME there.
USER app
EXPOSE 8000
# Request logging comes from app.observability (no query strings), so uvicorn's is off.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
