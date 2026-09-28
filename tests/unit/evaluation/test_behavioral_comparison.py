from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest

from notebook_to_kedro.evaluation import (
    BEHAVIORAL_COMPARISON_SCHEMA_VERSION,
    ArrayBehaviorValue,
    BehavioralCase,
    BehavioralCaseComparison,
    BehavioralCorpusComparison,
    BehavioralExecutionException,
    BehavioralExecutionOutput,
    BehavioralExecutionResult,
    BehavioralOutputComparison,
    ComparisonSpec,
    ExpectedBehaviorException,
    ExpectedBehaviorOutput,
    ListBehaviorValue,
    ObjectBehaviorValue,
    ScalarBehaviorValue,
    TableBehaviorValue,
    behavioral_case_comparison_to_dict,
    behavioral_case_comparison_to_json,
    behavioral_corpus_comparison_to_dict,
    behavioral_corpus_comparison_to_json,
    compare_behavioral_corpus,
    compare_behavioral_result,
)
from notebook_to_kedro.evaluation import behavioral_comparison as comparison


def _spec(kind: str, **changes: object) -> ComparisonSpec:
    values: dict[str, object] = {
        "kind": kind,
        "absolute_tolerance": None,
        "relative_tolerance": None,
        "equal_nan": None,
        "check_dtype": None,
        "check_order": None,
        "check_index": None,
    }
    if kind == "numeric":
        values.update(absolute_tolerance=0.01, relative_tolerance=0.01, equal_nan=False)
    elif kind == "array":
        values.update(
            absolute_tolerance=0.01,
            relative_tolerance=0.01,
            equal_nan=False,
            check_dtype=True,
        )
    elif kind == "table":
        values.update(
            absolute_tolerance=0.01,
            relative_tolerance=0.01,
            equal_nan=False,
            check_dtype=True,
            check_order=True,
            check_index=True,
        )
    values.update(changes)
    return ComparisonSpec(**cast("Any", values))


def _case(
    value: object = ScalarBehaviorValue(2),
    spec: ComparisonSpec | None = None,
    *,
    case_id: str = "case",
    expected_exception: ExpectedBehaviorException | None = None,
) -> BehavioralCase:
    outputs: tuple[ExpectedBehaviorOutput, ...] = ()
    if expected_exception is None:
        outputs = (
            ExpectedBehaviorOutput(
                "result",
                cast("Any", value),
                spec or _spec("exact"),
            ),
        )
    return BehavioralCase(
        schema_version="1.0",
        case_id=case_id,
        node_code_case_id=f"node-{case_id}",
        review_status="approved",
        inputs=(),
        expected_outputs=outputs,
        expected_exception=expected_exception,
    )


def _result(  # noqa: PLR0913
    value: object = ScalarBehaviorValue(2),
    *,
    case_id: str = "case",
    status: str = "success",
    exception: BehavioralExecutionException | None = None,
    output_name: str = "result",
    diagnostic: str | None = None,
) -> BehavioralExecutionResult:
    outputs: tuple[BehavioralExecutionOutput, ...] = ()
    if status == "success":
        outputs = (BehavioralExecutionOutput(output_name, cast("Any", value)),)
    return BehavioralExecutionResult(
        schema_version="1.0",
        case_id=case_id,
        node_code_case_id=f"node-{case_id}",
        status=cast("Any", status),
        outputs=outputs,
        exception=exception,
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_seconds=0.01,
        diagnostic_message=diagnostic,
    )


def test_exact_comparison_and_report_serialization() -> None:
    value = ObjectBehaviorValue(
        (
            ("name", ScalarBehaviorValue("sample")),
            (
                "values",
                ListBehaviorValue((ScalarBehaviorValue(1), ScalarBehaviorValue(value=True))),
            ),
        )
    )

    report = compare_behavioral_result(_case(value), _result(value))
    payload = behavioral_case_comparison_to_dict(report)

    assert report.status == "matched"
    assert report.output_comparisons[0].matched
    assert payload["schema_version"] == BEHAVIORAL_COMPARISON_SCHEMA_VERSION
    assert json.loads(behavioral_case_comparison_to_json(report)) == payload


