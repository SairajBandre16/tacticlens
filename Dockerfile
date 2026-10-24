# TacticLens API + Match Center. Golden data and trained models are baked in; live mode needs only env vars.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install -e ".[azure]"
COPY contracts ./contracts
COPY web ./web
COPY data/golden ./data/golden
COPY data/models ./data/models
RUN useradd --create-home app && mkdir -p data/cache && chown -R app data/cache
USER app
EXPOSE 8000
CMD ["uvicorn", "tacticlens.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
