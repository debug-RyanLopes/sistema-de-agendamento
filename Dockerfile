# Imagem única que serve a área do cliente (8000) e a da empresa (8001).
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    HOST=0.0.0.0

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home --uid 1000 barbearia \
    && mkdir -p /dados && chown -R barbearia:barbearia /app /dados
USER barbearia

ENV DATABASE_URL=sqlite:////dados/barbearia.db

EXPOSE 8000 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=3)" || exit 1

CMD ["python", "-m", "scripts.dev"]
