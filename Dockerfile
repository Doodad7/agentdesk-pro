# Dockerfile for AgentDesk Pro (FastAPI + Tesseract + Postgres client)
FROM python:3.11-slim

# make apt noninteractive (avoids prompts during build)
ENV DEBIAN_FRONTEND=noninteractive

# working directory
WORKDIR /app

# install system dependencies needed by some Python libs and Tesseract OCR
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    git \
    tesseract-ocr \
    libleptonica-dev \
    libtesseract-dev \
 && rm -rf /var/lib/apt/lists/*

# copy requirements and install python deps
COPY requirements.txt /app/requirements.txt

# upgrade pip then install requirements
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt

# copy project source
COPY . /app
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# environment
ENV PYTHONUNBUFFERED=1

# expose port that FastAPI/uvicorn will use
EXPOSE 8000

# default command to run the app
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

