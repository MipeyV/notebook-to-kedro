"""Standalone test source; generated suites have no converter dependency."""

TEST_MODULE = '''"""Explicit supplied oracles. Running pytest executes project code."""

import builtins
import copy
import functools
import hashlib
import importlib
import json
import math
import numbers
import re
import stat
from pathlib import Path

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "tests/regression_cases.json").read_text(encoding="utf-8"))
CASES = DATA["contract"]["scenarios"]


def _fixtures():
    captures, total = {}, 0
    for name, definition in DATA["contract"]["fixtures"].items():
        digest = definition["sha256"]
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None or definition["path"] != (
            "regression_fixtures/" + digest + ".csv"
        ):
            raise ValueError("Invalid generated CSV fixture path")
        path = ROOT / "tests" / definition["path"]
        for directory in (ROOT / "tests", path.parent):
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Fixture directories must be regular")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Fixtures must be regular files")
        with path.open("rb") as stream:
            content = stream.read(min(1024 * 1024, 8 * 1024 * 1024 - total) + 1)
        total += len(content)
        if len(content) > 1024 * 1024 or total > 8 * 1024 * 1024:
            raise ValueError("CSV fixture byte budget exceeded")
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("CSV fixture SHA-256 mismatch")
        captures[name] = content
    return captures


FIXTURES = _fixtures()


def _json(actual, expected):
    options = dict(sort_keys=True, allow_nan=False, separators=(",", ":"))
    assert json.dumps(actual, **options) == json.dumps(expected, **options)


def _materialize(value):
    kind = value["kind"]
    if kind == "json":
        return copy.deepcopy(value["value"])
    if kind == "csv":
        import io
        import pandas as pd
        return pd.read_csv(io.BytesIO(FIXTURES[value["fixture"]]))
    if kind == "array":
        import numpy as np
        return np.array(value["data"], dtype=value["dtype"])
    import pandas as pd
    if kind == "series":
        result = pd.Series(value["data"], index=value["index"], name=value["name"],
                           dtype=value["dtype"])
    else:
        result = pd.DataFrame(value["data"], index=value["index"], columns=value["columns"])
        result = result.astype(dict(zip(value["columns"], value["dtypes"], strict=True)))
        result.columns.name = value["column_name"]
    result.index.name = value["index_name"]
    return result


def _observe(actual, expected):
    kind = expected["kind"]
    if kind == "json":
        _json(actual, expected["value"])
    elif kind == "number":
        assert isinstance(actual, numbers.Real) and not isinstance(actual, bool)
        assert math.isfinite(actual)
        assert math.isclose(actual, expected["value"], abs_tol=expected["abs_tol"],
                            rel_tol=expected["rel_tol"])
    elif kind == "array":
        import numpy as np
        assert isinstance(actual, np.ndarray)
        assert str(actual.dtype) == expected["dtype"]
        _json(actual.tolist(), expected["data"])
    else:
        import pandas as pd
        if kind == "series":
            assert isinstance(actual, pd.Series)
            _json(actual.name, expected["name"])
            assert str(actual.dtype) == expected["dtype"]
            _json(actual.tolist(), expected["data"])
        else:
            assert isinstance(actual, pd.DataFrame)
            _json(actual.columns.tolist(), expected["columns"])
            _json(actual.columns.name, expected["column_name"])
            _json([str(dtype) for dtype in actual.dtypes], expected["dtypes"])
            columns = [actual.iloc[:, i].tolist() for i in range(len(actual.columns))]
            rows = [list(row) for row in zip(*columns, strict=True)] if columns else (
                [[] for _ in actual.index]
            )
            _json(rows, expected["data"])
        _json(actual.index.tolist(), expected["index"])
        _json(actual.index.name, expected["index_name"])


def _exception(error, expected):
    assert type(error) is getattr(builtins, expected["type"])
    assert str(error) == expected["message"]


def _catalog(case, tmp_path, monkeypatch):
    config = OmegaConfigLoader(conf_source=str(ROOT / "conf/base"))["catalog"] if DATA[
        "catalog"
    ] else {}
    if config != DATA["catalog"]:
        raise ValueError("Regression catalog must match the generated CSV declarations")
    prepared = {}
    for ordinal, (name, settings) in enumerate(config.items()):
        if set(settings) != {"type", "filepath"} or settings["type"] != (
            "kedro_datasets.pandas.CSVDataset"
        ):
            raise ValueError("Regression catalog requires plain CSV datasets")
        path = tmp_path / (str(ordinal) + ".csv")
        path.write_bytes(FIXTURES[case["inputs"][name]])
        prepared[name] = {"type": settings["type"], "filepath": str(path)}
    monkeypatch.chdir(tmp_path)
    catalog = DataCatalog.from_config(prepared)
    for name in DATA["produced"]:
        catalog[name] = MemoryDataset()
    for name, value in case["parameters"].items():
        catalog["params:" + name] = MemoryDataset(copy.deepcopy(value))
    return catalog


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_pipeline(case, tmp_path, monkeypatch):
    catalog = _catalog(case, tmp_path, monkeypatch)
    registry = importlib.import_module(DATA["package_name"] + ".pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    if "expected" in case:
        SequentialRunner().run(pipeline, catalog)
        for name, expected in case["expected"].items():
            _observe(catalog.load(name), expected)
        return
    expected = case["raises"]
    target = next(node for node in pipeline.nodes if node.name == DATA["nodes"][
        expected["node"]
    ]["name"])
    original, observed = target.func, []

    @functools.wraps(original)
    def tracked(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except Exception as error:
            observed.append(error)
            raise

    monkeypatch.setattr(target, "func", tracked)
    with pytest.raises(Exception) as caught:
        SequentialRunner().run(pipeline, catalog)
    assert observed and caught.value is observed[-1]
    _exception(caught.value, expected)
    assert all(not catalog.exists(name) for name in DATA["final_outputs"])


NODE_CASES = [pytest.param(name, case, id=scenario["id"] + "--" + name)
              for scenario in CASES for name, case in scenario.get("nodes", {}).items()]

if NODE_CASES:
    @pytest.mark.parametrize(("name", "case"), NODE_CASES)
    def test_node(name, case):
        nodes = importlib.import_module(DATA["nodes_module"])
        binding = DATA["nodes"][name]
        function = getattr(nodes, binding["name"])
        inputs = {key: _materialize(value) for key, value in case["inputs"].items()}
        if "raises" in case:
            with pytest.raises(Exception) as caught:
                function(**inputs)
            _exception(caught.value, case["raises"])
            return
        result = function(**inputs)
        results = (result,) if len(binding["outputs"]) == 1 else result
        assert isinstance(results, tuple) and len(results) == len(binding["outputs"])
        for output, actual in zip(binding["outputs"], results, strict=True):
            _observe(actual, case["expected"][output])
'''
