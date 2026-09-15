# Upgrade Document Contract

Read this reference during Explore and Discover before generating upgrade documents.

## Output paths

Use the normalized target version without a leading `v` in these paths:

- `docs/how-to/upgrade-pipecat-v<TARGET>-compatibility.md`
- `docs/how-to/adopt-pipecat-v<TARGET>-features.md`

Respect a user-specified output directory or filename. Unless the user says the documents are review-only or
untracked, treat them as normal upgrade deliverables. Do not add navigation links unless repository conventions
or the user require them.

## Shared evidence rules

- State the detected current version, target version, resolution date, and whether the target is the latest stable
  release or an explicit user-selected version.
- Cover the current release entry as baseline and every stable release in `(CURRENT, TARGET]`. Include a release
  coverage table so omissions are visible.
- Cite canonical release/CHANGELOG URLs near the relevant finding. Use source diffs and installed target source
  to confirm exact APIs, not as a substitute for reading the release notes.
- Map every actionable finding to concrete repository components and paths. If paths must be discovered at run
  time, state the search rule and replace it with actual paths before implementation.
- Use simple language with enough technical detail to explain the contract, failure mode, and expected behavior.
- Record a relevant release note that requires no repository change in a no-action/deferred section with the
  reason. Do not silently omit it.

## Compatibility document

This document contains only work required to keep existing repository behavior working and supported after the
upgrade. Use these sections:

1. Scope and detected dependency surfaces.
2. Required migration changes.
3. Files and examples that must be exercised.
4. Release-note impact and no-action assessment.
5. Upgrade order and validation commands.

The required-change table must contain:

| Priority | Component and files | Required change | Why it is needed | Expected result | Status / evidence |
|---|---|---|---|---|---|

Assign the lowest defensible priority:

- **Blocker** — the upgrade cannot resolve, install, import, build, start a basic supported pipeline, or preserve a
  required server/client wire contract without it; it also includes a known correctness or safety failure that
  makes the upgraded baseline unusable.
- **High** — existing behavior can start, but an important supported path can fail, hang, silently degrade, or
  become operationally unsafe.
- **Medium** — compatibility debt, deprecation cleanup, or a narrower supported path that remains functional in
  the target release but should be migrated.
- **Low** — low-risk cleanup or validation hardening tied to the upgrade, with no immediate runtime failure.

Do not promote High/Medium/Low work to Blocker merely to avoid the human checkpoint. Keep optional product
improvements out of this document.

Initial status is `Planned`. During implementation use `Applied`, `Verified`, or `Deferred`, followed by concise
file and validation evidence. If a purported Blocker is disproved during implementation, reclassify it and leave
it for the post-review stage.

## Feature-adoption document

This document contains improvements made possible by the target releases but not required for compatibility.
Use these sections:

1. Scope and explicit statement that implementation requires separate user authorization.
2. Recommended improvements.
3. Features to defer or leave disabled, with reasons.
4. Suggested adoption sequence.

The recommendation table must contain:

| Improvement | Components and files | Required implementation change | Why it helps | Expected improvement | Preconditions / risks |
|---|---|---|---|---|---|

Include applicable observability, evaluation, turn-taking, transport, tool, reliability, and developer-experience
features discovered in the release range. Explain why provider-specific or architecture-mismatched features do
not apply. Do not turn a feature recommendation into a dependency bump, code edit, configuration change, test
change, workflow edit, or deployment change without a later explicit user request.

## Pre-implementation review

Before editing runtime/dependency code, present both document paths and summarize:

- Blocker count and affected surfaces.
- High/Medium/Low counts.
- Optional feature count.
- Any unresolved evidence or unavailable source.

Document creation is not the blocker-review checkpoint. Continue to the Blocker implementation stage unless the
user asks to review the plan first. The mandatory stop occurs after all Blockers have been applied and validated.