@pytest.mark.parametrize(
    ("expected", "actual", "diagnostic"),
    [
        (ScalarBehaviorValue(1), ListBehaviorValue((ScalarBehaviorValue(1),)), "kind differs"),
        (ScalarBehaviorValue(value=True), ScalarBehaviorValue(1), "value differs"),
        (
            ListBehaviorValue((ScalarBehaviorValue(1),)),
            ListBehaviorValue((ScalarBehaviorValue(1), ScalarBehaviorValue(2))),
            "length differs",
        ),
        (
            ListBehaviorValue((ScalarBehaviorValue(1),)),
            ListBehaviorValue((ScalarBehaviorValue(2),)),
            "value[0] differs",
        ),
        (
            ObjectBehaviorValue((("a", ScalarBehaviorValue(1)),)),
            ObjectBehaviorValue((("b", ScalarBehaviorValue(1)),)),
            "keys/order differ",
        ),
        (
            ObjectBehaviorValue((("a", ScalarBehaviorValue(1)),)),
            ObjectBehaviorValue((("a", ScalarBehaviorValue(2)),)),
            "value.a differs",
        ),
        (
            ListBehaviorValue((ArrayBehaviorValue("int64", (1,), (1,)),)),
            ListBehaviorValue((ArrayBehaviorValue("float64", (1,), (1,)),)),
            "array structure differs",
        ),
        (
            ListBehaviorValue((ArrayBehaviorValue("int64", (1,), (1,)),)),
            ListBehaviorValue((ArrayBehaviorValue("int64", (1,), (2,)),)),
            "value[0][0] differs",
        ),
        (
            ListBehaviorValue((TableBehaviorValue(("a",), ("int64",), ((1,),), (0,)),)),
            ListBehaviorValue((TableBehaviorValue(("b",), ("int64",), ((1,),), (0,)),)),
            "table structure differs",
        ),
        (
            ListBehaviorValue((TableBehaviorValue(("a",), ("int64",), ((1,),), (0,)),)),
            ListBehaviorValue((TableBehaviorValue(("a",), ("int64",), ((2,),), (0,)),)),
            "value[0][0] differs",
        ),
    ],
)
def test_exact_comparison_reports_first_difference(
    expected: object, actual: object, diagnostic: str
) -> None:
    report = compare_behavioral_result(_case(expected), _result(actual))

    assert report.status == "mismatch"
    assert diagnostic in cast("str", report.output_comparisons[0].diagnostic_message)


def test_numeric_comparison_applies_tolerances_and_rejects_non_numeric_actual() -> None:
    case = _case(ScalarBehaviorValue(10.0), _spec("numeric"))

    assert compare_behavioral_result(case, _result(ScalarBehaviorValue(10.05))).status == "matched"
    mismatch = compare_behavioral_result(case, _result(ScalarBehaviorValue(11.0)))
    wrong_kind = compare_behavioral_result(case, _result(ScalarBehaviorValue("10")))

    assert "numeric value differs" in cast("str", mismatch.output_comparisons[0].diagnostic_message)
    assert "numeric scalar" in cast("str", wrong_kind.output_comparisons[0].diagnostic_message)


def test_numeric_nan_policy_is_explicit() -> None:
    allows_nan = _spec("numeric", equal_nan=True)
    rejects_nan = _spec("numeric", equal_nan=False)

    assert comparison._numeric_equal(float("nan"), float("nan"), allows_nan)
    assert not comparison._numeric_equal(float("nan"), 1.0, allows_nan)
    assert not comparison._numeric_equal(1.0, float("nan"), allows_nan)
    assert not comparison._numeric_equal(float("nan"), float("nan"), rejects_nan)


def test_array_comparison_checks_shape_dtype_values_and_kind() -> None:
    expected = ArrayBehaviorValue("float64", (2,), (1.0, 2.0))
    case = _case(expected, _spec("array"))

    assert (
        compare_behavioral_result(
            case, _result(ArrayBehaviorValue("float64", (2,), (1.005, 2.0)))
        ).status
        == "matched"
    )
    for actual, message in (
        (ArrayBehaviorValue("float64", (1, 2), (1.0, 2.0)), "shape differs"),
        (ArrayBehaviorValue("float32", (2,), (1.0, 2.0)), "dtype differs"),
        (ArrayBehaviorValue("float64", (2,), (1.0, 3.0)), "value[1] differs"),
        (ScalarBehaviorValue(1), "array output kind differs"),
    ):
        report = compare_behavioral_result(case, _result(actual))
        assert message in cast("str", report.output_comparisons[0].diagnostic_message)

    ignores_dtype = _case(expected, _spec("array", check_dtype=False))
    assert (
        compare_behavioral_result(
            ignores_dtype, _result(ArrayBehaviorValue("float32", (2,), (1.0, 2.0)))
        ).status
        == "matched"
    )


