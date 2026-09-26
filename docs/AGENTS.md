# Coding Agent Instructions

## Role and authority

The CEO makes decisions about scope, architecture, priorities, and product direction. The agent executes approved work. If unsure, stop and ask the CEO.

The repository authority order is:

```text
CEO instruction
    ↓
AGENTS.md
    ↓
Approved task
    ↓
DECISIONS.md
    ↓
Current architecture/code
    ↓
Other documentation
```

## Required workflow

1. **Read context before acting.** Read [CONTEXT.md](CONTEXT.md), [TASKS.md](TASKS.md), [DECISIONS.md](DECISIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md), relevant documentation and code, and relevant entries in [COMPLETED.md](COMPLETED.md). Understand the requested result, current state, and constraints before editing.
2. **Follow the exact request.** Complete only the explicitly requested task. Do not expand scope, make unrelated improvements, or start the next task without an explicit CEO request.
3. **Do not make consequential assumptions.** Separate verified facts from unknowns. Ask the CEO when requirements are unclear, conflicting, or require a product or design decision. If an existing file conflicts with the request or permission to modify it is unclear, ask before changing it.
4. **Use minimum necessary changes.** Modify only files needed for the approved task. Preserve unrelated content and existing user changes.
5. **Obtain explicit permission for major changes.** This includes deleting or renaming files, restructuring directories, changing architecture, adding or replacing major dependencies, changing database schemas, performing migrations, changing deployment or infrastructure, changing authentication or security controls, and publishing, deploying, or releasing anything.
6. **Verify completed work where possible.** Use appropriate existing tests, checks, builds, or documentation validation. Report actual results and limitations. Do not claim verification passed when it failed or was unavailable.
7. **Record completed work.** Append an entry using the template in [COMPLETED.md](COMPLETED.md), including changed files, verification, decisions, and remaining issues.
8. **Report the result.** Explain what changed, list files created or modified, and identify anything still requiring CEO approval. Stop after the approved task.

## Current approved scope

This repository is in documentation setup only. The product concept is recorded in CONTEXT.md. The CEO-approved technology stack is recorded in [ARCHITECTURE.md](ARCHITECTURE.md). Detailed architecture and implementation remain pending CEO approval.

Do not write application code, install dependencies, choose a technology stack or database, design APIs or the final data model, build OSINT collectors, implement scraping or scoring, or design the application architecture unless the CEO explicitly approves that work. Documentation placeholders are not approval to design or implement their subjects.

TASKS.md contains approved tasks only. DECISIONS.md records CEO-approved decisions only; agents must not invent decisions or approvals.
