# ketabonline-kurasi: sensus metadata, pencocokan, GUI. Dibangun lokal di server (tidak perlu registry):
#   docker compose build
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 KETAB_DATA=/data
RUN pip install --no-cache-dir flask==3.1.0 waitress==3.0.2 openpyxl==3.1.5

WORKDIR /srv
COPY ketab ./ketab

RUN useradd --system --uid 10001 ketab
USER ketab

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/sehat',timeout=4)" || exit 1
ENTRYPOINT ["python", "-m", "ketab"]
CMD ["gui"]
