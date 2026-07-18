Modern Python Quality Tools (2026)

Install:
uv add --dev ruff basedpyright deptry pip-audit vulture

──────────────────────────────────────────────

1. Ruff ⭐ (Run every commit)
Use:
• Linting
• Formatting
• Import sorting
• Auto-fix common issues

Commands:
uv run ruff check .
uv run ruff check . --fix
uv run ruff format .

──────────────────────────────────────────────

2. BasedPyright ⭐ (Run every commit)
Use:
• Static type checking
• Finds type errors before runtime

Command:
uv run basedpyright

──────────────────────────────────────────────

3. Deptry (Run occasionally)
Use:
• Finds unused dependencies
• Finds missing dependencies
• Detects incorrect dependency declarations

Command:
uv run deptry .

──────────────────────────────────────────────

4. Vulture (Run occasionally)
Use:
• Detects dead code
• Unused functions
• Unused classes
• Unused variables

Command:
uv run vulture .

──────────────────────────────────────────────

5. pip-audit (Run before release / occasionally)
Use:
• Scans installed packages for known security vulnerabilities (CVEs)
• Suggests upgrading vulnerable packages

Command:
uv run pip-audit

──────────────────────────────────────────────

Recommended Workflow

Every Commit:
uv run ruff check . --fix
uv run ruff format .
uv run basedpyright

Occasional Cleanup:
uv run deptry .
uv run vulture .

Before Release / CI:
uv run pip-audit