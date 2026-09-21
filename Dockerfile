FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY adintel ./adintel
COPY tests ./tests

RUN mkdir -p /app/output /app/fixtures

ENTRYPOINT ["python", "-m", "adintel"]
CMD ["status"]
