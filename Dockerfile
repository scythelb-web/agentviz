FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir 'bcrypt<5'

COPY app/ ./app/

RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/agentviz.db

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
