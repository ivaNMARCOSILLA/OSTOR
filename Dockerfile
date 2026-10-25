FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home maggy && mkdir -p /data/maggy && chown -R maggy:maggy /app /data/maggy
COPY --chown=maggy:maggy . .
ENV MAGGY_DATA_DIR=/data/maggy MAGGY_COOKIE_SECURE=1
USER maggy
VOLUME ["/data/maggy"]
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "60", "app:app"]
