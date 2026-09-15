"""Shared analysis contracts. Adapters do not depend on the CLI or report."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Protocol


def stable_id(*parts: object) -> str:
    return sha256("\0".join(map(str, parts)).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Location:
    file: str
    line: int = 1
    column: int = 1

    def evidence(self, detail: str) -> dict:
        return {"file": self.file, "line": self.line, "column": self.column, "detail": detail}


@dataclass
class Project:
    root: Path
    name: str
    key: str
    languages: list[str] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    files_pending: bool = False

    @property
    def id(self) -> str:
        return stable_id("project", self.key)


@dataclass
class Expr:
    kind: str
    value: str = ""
    args: list[Expr] = field(default_factory=list)
    props: dict[str, Expr] = field(default_factory=dict)
    loc: Location = field(default_factory=lambda: Location(""))


@dataclass
class Binding:
    name: str
    expr: Expr
    scope: str
    type_name: str = ""


@dataclass
class Function:
    name: str
    scope: str
    parent: str
    params: list[str]
    defaults: dict[str, Expr]
    returns: list[Expr]
    loc: Location


@dataclass
class Import:
    local: str
    module: str
    member: str = ""
    scope: str = ""


@dataclass
class Call:
    expr: Expr
    scope: str


@dataclass
class Unit:
    path: str
    language: str
    bindings: list[Binding] = field(default_factory=list)
    functions: list[Function] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    parents: dict[str, str] = field(default_factory=lambda: {"": ""})
    diagnostics: list[dict] = field(default_factory=list)


class Adapter(Protocol):
    language: str

    def parse(self, path: str, source: bytes) -> Unit: ...


@dataclass
class Value:
    kind: str
    text: str = ""
    props: dict[str, Value] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    evidence: list[dict] = field(default_factory=list)

    @classmethod
    def unknown(cls, name: str, reason: str, loc: Location | None = None) -> Value:
        return cls("unknown", "{" + name + "}", reasons=(reason,),
                   evidence=[loc.evidence(reason)] if loc else [])


def merge_evidence(*values: Value) -> list[dict]:
    result = []
    for value in values:
        for item in value.evidence:
            if item not in result:
                result.append(item)
    return result[:40]
