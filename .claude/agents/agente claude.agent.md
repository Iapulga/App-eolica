# AGENTS.md

## Product intent
Wind energy calculation app. General-purpose tool — no hardcoded academic restrictions.
Academic features = optional presets/profiles only.

## Core principles
- Additive changes over rewrites. Preserve backward compatibility.
- Warnings before hard stops. No global blockers.
- Free mode must work fully without academic presets.

## Architecture
- Calculation logic separated from Streamlit UI.
- Reuse helpers — no formula duplication across pages.
- Small, reviewable edits only.
- Never remove stable features without a same-PR replacement.

## Safe change policy
- Inspect affected files BEFORE editing. Understand existing behavior first.
- No destructive migrations without rollback path.
- No unnecessary renames or file moves.

## Code style
- Readable and explicit. Comments only where intent is non-obvious.
- Clear function names. Small helpers preferred.
- New features integrate into existing UX patterns.

## Task execution (token-efficient workflow)
1. Read only the files you will actually change — do not open all files speculatively.
2. State a one-paragraph plan before touching any file.
3. Make all edits in a single pass per file when possible.
4. After edits: list changed files + lines, run `python -m py_compile` on each, report result.
5. Do not re-read files you already have in context unless the file changed.
6. Do not produce summaries longer than 5 bullet points unless asked.

## CSS rules — critical (active bug)
**Expanders broken in Phases 1, 3, 4, 5, 6.**
Root cause: parent card containers have `overflow: hidden !important`
which clips expander content when it opens.

Fix rule:
- `overflow: hidden` → ALLOWED only on: `[data-baseweb="input"]`,
  `.stDataFrame`, chart wrappers, and fixed-height graphic cards
  that contain NO `st.expander` inside.
- `overflow: visible` → REQUIRED on any `.st-key-fX_card_*` container
  that wraps one or more `st.expander` calls.

To identify which cards need the fix:
1. Search each phase file for `with st.expander`.
2. Find the enclosing `_phase_card("fX_card_NAME")` call.
3. Find the CSS selector `.st-key-fX_card_NAME` and set overflow to visible.

Files to fix:
- `pages/1_Fase_1_Aerogenerador.py` — `.st-key-f1_card_g` line ~1121
- `pages/4_Fase_4_Estelas_y_arreglo.py` — find card wrapping expanders
- `pages/5_Fase_5_AEP_bruta_y_neta.py` — find card wrapping expanders
- `pages/6_Fase_6_Exportar_y_guardar.py` — find card wrapping expanders

Phase 3 already has `overflow: visible` on `f3_card_expanders` — skip it.

After fixing, verify with: `python -m py_compile pages/X_Fase_X.py && echo OK`

## Priority order
1. Fix expander overflow bug (see CSS rules above) — CURRENT TASK
2. Modularity and separation of concerns
3. Free/general workflow integrity
4. Optional academic profile/presets
5. Reporting and LaTeX export improvements