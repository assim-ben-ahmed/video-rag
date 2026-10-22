# Runs locally and as a Hugging Face Space (Docker SDK, port 7860, non-root user 1000).
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    DATA_DIR=/home/user/data \
    WHISPER_MODEL=small \
    PUBLIC_MODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Download the Whisper model at build time so the first upload does not wait for it.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

COPY --chown=user videorag videorag
COPY --chown=user web web
COPY --chown=user demo demo

EXPOSE 7860
CMD ["uvicorn", "videorag.app:app", "--host", "0.0.0.0", "--port", "7860"]
