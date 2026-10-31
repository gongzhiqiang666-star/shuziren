FROM python:3.12.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt \
 && useradd --uid 10002 --create-home worker
COPY app.py .
USER worker
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 BGE_MODEL_DIR=/models
EXPOSE 8010
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8010","--no-access-log"]
