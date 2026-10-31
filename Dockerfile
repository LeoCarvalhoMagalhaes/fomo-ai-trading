# Imagem usada no Render (ver docs/publicacao.md) e opcional no PC. Notificações do Windows não funcionam no contêiner.
FROM node:24-alpine AS front
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=front /app/frontend/dist frontend/dist
ENV FOMOAI_DATA_DIR=/data
VOLUME /data
EXPOSE 8765
WORKDIR /app/backend
# O Render informa a porta em $PORT
CMD ["sh", "-c", "exec python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8765} --proxy-headers --forwarded-allow-ips='*'"]
