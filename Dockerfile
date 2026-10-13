# Works on Railway, Koyeb, Fly.io, Google Cloud Run, any VPS…
FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PORT=8080 \
    DATA_DIR=/app/data \
    UPLOADS_DIR=/app/uploads
EXPOSE 8080
CMD ["python3", "server.py"]
