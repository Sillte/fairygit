# Copilot Instructions

## Architectural Principles

Preserve the project's existing package boundaries and design policies when
modifying code.

Do not apply Clean Architecture terminology mechanically. The project may use
project-specific boundaries when they make dependencies and responsibilities
more explicit.

When making a structural change, first identify:

1. Who uses the concept?
2. Who implements or extends the concept?
3. What is the smallest package boundary that should own the concept?
4. Which dependencies are allowed across that boundary?

Prefer making these boundaries explicit over relying on conventions that are
only apparent from implementation details.

---

## Public API

Each package should have an intentional Public API.

Code outside a package should normally import only symbols exposed by that
package's `__init__.py`.

Do not import internal implementation modules of another package merely because
they are convenient or currently available.

A module such as `models.py`, `types.py`, or `protocol.py` is not Public API
merely because it exists or contains generally useful types. Its symbols become
Public API only when the package intentionally exposes them.

When changing a package structure, preserve and clarify its Public API rather
than exposing internal implementation details.

---

## Contract

`contract` is a project-specific boundary for extension authors.

A contract contains concepts that an implementation extending a package or
infrastructure must understand in order to integrate with it.

Depending on the package, this may include:

- protocols implemented by extensions
- data types exchanged with extensions
- operation types required by extension implementations
- other concepts shared between the package implementation and extension authors

The purpose of `contract` is to make the extension boundary explicit.

Do not assume that every protocol belongs in `domain`, or that every contract
must be called a `port` according to Clean Architecture terminology.

The important question is the dependency boundary:

- ordinary package users have a user-facing Public API;
- extension authors have an extension-facing contract;
- internal implementations may depend on the contract without making their
  implementation details public.

These boundaries should be kept separate when their consumers or scope differ.

---

## Domain vs Contract

Use `domain` for concepts belonging to the package's domain and its ordinary
users.

Use `contract` when a concept primarily defines what an extension or
infrastructure implementation must provide or understand.

A concept may be an architectural "port" in the general Clean Architecture
sense while still belonging to `contract` in this project.

Do not move a concept between `domain` and `contract` solely to conform to
generic architectural terminology.

---

## Infrastructure

Infrastructure-specific concepts should remain inside the smallest
infrastructure boundary that contains their responsibilities.

If a protocol or data type is used only to implement or extend a particular
infrastructure mechanism, it should normally remain within that infrastructure
package.

Do not move an infrastructure contract to a higher-level package merely
because external code implements it.

The fact that something is implemented externally does not by itself determine
its architectural layer.

Its scope and dependency relationships determine its placement.

---

## Implementations

Implementation modules belong with the mechanism they implement.

Keep implementation details behind the appropriate Public API or contract.

Do not expose implementation modules merely to make imports convenient.

When an `impls` directory represents implementations of a particular runner
or infrastructure mechanism, treat those implementations as part of that
mechanism rather than introducing a separate architectural layer without a
clear reason.

---

## Dependency Direction

Prefer dependencies that point toward stable boundaries.

A contract may be depended upon by its implementations.

The contract must not depend on concrete implementations.

Higher-level code should not become dependent on infrastructure
implementation details merely because those details are convenient to access.

When introducing a dependency, consider whether it crosses a package boundary
and whether that dependency is part of the intended API or contract.

---

## Imports

For imports within the same package, both relative and absolute imports are
currently acceptable.

Do not perform broad import-style refactoring solely to enforce one of these
styles.

The important architectural rule is the package boundary, not the syntactic
choice between relative and absolute imports.

For imports from another package, prefer its Public API or explicitly defined
contract.

Avoid reaching into another package's internal modules.

---

## Refactoring

Before performing a structural refactoring:

1. Inspect the package tree and existing dependencies.
2. Identify the consumers and implementers of the affected concept.
3. Determine whether the concept belongs to the Public API, an extension
   contract, an internal implementation, or a domain boundary.
4. Make the smallest change that restores or clarifies the intended boundary.
5. Update imports and exports consistently.
6. Avoid unrelated architectural changes.

Do not broaden a package's Public API merely to avoid a refactoring.

Do not introduce a new architectural layer unless the dependency boundary
actually requires one.

When the correct placement is uncertain, preserve the existing behavior and
make the uncertainty explicit rather than inventing a new abstraction.

---

## Design Policy

Package-specific `Design Policy` documents (`DESIGN_POLICY.md` in the package root) are authoritative for the
corresponding package.

When a package-specific policy provides a more precise rule than these general
instructions, follow the package-specific policy.

Do not "correct" a project-specific design solely because another architecture
or codebase commonly uses different terminology or structure.

The goal is to make dependency boundaries explicit, stable, and understandable
to both human developers and coding agents.
