FROM python:3.13-slim
WORKDIR /opt/algobot
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev git && rm -rf /var/lib/apt/lists/*
COPY requirements/base.txt /opt/algobot/requirements/base.txt
RUN pip install --no-cache-dir -r /opt/algobot/requirements/base.txt
COPY . /opt/algobot
COPY deploy/external-worker/start.sh /usr/local/bin/algobot-worker-start
RUN chmod +x /usr/local/bin/algobot-worker-start
ENTRYPOINT ["/usr/local/bin/algobot-worker-start"]
