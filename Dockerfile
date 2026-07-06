FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV NOTES_DB_PATH=/data/notes.db
VOLUME ["/data"]

ENTRYPOINT ["python", "-m", "notes_agent.cli"]
