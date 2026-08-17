"""Deterministic JSON serialization for notebook facts."""

import json
from collections.abc import Mapping, Sequence
from typing import TypeAlias, cast

from notebook_to_kedro.ir.facts import (
    CallFacts,
    CellFacts,
    CellKind,
    DependencyFacts,
    Diagnostic,
    DiagnosticDetail,
    ImportFacts,
    ImportKind,
    JsonPrimitive,
    KeywordArgument,
    NotebookFacts,
    NotebookMetadata,
    Severity,
    SourceLocation,
    StatementFacts,
    SymbolAccess,
    SymbolFacts,
    SymbolKind,
)

JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def _location_to_dict(location: SourceLocation | None) -> JsonValue:
    if location is None:
        return None
    return {
        "cell_index": location.cell_index,
        "start_line": location.start_line,
        "start_column": location.start_column,
        "end_line": location.end_line,
        "end_column": location.end_column,
    }


def _access_to_dict(access: SymbolAccess) -> JsonObject:
    return {"cell_index": access.cell_index, "statement_id": access.statement_id}


def _import_to_dict(import_: ImportFacts) -> JsonObject:
    return {
        "kind": import_.kind.value,
        "module": import_.module,
        "name": import_.name,
        "alias": import_.alias,
        "bound_name": import_.bound_name,
        "location": _location_to_dict(import_.location),
    }


def _call_to_dict(call: CallFacts) -> JsonObject:
    return {
        "id": call.id,
        "qualified_name": call.qualified_name,
        "receiver": call.receiver,
        "method": call.method,
        "positional_argument_sources": list(call.positional_argument_sources),
        "keyword_argument_sources": {
            argument.name: argument.source for argument in call.keyword_arguments
        },
        "literal_arguments": list(call.literal_arguments),
        "possible_mutation_targets": list(call.possible_mutation_targets),
        "location": _location_to_dict(call.location),
    }


def _statement_to_dict(statement: StatementFacts) -> JsonObject:
    return {
        "id": statement.id,
        "index": statement.index,
        "ast_type": statement.ast_type,
        "source": statement.source,
        "location": _location_to_dict(statement.location),
        "reads": list(statement.reads),
        "writes": list(statement.writes),
        "calls": list(statement.call_ids),
        "conditional": statement.conditional,
    }


def _cell_to_dict(cell: CellFacts) -> JsonObject:
    return {
        "id": cell.id,
        "index": cell.index,
        "kind": cell.kind.value,
        "execution_count": cell.execution_count,
        "source": cell.source,
        "statements": [_statement_to_dict(statement) for statement in cell.statements],
        "reads": list(cell.reads),
        "writes": list(cell.writes),
        "imports": [_import_to_dict(import_) for import_ in cell.imports],
        "calls": [_call_to_dict(call) for call in cell.calls],
        "diagnostic_codes": list(cell.diagnostic_codes),
    }


def _symbol_to_dict(symbol: SymbolFacts) -> JsonObject:
    return {
        "name": symbol.name,
        "kind": symbol.kind.value,
        "definitions": [_access_to_dict(access) for access in symbol.definitions],
        "reads": [_access_to_dict(access) for access in symbol.reads],
    }


def _dependency_to_dict(dependency: DependencyFacts) -> JsonObject:
    return {
        "id": dependency.id,
        "symbol": dependency.symbol,
        "producer": _access_to_dict(dependency.producer),
        "consumer": _access_to_dict(dependency.consumer),
        "resolution": dependency.resolution,
    }


def _diagnostic_to_dict(diagnostic: Diagnostic) -> JsonObject:
    return {
        "id": diagnostic.id,
        "code": diagnostic.code,
        "severity": diagnostic.severity.value,
        "message": diagnostic.message,
        "blocking": diagnostic.blocking,
        "location": _location_to_dict(diagnostic.location),
        "related_symbol": diagnostic.related_symbol,
        "details": {detail.key: detail.value for detail in diagnostic.details},
    }


