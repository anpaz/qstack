"""Single-step compilation results and reproducible verification artifacts.

An artifact contains exactly the source and target of one compiler invocation.
It never contains the witnesses or modules from earlier invocations.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

from xdsl.context import Context
from xdsl.dialects.builtin import Builtin, ModuleOp
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack.dialect import QStack
from qstack.dialect.registry import registered_isa_dialects

if TYPE_CHECKING:
    from qstack.verification.model import Witness


ARTIFACT_VERSION = 2


class ArtifactError(ValueError):
    """A compilation artifact is missing, malformed, or has changed."""


def module_text(module: ModuleOp) -> str:
    stream = StringIO()
    Printer(stream=stream).print_op(module)
    return stream.getvalue()


def parse_module(text: str) -> ModuleOp:
    context = Context()
    context.load_dialect(Builtin)
    context.load_dialect(QStack)
    for dialect in registered_isa_dialects():
        context.load_dialect(dialect)
    module = Parser(context, text).parse_module()
    from qstack.verifier import verify_module

    module.verify()
    verify_module(module)
    return module


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompilationArtifact:
    source: str
    target: str
    source_sha256: str
    target_sha256: str
    witness: Witness | None

    def validate_hashes(self) -> None:
        if _digest(self.source) != self.source_sha256:
            raise ArtifactError("source IR does not match its recorded SHA-256")
        if _digest(self.target) != self.target_sha256:
            raise ArtifactError("target IR does not match its recorded SHA-256")
        if self.witness is not None and (
            self.witness.source_sha256 != self.source_sha256
            or self.witness.target_sha256 != self.target_sha256
        ):
            raise ArtifactError("witness is bound to different source or target IR")

    def to_dict(self) -> dict[str, object]:
        return {
            "version": ARTIFACT_VERSION,
            "source": self.source,
            "target": self.target,
            "source_sha256": self.source_sha256,
            "target_sha256": self.target_sha256,
            "witness": None if self.witness is None else self.witness.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CompilationArtifact:
        from qstack.verification.model import Witness

        if data.get("version") != ARTIFACT_VERSION:
            raise ArtifactError(f"unsupported compilation artifact version {data.get('version')!r}")
        try:
            raw_witness = data["witness"]
            witness = None if raw_witness is None else Witness.from_dict(raw_witness)
            artifact = cls(
                source=str(data["source"]),
                target=str(data["target"]),
                source_sha256=str(data["source_sha256"]),
                target_sha256=str(data["target_sha256"]),
                witness=witness,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactError("malformed compilation artifact") from exc
        artifact.validate_hashes()
        return artifact


def load_artifact(path: str | Path) -> CompilationArtifact:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactError(f"cannot read compilation artifact {path}") from exc
    if not isinstance(data, dict):
        raise ArtifactError("compilation artifact must be a JSON object")
    return CompilationArtifact.from_dict(data)


@dataclass(frozen=True)
class CompilationResult:
    """Current module and the witness for only its immediately preceding step."""

    module: ModuleOp
    witness: Witness | None = None
    artifact_path: Path | None = None

    def __getattr__(self, name: str):
        """Keep existing IR inspection code working during the result-API migration."""
        return getattr(self.module, name)

    @classmethod
    def from_module(cls, module: ModuleOp) -> CompilationResult:
        """Enter the compiler pipeline with directly constructed IR."""
        from qstack.verifier import verify_module

        module.verify()
        verify_module(module)
        return cls(module)

    @classmethod
    def from_step(
        cls,
        source: CompilationResult,
        target_module: ModuleOp,
        witness: Witness | None = None,
        *,
        artifact_path: str | Path | None = None,
        source_snapshot: str | None = None,
    ) -> CompilationResult:
        """Persist the exact module pair and return the new single-step result."""
        from qstack.verifier import verify_module

        source.module.verify()
        target_module.verify()
        verify_module(source.module)
        verify_module(target_module)
        source_ir = module_text(source.module)
        if source_snapshot is not None and source_ir != source_snapshot:
            raise ArtifactError("compiler mutated its source module")
        target_ir = module_text(target_module)
        source_hash = _digest(source_ir)
        target_hash = _digest(target_ir)
        if witness is not None and (
            witness.source_sha256 != source_hash or witness.target_sha256 != target_hash
        ):
            raise ArtifactError("witness hashes do not match the compiled modules")
        artifact = CompilationArtifact(
            source_ir, target_ir, source_hash, target_hash, witness
        )
        if artifact_path is None:
            descriptor, filename = tempfile.mkstemp(prefix="qstack-step-", suffix=".json")
            path = Path(filename)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(artifact.to_dict(), stream, sort_keys=True, separators=(",", ":"))
        else:
            path = Path(artifact_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, filename = tempfile.mkstemp(
                prefix=path.name + ".", suffix=".tmp", dir=path.parent
            )
            temporary = Path(filename)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(artifact.to_dict(), stream, sort_keys=True, separators=(",", ":"))
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        loaded = load_artifact(path)
        if loaded.target != target_ir or loaded.source != source_ir:
            raise ArtifactError("compilation artifact did not round-trip")
        return cls(target_module, witness, path)

    @classmethod
    def load(cls, path: str | Path) -> CompilationResult:
        artifact = load_artifact(path)
        return cls(parse_module(artifact.target), artifact.witness, Path(path).resolve())

    def save(self, path: str | Path) -> CompilationResult:
        """Keep an automatically created step artifact at a chosen path."""
        if self.artifact_path is None:
            raise ArtifactError("initial compilation result has no step artifact")
        artifact = load_artifact(self.artifact_path)
        if module_text(self.module) != artifact.target or self.witness != artifact.witness:
            raise ArtifactError("result does not match its step artifact")
        destination = Path(path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.artifact_path != destination:
            descriptor, filename = tempfile.mkstemp(
                prefix=destination.name + ".", suffix=".tmp", dir=destination.parent
            )
            temporary = Path(filename)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    with self.artifact_path.open("rb") as source:
                        shutil.copyfileobj(source, stream)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        return CompilationResult(self.module, self.witness, destination)
