"""Immutable, bounded DataFrame metadata declarations without pandas imports."""

from __future__ import annotations

from dataclasses import dataclass

from notebook_to_kedro.exceptions import ProjectGenerationError

MAX_FRAME_SCHEMAS = 64
MAX_FRAME_COLUMNS = 256
MAX_COLUMN_NAME = 128
_PAIR_LENGTH = 2
ALLOWED_FRAME_DTYPES = frozenset(
    {
        "bool",
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "float16",
        "float32",
        "float64",
        "object",
        "Int8",
        "Int16",
        "Int32",
        "Int64",
        "UInt8",
        "UInt16",
        "UInt32",
        "UInt64",
        "Float32",
        "Float64",
        "boolean",
        "string",
        "str",
        "category",
        "datetime64[ns]",
        "datetime64[us]",
        "timedelta64[ns]",
        "timedelta64[us]",
    }
)


@dataclass(frozen=True, slots=True)
class DataFrameSchema:
    """Ordered column/dtype metadata; no row values, index or nullability rules."""

    columns: tuple[tuple[str, str], ...]
    allow_extra_columns: bool = False

    def __post_init__(self) -> None:
        """Validate immutable direct API values with the same structural limits as JSON."""
        if (
            not isinstance(self.allow_extra_columns, bool)
            or type(self.columns) is not tuple
            or not 0 < len(self.columns) <= MAX_FRAME_COLUMNS
        ):
            raise ProjectGenerationError(
                "DataFrame schemas require bounded columns and a boolean extra-column policy"
            )
        names: set[str] = set()
        for column in self.columns:
            if (
                type(column) is not tuple
                or len(column) != _PAIR_LENGTH
                or type(column[0]) is not str
                or not 0 < len(column[0]) <= MAX_COLUMN_NAME
                or not column[0].isprintable()
                or column[0] in names
                or type(column[1]) is not str
                or column[1] not in ALLOWED_FRAME_DTYPES
            ):
                raise ProjectGenerationError(
                    "DataFrame schemas require unique printable column names and allowed dtypes"
                )
            names.add(column[0])

    def to_dict(self) -> dict[str, object]:
        """Preserve column order explicitly even when enclosing JSON keys are sorted."""
        return {
            "columns": [{"name": name, "dtype": dtype} for name, dtype in self.columns],
            "allow_extra_columns": self.allow_extra_columns,
        }


def parse_frame_schemas(value: object) -> tuple[tuple[str, DataFrameSchema], ...]:
    """Decode strict JSON structures; dataset/type binding belongs to the parent contract."""
    if not isinstance(value, dict) or not 0 < len(value) <= MAX_FRAME_SCHEMAS:
        raise ProjectGenerationError("Schema 1.1 requires bounded nonempty dataframes")
    result: list[tuple[str, DataFrameSchema]] = []
    for dataset, item in value.items():
        if (
            not isinstance(item, dict)
            or "columns" not in item
            or set(item) - {"columns", "allow_extra_columns"}
            or not isinstance(item["columns"], list)
        ):
            raise ProjectGenerationError("DataFrame schema has missing, unknown or invalid fields")
        columns: list[tuple[str, str]] = []
        for column in item["columns"]:
            if not isinstance(column, dict) or set(column) != {"name", "dtype"}:
                raise ProjectGenerationError("Schema columns require name and dtype")
            columns.append((column["name"], column["dtype"]))
        result.append(
            (dataset, DataFrameSchema(tuple(columns), item.get("allow_extra_columns", False)))
        )
    return tuple(result)
