"""Versioned behavioral evidence contracts without runtime code execution."""

from collections.abc import Callable
from dataclasses import replace
from math import inf, nan
from pathlib import Path
from typing import cast

import pytest

from notebook_to_kedro.evaluation import (
    BEHAVIORAL_CASE_SCHEMA_VERSION,
    ArrayBehaviorValue,
    BehavioralCase,
    BehaviorInput,
    ComparisonSpec,
    ExpectedBehaviorException,
    ExpectedBehaviorOutput,
    ListBehaviorValue,
    NodeCodeCase,
    ObjectBehaviorValue,
    ScalarBehaviorValue,
    TableBehaviorValue,
    behavioral_case_from_dict,
    behavioral_case_from_json,
    behavioral_case_to_dict,
    behavioral_case_to_json,
    load_behavioral_case,
    load_behavioral_corpus,
    load_node_code_corpus,
    validate_behavioral_case,
    validate_behavioral_corpus,
)

ROOT = Path(__file__).parents[3]
CORPUS = ROOT / "tests/fixtures/evaluation/behavioral/v1"
NODE_CORPUS = ROOT / "tests/fixtures/evaluation/node_code/v1"
PayloadMutation = Callable[[dict[str, object]], dict[str, object]]


@pytest.fixture
def cases() -> tuple[BehavioralCase, ...]:
    return load_behavioral_corpus(CORPUS)


@pytest.fixture
def case(cases: tuple[BehavioralCase, ...]) -> BehavioralCase:
    return cases[0]


@pytest.fixture
def node_cases() -> tuple[NodeCodeCase, ...]:
    return load_node_code_corpus(NODE_CORPUS)


def test_corpus_round_trips_in_filename_order_and_matches_node_interfaces(
    cases: tuple[BehavioralCase, ...], node_cases: tuple[NodeCodeCase, ...]
) -> None:
    assert BEHAVIORAL_CASE_SCHEMA_VERSION == "1.0"
    assert tuple(case.case_id for case in cases) == (
        "custom-ratio-standard",
        "custom-ratio-missing-column",
        "evaluate-regression-standard",
        "fill-missing-standard",
        "split-holdout-standard",
    )
    for case in cases:
        assert behavioral_case_from_dict(behavioral_case_to_dict(case)) == case
        assert behavioral_case_from_json(behavioral_case_to_json(case)) == case
        assert behavioral_case_to_json(case, indent=None).endswith("\n")
    validate_behavioral_corpus(cases, node_cases)
    exception_case = cases[1]
    assert exception_case.expected_outputs == ()
    assert exception_case.expected_exception == ExpectedBehaviorException("KeyError", "revenue")


def test_nested_json_values_are_immutable_and_deterministic() -> None:
    value = ObjectBehaviorValue(
        (
            ("enabled", ScalarBehaviorValue(value=True)),
            (
                "labels",
                ListBehaviorValue((ScalarBehaviorValue("a"), ScalarBehaviorValue(None))),
            ),
        )
    )
    case = BehavioralCase(
        schema_version="1.0",
        case_id="nested-json",
        node_code_case_id="node",
        review_status="approved",
        inputs=(BehaviorInput("config", value),),
    )
    assert behavioral_case_from_json(behavioral_case_to_json(case)) == case


@pytest.mark.parametrize("value", [nan, inf, -inf, [], {}])
def test_scalar_rejects_non_finite_or_non_scalar_values(value: object) -> None:
    with pytest.raises(ValueError, match=r"finite|JSON scalar"):
        ScalarBehaviorValue(value)  # type: ignore[arg-type]


