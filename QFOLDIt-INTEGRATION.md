# qFoldIT Consolidation & Validation Notice

**Status checked:** 2026-10-12  
**Repository role:** frozen Python Toolbelt migration source and historical capability lineage.

New qFoldIT orchestration and release work belongs in the canonical [`qfoldit/UEFN-QFOLDIT`](https://github.com/qfoldit/UEFN-QFOLDIT) repository, not in this historical fork.

## Canonical architecture

```text
Scientific / Industrial Mission
          ↓
Rust Mission Contract / Scientific Action Envelope
          ↓
qFoldIT Rust policy + runtime adapter
          ↓
qfoldit-uefn-mcp (Node.js stdio MCP sidecar)
          ↓
Epic official local UEFN MCP endpoint
          ↓
Running UEFN editor
```

## Local integration validation

The project owner confirms that, on 2026-10-12, the live connection to a running UEFN editor and real editor operations were fully tested locally through the canonical integration. The qFoldIT sidecar CI also passed on merge commit [`fba302a`](https://github.com/qfoldit/UEFN-QFOLDIT/commit/fba302a660938d35de3306b2ef0a9ee74437a23f).

This status applies to the canonical qFoldIT integration, **not to this old Python MCP bridge**. It also does not mean custom qFoldIT tools have been registered as first-party tools in Epic's official MCP server.

## Current Rust qualification

The Rust source defines mission/capability/evidence/economics contracts and a Rust-native Toolbelt policy surface, including tool manifest authorization, action-envelope integrity checks, local path safety, launch-session handling and publish auditing. However, the wider Rust workspace currently has failed format/compiler/conformance CI gates; the live UEFN test result and workspace build status are separate facts.

- [Canonical Rust implementation status](https://github.com/qfoldit/UEFN-QFOLDIT/blob/main/docs/RUST-IMPLEMENTATION-STATUS-2026-10-12.md)
- [Epic UEFN MCP integration contract](https://github.com/qfoldit/UEFN-QFOLDIT/blob/main/docs/UEFN-EPIC-MCP-INTEGRATION.md)
- [PR #18 — merged sidecar integration](https://github.com/qfoldit/UEFN-QFOLDIT/pull/18)

Do not create a second qFoldIT control plane in this repository. Preserve the upstream authorship, copyright, licensing and attribution requirements for all imported/reference components.
