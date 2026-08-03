FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DMA_DATABASE_PATH=/data/dma.db

WORKDIR /app

COPY services/dma-api/pyproject.toml ./pyproject.toml
COPY services/dma-api/src ./src

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 dma \
    && mkdir /data \
    && chown dma:dma /data

USER dma

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["python", "-m", "uvicorn", "dma_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
