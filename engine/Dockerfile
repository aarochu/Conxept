# Python engine: EngineService + InstructorAgentService on :50051.
# Build from the repo root: docker build -f engine/Dockerfile .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY engine/requirements.txt engine/requirements.txt
RUN pip install -r engine/requirements.txt

COPY proto proto
COPY sql sql
COPY engine engine
RUN mkdir -p engine/gen \
 && python -m grpc_tools.protoc -I proto \
      --python_out=engine/gen --grpc_python_out=engine/gen --pyi_out=engine/gen \
      proto/misconception/v1/*.proto \
 && useradd --system --no-create-home --uid 10001 engine \
 && chown -R 10001 /app

USER 10001
WORKDIR /app/engine
EXPOSE 50051
CMD ["python", "server.py"]
