# qFoldIT Rust Migration Boundary

The canonical qFoldIT UEFN Toolbelt runtime is now implemented in Rust inside `qfoldit/UEFN-QFOLDIT/crates/uefn-toolbelt`.

This repository is retained as historical and implementation lineage. New qFoldIT orchestration, mission semantics, provenance, permission logic and tool registry features must be implemented in the canonical Rust workspace first.

The migration is capability-first rather than a blind one-to-one rewrite of every historical Python command. Individual tools may be retired from this repository after Rust parity, conformance coverage and provenance preservation are established.