def test_table_comparison_can_align_columns_and_ignore_dtype_and_index() -> None:
    expected = TableBehaviorValue(("a", "b"), ("float64", "object"), ((1.0, "x"),), (10,))
    spec = _spec("table", check_dtype=False, check_order=False, check_index=False)
    actual = TableBehaviorValue(("b", "a"), ("string", "float32"), (("x", 1.005),), (99,))

    assert compare_behavioral_result(_case(expected, spec), _result(actual)).status == "matched"


@pytest.mark.parametrize(
    ("actual", "message"),
    [
        (
            TableBehaviorValue(("b", "a"), ("object", "float64"), (("x", 1.0),), (10,)),
            "columns/order differ",
        ),
        (
            TableBehaviorValue(("a", "c"), ("float64", "object"), ((1.0, "x"),), (10,)),
            "columns differ",
        ),
        (
            TableBehaviorValue(
                ("a", "b"), ("float64", "object"), ((1.0, "x"), (2.0, "y")), (10, 11)
            ),
            "row count differs",
        ),
        (
            TableBehaviorValue(("a", "b"), ("float64", "object"), ((1.0, "x"),), (11,)),
            "index[0] differs",
        ),
        (
            TableBehaviorValue(("a", "b"), ("float32", "object"), ((1.0, "x"),), (10,)),
            "dtype for 'a' differs",
        ),
        (
            TableBehaviorValue(("a", "b"), ("float64", "object"), ((1.0, "y"),), (10,)),
            "value[0, 'b'] differs",
        ),
        (ScalarBehaviorValue(1), "table output kind differs"),
    ],
)
def test_table_comparison_reports_structural_and_cell_differences(
    actual: object, message: str
) -> None:
    expected = TableBehaviorValue(("a", "b"), ("float64", "object"), ((1.0, "x"),), (10,))
    spec = _spec("table", check_order=message != "columns differ")
    report = compare_behavioral_result(_case(expected, spec), _result(actual))

    assert message in cast("str", report.output_comparisons[0].diagnostic_message)


def test_expected_exception_matches_type_and_message_fragment() -> None:
    case = _case(expected_exception=ExpectedBehaviorException("KeyError", "revenue"))

    matched = compare_behavioral_result(
        case,
        _result(status="exception", exception=BehavioralExecutionException("KeyError", "revenue")),
    )
    wrong_type = compare_behavioral_result(
        case,
        _result(
            status="exception", exception=BehavioralExecutionException("ValueError", "revenue")
        ),
    )
    wrong_message = compare_behavioral_result(
        case,
        _result(status="exception", exception=BehavioralExecutionException("KeyError", "cost")),
    )
    no_exception = compare_behavioral_result(case, _result())

    assert matched.status == "matched"
    assert matched.exception_matched
    assert "type differs" in cast("str", wrong_type.diagnostic_message)
    assert "message" in cast("str", wrong_message.diagnostic_message)
    assert no_exception.diagnostic_message == "expected exception was not raised"

    no_message_case = _case(expected_exception=ExpectedBehaviorException("KeyError"))
    assert (
        compare_behavioral_result(
            no_message_case,
            _result(
                status="exception", exception=BehavioralExecutionException("KeyError", "anything")
            ),
        ).status
        == "matched"
    )


def test_execution_failures_and_interface_differences_have_distinct_statuses() -> None:
    case = _case()
    timeout = compare_behavioral_result(
        case, _result(status="timeout", diagnostic="deadline exceeded")
    )
    unnamed_failure = compare_behavioral_result(
        case, _result(status="process_failure", diagnostic="worker failed")
    )
    wrong_name = compare_behavioral_result(case, _result(output_name="other"))
    unexpected = compare_behavioral_result(
        case,
        _result(status="exception", exception=BehavioralExecutionException("ValueError", "bad")),
    )

    assert timeout.status == "execution_error"
    assert timeout.diagnostic_message == "deadline exceeded"
    assert unnamed_failure.status == "execution_error"
    assert "names/order" in cast("str", wrong_name.diagnostic_message)
    assert "unexpected exception" in cast("str", unexpected.diagnostic_message)

    with pytest.raises(ValueError, match="identity"):
        compare_behavioral_result(case, _result(case_id="other"))


