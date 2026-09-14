---
name: defend-it
description: Review the work done since the last commit and explain every decision in terms the developer could defend in a technical interview. Use after finishing a block of work and before committing, or whenever the developer asks for a review pass, a defence check, or to walk through what was just built.
---

# Defend it

This project is a take-home assignment. The reviewer will ask the developer to
walk through the decisions and trade-offs in a 45-minute conversation. Code the
developer cannot explain is worse than code that does less.

The goal of this skill is not to find bugs. It is to make sure nothing was
written that the developer does not understand and could not justify out loud.

## How to run it

1. Get the diff of everything not yet committed (`git diff` and `git diff
--staged`, plus untracked files).

2. Go through it and produce a short report with these sections:

   **What was built** — two or three sentences, plain language, no file list.

   **Decisions taken** — every choice that had a real alternative. For each one:
   what was chosen, what the alternative was, and the one-sentence reason. If a
   decision was made implicitly (a default, a library convention, something
   copied from documentation), say so explicitly — those are the ones that
   ambush people in interviews.

   **Non-obvious code** — anything a reader would have to stop and think about:
   concurrency, transactions, generators holding a database cursor open,
   timing-safe comparisons, dialect-specific SQL. Explain what it does and why
   the simpler version would not work.

   **Cannot be defended yet** — be direct here. Anything in the diff whose
   rationale is "the framework does it this way" or "it was generated and it
   works" goes in this list. This is the most valuable section; do not soften
   it or leave it empty to be agreeable.

   **For NOTES.md** — any decision from this block that belongs in the
   deliverable, drafted as a sentence or two ready to paste.

3. Keep the whole report under roughly 400 words. It is read after every block
   of work, so it has to stay short enough to actually be read.

## Rules

- Do not rewrite code as part of this pass. If something is wrong, say so and
  stop; fixing it is a separate decision.
- Do not praise the code. The report has no value if it flatters.
- Judge against the project's own constraints in CLAUDE.md, especially the
  non-goals. An abstraction that was not asked for is a finding, even if it is
  well written.
