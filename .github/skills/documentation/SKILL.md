---
name: documentation
description: >
  Decide what information belongs in docstrings, DESIGN_POLICY.md,
  or other documentation. Use when creating, reviewing, updating,
  or removing documentation or design documentation.
user-invocable: true
---

# Documentation

Use this skill when creating, reviewing, updating, or removing
documentation or docstrings.

## Principles

- Document knowledge that would otherwise be lost.
- Do not duplicate information reliably available from code,
  types, APIs, tests, or other authoritative sources.
- Prefer the smallest useful document.
- Remove documentation when its information becomes reliably
  recoverable elsewhere.
- Assume that readers have perfect knowledge of the programming language
  and external packages. Do not document general language or package
  knowledge unless it is necessary to explain project-specific behavior, constraints, or design decisions.

## Documentation Ownership

- **Docstring**: documentation for users of an individual API.
  - information needed by users of an individual API
  - API-specific usage and behavior

- **DESIGN_POLICY.md**: documentation for the developers of the codebase.
  - purpose of package
  - project-specific terminology
  - responsibilities
  - responsibility boundaries
  - design decisions
  - constraints
  - rationale

## Procedure

1. Identify the information being documented and determine the appropriate documentation owner.
2. Check whether the information is reliably available from an authoritative source.
3. If it is, do not duplicate it.
4. Write only the information that would otherwise be lost.
5. Review existing documentation and remove information that is
   obsolete, duplicated, or otherwise no longer necessary.

### Completion Check

Before finishing, confirm that:

- Every statement has an intentional documentation owner.
- The document does not unnecessarily duplicate another source of truth.
- The document is concise and contains no empty sections.

## When Working with DESIGN_POLICY.md

Before modifying a DESIGN_POLICY.md, read all applicable policies.

A DESIGN_POLICY.md applies to its directory and descendants.
A more specific policy refines a broader policy.

A DESIGN_POLICY.md should contain only information that cannot
be reliably recovered from code or other sources of truth.

Use only sections that contain meaningful information.

Common sections include:

- Purpose
- Terminology
- Design
- Rules
- Notes
- Discussions

### Completion Check

When finishing a DESIGN_POLICY.md change, confirm that:

- The scope and applicable policies are clear.
- Final decisions are separated from unresolved discussions.