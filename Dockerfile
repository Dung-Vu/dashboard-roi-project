FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5056 \
    DEBUG=0

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app
RUN mkdir -p /app/data

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app.py cache.py config.py dashboard_service.py odoo_client.py ./
COPY index.html app.js styles.css ./
COPY assets ./assets

RUN chown -R app:app /app
USER app

EXPOSE 5056

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5056} --workers ${WEB_CONCURRENCY:-2} --threads ${WEB_THREADS:-4} --timeout 120 app:app"]
