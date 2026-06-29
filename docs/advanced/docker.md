---
description: Running HiveMind with Docker
icon: docker
---

# Docker Deployment

## Quick start

```bash
docker compose up -d
```

Opens at [http://localhost:9090](http://localhost:9090).

## Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 9090
CMD ["python", "-m", "hivemind", "serve", "--host", "0.0.0.0", "--port", "9090"]
```

## Docker Compose

```yaml
version: "3"
services:
  hivemind:
    build: .
    ports:
      - "9090:9090"
    volumes:
      - ./hives:/app/hives
      - ./data:/app/data
    restart: unless-stopped
```

## Volumes

- `./hives` — persistent hive data (knowledge graphs, embeddings, backups)
- `./data` — persistent global data (meta-graph, permissions)

## Including sentence-transformers

To enable vector embeddings in Docker, add `sentence-transformers` to `requirements.txt` before building:

```
networkx>=3.4.0
PyYAML>=6.0.0
requests>=2.32.0
sentence-transformers
```

Then rebuild:

```bash
docker compose build --no-cache
docker compose up -d
```
