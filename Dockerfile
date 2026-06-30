FROM python:3.12-slim

WORKDIR /app

# Copy only essential static files and requirements. 
# Hives and data are now provided via volumes for external persistence.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hivemind/ hivemind/
COPY config.yaml .
COPY index.html .
COPY data/ data/

EXPOSE 9090

CMD ["python", "-m", "hivemind", "serve", "--host", "0.0.0.0", "--port", "9090"]
