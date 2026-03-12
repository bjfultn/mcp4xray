FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    pyvo \
    astroquery \
    "mcp[cli]>=1.0" \
    uvicorn

COPY server.py .

EXPOSE 8001 8002

CMD ["python", "server.py", "--streaming"]
