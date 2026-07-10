FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Create prefect home directory
RUN mkdir -p /root/.prefect
RUN mkdir -p /app/.prefect

COPY requirements.txt .



RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 4200