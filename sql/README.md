# Database SQL

These files are operational database proposals and maintenance helpers. The
MOCAviz application does not execute them automatically. Review the target
schema, permissions, and execution plan before applying any file.

- `indexes/`: optional index additions and recommendations.
- `schema/`: schema extensions used by application features.
- `staging/`: generated or hand-reviewed data staging statements.
- `views/`: public database view definitions.

Files named `recommended_*` are proposals. Staging scripts may contain
environment-specific identifiers and should be regenerated or reviewed before
reuse.
