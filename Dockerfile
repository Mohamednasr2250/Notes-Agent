FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV NOTES_DB_PATH=/data/notes.db
ENV PORT=5000
EXPOSE 5000
VOLUME ["/data"]

CMD ["python", "-m", "notes_agent.cli"]