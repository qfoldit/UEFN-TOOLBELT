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