def test_corpus_aggregation_preserves_case_order_and_serializes_counts() -> None:
    cases = (_case(case_id="one"), _case(case_id="two"), _case(case_id="three"))
    results = (
        _result(case_id="three", status="timeout", diagnostic="timeout"),
        _result(ScalarBehaviorValue(3), case_id="two"),
        _result(case_id="one"),
    )

    report = compare_behavioral_corpus(cases, results)
    payload = behavioral_corpus_comparison_to_dict(report)

    assert tuple(item.case_id for item in report.cases) == ("one", "two", "three")
    assert (report.case_count, report.matched_count, report.mismatch_count) == (3, 1, 1)
    assert report.execution_error_count == 1
    assert report.match_rate == pytest.approx(1 / 3)
    assert not report.exact_match
    assert payload["matched_count"] == 1
    assert json.loads(behavioral_corpus_comparison_to_json(report)) == payload


def test_corpus_comparison_rejects_incomplete_or_duplicate_inputs() -> None:
    one = _case(case_id="one")
    result = _result(case_id="one")

    with pytest.raises(ValueError, match="at least one"):
        compare_behavioral_corpus((), ())
    with pytest.raises(ValueError, match="case IDs must be unique"):
        compare_behavioral_corpus((one, one), (result,))
    with pytest.raises(ValueError, match="result IDs must be unique"):
        compare_behavioral_corpus((one,), (result, result))
    with pytest.raises(ValueError, match="same case IDs"):
        compare_behavioral_corpus((one,), (_result(case_id="two"),))


def test_comparison_report_contracts_reject_inconsistent_states() -> None:
    output = BehavioralOutputComparison("result", "exact", matched=True)
    case = BehavioralCaseComparison(
        schema_version="1.0",
        case_id="case",
        node_code_case_id="node",
        execution_status="success",
        status="matched",
        output_comparisons=(output,),
    )
    corpus = BehavioralCorpusComparison("1.0", (case,))

    assert corpus.exact_match
    for constructor, message in (
        (lambda: BehavioralOutputComparison("", "exact", matched=True), "output name"),
        (
            lambda: BehavioralOutputComparison("result", cast("Any", "bad"), matched=True),
            "kind",
        ),
        (
            lambda: BehavioralOutputComparison(
                "result", "exact", matched=True, diagnostic_message="bad"
            ),
            "cannot contain",
        ),
        (lambda: BehavioralOutputComparison("result", "exact", matched=False), "requires"),
        (lambda: replace(case, schema_version="2.0"), "schema version"),
        (lambda: replace(case, case_id=""), "case IDs"),
        (lambda: replace(case, execution_status=cast("Any", "bad")), "execution status"),
        (lambda: replace(case, status=cast("Any", "bad")), "comparison status"),
        (lambda: replace(case, output_comparisons=(cast("Any", object()),)), "output comparisons"),
        (lambda: replace(case, exception_matched=True), "output and exception"),
        (lambda: replace(case, diagnostic_message="bad"), "matched comparison"),
        (lambda: replace(case, status="mismatch"), "requires a diagnostic"),
        (lambda: replace(corpus, schema_version="2.0"), "schema version"),
        (lambda: replace(corpus, cases=()), "at least one"),
        (lambda: replace(corpus, cases=(cast("Any", object()),)), "corpus cases"),
        (lambda: replace(corpus, cases=(case, case)), "must be unique"),
    ):
        with pytest.raises(ValueError, match=message):
            constructor()


def test_internal_contract_guards_reject_impossible_expected_values() -> None:
    exact = _spec("exact")
    with pytest.raises(TypeError, match="unsupported behavior value"):
        comparison._compare_exact(cast("Any", object()), cast("Any", object()), "value")
    with pytest.raises(ValueError, match="numeric comparison"):
        comparison._compare_value(
            ScalarBehaviorValue("x"), ScalarBehaviorValue(1), _spec("numeric")
        )
    with pytest.raises(ValueError, match="array comparison"):
        comparison._compare_value(ScalarBehaviorValue(1), ScalarBehaviorValue(1), _spec("array"))
    with pytest.raises(ValueError, match="table comparison"):
        comparison._compare_value(ScalarBehaviorValue(1), ScalarBehaviorValue(1), _spec("table"))
    with pytest.raises(ValueError, match="does not expect"):
        comparison._compare_expected_exception(_case(), _result())
    invalid_exception = _result(
        status="exception", exception=BehavioralExecutionException("ValueError", "bad")
    )
    object.__setattr__(invalid_exception, "exception", None)
    with pytest.raises(ValueError, match="does not contain"):
        compare_behavioral_result(_case(), invalid_exception)
    with pytest.raises(ValueError, match="does not contain"):
        comparison._compare_expected_exception(
            _case(expected_exception=ExpectedBehaviorException("ValueError")),
            invalid_exception,
        )
    assert not comparison._compare_primitive_sequence((1,), (), "value")[0]
    assert exact.kind == "exact"