def test_collection_values_reject_invalid_entries() -> None:
    with pytest.raises(ValueError, match="list items"):
        ListBehaviorValue((object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="object keys must not be empty"):
        ObjectBehaviorValue((("", ScalarBehaviorValue(1)),))
    with pytest.raises(ValueError, match="object keys must be unique"):
        ObjectBehaviorValue((("a", ScalarBehaviorValue(1)), ("a", ScalarBehaviorValue(2))))
    with pytest.raises(ValueError, match="object entries"):
        ObjectBehaviorValue((("a", object()),))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"dtype": " "}, "dtype must not be empty"),
        ({"shape": ()}, "non-negative dimensions"),
        ({"shape": (-1,)}, "non-negative dimensions"),
        ({"shape": (2,)}, "flattened value count"),
        ({"values": (nan,)}, "array value must be finite"),
    ],
)
def test_array_rejects_invalid_contract(changes: dict[str, object], message: str) -> None:
    value = ArrayBehaviorValue("float64", (1,), (1.0,))
    with pytest.raises(ValueError, match=message):
        replace(value, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"columns": ()}, "columns must contain"),
        ({"columns": ("a", "a"), "dtypes": ("int64", "int64")}, "must be unique"),
        ({"dtypes": ()}, "dtypes must match"),
        ({"dtypes": ("",)}, "dtypes must match"),
        ({"rows": ((1, 2),)}, "rows must match"),
        ({"rows": ((1,),), "index": (0, 1)}, "index must be empty or match"),
        ({"rows": ((nan,),)}, "table value must be finite"),
    ],
)
def test_table_rejects_invalid_contract(changes: dict[str, object], message: str) -> None:
    value = TableBehaviorValue(("a",), ("float64",), ((1.0,),), (0,))
    with pytest.raises(ValueError, match=message):
        replace(value, **changes)  # type: ignore[arg-type]


def _exact() -> ComparisonSpec:
    return ComparisonSpec("exact")


def _numeric() -> ComparisonSpec:
    return ComparisonSpec(
        "numeric", absolute_tolerance=1e-12, relative_tolerance=1e-9, equal_nan=False
    )


def _array() -> ComparisonSpec:
    return ComparisonSpec(
        "array",
        absolute_tolerance=0.0,
        relative_tolerance=0.0,
        equal_nan=False,
        check_dtype=True,
    )


def _table() -> ComparisonSpec:
    return ComparisonSpec(
        "table",
        absolute_tolerance=0.0,
        relative_tolerance=0.0,
        equal_nan=True,
        check_dtype=True,
        check_order=True,
        check_index=True,
    )


def test_all_comparison_specs_accept_their_exact_fields() -> None:
    assert (_exact().kind, _numeric().kind, _array().kind, _table().kind) == (
        "exact",
        "numeric",
        "array",
        "table",
    )


@pytest.mark.parametrize("value", [-1.0, inf, nan])
def test_comparison_rejects_invalid_tolerances(value: float) -> None:
    with pytest.raises(ValueError, match="non-negative finite"):
        ComparisonSpec("numeric", absolute_tolerance=value, relative_tolerance=0.0, equal_nan=False)


def test_comparison_rejects_unknown_kind_or_wrong_field_set() -> None:
    with pytest.raises(ValueError, match="unsupported comparator"):
        ComparisonSpec("unknown")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="fields do not match"):
        ComparisonSpec("exact", 0.0)
    with pytest.raises(ValueError, match="fields do not match"):
        ComparisonSpec(
            "numeric",
            absolute_tolerance=0.0,
            relative_tolerance=0.0,
            equal_nan=False,
            check_dtype=True,
        )
    with pytest.raises(ValueError, match="fields do not match"):
        ComparisonSpec(
            "array",
            absolute_tolerance=0.0,
            relative_tolerance=0.0,
            equal_nan=False,
            check_dtype=True,
            check_order=True,
        )
    with pytest.raises(ValueError, match="fields do not match"):
        ComparisonSpec(
            "table",
            absolute_tolerance=0.0,
            relative_tolerance=0.0,
            equal_nan=False,
            check_dtype=True,
            check_order=True,
        )


def test_outputs_require_compatible_comparators_and_values() -> None:
    assert ExpectedBehaviorOutput("value", ScalarBehaviorValue(1), _exact()).output_name == "value"
    assert (
        ExpectedBehaviorOutput("value", ScalarBehaviorValue(1), _numeric()).output_name == "value"
    )
    with pytest.raises(ValueError, match="output name must not be empty"):
        ExpectedBehaviorOutput(" ", ScalarBehaviorValue(1), _exact())
    with pytest.raises(ValueError, match="serializable value"):
        ExpectedBehaviorOutput("value", object(), _exact())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="numeric comparison"):
        ExpectedBehaviorOutput("value", ScalarBehaviorValue(value=True), _numeric())
    with pytest.raises(ValueError, match="numeric comparison"):
        ExpectedBehaviorOutput("value", ScalarBehaviorValue("1"), _numeric())
    with pytest.raises(ValueError, match="array comparison"):
        ExpectedBehaviorOutput("value", ScalarBehaviorValue(1), _array())
    with pytest.raises(ValueError, match="table comparison"):
        ExpectedBehaviorOutput("value", ScalarBehaviorValue(1), _table())
    with pytest.raises(ValueError, match="dedicated comparator"):
        ExpectedBehaviorOutput("value", ArrayBehaviorValue("int64", (1,), (1,)), _exact())
    with pytest.raises(ValueError, match="dedicated comparator"):
        ExpectedBehaviorOutput("value", TableBehaviorValue(("a",), ("int64",), ((1,),)), _exact())


