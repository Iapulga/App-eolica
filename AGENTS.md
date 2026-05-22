# AGENTS.md

## Product intent

This repository contains a wind energy application that must remain a general-purpose tool.
Do not overfit the application to a single academic assignment or one-off workflow.
Academic requirements should be implemented as optional presets, templates, or report profiles.

## Core principles

- Preserve backward compatibility whenever reasonably possible.
- Prefer additive and modular changes over breaking rewrites.
- Keep the app usable in free mode without hard-coded academic restrictions.
- Treat validation rules such as minimum turbine count, power caps, mandatory sections, or specific report formats as optional profiles, not global blockers.
- Use warnings and recommendations before hard stops.

## Architecture expectations

- Keep calculation logic separated from the Streamlit UI as much as practical.
- Reuse shared helpers instead of duplicating formulas across pages.
- Prefer small, reviewable edits.
- Do not remove stable features unless a replacement is implemented in the same change.
- Keep database and project-file compatibility in mind when changing schemas or saved project structures.

## Domain expectations

- Support multiple wind-analysis workflows when possible.
- Prefer configurable inputs over fixed assumptions.
- Keep support open for multiple data sources, turbine models, statistical models, wake models, loss assumptions, and report formats.
- Make academic export features optional and isolated from the core workflow.

## Safe change policy

- Before editing, inspect the affected files and understand existing behavior.
- Avoid unnecessary renames or file moves.
- Do not introduce destructive migrations without a rollback path.
- When changing saved project structure, include compatibility handling for older projects when feasible.

## Implementation style

- Keep code readable and explicit.
- Add concise comments only where the intent is not obvious.
- Prefer clear function names and small helper functions.
- When adding a new feature, integrate it into the existing UX patterns instead of creating disconnected flows.

## Task execution guidance

- For non-trivial tasks, first summarize the plan and identify the files to change.
- After edits, list exactly what changed and any follow-up risks.
- When possible, run or suggest the most relevant verification step.

## Current product direction

Prioritize work in this order unless the user says otherwise:

1. Strengthen modularity and separation of concerns.
2. Preserve and improve the free/general workflow.
3. Add optional profiles or presets, including an academic mode.
4. Improve reporting and export, including LaTeX-based academic reports as optional outputs.
5. Expand support for more wind data, models, and scenario comparisons.
