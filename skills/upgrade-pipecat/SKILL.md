---
name: upgrade-pipecat
description: Plan and perform a staged Nemotron Voice Agent Pipecat upgrade. Detects the installed version, finds the latest stable release, reads every changelog in range, writes separate compatibility and feature-adoption documents, applies blockers, and pauses for human review before remaining compatibility work. Optional features are never implemented without explicit user authorization.
version: "2.3.0"
metadata:
  author: NVIDIA Voice Agent Team <nemotron-voice-agent@nvidia.com>
  tags: [upgrade, migration, pipecat, voice-agent, nemotron]
---

# Pipecat Version Upgrade — Nemotron Voice Agent

Plan and migrate this repo to a new `pipecat-ai` version through explicit priority gates. Repo root is the
working directory.

## Invocation

```text
/upgrade-pipecat [new=<target>] [old=<source>]
```

- **`new`** (optional): target `pipecat-ai` version. Omit it to use the latest stable GitHub release. An explicit
  value can be a PyPI version (`1.5.0`), local pipecat checkout path (full diff), git tag (`v1.5.0`), or docs
  URL (`https://docs.pipecat.ai/`, least complete). Do not select a prerelease unless the user explicitly asks.
- **`old`** (optional): current version. A version string enables CHANGELOG/git diff. Omit to auto-detect from
  `pyproject.toml` (`pipecat-ai[...]==X.Y.Z`) + `uv.lock`.

The default migration range starts at the version used by the repository and ends at the latest stable
`pipecat-ai` release. Read the current release entry as baseline context and every subsequent release through
the target. Latest version and release notes come from the canonical
**<https://github.com/pipecat-ai/pipecat/releases>**. Never infer "latest" from model knowledge, the local
environment, or an old lockfile.

The skill scans BOTH dependency surfaces for every Pipecat package and reads each one's own release notes:

- **Server (Python)** — `pyproject.toml`/`uv.lock`: every `pipecat*` dependency (for example, `pipecat-ai-subagents`,
  `pipecat-ai-flows`, …).
- **Client (npm)** — `client/package.json`: every `@pipecat-ai/*` dependency (for example, `client-js`, `client-react`,
  `*-transport`, …).

Extras and every dependency change are derived from these notes + the lockfiles — nothing about specific
packages is hardcoded here.

## Required outputs and authorization boundary

Before changing dependencies or runtime code, create the two upgrade documents defined in
[references/upgrade-document-contract.md](references/upgrade-document-contract.md):

- `docs/how-to/upgrade-pipecat-v<TARGET>-compatibility.md` contains required migration work, prioritized as
  Blocker, High, Medium, or Low.
- `docs/how-to/adopt-pipecat-v<TARGET>-features.md` contains optional improvements enabled by the new release.

Treat the compatibility document as the executable work queue. Apply all Blocker items, validate them, update
their status/evidence in the document, and then stop for human review. Do not start any High, Medium, or Low item
until the user explicitly approves continuing after seeing the blocker diff and validation results.

Treat the feature-adoption document as advisory-only. Creating or revising that document does not authorize any
feature implementation. Do not make source, configuration, dependency, test, workflow, or deployment changes
because of an item in that document unless the user explicitly asks to implement that item. Approval to continue
the compatibility upgrade never includes optional feature adoption.

## Phases (run in order)

1. **Explore and Discover** — [workflows/01-explore-discover.md](workflows/01-explore-discover.md). Read release
   notes for every release in range, analyze against the repo, confirm with source diff + per-example scan, and
   create both upgrade documents.
2. **Priority-Gated Implementation** — [workflows/02-plan-implement.md](workflows/02-plan-implement.md). Apply
   Blockers only, present the review package, pause for explicit approval, then implement approved High/Medium/Low
   compatibility work. Never consume the feature-adoption list as implementation instructions.
3. **Gap Analysis Loop** — [workflows/03-gap-analysis-loop.md](workflows/03-gap-analysis-loop.md), after the
   required human approval for remaining compatibility work.
4. **Deploy and Validate** — [workflows/04-deploy-validate.md](workflows/04-deploy-validate.md), after the same
   compatibility approval. Optional features remain out of scope.

## Pipecat docs MCP — use for any doubt

For ANY Pipecat uncertainty (signature, moved module, intended usage, migration path), query the
`pipecat-docs` MCP tool `search_daily_knowledge_sources` (backed by <https://daily-docs.mcp.kapa.ai>) instead of
guessing. Pass one complete sentence as `query`; cite the returned `source_url` in the change log. For exact
signatures, trust the actual installed/new source; use the MCP for intent and migration guidance.

## Principles

- **Release-notes-driven (hard gate)**: read the `pipecat-ai` release notes + CHANGELOG for EVERY release in
  range — including the current version as baseline — and each `pipecat*` subpackage's own notes before doing
  anything else. Do not start the diff, plan, documents, or any edit until this is done and recorded. Most missed
  migrations come from skipping this. The source diff only confirms and completes the notes.
- **Dependencies follow the notes, not assumptions**: discover the repo's current Pipecat-related dependencies
  from `pyproject.toml`/`uv.lock`, then let the `pipecat-ai` notes dictate what happens to each — bumped,
  renamed, newly required, or folded into core (dependency removed + imports migrated). Never hardcode or assume
  a companion package stays separate, stays present, or co-versions.
- **Discovery-first**: never assume module paths, frame names, service constructors, or processor APIs — scan
  the installed package and new source. Pipecat reorganizes its module tree between versions.
- **Generic**: works for any transition; discover changes, hardcode nothing.
- **Examples are the unit of work**: 5 examples (`generic`, `multilingual`, `omni_assistant`,
  `omni_assistant_subagents`, `frontend_backend_agent`), each with its own `pipeline.py`. One agent per example + one
  cross-cutting agent for `src/examples/shared/` and `src/server.py`.
- **Custom service subclasses require parent-API review**: explicitly inspect
  `src/examples/shared/nvidia_word_tts.py` (`NvidiaWordTTSService`) and
  `src/examples/omni_assistant/nvidia_omni_multimodal_service.py`, plus the downstream
  `SubagentsSpeakerOmniService` in
  `src/examples/omni_assistant_subagents/subagents/speaker/agent.py`. Diff their upstream
  parent services before validating overrides, lifecycle methods, settings, frames, and
  private compatibility contracts.
- **Server + client move together (RTVI contract)**: the RTVI wire protocol couples the Python server to the
  `@pipecat-ai/*` client packages, so they must be upgraded in lockstep. Bump `client/package.json` to versions
  compatible with the target `pipecat-ai`, migrate `client/src/` RTVI usage (renamed events/messages), and gate
  on `npm` lint+build. Discover the client packages — do not assume which exist.
- **Iterative convergence**: gap analysis loops until a pass finds zero gaps.
- **Priority is an execution boundary**: compatibility Blockers are the only implementation work allowed before
  the review checkpoint. A lower-priority change does not become a Blocker merely because it is convenient to
  combine with one.
- **Optional means opt-in**: findings in the feature-adoption document remain recommendations until the user
  explicitly authorizes their implementation.
- **Validation gates**: `uv sync`, import smoke tests, `ruff`, `pytest`, Compose deploy. Human input only for
  the required blocker review, scope decisions, and validation that needs credentials or hardware.