def test_inputs_and_expected_exceptions_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="argument name must not be empty"):
        BehaviorInput(" ", ScalarBehaviorValue(1))
    with pytest.raises(ValueError, match="serializable value"):
        BehaviorInput("value", object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exception type must not be empty"):
        ExpectedBehaviorException("")
    with pytest.raises(ValueError, match="message fragment must not be empty"):
        ExpectedBehaviorException("ValueError", " ")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": "2.0"}, "unsupported behavioral case"),
        ({"case_id": ""}, "behavioral case id must not be empty"),
        ({"node_code_case_id": " "}, "node code case id must not be empty"),
        ({"review_status": "pending"}, "explicitly approved"),
    ],
)
def test_behavioral_case_rejects_invalid_contract(
    case: BehavioralCase, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(case, **changes)  # type: ignore[arg-type]


def test_behavioral_case_rejects_wrong_types_duplicates_and_two_outcomes(
    case: BehavioralCase,
) -> None:
    with pytest.raises(ValueError, match="inputs must use"):
        replace(case, inputs=(object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="outputs must use"):
        replace(case, expected_outputs=(object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="expected_exception must use"):
        replace(case, expected_exception=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="input names must be unique"):
        replace(case, inputs=(case.inputs[0], case.inputs[0]))
    with pytest.raises(ValueError, match="output names must be unique"):
        replace(case, expected_outputs=(case.expected_outputs[0], case.expected_outputs[0]))
    with pytest.raises(ValueError, match="both outputs and an exception"):
        replace(case, expected_exception=ExpectedBehaviorException("ValueError"))


def test_interface_validation_rejects_wrong_links_arguments_and_outputs(
    case: BehavioralCase, node_cases: tuple[NodeCodeCase, ...]
) -> None:
    node = next(item for item in node_cases if item.case_id == case.node_code_case_id)
    validate_behavioral_case(case, node)
    with pytest.raises(ValueError, match="wrong node code case"):
        validate_behavioral_case(replace(case, node_code_case_id="other"), node)
    with pytest.raises(ValueError, match="input names and order"):
        validate_behavioral_case(replace(case, inputs=()), node)
    with pytest.raises(ValueError, match="output names and order"):
        validate_behavioral_case(replace(case, expected_outputs=()), node)
    exception = replace(
        case,
        expected_outputs=(),
        expected_exception=ExpectedBehaviorException("RuntimeError"),
    )
    validate_behavioral_case(exception, node)


def test_corpus_validation_rejects_empty_duplicates_and_unknown_links(
    case: BehavioralCase, node_cases: tuple[NodeCodeCase, ...]
) -> None:
    with pytest.raises(ValueError, match="at least one case"):
        validate_behavioral_corpus((), node_cases)
    with pytest.raises(ValueError, match="behavioral case IDs must be unique"):
        validate_behavioral_corpus((case, case), node_cases)
    with pytest.raises(ValueError, match="node code case IDs must be unique"):
        validate_behavioral_corpus((case,), (node_cases[0], node_cases[0]))
    with pytest.raises(ValueError, match="unknown node code case"):
        validate_behavioral_corpus((replace(case, node_code_case_id="missing"),), node_cases)


def _payload(case: BehavioralCase) -> dict[str, object]:
    return behavioral_case_to_dict(case)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: {**data, "extra": True}, "invalid behavioral case fields"),
        (lambda data: {**data, "review_status": "pending"}, "must be 'approved'"),
        (lambda data: {**data, "case_id": 1}, "case_id must be a string"),
        (lambda data: {**data, "inputs": "bad"}, "inputs must be an array"),
        (lambda data: {**data, "expected_outputs": "bad"}, "must be an array"),
        (lambda data: {**data, "inputs": [1]}, "behavior input must be an object"),
        (
            lambda data: {**data, "inputs": [{"argument_name": "x"}]},
            "invalid behavior input fields",
        ),
        (
            lambda data: {
                **data,
                "expected_exception": {"type_name": "ValueError", "message_contains": 1},
                "expected_outputs": [],
            },
            "message_contains must be a string or null",
        ),
    ],
)
def test_decoder_rejects_invalid_envelopes(
    case: BehavioralCase, mutate: PayloadMutation, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        behavioral_case_from_dict(mutate(_payload(case)))


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"kind": "unknown"}, "unsupported behavior value kind"),
        ({"kind": "scalar", "value": []}, "must be a JSON scalar"),
        ({"kind": "list", "items": "bad"}, "items must be an array"),
        ({"kind": "object", "entries": [1]}, "object entry must be an object"),
        (
            {"kind": "object", "entries": [{"key": "a"}]},
            "invalid object entry fields",
        ),
        (
            {"kind": "array", "dtype": "int64", "shape": [True], "values": [1]},
            "shape must contain integers",
        ),
        (
            {
                "kind": "table",
                "columns": [1],
                "dtypes": ["int64"],
                "rows": [[1]],
                "index": [],
            },
            "columns must contain strings",
        ),
    ],
)
def test_decoder_rejects_invalid_values(case: BehavioralCase, value: object, message: str) -> None:
    payload = _payload(case)
    payload["inputs"] = [{"argument_name": "sales", "value": value}]
    with pytest.raises(ValueError, match=message):
        behavioral_case_from_dict(payload)


