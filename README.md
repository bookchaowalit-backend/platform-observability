# platform-observability

Shared Python API instrumentation and private scrape/rule configuration are
implemented locally; see [shared runtime telemetry](docs/shared-runtime.md).
This does not activate the older compatibility surfaces or a production stack.

`Observability` platform boundary for the Book Platform portfolio.

## Scope

This repository owns the `observability` capability: logs, metrics, traces, alerts, status.
The current source implementation is recorded as `infra/self-hosted-stack` in the
parent registry. This checkout is a local scaffold; it contains no production
provider integration, database writer, credential, or customer payload.

## Boundary

- Owner: `bookchaowalit-backend`
- Repository: `platform-observability`
- Target remote: `https://github.com/bookchaowalit-backend/platform-observability.git` (published; runtime not activated)
- Contract: `book-platform.contract.v1`
- Status: `scaffolded`
- Data owner: the platform boundary identified in `contract.json`

The platform communicates through versioned API or event contracts. Consumers
must not import another platform's database, migration, or private runtime
module. `solo-empire` remains the control plane and compatibility adapter until
parity and rollback evidence permit a cutover.

## Local verification

Run from this repository (Python 3.11+, no third-party packages):

```bash
bash scripts/check.sh
```

The check validates `contract.json` against
[`schema/book-platform.contract.v1.schema.json`](schema/book-platform.contract.v1.schema.json),
confirms that the README and [`docs/CONTRACT-SURFACE.md`](docs/CONTRACT-SURFACE.md)
agree with the contract, and runs the unit tests in `tests/`. GitHub Actions
runs the same command on every push and pull request
(`.github/workflows/check.yml`).

`scripts/check_schema_pin.py` fails when the vendored schema no longer
matches the sha256 pinned in `schema/book-platform.contract.v1.schema.json.sha256`
(the canonical copy lives in `bookchaowalit-backend-core/contracts/`; change it
there first, then copy the schema and its pin here). Pass
`--canonical ../platform-backend-core` to also compare with a local
checkout. `python3 scripts/check_registry_alignment.py --solo-empire ../solo-empire`
compares this contract with the parent platform registry (local only; read-only).

The `platform_observability` package (`src/`) has third-party dependencies,
locked in `uv.lock`. Install them with `uv sync --frozen --all-extras`, then
run `ruff check .`, `mypy` and `python -m pytest` (tests/ and runtime_tests/).
CI runs the same through the shared `ci-python` workflow, with a coverage gate.

The check validates repository shape and contract metadata only. It does not
claim deployment, provider connectivity, data migration, or production
readiness.

## Contract surface

Dependencies: none. The interfaces this boundary owns or consumes, with
their auth, idempotency and error behaviour, are listed in
[`docs/CONTRACT-SURFACE.md`](docs/CONTRACT-SURFACE.md). Planned work is tracked
in [`docs/UPGRADE-PLAN.md`](docs/UPGRADE-PLAN.md).

## Migration gate

Before activating a remote or changing a consumer, add sanitized fixtures for
success, duplicate delivery, timeout and provider failure; prove tenant/privacy
isolation; compare the old and new contract; and rehearse rollback on a
disposable state store. Record the evidence in the parent platform registry.
