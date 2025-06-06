FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . target/
RUN useradd --uid 1000 --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser
CMD ["python", "-m", "target", "--uri", "tcp://0.0.0.0:5000"]