def notebook_facts_to_dict(facts: NotebookFacts) -> dict[str, object]:
    """Convert notebook facts to their canonical JSON-compatible dictionary."""
    metadata = facts.notebook
    payload: JsonObject = {
        "schema_version": facts.schema_version,
        "analyzer_version": facts.analyzer_version,
        "notebook": {
            "path": metadata.path,
            "nbformat": metadata.nbformat,
            "nbformat_minor": metadata.nbformat_minor,
            "language": metadata.language,
            "kernel_name": metadata.kernel_name,
            "cell_count": metadata.cell_count,
            "content_sha256": metadata.content_sha256,
        },
        "cells": [_cell_to_dict(cell) for cell in facts.cells],
        "symbols": [_symbol_to_dict(symbol) for symbol in facts.symbols],
        "dependencies": [_dependency_to_dict(dependency) for dependency in facts.dependencies],
        "diagnostics": [_diagnostic_to_dict(diagnostic) for diagnostic in facts.diagnostics],
    }
    return cast("dict[str, object]", payload)


def notebook_facts_to_json(facts: NotebookFacts, *, indent: int | None = 2) -> str:
    """Serialize notebook facts with stable key and collection ordering."""
    return json.dumps(
        notebook_facts_to_dict(facts),
        ensure_ascii=False,
        indent=indent,
        separators=(",", ":") if indent is None else None,
        sort_keys=True,
    )


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        message = f"{field_name} must be an object"
        raise TypeError(message)
    if not all(isinstance(key, str) for key in value):
        message = f"{field_name} keys must be strings"
        raise TypeError(message)
    return cast("Mapping[str, object]", value)


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        message = f"{field_name} must be an array"
        raise TypeError(message)
    return cast("Sequence[object]", value)


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        message = f"{field_name} must be a string"
        raise TypeError(message)
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        message = f"{field_name} must be an integer"
        raise TypeError(message)
    return value


