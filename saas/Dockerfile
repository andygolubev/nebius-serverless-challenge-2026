# Single image: builds the React frontend, then serves it from the FastAPI backend.

# --- Stage 1: build the frontend -----------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build   # emits to /app/backend/static (see vite.config.ts)

# --- Stage 2: backend runtime --------------------------------------------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# Bring in the built static assets produced by stage 1.
COPY --from=frontend /app/backend/static ./static

# Non-root to match the Deployment securityContext.
RUN useradd -u 10001 -m appuser
USER 10001

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
