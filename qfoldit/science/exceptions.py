"""
Custom exceptions for protein-design-mcp.

All exceptions inherit from ProteinDesignError for easy catching.
"""


class ProteinDesignError(Exception):
    """Base exception for protein design errors."""

    pass


class InvalidPDBError(ProteinDesignError):
    """Raised when PDB file is invalid or malformed."""

    pass


class PipelineError(ProteinDesignError):
    """Raised when a pipeline step fails."""

    pass


class RFdiffusionError(PipelineError):
    """Raised when RFdiffusion execution fails."""

    pass


class ProteinMPNNError(PipelineError):
    """Raised when ProteinMPNN execution fails."""

    pass


class ESMFoldError(PipelineError):
    """Raised when ESMFold prediction fails."""

    pass


class AlphaFold2Error(PipelineError):
    """Raised when AlphaFold2/ColabFold prediction fails."""

    pass


class PyRosettaError(PipelineError):
    """Raised when PyRosetta execution fails."""

    pass


class BoltzError(PipelineError):
    """Raised when Boltz prediction fails."""

    pass


class ZairaChemError(PipelineError):
    """Raised when ZairaChem (QSAR/bioactivity) execution fails."""

    pass


class QuantumBackendError(PipelineError):
    """Raised when a quantum-computing backend (qupepfold/Qiskit/Braket)
    is present but fails during execution (bad circuit, backend
    rejection, timeout, etc).

    Deliberately NOT used for "the quantum venv/package isn't installed"
    -- that case is handled as a normal, structured error dict (see
    pipelines/quantum_runner.py) so the MCP dispatch loop never crashes
    the server process just because an optional heavy dependency
    (Qiskit / Amazon Braket / qupepfold) isn't present in the active venv.
    """

    pass


class ValidationError(ProteinDesignError):
    """Raised when validation fails."""

    pass


class ResourceNotFoundError(ProteinDesignError):
    """Raised when a requested resource is not found."""

    pass


class PresetError(ProteinDesignError):
    """Base for errors raised by science/presets.py's level-preset catalog."""

    pass


class PresetNotFoundError(PresetError):
    """Raised when a preset key isn't in presets.PRESETS."""

    pass


class PresetSourceRequiredError(PresetError):
    """Raised when build_level()/build_universal_level() is asked to build a
    single_player preset with no source result supplied. presets.py never
    fabricates a science result to fill the gap -- this error is the
    documented alternative to silently inventing one."""

    pass


class PresetContentBlockedError(PresetError):
    """Raised when a built level's text (title override, tagline, level/
    achievement descriptions -- anything that could carry a prompt- or
    source-controlled string) matches a compliance/trust_runtime.py
    watchlist term with no covering license_manifest.json entry.
    Presets are levels assembled from prompts; that text goes through the
    SAME default-deny IP gate as run_toolbelt_tool/execute_python before a
    level is ever returned, not just when something is actually placed in
    UEFN. Never bypass this to "let the level through anyway" -- fix the
    prompt/title, or add a real manifest entry if the brand is genuinely
    licensed."""

    pass