def _optional_integer(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _integer(value, field_name)


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        message = f"{field_name} must be a boolean"
        raise TypeError(message)
    return value


def _primitive(value: object, field_name: str) -> JsonPrimitive:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    message = f"{field_name} must be a JSON primitive"
    raise TypeError(message)


def _required(payload: Mapping[str, object], field_name: str) -> object:
    try:
        return payload[field_name]
    except KeyError as error:
        message = f"missing required field: {field_name}"
        raise ValueError(message) from error


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    return tuple(_string(item, f"{field_name} item") for item in _sequence(value, field_name))


def _location_from_value(value: object, field_name: str) -> SourceLocation | None:
    if value is None:
        return None
    payload = _mapping(value, field_name)
    return SourceLocation(
        cell_index=_integer(_required(payload, "cell_index"), f"{field_name}.cell_index"),
        start_line=_optional_integer(payload.get("start_line"), f"{field_name}.start_line"),
        start_column=_optional_integer(payload.get("start_column"), f"{field_name}.start_column"),
        end_line=_optional_integer(payload.get("end_line"), f"{field_name}.end_line"),
        end_column=_optional_integer(payload.get("end_column"), f"{field_name}.end_column"),
    )


def _required_location(value: object, field_name: str) -> SourceLocation:
    location = _location_from_value(value, field_name)
    if location is None:
        message = f"{field_name} must not be null"
        raise TypeError(message)
    return location


def _access_from_value(value: object, field_name: str) -> SymbolAccess:
    payload = _mapping(value, field_name)
    return SymbolAccess(
        cell_index=_integer(_required(payload, "cell_index"), f"{field_name}.cell_index"),
        statement_id=_string(_required(payload, "statement_id"), f"{field_name}.statement_id"),
    )


def _import_from_value(value: object, field_name: str) -> ImportFacts:
    payload = _mapping(value, field_name)
    return ImportFacts(
        kind=ImportKind(_string(_required(payload, "kind"), f"{field_name}.kind")),
        module=_string(_required(payload, "module"), f"{field_name}.module"),
        name=_optional_string(payload.get("name"), f"{field_name}.name"),
        alias=_optional_string(payload.get("alias"), f"{field_name}.alias"),
        bound_name=_string(_required(payload, "bound_name"), f"{field_name}.bound_name"),
        location=_required_location(_required(payload, "location"), f"{field_name}.location"),
    )


def _call_from_value(value: object, field_name: str) -> CallFacts:
    payload = _mapping(value, field_name)
    keyword_sources = _mapping(
        _required(payload, "keyword_argument_sources"),
        f"{field_name}.keyword_argument_sources",
    )
    literal_values = _sequence(
        _required(payload, "literal_arguments"), f"{field_name}.literal_arguments"
    )
    return CallFacts(
        id=_string(_required(payload, "id"), f"{field_name}.id"),
        qualified_name=_string(
            _required(payload, "qualified_name"), f"{field_name}.qualified_name"
        ),
        receiver=_optional_string(payload.get("receiver"), f"{field_name}.receiver"),
        method=_optional_string(payload.get("method"), f"{field_name}.method"),
        positional_argument_sources=_string_tuple(
            _required(payload, "positional_argument_sources"),
            f"{field_name}.positional_argument_sources",
        ),
        keyword_arguments=tuple(
            KeywordArgument(name, _string(source, f"{field_name}.keyword source"))
            for name, source in sorted(keyword_sources.items())
        ),
        literal_arguments=tuple(
            _primitive(item, f"{field_name}.literal argument") for item in literal_values
        ),
        possible_mutation_targets=_string_tuple(
            _required(payload, "possible_mutation_targets"),
            f"{field_name}.possible_mutation_targets",
        ),
        location=_required_location(_required(payload, "location"), f"{field_name}.location"),
    )


def _statement_from_value(value: object, field_name: str) -> StatementFacts:
    payload = _mapping(value, field_name)
    return StatementFacts(
        id=_string(_required(payload, "id"), f"{field_name}.id"),
        index=_integer(_required(payload, "index"), f"{field_name}.index"),
        ast_type=_string(_required(payload, "ast_type"), f"{field_name}.ast_type"),
        source=_string(_required(payload, "source"), f"{field_name}.source"),
        location=_required_location(_required(payload, "location"), f"{field_name}.location"),
        reads=_string_tuple(_required(payload, "reads"), f"{field_name}.reads"),
        writes=_string_tuple(_required(payload, "writes"), f"{field_name}.writes"),
        call_ids=_string_tuple(_required(payload, "calls"), f"{field_name}.calls"),
        conditional=_boolean(_required(payload, "conditional"), f"{field_name}.conditional"),
    )


def _cell_from_value(value: object, field_name: str) -> CellFacts:
    payload = _mapping(value, field_name)
    return CellFacts(
        id=_string(_required(payload, "id"), f"{field_name}.id"),
        index=_integer(_required(payload, "index"), f"{field_name}.index"),
        kind=CellKind(_string(_required(payload, "kind"), f"{field_name}.kind")),
        execution_count=_optional_integer(
            payload.get("execution_count"), f"{field_name}.execution_count"
        ),
        source=_string(_required(payload, "source"), f"{field_name}.source"),
        statements=tuple(
            _statement_from_value(item, f"{field_name}.statements item")
            for item in _sequence(_required(payload, "statements"), f"{field_name}.statements")
        ),
        reads=_string_tuple(_required(payload, "reads"), f"{field_name}.reads"),
        writes=_string_tuple(_required(payload, "writes"), f"{field_name}.writes"),
        imports=tuple(
            _import_from_value(item, f"{field_name}.imports item")
            for item in _sequence(_required(payload, "imports"), f"{field_name}.imports")
        ),
        calls=tuple(
            _call_from_value(item, f"{field_name}.calls item")
            for item in _sequence(_required(payload, "calls"), f"{field_name}.calls")
        ),
        diagnostic_codes=_string_tuple(
            _required(payload, "diagnostic_codes"), f"{field_name}.diagnostic_codes"
        ),
    )


def _symbol_from_value(value: object, field_name: str) -> SymbolFacts:
    payload = _mapping(value, field_name)
    return SymbolFacts(
        name=_string(_required(payload, "name"), f"{field_name}.name"),
        kind=SymbolKind(_string(_required(payload, "kind"), f"{field_name}.kind")),
        definitions=tuple(
            _access_from_value(item, f"{field_name}.definitions item")
            for item in _sequence(_required(payload, "definitions"), f"{field_name}.definitions")
        ),
        reads=tuple(
            _access_from_value(item, f"{field_name}.reads item")
            for item in _sequence(_required(payload, "reads"), f"{field_name}.reads")
        ),
    )


def _dependency_from_value(value: object, field_name: str) -> DependencyFacts:
    payload = _mapping(value, field_name)
    return DependencyFacts(
        id=_string(_required(payload, "id"), f"{field_name}.id"),
        symbol=_string(_required(payload, "symbol"), f"{field_name}.symbol"),
        producer=_access_from_value(_required(payload, "producer"), f"{field_name}.producer"),
        consumer=_access_from_value(_required(payload, "consumer"), f"{field_name}.consumer"),
        resolution=_string(_required(payload, "resolution"), f"{field_name}.resolution"),
    )


def _diagnostic_from_value(value: object, field_name: str) -> Diagnostic:
    payload = _mapping(value, field_name)
    details = _mapping(_required(payload, "details"), f"{field_name}.details")
    return Diagnostic(
        id=_string(_required(payload, "id"), f"{field_name}.id"),
        code=_string(_required(payload, "code"), f"{field_name}.code"),
        severity=Severity(_string(_required(payload, "severity"), f"{field_name}.severity")),
        message=_string(_required(payload, "message"), f"{field_name}.message"),
        blocking=_boolean(_required(payload, "blocking"), f"{field_name}.blocking"),
        location=_location_from_value(payload.get("location"), f"{field_name}.location"),
        related_symbol=_optional_string(
            payload.get("related_symbol"), f"{field_name}.related_symbol"
        ),
        details=tuple(
            DiagnosticDetail(key, _primitive(detail, f"{field_name}.detail"))
            for key, detail in sorted(details.items())
        ),
    )


def _metadata_from_value(value: object) -> NotebookMetadata:
    payload = _mapping(value, "notebook")
    return NotebookMetadata(
        path=_string(_required(payload, "path"), "notebook.path"),
        nbformat=_integer(_required(payload, "nbformat"), "notebook.nbformat"),
        nbformat_minor=_integer(_required(payload, "nbformat_minor"), "notebook.nbformat_minor"),
        language=_string(_required(payload, "language"), "notebook.language"),
        kernel_name=_optional_string(payload.get("kernel_name"), "notebook.kernel_name"),
        cell_count=_integer(_required(payload, "cell_count"), "notebook.cell_count"),
        content_sha256=_string(_required(payload, "content_sha256"), "notebook.content_sha256"),
    )


def notebook_facts_from_dict(payload: Mapping[str, object]) -> NotebookFacts:
    """Validate and reconstruct notebook facts from a decoded JSON object."""
    return NotebookFacts(
        schema_version=_string(_required(payload, "schema_version"), "schema_version"),
        analyzer_version=_string(_required(payload, "analyzer_version"), "analyzer_version"),
        notebook=_metadata_from_value(_required(payload, "notebook")),
        cells=tuple(
            _cell_from_value(item, "cells item")
            for item in _sequence(_required(payload, "cells"), "cells")
        ),
        symbols=tuple(
            _symbol_from_value(item, "symbols item")
            for item in _sequence(_required(payload, "symbols"), "symbols")
        ),
        dependencies=tuple(
            _dependency_from_value(item, "dependencies item")
            for item in _sequence(_required(payload, "dependencies"), "dependencies")
        ),
        diagnostics=tuple(
            _diagnostic_from_value(item, "diagnostics item")
            for item in _sequence(_required(payload, "diagnostics"), "diagnostics")
        ),
    )


def notebook_facts_from_json(payload: str) -> NotebookFacts:
    """Decode JSON and reconstruct validated notebook facts."""
    decoded: object = json.loads(payload)
    return notebook_facts_from_dict(_mapping(decoded, "root"))
