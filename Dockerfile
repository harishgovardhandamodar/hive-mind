FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hivemind/ hivemind/
COPY config.yaml .
COPY index.html .
COPY data/ data/
COPY hives/ hives/

EXPOSE 9090

CMD ["python", "-m", "hivemind", "serve", "--host", "0.0.0.0", "--port", "9090"]
