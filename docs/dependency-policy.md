# Dependency policy

Runtime and development dependencies are exact-pinned in `pyproject.toml`, `uv.lock` and `package-lock.json`. CI installs frozen locks, runs `pip-audit` and `npm audit --audit-level=high`, and fails on a known high-severity issue. Dependabot groups weekly Python/Node updates and monthly Actions/Docker updates.

Patch releases may merge after green quality, security and behavior gates. Minor/major updates require release-note review, migration/deprecation review and focused integration tests. Security fixes take priority; if no compatible fix exists, document exploitability, compensating controls, owner and expiry—never silently suppress the advisory. Remove unused packages promptly and use only maintained primary registries.