def test_decoder_rejects_invalid_comparison_fields(case: BehavioralCase) -> None:
    payload = _payload(case)
    outputs = payload["expected_outputs"]
    assert isinstance(outputs, list)
    output = outputs[0]
    assert isinstance(output, dict)
    comparison = output["comparison"]
    assert isinstance(comparison, dict)
    comparison["absolute_tolerance"] = "bad"
    with pytest.raises(ValueError, match="must be a number or null"):
        behavioral_case_from_dict(payload)

    payload = _payload(case)
    outputs = cast("list[dict[str, object]]", payload["expected_outputs"])
    comparison = cast("dict[str, object]", outputs[0]["comparison"])
    comparison["equal_nan"] = 1
    with pytest.raises(ValueError, match="must be a boolean or null"):
        behavioral_case_from_dict(payload)

    payload = _payload(case)
    outputs = cast("list[dict[str, object]]", payload["expected_outputs"])
    comparison = cast("dict[str, object]", outputs[0]["comparison"])
    comparison["kind"] = "unknown"
    with pytest.raises(ValueError, match="unsupported comparator kind"):
        behavioral_case_from_dict(payload)


def test_decoder_accepts_exact_comparator_with_null_optional_fields(
    case: BehavioralCase,
) -> None:
    payload = _payload(case)
    outputs = cast("list[dict[str, object]]", payload["expected_outputs"])
    outputs[0]["value"] = {"kind": "scalar", "value": "reviewed"}
    outputs[0]["comparison"] = {
        "kind": "exact",
        "absolute_tolerance": None,
        "relative_tolerance": None,
        "equal_nan": None,
        "check_dtype": None,
        "check_order": None,
        "check_index": None,
    }
    restored = behavioral_case_from_dict(payload)
    assert restored.expected_outputs[0].comparison == _exact()


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        '{"a": 1, "a": 2}',
        '{"value": NaN}',
        '{"value": Infinity}',
    ],
)
def test_json_decoder_rejects_invalid_duplicate_or_non_finite_json(payload: str) -> None:
    with pytest.raises(ValueError, match="invalid behavioral case JSON"):
        behavioral_case_from_json(payload)


def test_loader_reports_missing_empty_and_duplicate_corpora(
    case: BehavioralCase, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="cannot read behavioral case"):
        load_behavioral_case(tmp_path / "missing.json")
    with pytest.raises(ValueError, match="contains no JSON cases"):
        load_behavioral_corpus(tmp_path)
    payload = behavioral_case_to_json(case)
    (tmp_path / "a.json").write_text(payload, encoding="utf-8")
    (tmp_path / "b.json").write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_behavioral_corpus(tmp_path)


def test_serializer_rejects_non_finite_values_even_after_unsafe_mutation(
    case: BehavioralCase,
) -> None:
    value = object.__new__(ScalarBehaviorValue)
    object.__setattr__(value, "value", nan)
    object.__setattr__(value, "kind", "scalar")
    unsafe = replace(case, inputs=(BehaviorInput(case.inputs[0].argument_name, value),))
    with pytest.raises(ValueError, match="Out of range float values"):
        behavioral_case_to_json(unsafe)
