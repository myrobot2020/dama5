FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install deps (includes chromadb + sentence-transformers for local mode).
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# App code + corpora. (Persisted Chroma indexes are not committed; build at runtime via /api/build.)
COPY an1_app.py an1_build_index.py an1_vertex_core.py an1_build_vertex_bundle.py dama_firebase_auth.py dama_auth_ui.py dama_diy_auth.py chat_embed.html /app/
COPY static/ /app/static/
COPY an1.json an2.json an3.json /app/
COPY aud/audio_map.json /app/aud/audio_map.json

EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn an1_app:app --host 0.0.0.0 --port ${PORT}"]

