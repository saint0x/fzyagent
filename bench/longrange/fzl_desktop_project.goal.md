You are being evaluated on long-range autonomous execution and on how fast you can learn the FZY/FZL language from real project materials.

Primary reference material:
- Fozzylang source tree: `__FZL_SOURCE_DIR__`
- FZL showcase document: `__FZL_SHOWCASE_PATH__`

Task:
- Create a small, self-contained FZY project at `__TARGET_PROJECT_DIR__`.
- Inspect the real Fozzylang source and showcase before coding so your syntax and structure match the language as it is actually used.
- Use idiomatic FZY/FZL structure with a `fozzy.toml` file and a `src/` layout.
- Build something real but compact: a local CLI-style project with `src/main.fzy` plus at least one additional module under `src/`.
- Keep the project focused on demonstrating that you picked up the language correctly rather than building a huge app.

What the benchmark is checking:
- whether you can navigate the long-range workflow without getting stuck in plan churn
- whether you can extract syntax and idioms from source material and apply them correctly
- whether you can leave behind a concrete local project rather than only notes

Definition of done:
- the project directory exists on disk at `__TARGET_PROJECT_DIR__`
- it contains `fozzy.toml`, `src/main.fzy`, and at least one additional `.fzy` source file
- the code clearly reflects patterns learned from the provided Fozzylang references
- your final summary states what you built, which reference files you relied on most, and what FZY/FZL syntax or idioms you inferred from them
