# Personal Local Docker Runbook

This runbook is for personal local use of v1.0.1+ on Docker Compose. It is not a public production deployment guide.

## Scope

- Target UI: http://localhost:3000
- Target API: http://localhost:8091
- Database: Docker Compose postgres service on host port 5500
- Default auth mode: local development mode (`AUTH_ENABLED=false`)
- Default embedding: local hash embedding with hybrid lexical retrieval

## Safe startup

```bash
docker compose up -d --build
docker compose ps
```

Expected services:

- `backend`: running and healthy
- `postgres`: running and healthy
- `frontend`: running

## Read-only health checks

```bash
python scripts/personal_local_check.py
```

This script is read-only. It checks Git safety, Docker service status, `/health`, `/health/ready`, frontend HTTP, backend smoke, docs secret scan, and frontend mojibake scan. It skips model smoke by default.

If you want to explicitly run a real LLM connectivity check, use:

```bash
python scripts/personal_local_check.py --run-model-smoke
```

## Demo data

Demo seeding is a write operation, but it is idempotent:

```bash
docker compose exec backend python scripts/seed_demo.py
```

To remove only demo data:

```bash
docker compose exec backend python scripts/reset_demo.py
```

Do not use `docker compose down -v` unless you intentionally want to delete the local database volume.

## RAG smoke path

After demo data exists:

1. Open http://localhost:3000/papers
2. Open a completed demo paper.
3. Ask an English question first, for example: `What problem does attention solve?`
4. For Chinese questions against English papers, query expansion can help, but local hash embedding is still limited.
5. Use low-confidence mode when strict RAG returns `insufficient_context` but sources are available.
6. Try cross-paper QA at http://localhost:3000/papers/ask.

Expected personal-use behavior:

- Some strict RAG questions answer when lexical evidence exists.
- Low-confidence mode can produce tentative answers from retrieved sources.
- Source items expose `retrieval_mode`, `lexical_score`, and `vector_score`.
- `query_expansion_applied=true` means Chinese query expansion was used only for lexical scoring; the original user question is still sent to the LLM.

## Common troubleshooting

### Docker Desktop not running

Symptoms:

- `docker compose ps` fails.
- `personal_local_check.py` reports Docker unavailable.

Fix:

1. Start Docker Desktop.
2. Wait until Docker reports running.
3. Re-run `docker compose up -d --build`.

### Port conflict

Current host ports:

- frontend: 3000
- backend: 8091
- postgres: 5500

On Windows, Hyper-V may reserve ranges around 8000. Check:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

If you change ports, update Docker Compose, frontend API URLs, docs, and tests together.

### Backend unhealthy

```bash
docker compose logs backend
docker compose exec -T backend python scripts/smoke_check.py
```

Check database readiness, pgvector, and core tables.

### Frontend cannot reach backend

Check:

- `NEXT_PUBLIC_API_URL=http://localhost:8091`
- `INTERNAL_API_URL=http://backend:8000` inside Docker, or `http://localhost:8091` for local host development
- Browser can open http://localhost:8091/health


### `/health/ready` reports Alembic is behind but tables already exist

Symptoms:

- `python scripts/personal_local_check.py` fails on `GET /health/ready`.
- The readiness payload shows `ready=false`, for example `alembic_current=003_job_runs` and `alembic_head=004_research_notes`.
- Running `docker compose exec -T backend python -m alembic upgrade head` may fail with `DuplicateTableError` for `research_notes` if the table was already created by an older local startup path.

Non-destructive checks:

```bash
docker compose exec -T backend python -m alembic current
docker compose exec -T backend python -m alembic heads
docker compose exec -T postgres psql -U postgres -d research_assistant -c "\d research_notes"
```

If `research_notes` already exists and matches the expected local schema, stamp the migration version instead of deleting the Docker volume:

```bash
docker compose exec -T backend python -m alembic stamp 004_research_notes
python scripts/personal_local_check.py
```

This is non-destructive: it updates Alembic version metadata only. Do not use `docker compose down -v` unless you intentionally want to delete the local database volume.

### Old volume or embedding dimension mismatch

If you changed `EMBEDDING_DIMENSION`, you must rebuild embeddings and may need a DB migration or volume rebuild.

For local personal data, only run `docker compose down -v` if you accept deleting the local database volume.

## Dangerous operations not part of personal checks

Do not run these as part of routine personal startup:

- `eval_real_model.py` unless explicitly authorized
- restore scripts with `-ConfirmRestore`
- cleanup scripts with `--confirm`
- `docker compose down -v` unless you intentionally want to delete local DB data
- `git tag`, `git push`, or force push from a personal health-check flow

Never paste `.env`, API keys, Authorization headers, session tokens, or real DATABASE_URL values into reports.
