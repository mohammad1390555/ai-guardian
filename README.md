# AI Guardian

AI-powered CLI tool for automated project analysis, bug detection, UI
inspection, and assisted fixing. It continuously inspects a project,
understands its architecture, explains every issue in detail, optionally
applies conservative targeted fixes, validates the result, and keeps going.

## Features

- Three analysis modes: **Bug Fixer**, **UI Fixer**, and **Project Analyzer**
- Continuous analysis loop with an internal work queue and resume support
- Auto Fix with backups, atomic writes, change logging, rollback, and re-checks
- Automatic secret redaction before any content leaves your machine
- Technology-aware validation (`npm run build`, `tsc --noEmit`, `pytest`, etc.)
- Live Markdown notepad plus full Markdown and JSON reports
- Interactive command console with status, findings, history, and config commands

## Installation

```bash
pip install -r requirements.txt
pip install .
```

Requirements: Python 3.9+, `openai`, and `rich` (installed automatically).

## Configuration

A `guardian.json` file is created in the project directory on first run.
All settings are configurable:

```json
{
  "provider": {
    "base_url": "https://integrate.api.nvidia.com/v1",
    "model": "deepseek-ai/deepseek-v4-flash-0731",
    "api_key_env": "NVIDIA_API_KEY"
  },
  "generation": {
    "temperature": 1,
    "top_p": 0.95,
    "max_tokens": 16384,
    "reasoning": { "enabled": true, "effort": "high" }
  },
  "analysis": {
    "mode": "bug_fixer",
    "auto_fix": false,
    "continuous": true
  },
  "backup": {
    "enabled": true,
    "directory": ".backups",
    "max_project_size_mb": 500
  }
}
```

Any OpenAI-compatible endpoint works: change `provider.base_url`,
`provider.model`, and `provider.api_key_env`.

## Usage

```bash
export NVIDIA_API_KEY=your_key_here
guardian
```

The interactive session walks through project selection (typed path,
current directory, or a directory browser), shows a project summary with
detected technologies, then opens the command console:

```
help / status / scan / pause / resume / fix / findings
report / history / config / mode / validate / rollback / clear / exit
```

### Example session

```
guardian> scan
> Scanning project...
> Creating project backup...
[cyan][####################] 100%] (12/12)
Analyzing: src/api/auth.ts
  FINDING [HIGH] src/api/auth.ts:87 - Authentication
  Potential authentication bypass via unsigned token field.

guardian> report
Markdown report: reports/analysis_2026-08-26_07-10-33.md
JSON report:     reports/analysis_2026-08-26_07-10-33.json
```

## Safety

- Backups are created before any modification; originals are never touched first
- All file writes are atomic; every change is logged and reversible
- Path traversal protection prevents edits outside the project root
- Secrets (API keys, tokens, passwords, private keys, database URLs) are
  redacted automatically before being sent to the model
- Validation only runs a whitelist of non-destructive commands

## License

MIT
