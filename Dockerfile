FROM python:3.12-slim

WORKDIR /app

# install deps first so this layer caches when only source changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY upstreams ./upstreams

EXPOSE 8000

# a non-root user is good hygiene for containers
RUN useradd --create-home appuser
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
