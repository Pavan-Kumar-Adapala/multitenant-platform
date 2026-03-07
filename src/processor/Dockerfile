FROM python:3.12-slim

# Non-root user for security
RUN groupadd -r processor && useradd -r -g processor processor

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY process.py .
RUN chown -R processor:processor /app

USER processor
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "process.py"]