# RunMyCampus Companion (Docker) — v3.37.0

Server appliance for the Migration Cloud handshake + canonical-CSV
ingest. See `docs/COMPANION_SIBLINGS_HANDSHAKE_AND_CSV_INGEST.md` at
the repo root for the full architectural-boundary contract.

## Run

```bash
cd companion-docker
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Or via Docker:

```bash
docker build -t rmc-companion-docker .
docker run --rm -p 8080:8080 rmc-companion-docker
```

## Test

```bash
cd companion-docker
pytest tests/   # 14 pass + 5 skip on environments without pynacl/fastapi
```

## What this appliance does NOT do

It does NOT log into PowerSchool / Blackbaud / Veracross / Alma / FACTS
/ Skyward. Programmatic vendor login lives in `companion-extension/`
where the operator's own authenticated browser tab is the security
boundary.
