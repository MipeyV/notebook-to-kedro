"""Deterministic comparison of reviewed behavioral evidence and execution results."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

from notebook_to_kedro.evaluation.behavioral import (
    ArrayBehaviorValue,
    BehavioralCase,
    BehaviorValue,
    ComparatorKind,
    ComparisonSpec,
    ExpectedBehaviorOutput,
    ListBehaviorValue,
    ObjectBehaviorValue,
    ScalarBehaviorValue,
    TableBehaviorValue,
)

if TYPE_CHECKING:
    from notebook_to_kedro.evaluation.behavioral_execution import (
        BehavioralExecutionResult,
        BehavioralExecutionStatus,
    )

BEHAVIORAL_COMPARISON_SCHEMA_VERSION = "1.0"
BehavioralComparisonStatus: TypeAlias = Literal["matched", "mismatch", "execution_error"]


@dataclass(frozen=True, slots=True)
class BehavioralOutputComparison:
    """Comparison outcome for one named successful output."""

    output_name: str
    comparator_kind: ComparatorKind
    matched: bool
    diagnostic_message: str | None = None

    def __post_init__(self) -> None:
        if not self.output_name.strip():
            raise ValueError("comparison output name must not be empty")
        if self.comparator_kind not in ("exact", "numeric", "array", "table"):
            raise ValueError(f"unsupported comparator kind: {self.comparator_kind!r}")
        if self.matched and self.diagnostic_message is not None:
            raise ValueError("matched output comparison cannot contain a diagnostic")
        if not self.matched and not self.diagnostic_message:
            raise ValueError("mismatched output comparison requires a diagnostic")


@dataclass(frozen=True, slots=True)
class BehavioralCaseComparison:
    """Versioned behavioral comparison report for one reviewed scenario."""

    schema_version: str
    case_id: str
    node_code_case_id: str
    execution_status: BehavioralExecutionStatus
    status: BehavioralComparisonStatus
    output_comparisons: tuple[BehavioralOutputComparison, ...] = ()
    exception_matched: bool | None = None
    diagnostic_message: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != BEHAVIORAL_COMPARISON_SCHEMA_VERSION:
            raise ValueError(f"unsupported comparison schema version: {self.schema_version!r}")
        if not self.case_id.strip() or not self.node_code_case_id.strip():
            raise ValueError("comparison case IDs must not be empty")
        if self.execution_status not in (
            "success",
            "exception",
            "setup_failure",
            "timeout",
            "process_failure",
            "serialization_failure",
        ):
            raise ValueError(f"unsupported execution status: {self.execution_status!r}")
        if self.status not in ("matched", "mismatch", "execution_error"):
            raise ValueError(f"unsupported comparison status: {self.status!r}")
        if any(
            not isinstance(item, BehavioralOutputComparison) for item in self.output_comparisons
        ):
            raise ValueError("output comparisons must use BehavioralOutputComparison values")
        if self.output_comparisons and self.exception_matched is not None:
            raise ValueError("a comparison cannot contain output and exception outcomes")
        if self.status == "matched" and (
            self.diagnostic_message is not None
            or any(not item.matched for item in self.output_comparisons)
            or self.exception_matched is False
        ):
            raise ValueError("matched comparison contains a mismatch diagnostic")
        if self.status != "matched" and not self.diagnostic_message:
            raise ValueError("non-matching comparison requires a diagnostic")


@dataclass(frozen=True, slots=True)
class BehavioralCorpusComparison:
    """Aggregate deterministic results for a complete behavioral corpus."""

    schema_version: str
    cases: tuple[BehavioralCaseComparison, ...]

    def __post_init__(self) -> None:
        if self.schema_version != BEHAVIORAL_COMPARISON_SCHEMA_VERSION:
            raise ValueError(f"unsupported comparison schema version: {self.schema_version!r}")
        if not self.cases:
            raise ValueError("behavioral comparison corpus requires at least one case")
        if any(not isinstance(item, BehavioralCaseComparison) for item in self.cases):
            raise ValueError("corpus cases must use BehavioralCaseComparison values")
        case_ids = tuple(item.case_id for item in self.cases)
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("behavioral comparison case IDs must be unique")

    @property
    def case_count(self) -> int:
        """Return the number of compared scenarios."""
        return len(self.cases)

    @property
    def matched_count(self) -> int:
        """Return the number of scenarios matching their expectations."""
        return sum(case.status == "matched" for case in self.cases)

    @property
    def mismatch_count(self) -> int:
        """Return the number of completed executions with behavioral differences."""
        return sum(case.status == "mismatch" for case in self.cases)

    @property
    def execution_error_count(self) -> int:
        """Return the number of scenarios that could not be executed reliably."""
        return sum(case.status == "execution_error" for case in self.cases)

    @property
    def match_rate(self) -> float:
        """Return the proportion of matching scenarios in the corpus."""
        return self.matched_count / self.case_count

    @property
    def exact_match(self) -> bool:
        """Return whether every scenario matches its reviewed expectation."""
        return self.matched_count == self.case_count


def compare_behavioral_result(
    case: BehavioralCase, result: BehavioralExecutionResult
) -> BehavioralCaseComparison:
    """Compare one isolated execution result with its reviewed expectation."""
    if (case.case_id, case.node_code_case_id) != (result.case_id, result.node_code_case_id):
        raise ValueError("execution result identity does not match behavioral case")
    if result.status not in ("success", "exception"):
        return _case_comparison(
            case,
            result,
            "execution_error",
            diagnostic=result.diagnostic_message or f"execution failed with status {result.status}",
        )
    if case.expected_exception is not None:
        return _compare_expected_exception(case, result)
    if result.status == "exception":
        exception = result.exception
        if exception is None:
            raise ValueError("exception execution result does not contain an exception")
        return _case_comparison(
            case,
            result,
            "mismatch",
            diagnostic=f"unexpected exception: {exception.type_name}: {exception.message}",
        )

    expected_names = tuple(item.output_name for item in case.expected_outputs)
    actual_names = tuple(item.output_name for item in result.outputs)
    if actual_names != expected_names:
        return _case_comparison(
            case,
            result,
            "mismatch",
            diagnostic=(
                "execution output names/order differ: "
                f"expected {expected_names!r}, actual {actual_names!r}"
            ),
        )

    comparisons = tuple(
        _compare_output(expected, actual.value)
        for expected, actual in zip(case.expected_outputs, result.outputs, strict=True)
    )
    mismatches = tuple(item for item in comparisons if not item.matched)
    if mismatches:
        return _case_comparison(
            case,
            result,
            "mismatch",
            outputs=comparisons,
            diagnostic=f"{len(mismatches)} of {len(comparisons)} outputs differ",
        )
    return _case_comparison(case, result, "matched", outputs=comparisons)


def compare_behavioral_corpus(
    cases: tuple[BehavioralCase, ...], results: tuple[BehavioralExecutionResult, ...]
) -> BehavioralCorpusComparison:
    """Pair results by case ID and compare them in reviewed corpus order."""
    if not cases:
        raise ValueError("behavioral comparison corpus requires at least one case")
    case_ids = tuple(case.case_id for case in cases)
    result_ids = tuple(result.case_id for result in results)
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("behavioral case IDs must be unique")
    if len(set(result_ids)) != len(result_ids):
        raise ValueError("behavioral execution result IDs must be unique")
    if set(case_ids) != set(result_ids):
        raise ValueError("behavioral cases and execution results must contain the same case IDs")
    results_by_id = {result.case_id: result for result in results}
    return BehavioralCorpusComparison(
        schema_version=BEHAVIORAL_COMPARISON_SCHEMA_VERSION,
        cases=tuple(compare_behavioral_result(case, results_by_id[case.case_id]) for case in cases),
    )


def behavioral_case_comparison_to_dict(report: BehavioralCaseComparison) -> dict[str, object]:
    """Return one comparison report as a canonical JSON-compatible dictionary."""
    return {
        "schema_version": report.schema_version,
        "case_id": report.case_id,
        "node_code_case_id": report.node_code_case_id,
        "execution_status": report.execution_status,
        "status": report.status,
        "output_comparisons": [
            {
                "output_name": item.output_name,
                "comparator_kind": item.comparator_kind,
                "matched": item.matched,
                "diagnostic_message": item.diagnostic_message,
            }
            for item in report.output_comparisons
        ],
        "exception_matched": report.exception_matched,
        "diagnostic_message": report.diagnostic_message,
    }


def behavioral_case_comparison_to_json(
    report: BehavioralCaseComparison, *, indent: int | None = 2
) -> str:
    """Serialize one behavioral comparison report deterministically."""
    return (
        json.dumps(
            behavioral_case_comparison_to_dict(report),
            indent=indent,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def behavioral_corpus_comparison_to_dict(
    report: BehavioralCorpusComparison,
) -> dict[str, object]:
    """Return an aggregate behavioral report as a canonical dictionary."""
    return {
        "schema_version": report.schema_version,
        "case_count": report.case_count,
        "matched_count": report.matched_count,
        "mismatch_count": report.mismatch_count,
        "execution_error_count": report.execution_error_count,
        "match_rate": report.match_rate,
        "exact_match": report.exact_match,
        "cases": [behavioral_case_comparison_to_dict(case) for case in report.cases],
    }


def behavioral_corpus_comparison_to_json(
    report: BehavioralCorpusComparison, *, indent: int | None = 2
) -> str:
    """Serialize an aggregate behavioral comparison report deterministically."""
    return (
        json.dumps(
            behavioral_corpus_comparison_to_dict(report),
            indent=indent,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def _case_comparison(  # noqa: PLR0913
    case: BehavioralCase,
    result: BehavioralExecutionResult,
    status: BehavioralComparisonStatus,
    *,
    outputs: tuple[BehavioralOutputComparison, ...] = (),
    exception_matched: bool | None = None,
    diagnostic: str | None = None,
) -> BehavioralCaseComparison:
    return BehavioralCaseComparison(
        schema_version=BEHAVIORAL_COMPARISON_SCHEMA_VERSION,
        case_id=case.case_id,
        node_code_case_id=case.node_code_case_id,
        execution_status=result.status,
        status=status,
        output_comparisons=outputs,
        exception_matched=exception_matched,
        diagnostic_message=diagnostic,
    )


def _compare_expected_exception(
    case: BehavioralCase, result: BehavioralExecutionResult
) -> BehavioralCaseComparison:
    expected = case.expected_exception
    if expected is None:
        raise ValueError("behavioral case does not expect an exception")
    if result.status != "exception":
        return _case_comparison(
            case,
            result,
            "mismatch",
            exception_matched=False,
            diagnostic="expected exception was not raised",
        )
    actual = result.exception
    if actual is None:
        raise ValueError("exception execution result does not contain an exception")
    type_matches = actual.type_name == expected.type_name
    message_matches = (
        expected.message_contains is None or expected.message_contains in actual.message
    )
    if type_matches and message_matches:
        return _case_comparison(case, result, "matched", exception_matched=True)
    if not type_matches:
        diagnostic = (
            f"exception type differs: expected {expected.type_name!r}, actual {actual.type_name!r}"
        )
    else:
        diagnostic = (
            f"exception message does not contain expected fragment {expected.message_contains!r}"
        )
    return _case_comparison(
        case,
        result,
        "mismatch",
        exception_matched=False,
        diagnostic=diagnostic,
    )


def _compare_output(
    expected: ExpectedBehaviorOutput, actual: BehaviorValue
) -> BehavioralOutputComparison:
    comparison = expected.comparison
    matched, diagnostic = _compare_value(expected.value, actual, comparison)
    return BehavioralOutputComparison(
        output_name=expected.output_name,
        comparator_kind=comparison.kind,
        matched=matched,
        diagnostic_message=diagnostic,
    )


def _compare_value(
    expected: BehaviorValue, actual: BehaviorValue, comparison: ComparisonSpec
) -> tuple[bool, str | None]:
    if comparison.kind == "exact":
        return _compare_exact(expected, actual, "value")
    if comparison.kind == "numeric":
        return _compare_numeric(expected, actual, comparison)
    if comparison.kind == "array":
        return _compare_array_value(expected, actual, comparison)
    return _compare_table_value(expected, actual, comparison)


def _compare_numeric(
    expected: BehaviorValue, actual: BehaviorValue, comparison: ComparisonSpec
) -> tuple[bool, str | None]:
    if not isinstance(expected, ScalarBehaviorValue) or not _is_numeric(expected.value):
        raise ValueError("numeric comparison requires a scalar expected value")
    if not isinstance(actual, ScalarBehaviorValue) or not _is_numeric(actual.value):
        return False, "numeric output requires a numeric scalar actual value"
    if _numeric_equal(expected.value, actual.value, comparison):
        return True, None
    return False, f"numeric value differs: expected {expected.value!r}, actual {actual.value!r}"


def _compare_array_value(
    expected: BehaviorValue, actual: BehaviorValue, comparison: ComparisonSpec
) -> tuple[bool, str | None]:
    if not isinstance(expected, ArrayBehaviorValue):
        raise ValueError("array comparison requires an array expected value")
    if not isinstance(actual, ArrayBehaviorValue):
        return False, f"array output kind differs: actual {actual.kind!r}"
    return _compare_array(expected, actual, comparison)


def _compare_table_value(
    expected: BehaviorValue, actual: BehaviorValue, comparison: ComparisonSpec
) -> tuple[bool, str | None]:
    if not isinstance(expected, TableBehaviorValue):
        raise ValueError("table comparison requires a table expected value")
    if not isinstance(actual, TableBehaviorValue):
        return False, f"table output kind differs: actual {actual.kind!r}"
    return _compare_table(expected, actual, comparison)


def _compare_exact(  # noqa: PLR0911, PLR0912
    expected: BehaviorValue, actual: BehaviorValue, path: str
) -> tuple[bool, str | None]:
    if type(expected) is not type(actual):
        return False, f"{path} kind differs: expected {expected.kind!r}, actual {actual.kind!r}"
    if isinstance(expected, ScalarBehaviorValue) and isinstance(actual, ScalarBehaviorValue):
        return _compare_primitive(expected.value, actual.value, path)
    if isinstance(expected, ListBehaviorValue) and isinstance(actual, ListBehaviorValue):
        if len(expected.items) != len(actual.items):
            return (
                False,
                f"{path} length differs: expected {len(expected.items)}, "
                f"actual {len(actual.items)}",
            )
        for index, (expected_item, actual_item) in enumerate(
            zip(expected.items, actual.items, strict=True)
        ):
            matched, diagnostic = _compare_exact(expected_item, actual_item, f"{path}[{index}]")
            if not matched:
                return matched, diagnostic
        return True, None
    if isinstance(expected, ObjectBehaviorValue) and isinstance(actual, ObjectBehaviorValue):
        expected_keys = tuple(key for key, _ in expected.entries)
        actual_keys = tuple(key for key, _ in actual.entries)
        if expected_keys != actual_keys:
            return (
                False,
                f"{path} keys/order differ: expected {expected_keys!r}, actual {actual_keys!r}",
            )
        for (key, expected_item), (_, actual_item) in zip(
            expected.entries, actual.entries, strict=True
        ):
            matched, diagnostic = _compare_exact(expected_item, actual_item, f"{path}.{key}")
            if not matched:
                return matched, diagnostic
        return True, None
    if isinstance(expected, ArrayBehaviorValue) and isinstance(actual, ArrayBehaviorValue):
        if (expected.dtype, expected.shape) != (actual.dtype, actual.shape):
            return False, f"{path} array structure differs"
        return _compare_primitive_sequence(expected.values, actual.values, path)
    if isinstance(expected, TableBehaviorValue) and isinstance(actual, TableBehaviorValue):
        if (expected.columns, expected.dtypes, expected.index) != (
            actual.columns,
            actual.dtypes,
            actual.index,
        ):
            return False, f"{path} table structure differs"
        expected_values = tuple(value for row in expected.rows for value in row)
        actual_values = tuple(value for row in actual.rows for value in row)
        return _compare_primitive_sequence(expected_values, actual_values, path)
    raise TypeError(f"unsupported behavior value: {type(expected).__name__}")


def _compare_array(
    expected: ArrayBehaviorValue,
    actual: ArrayBehaviorValue,
    comparison: ComparisonSpec,
) -> tuple[bool, str | None]:
    if expected.shape != actual.shape:
        return False, f"array shape differs: expected {expected.shape!r}, actual {actual.shape!r}"
    if comparison.check_dtype and expected.dtype != actual.dtype:
        return False, f"array dtype differs: expected {expected.dtype!r}, actual {actual.dtype!r}"
    for index, (expected_value, actual_value) in enumerate(
        zip(expected.values, actual.values, strict=True)
    ):
        if not _tolerant_primitive_equal(expected_value, actual_value, comparison):
            return (
                False,
                f"array value[{index}] differs: expected {expected_value!r}, "
                f"actual {actual_value!r}",
            )
    return True, None


def _compare_table(  # noqa: PLR0911
    expected: TableBehaviorValue,
    actual: TableBehaviorValue,
    comparison: ComparisonSpec,
) -> tuple[bool, str | None]:
    if comparison.check_order:
        if expected.columns != actual.columns:
            return (
                False,
                f"table columns/order differ: expected {expected.columns!r}, "
                f"actual {actual.columns!r}",
            )
    elif set(expected.columns) != set(actual.columns):
        return (
            False,
            f"table columns differ: expected {expected.columns!r}, actual {actual.columns!r}",
        )

    if len(expected.rows) != len(actual.rows):
        return (
            False,
            f"table row count differs: expected {len(expected.rows)}, actual {len(actual.rows)}",
        )
    if comparison.check_index:
        matched, diagnostic = _compare_primitive_sequence(
            expected.index, actual.index, "table index"
        )
        if not matched:
            return matched, diagnostic

    actual_positions = {column: index for index, column in enumerate(actual.columns)}
    expected_positions = {column: index for index, column in enumerate(expected.columns)}
    if comparison.check_dtype:
        for column in expected.columns:
            expected_dtype = expected.dtypes[expected_positions[column]]
            actual_dtype = actual.dtypes[actual_positions[column]]
            if expected_dtype != actual_dtype:
                return (
                    False,
                    f"table dtype for {column!r} differs: expected {expected_dtype!r}, "
                    f"actual {actual_dtype!r}",
                )

    for row_index, (expected_row, actual_row) in enumerate(
        zip(expected.rows, actual.rows, strict=True)
    ):
        for column in expected.columns:
            expected_value = expected_row[expected_positions[column]]
            actual_value = actual_row[actual_positions[column]]
            if not _tolerant_primitive_equal(expected_value, actual_value, comparison):
                return (
                    False,
                    f"table value[{row_index}, {column!r}] differs: "
                    f"expected {expected_value!r}, actual {actual_value!r}",
                )
    return True, None


def _compare_primitive_sequence(
    expected: tuple[object, ...], actual: tuple[object, ...], path: str
) -> tuple[bool, str | None]:
    if len(expected) != len(actual):
        return False, f"{path} length differs: expected {len(expected)}, actual {len(actual)}"
    for index, (expected_value, actual_value) in enumerate(zip(expected, actual, strict=True)):
        matched, diagnostic = _compare_primitive(expected_value, actual_value, f"{path}[{index}]")
        if not matched:
            return matched, diagnostic
    return True, None


def _compare_primitive(expected: object, actual: object, path: str) -> tuple[bool, str | None]:
    if type(expected) is type(actual) and expected == actual:
        return True, None
    return False, f"{path} differs: expected {expected!r}, actual {actual!r}"


def _tolerant_primitive_equal(expected: object, actual: object, comparison: ComparisonSpec) -> bool:
    if _is_numeric(expected) and _is_numeric(actual):
        return _numeric_equal(expected, actual, comparison)
    return type(expected) is type(actual) and expected == actual


def _numeric_equal(expected: object, actual: object, comparison: ComparisonSpec) -> bool:
    expected_number = cast("int | float", expected)
    actual_number = cast("int | float", actual)
    if isinstance(expected_number, float) and math.isnan(expected_number):
        return bool(
            comparison.equal_nan and isinstance(actual_number, float) and math.isnan(actual_number)
        )
    if isinstance(actual_number, float) and math.isnan(actual_number):
        return False
    return math.isclose(
        expected_number,
        actual_number,
        rel_tol=cast("float", comparison.relative_tolerance),
        abs_tol=cast("float", comparison.absolute_tolerance),
    )


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
