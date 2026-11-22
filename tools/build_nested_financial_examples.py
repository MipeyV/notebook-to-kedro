"""Author fixed nested-estimator cases using the unchanged synthetic financial datasets."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from notebook_to_kedro.generation.writer import write_project

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples/banking_insurance"
SOURCES = {"credit_pipeline": "credit_default", "lapse_calibrated_vote": "insurance_lapse"}


def _json(value: object) -> str:
    return json.dumps(value, indent=2, allow_nan=False) + "\n"


def _credit_type_declarations(source: str) -> str:
    """Render explicit example types without inference or runtime certification."""
    datasets = {
        "raw": "pandas.DataFrame",
        "df": "pandas.DataFrame",
        "horizon_months": "int",
        "train_end_month": "int",
        "portfolio_rows": "int",
        **dict.fromkeys(
            ("train", "validation", "test", "X_train", "X_validation", "X_test", "scored_test"),
            "pandas.DataFrame",
        ),
        **dict.fromkeys(("y_train", "y_validation", "y_test"), "pandas.Series"),
        "preprocessor": "sklearn.base.BaseEstimator",
        "model": "sklearn.pipeline.Pipeline",
        "fitted_model": "sklearn.pipeline.Pipeline",
        "threshold": "float",
        **dict.fromkeys(
            (
                "validation_scores",
                "candidate_thresholds",
                "validation_alerts",
                "validation_misses",
                "validation_false_alerts",
                "validation_costs",
                "test_scores",
                "test_predictions",
                "matrix",
            ),
            "numpy.ndarray",
        ),
    }
    return (
        json.dumps(
            {
                "schema_version": "1.0",
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "datasets": datasets,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def _source(cell: dict[str, Any]) -> str:
    return "".join(cell["source"])


def _imports(*, calibrated: bool, stacking: bool) -> str:
    calibration = (
        "from sklearn.calibration import CalibratedClassifierCV\n"
        if calibrated and not stacking
        else ""
    )
    ensemble = (
        "from sklearn.ensemble import RandomForestClassifier, StackingClassifier\n"
        if stacking
        else "from sklearn.ensemble import RandomForestClassifier, VotingClassifier\n"
        if calibrated
        else ""
    )
    temporal = "from sklearn.model_selection import TimeSeriesSplit\n" if calibrated else ""
    return (
        "import numpy as np\nimport pandas as pd\n"
        + calibration
        + "from sklearn.compose import ColumnTransformer\n"
        + ensemble
        + "from sklearn.impute import SimpleImputer\n"
        + "from sklearn.linear_model import LogisticRegression\n"
        + "from sklearn.metrics import (\n    average_precision_score,\n    brier_score_loss,\n"
        + "    confusion_matrix,\n    precision_score,\n    recall_score,\n    roc_auc_score,\n)\n"
        + temporal
        + "from sklearn.pipeline import Pipeline\n"
        + "from sklearn.preprocessing import OneHotEncoder, StandardScaler\n\n"
    )


_PREPROCESSOR = """preprocessor = ColumnTransformer(
    [
        (
            "numeric",
            Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scale", StandardScaler()),
                ]
            ),
            numeric_columns,
        ),
        (
            "categorical",
            Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="most_frequent")),
                    ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                ]
            ),
            categorical_columns,
        ),
    ],
    remainder="drop",
    sparse_threshold=0.0,
)"""

_CREDIT_MODEL = """model = Pipeline(
    [
        ("preprocessing", preprocessor),
        ("classifier", LogisticRegression(C=1.0, max_iter=300, random_state=42)),
    ]
)
model.fit(X_train, y_train)"""

_CALIBRATED_MODEL = """model = CalibratedClassifierCV(
    estimator=Pipeline(
        [
            ("preprocessing", preprocessor),
            (
                "classifier",
                VotingClassifier(
                    estimators=[
                        ("linear", LogisticRegression(C=1.0, max_iter=300, random_state=42)),
                        (
                            "forest",
                            RandomForestClassifier(
                                n_estimators=15,
                                random_state=42,
                                max_depth=4,
                                min_samples_leaf=8,
                                n_jobs=1,
                            ),
                        ),
                    ],
                    voting="soft",
                    weights=[1, 1],
                    n_jobs=1,
                ),
            ),
        ]
    ),
    method="sigmoid",
    cv=time_cv,
    ensemble=True,
    n_jobs=1,
)
model.fit(X_train, y_train)"""

_STACKING_MODEL = """model = StackingClassifier(
    estimators=[
        (
            "linear",
            Pipeline(
                [
                    ("preprocessing", preprocessor),
                    ("classifier", LogisticRegression(max_iter=300, random_state=42)),
                ]
            ),
        ),
        (
            "forest",
            Pipeline(
                [
                    ("preprocessing", preprocessor),
                    (
                        "classifier",
                        RandomForestClassifier(n_estimators=15, random_state=42, n_jobs=1),
                    ),
                ]
            ),
        ),
    ],
    final_estimator=LogisticRegression(max_iter=300, random_state=42),
    cv=time_cv,
    n_jobs=1,
)
model.fit(X_train, y_train)"""


def _notebook(case: str, base: Path, *, boundary: str = "") -> str:
    original = json.loads((base / "workflow.ipynb").read_text(encoding="utf-8"))
    old = [_source(cell) for cell in original["cells"] if cell["cell_type"] == "code"]
    calibrated = case == "lapse_calibrated_vote"
    first = (
        _imports(calibrated=calibrated, stacking=boundary == "stacking")
        + old[0][old[0].index("raw = ") :]
    )
    preprocessor = _PREPROCESSOR
    if calibrated:
        preprocessor += (
            "\ntime_cv = TimeSeriesSplit(n_splits=3, "
            "test_size=len(X_train) // 6, gap=len(X_train) // 3)"
        )
    model = (
        _STACKING_MODEL
        if boundary == "stacking"
        else _CALIBRATED_MODEL
        if calibrated
        else _CREDIT_MODEL
    )
    code = [first, old[1], old[2], preprocessor, model, *old[6:]]
    code[5] = code[5].replace("X_validation_encoded", "X_validation")
    code[6] = code[6].replace("X_test_encoded", "X_test")
    owner = (
        'model.calibrated_classifiers_[0].estimator.named_steps["preprocessing"]'
        if calibrated
        else 'model.named_steps["preprocessing"]'
    )
    if boundary == "alias":
        owner = "preprocessor"
    expression = owner + ".get_feature_names_out().tolist()"
    if calibrated and boundary == "stacking":
        expression = (
            '(\n    model.named_estimators_["linear"].named_steps["preprocessing"]'
            ".get_feature_names_out().tolist()\n)"
        )
    elif calibrated:
        expression = (
            "(\n    model.calibrated_classifiers_[0]\n"
            '    .estimator.named_steps["preprocessing"]\n'
            "    .get_feature_names_out()\n    .tolist()\n)"
        )
    code[-1] = code[-1].replace(
        "X_train_encoded.columns.tolist()",
        expression,
    )
    code[-1] += "\nfitted_model = model"
    for index, source in enumerate(code):
        compile(source, f"{case}/cell-{index}", "exec", dont_inherit=True)
    original["cells"] = [
        {
            "cell_type": "markdown",
            "id": "intro",
            "metadata": {},
            "source": [
                f"# Nested financial model: {case}\n",
                "Same seed-42 data and outer temporal cohorts as the baseline.\n",
                "Nested sklearn components remain estimator objects; "
                "conversion must preserve their behavior.",
            ],
        }
    ] + [
        {
            "cell_type": "code",
            "id": f"stage-{index:02d}",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": source.splitlines(keepends=True),
        }
        for index, source in enumerate(code)
    ]
    return json.dumps(original, indent=1, sort_keys=True) + "\n"


def build_files() -> dict[Path, str]:
    """Build source assets and explicit oracles without fitting an estimator."""
    files: dict[Path, str] = {}
    for case, source_case in SOURCES.items():
        root = Path(case)
        base = BASE / source_case
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        portfolio = (base / "data/portfolio.csv").read_bytes()
        if hashlib.sha256(portfolio).hexdigest() != manifest["portfolio_sha256"]:
            raise ValueError("Base portfolio identity differs from its manifest")
        for name in ("portfolio", "empty", "duplicate", "immature", "invalid_target"):
            files[root / f"data/{name}.csv"] = (
                (base / f"data/{name}.csv").read_bytes().decode("utf-8")
            )
        files[root / "dictionary.json"] = (base / "dictionary.json").read_text(encoding="utf-8")
        files[root / "workflow.ipynb"] = _notebook(case, base)
        if case == "credit_pipeline":
            files[root / "boundary_fitted_alias.ipynb"] = _notebook(case, base, boundary="alias")
        else:
            files[root / "boundary_stacking_timeseries.ipynb"] = _notebook(
                case, base, boundary="stacking"
            )
        features = [
            ("numeric__" if name in manifest["feature_columns"][:9] else "categorical__") + name
            for name in manifest["expected_encoded_features"]
        ]
        parameters = (
            {}
            if case == "credit_pipeline"
            else {
                "train_model.n_estimators": 15,
                "train_model.random_state": 42,
            }
        )
        regression = copy.deepcopy(
            json.loads((base / "regression.json").read_text(encoding="utf-8"))
        )
        for scenario in regression["scenarios"]:
            scenario["parameters"] = parameters
        baseline = regression["scenarios"][0]
        baseline["expected"]["feature_names"]["value"] = features
        baseline["nodes"]["task-0008"] = baseline["nodes"].pop("task-0009")
        files[root / "regression.json"] = _json(regression)
        manifest.update(
            base_case=source_case,
            model_kind=case,
            expected_encoded_features=features,
            calibrated_folds=3 if case == "lapse_calibrated_vote" else 0,
        )
        files[root / "manifest.json"] = _json(manifest)
        configuration = {
            "schema_version": "1.0",
            "project_root": ".",
            "source": "workflow.ipynb",
            "source_kind": "notebook",
            "package_name": case,
            "regression_contract": "regression.json",
        }
        files[root / "project.json"] = _json(configuration)
        files[root / "project-model.json"] = _json(
            {**configuration, "model_output": "fitted_model"}
        )
        if case == "credit_pipeline":
            files[root / "node-types.contract.json"] = _credit_type_declarations(
                files[root / "workflow.ipynb"]
            )
            files[root / "project-typed.json"] = (
                json.dumps(
                    {
                        **configuration,
                        "model_output": "fitted_model",
                        "node_types": "node-types.contract.json",
                    },
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            )
    return files


def main() -> None:
    """Publish fixed nested-estimator examples to a new destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    files = write_project(arguments.output, build_files())
    print(f"Wrote {len(files)} nested-case files to {arguments.output}")  # noqa: T201


if __name__ == "__main__":
    main()
