# qFoldIT Game Designer Skill

Creates Universal Assembly Graph plans and exports them to target runtimes.

UAG (this skill's output format, `references/uag_schema.md`) is a concrete, engine-facing 3D scene graph -- narrower than and distinct from SKG (Scientific Knowledge Graph) + SEM (Scientific Execution Model), the broader scientific-activity graph/execution model defined in the ecosystem's separate [Scientific World Schema](https://github.com/qfoldit/scientific-world-schema) (§7). A UAG document is what an SKG `DigitalTwin` node's content looks like when it targets a game engine; this skill only ever produces/consumes UAG, never SKG/SEM directly.
