"""Build fixed synthetic banking/insurance cases without executing notebooks or models."""

from __future__ import annotations

# The thresholds below are fixed synthetic corpus design values, not inferred business rules.
# ruff: noqa: PLR2004
import argparse
import csv
import hashlib
import io
import json
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebook_to_kedro.generation.writer import write_project

if TYPE_CHECKING:
    from collections.abc import Callable

Row = dict[str, int | str]
CASES: dict[str, dict[str, Any]] = {
    "credit_default": {
        "title": "Banking: synthetic 12-month credit default",
        "rows_per_month": 50,
        "id": "loan_id",
        "target": "default_12m",
        "miss_cost": 12,
        "numeric": [
            "monthly_income",
            "existing_debt_payment",
            "loan_amount",
            "term_months",
            "interest_rate_bp",
            "utilization_pct",
            "late_payments_12m",
            "employment_months",
            "internal_score",
        ],
        "categorical": ["employment_type", "loan_purpose", "origination_channel"],
        "categories": {
            "employment_type": ["salaried", "self_employed", "other"],
            "loan_purpose": ["vehicle", "home_improvement", "personal", "debt_consolidation"],
            "origination_channel": ["branch", "web", "broker"],
        },
        "new_category": "partner_app",
        "channel": "origination_channel",
        "target_definition": "A simulated borrower default event within 12 months of the snapshot; "
        "not a regulatory default definition or an empirical default model.",
    },
    "insurance_lapse": {
        "title": "Insurance: synthetic 12-month policy lapse",
        "rows_per_month": 60,
        "id": "policy_id",
        "target": "lapse_12m",
        "miss_cost": 4,
        "numeric": [
            "monthly_premium",
            "premium_increase_pct",
            "tenure_months",
            "auto_pay",
            "missed_payments_6m",
            "service_contacts_6m",
            "portal_visits_30d",
            "budget_share_pct",
            "coverage_units",
        ],
        "categorical": ["product_type", "payment_frequency", "sales_channel"],
        "categories": {
            "product_type": ["term_life", "whole_life", "savings"],
            "payment_frequency": ["monthly", "quarterly", "annual"],
            "sales_channel": ["agent", "broker", "web"],
        },
        "new_category": "embedded",
        "channel": "sales_channel",
        "target_definition": "A simulated policy cessation through nonpayment or policyholder "
        "cancellation within 12 months; death, maturity and other competing "
        "events are not modeled. This is binary prediction, not survival analysis.",
    },
}

DESCRIPTIONS = {
    "monthly_income": "Monthly income, synthetic currency units; before the loan snapshot",
    "existing_debt_payment": "Existing monthly debt service, synthetic currency units",
    "loan_amount": "Requested principal, synthetic currency units",
    "term_months": "Contract term in months",
    "interest_rate_bp": "Simulated annual contractual rate in basis points",
    "utilization_pct": "Existing revolving-credit utilization, percent",
    "late_payments_12m": "Count of late payments in the preceding 12 months",
    "employment_months": "Employment tenure at snapshot, months",
    "internal_score": "Arbitrary synthetic internal score, not a commercial credit score",
    "employment_type": "Simulated employment category",
    "loan_purpose": "Declared simulated loan purpose",
    "origination_channel": "Origination channel; partner_app appears only in the test cohort",
    "monthly_premium": "Current premium, synthetic currency units per month",
    "premium_increase_pct": "Known premium change at snapshot, percent",
    "tenure_months": "Elapsed policy tenure at snapshot, months",
    "auto_pay": "Automatic payment enabled at snapshot, binary",
    "missed_payments_6m": "Missed payments in the preceding six months",
    "service_contacts_6m": "Servicing contacts in the preceding six months",
    "portal_visits_30d": "Customer portal visits in the preceding 30 days",
    "budget_share_pct": "Simulated premium-to-budget ratio, percent",
    "coverage_units": "Arbitrary synthetic coverage units",
    "product_type": "Simulated life-policy product category",
    "payment_frequency": "Contractual premium payment frequency",
    "sales_channel": "Sales channel; embedded appears only in the test cohort",
}


def _draw(seed: int, case: str, row: int, field: str, limit: int) -> int:
    content = f"financial-cases-v1:{seed}:{case}:{row}:{field}".encode()
    return int.from_bytes(hashlib.sha256(content).digest()[:8], "big") % limit


def _add_months(month: int, offset: int) -> int:
    year, zero_based = divmod(month // 100 * 12 + month % 100 - 1 + offset, 12)
    return year * 100 + zero_based + 1


def _bank_features(draw: Callable[[str, int], int], year: int) -> tuple[Row, int]:
    income = 1600 + draw("income", 7001)
    debt_share = 5 + draw("debt_share", 61)
    utilization = draw("utilization", 101)
    late_draw = draw("late", 100)
    late = 0 if late_draw < 78 else 1 if late_draw < 92 else 2 if late_draw < 97 else 3
    score = 350 + draw("score", 601)
    features: Row = {
        "monthly_income": income,
        "existing_debt_payment": income * debt_share // 100,
        "loan_amount": income * (6 + draw("amount", 43)),
        "term_months": (12, 24, 36, 48, 60)[draw("term", 5)],
        "interest_rate_bp": 300 + draw("interest", 1401) + max(year - 2021, 0) * 75,
        "utilization_pct": utilization,
        "late_payments_12m": late,
        "employment_months": draw("employment", 301),
        "internal_score": score,
    }
    probability_bp = 120 + utilization * 4 + debt_share * 8 + (1000 - score) // 2 + late * 450
    probability_bp += 350 if year == 2020 else 200 if year >= 2023 else 0
    return features, min(5500, max(50, probability_bp))


def _insurance_features(draw: Callable[[str, int], int], year: int) -> tuple[Row, int]:
    increase = draw("increase", 31) - 5 + (5 if year >= 2023 else 0)
    tenure = 1 + draw("tenure", 180)
    auto_pay = int(draw("auto_pay", 100) < 70)
    missed = 0 if draw("missed_zero", 100) < 84 else 1 + draw("missed", 3)
    visits = draw("visits", 21)
    budget = 1 + draw("budget", 15)
    features: Row = {
        "monthly_premium": 30 + draw("premium", 471),
        "premium_increase_pct": increase,
        "tenure_months": tenure,
        "auto_pay": auto_pay,
        "missed_payments_6m": missed,
        "service_contacts_6m": draw("contacts", 7),
        "portal_visits_30d": visits,
        "budget_share_pct": budget,
        "coverage_units": 10 + draw("coverage", 191),
    }
    probability_bp = 350 + max(increase, 0) * 35 + missed * 700 + budget * 25
    probability_bp += (450 if tenure < 24 else 0) + (350 if visits < 3 else 0) - auto_pay * 350
    return features, min(6500, max(100, probability_bp))


def _rows(case: str, seed: int) -> list[Row]:
    spec = CASES[case]
    rows = []
    for month_index in range(84):
        month = _add_months(201801, month_index)
        for position in range(spec["rows_per_month"]):
            serial = month_index * spec["rows_per_month"] + position

            draw = partial(_draw, seed, case, serial)
            features, probability_bp = (
                _bank_features(draw, month // 100)
                if case == "credit_default"
                else _insurance_features(draw, month // 100)
            )
            for column, categories in spec["categories"].items():
                features[column] = categories[draw(column, len(categories))]
            if month >= 202401 and draw("new_channel", 100) < 20:
                features[spec["channel"]] = spec["new_category"]
            target = int(draw("outcome", 10000) < probability_bp)
            for column in spec["numeric"] + spec["categorical"]:
                if draw("missing_" + column, 100) < 4:
                    features[column] = ""
            rows.append(
                {
                    spec["id"]: f"SYN-{case.upper()}-{serial:06d}",
                    "snapshot_month": month,
                    **features,
                    "followup_months": 12,
                    "outcome_end_month": _add_months(month, 12),
                    "event_month": _add_months(month, 1 + draw("event_time", 12)) if target else "",
                    spec["target"]: target,
                }
            )
    return rows


def _csv(rows: list[Row], columns: list[str]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _json(value: object, *, indent: int = 2) -> str:
    return json.dumps(value, indent=indent, ensure_ascii=True, allow_nan=False) + "\n"


def _literal_list(values: list[str]) -> str:
    return "[\n" + "".join(f"    {json.dumps(value)},\n" for value in values) + "]"


def _cells(case: str) -> list[str]:
    spec = CASES[case]
    target, identifier, miss_cost = spec["target"], spec["id"], spec["miss_cost"]
    return [
        "import numpy as np\nimport pandas as pd\n"
        "from sklearn.ensemble import RandomForestClassifier\n"
        "from sklearn.metrics import (\n    average_precision_score,\n    brier_score_loss,\n"
        "    confusion_matrix,\n    precision_score,\n    recall_score,\n    roc_auc_score,\n)\n\n"
        'raw = pd.read_csv("data/portfolio.csv")\n'
        'assert not raw.empty, "Empty portfolio"\n'
        f'assert raw["{identifier}"].is_unique, "Duplicate entity IDs"',
        "horizon_months = 12\ntrain_end_month = 202101\nportfolio_rows = len(raw)\n"
        'df = raw.loc[raw["followup_months"] >= horizon_months].copy()\n'
        'assert not df.empty, "No complete outcome windows"\n'
        f'assert df["{target}"].isin([0, 1]).all(), "Invalid target"',
        'train = df.loc[df["snapshot_month"] < train_end_month].copy()\n'
        'validation = df.loc[df["snapshot_month"].between(202201, 202212)].copy()\n'
        'test = df.loc[df["snapshot_month"].between(202401, 202412)].copy()\n'
        'assert not train.empty, "Empty cohort"\n'
        'assert not validation.empty, "Empty cohort"\n'
        'assert not test.empty, "Empty cohort"\n'
        'assert train["outcome_end_month"].max() < validation["snapshot_month"].min()\n'
        'assert validation["outcome_end_month"].max() < test["snapshot_month"].min()',
        f"numeric_columns = {_literal_list(spec['numeric'])}\n"
        f"categorical_columns = {_literal_list(spec['categorical'])}\n"
        "feature_columns = numeric_columns + categorical_columns\n"
        "X_train = train[feature_columns].copy()\n"
        "X_validation = validation[feature_columns].copy()\n"
        "X_test = test[feature_columns].copy()\n"
        f'y_train = train["{target}"].astype(int)\n'
        f'y_validation = validation["{target}"].astype(int)\n'
        f'y_test = test["{target}"].astype(int)',
        "numeric_medians = X_train[numeric_columns].median()\n"
        "category_modes = X_train[categorical_columns].mode().iloc[0]\n"
        "X_train_filled = X_train.fillna(numeric_medians).fillna(category_modes)\n"
        "X_validation_filled = X_validation.fillna(numeric_medians).fillna(category_modes)\n"
        "X_test_filled = X_test.fillna(numeric_medians).fillna(category_modes)",
        "X_train_encoded = pd.get_dummies(X_train_filled, "
        "columns=categorical_columns, dtype=float)\n"
        "X_validation_encoded = pd.get_dummies(\n"
        "    X_validation_filled, columns=categorical_columns, dtype=float\n"
        ").reindex(columns=X_train_encoded.columns, fill_value=0.0)\n"
        "X_test_encoded = pd.get_dummies(X_test_filled, "
        "columns=categorical_columns, dtype=float).reindex(\n"
        "    columns=X_train_encoded.columns, fill_value=0.0\n)",
        "model = RandomForestClassifier(\n"
        "    n_estimators=40,\n    random_state=42,\n    max_depth=4,\n"
        '    min_samples_leaf=8,\n    class_weight="balanced",\n    n_jobs=1,\n)\n'
        "model.fit(X_train_encoded, y_train)",
        "validation_scores = model.predict_proba(X_validation_encoded)[:, 1]\n"
        "candidate_thresholds = np.array([0.15, 0.25, 0.35, 0.5, 0.65])\n"
        "validation_alerts = validation_scores[:, None] >= candidate_thresholds[None, :]\n"
        "validation_misses = ((y_validation.to_numpy()[:, None] == 1) "
        "& ~validation_alerts).sum(axis=0)\n"
        "validation_false_alerts = ((y_validation.to_numpy()[:, None] == 0) "
        "& validation_alerts).sum(axis=0)\n"
        f"validation_costs = validation_misses * {miss_cost} + validation_false_alerts\n"
        "threshold = float(candidate_thresholds[np.argmin(validation_costs)])",
        "test_scores = model.predict_proba(X_test_encoded)[:, 1]\n"
        "test_predictions = (test_scores >= threshold).astype(int)",
        "matrix = confusion_matrix(y_test, test_predictions, labels=[0, 1])\n"
        "metrics = {\n"
        '    "roc_auc": round(float(roc_auc_score(y_test, test_scores)), 8),\n'
        '    "average_precision": round(float(average_precision_score(y_test, test_scores)), 8),\n'
        '    "brier": round(float(brier_score_loss(y_test, test_scores)), 8),\n'
        '    "precision": round(float(precision_score(y_test, test_predictions, '
        "zero_division=0)), 8),\n"
        '    "recall": round(float(recall_score(y_test, test_predictions, zero_division=0)), 8),\n'
        '    "alert_rate": round(float(test_predictions.mean()), 8),\n'
        '    "positive_rate": round(float(y_test.mean()), 8),\n'
        '    "threshold": threshold,\n'
        '    "true_negatives": int(matrix[0, 0]),\n    "false_positives": int(matrix[0, 1]),\n'
        '    "false_negatives": int(matrix[1, 0]),\n    "true_positives": int(matrix[1, 1]),\n'
        f'    "cost_units": int(matrix[1, 0] * {miss_cost} + matrix[0, 1]),\n'
        "}",
        'cohort_counts = {\n    "train_rows": len(train),\n'
        '    "validation_rows": len(validation),\n    "test_rows": len(test),\n'
        '    "excluded_followup_rows": portfolio_rows - len(df),\n'
        '    "embargo_rows": len(df) - len(train) - len(validation) - len(test),\n}\n'
        "feature_names = X_train_encoded.columns.tolist()\n"
        'summary = {"counts": cohort_counts, "metrics": metrics, "features": feature_names}\n'
        f'scored_test = test[["{identifier}", "snapshot_month", "{target}"]].assign(\n'
        "    score=test_scores, prediction=test_predictions\n)",
    ]


def _notebook(case: str, *, boundary: str = "") -> str:
    code = _cells(case)
    if boundary != "assertions":
        code = [code[0] + "\n" + code[1], *code[2:]]
    if boundary == "catalog_reuse":
        code[-1] = code[-1].replace("portfolio_rows - len(df)", "len(raw) - len(df)")
    for index, source in enumerate(code):
        compile(source, f"{case}/cell-{index}", "exec", dont_inherit=True)
    return _json(
        {
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "intro",
                    "metadata": {},
                    "source": [
                        f"# {CASES[case]['title']}\n",
                        "Entirely synthetic. Training: 2018-2020; validation: 2022; test: 2024.\n",
                        "The 2021/2023 embargo cohorts prevent outcome-window overlap. "
                        "No user-defined functions.",
                    ],
                }
            ]
            + [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "id": f"stage-{index:02d}",
                    "metadata": {},
                    "outputs": [],
                    "source": source.splitlines(keepends=True),
                }
                for index, source in enumerate(code)
            ],
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python"},
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        },
        indent=1,
    )


def _counts(rows: list[Row]) -> dict[str, int]:
    return {
        "train_rows": sum(int(row["snapshot_month"]) < 202101 for row in rows),
        "validation_rows": sum(202201 <= int(row["snapshot_month"]) <= 202212 for row in rows),
        "test_rows": sum(202401 <= int(row["snapshot_month"]) <= 202412 for row in rows),
        "excluded_followup_rows": 0,
        "embargo_rows": sum(
            202101 <= int(row["snapshot_month"]) <= 202112
            or 202301 <= int(row["snapshot_month"]) <= 202312
            for row in rows
        ),
    }


def _feature_names(spec: dict[str, Any]) -> list[str]:
    return list(spec["numeric"]) + [
        f"{column}_{category}"
        for column in spec["categorical"]
        for category in sorted(spec["categories"][column])
    ]


def _regression(case: str, csvs: dict[str, str], counts: dict[str, int]) -> dict[str, Any]:
    def json_value(value: object) -> dict[str, Any]:
        return {"kind": "json", "value": value}

    def exception(message: str, node: str) -> dict[str, str]:
        return {"type": "AssertionError", "message": message, "node": node}

    spec = CASES[case]
    scenarios = [
        {
            "id": "baseline",
            "inputs": {"raw": "portfolio"},
            "parameters": {"train_model.n_estimators": 40, "train_model.random_state": 42},
            "expected": {
                "cohort_counts": json_value(counts),
                "feature_names": json_value(_feature_names(spec)),
            },
            "nodes": {
                "task-0009": {
                    "inputs": {
                        "y_test": {
                            "kind": "series",
                            "name": spec["target"],
                            "index": [0, 1, 2, 3],
                            "index_name": None,
                            "dtype": "int64",
                            "data": [0, 0, 1, 1],
                        },
                        "test_scores": {
                            "kind": "array",
                            "dtype": "float64",
                            "data": [0.1, 0.4, 0.35, 0.8],
                        },
                        "test_predictions": {
                            "kind": "array",
                            "dtype": "int64",
                            "data": [0, 0, 0, 1],
                        },
                        "threshold": json_value(0.5),
                    },
                    "expected": {
                        "matrix": {"kind": "array", "dtype": "int64", "data": [[2, 0], [1, 1]]},
                        "metrics": json_value(
                            {
                                "roc_auc": 0.75,
                                "average_precision": 0.83333333,
                                "brier": 0.158125,
                                "precision": 1.0,
                                "recall": 0.5,
                                "alert_rate": 0.25,
                                "positive_rate": 0.5,
                                "threshold": 0.5,
                                "true_negatives": 2,
                                "false_positives": 0,
                                "false_negatives": 1,
                                "true_positives": 1,
                                "cost_units": spec["miss_cost"],
                            }
                        ),
                    },
                }
            },
        }
    ]
    for name, message, node in (
        ("empty", "Empty portfolio", "task-0001"),
        ("duplicate", "Duplicate entity IDs", "task-0001"),
        ("immature", "No complete outcome windows", "task-0001"),
        ("invalid_target", "Invalid target", "task-0001"),
    ):
        scenarios.append(
            {
                "id": name,
                "inputs": {"raw": name},
                "parameters": scenarios[0]["parameters"],
                "raises": exception(message, node),
                "nodes": {
                    node: {
                        "inputs": {"raw": {"kind": "csv", "fixture": name}},
                        "raises": {"type": "AssertionError", "message": message},
                    }
                },
            }
        )
    return {
        "schema_version": "1.0",
        "fixtures": {
            name: {"path": f"data/{name}.csv", "sha256": hashlib.sha256(text.encode()).hexdigest()}
            for name, text in csvs.items()
        },
        "scenarios": scenarios,
    }


def build_files(seed: int = 42) -> dict[Path, str]:
    """Return deterministic case artifacts; model outputs are never captured as oracles."""
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be an unsigned 32-bit integer")
    guide = Path(__file__).resolve().parents[1] / "examples/banking_insurance/README.md"
    files: dict[Path, str] = {Path("README.md"): guide.read_text(encoding="utf-8")}
    for case, spec in CASES.items():
        root = Path(case)
        rows = _rows(case, seed)
        columns = list(rows[0])
        immature = {
            **rows[0],
            "followup_months": 6,
            "outcome_end_month": _add_months(201801, 6),
            "event_month": "",
            spec["target"]: "",
        }
        csvs = {
            "portfolio": _csv(rows, columns),
            "empty": _csv([], columns),
            "duplicate": _csv([rows[0], rows[0]], columns),
            "immature": _csv([immature], columns),
            "invalid_target": _csv([{**rows[0], spec["target"]: 2}], columns),
        }
        files.update({root / f"data/{name}.csv": text for name, text in csvs.items()})
        files[root / "workflow.ipynb"] = _notebook(case)
        files[root / "boundary_assertions.ipynb"] = _notebook(case, boundary="assertions")
        files[root / "boundary_catalog_reuse.ipynb"] = _notebook(case, boundary="catalog_reuse")
        files[root / "regression.json"] = _json(_regression(case, csvs, _counts(rows)))
        files[root / "project.json"] = _json(
            {
                "schema_version": "1.0",
                "project_root": ".",
                "source": "workflow.ipynb",
                "source_kind": "notebook",
                "package_name": case,
                "regression_contract": "regression.json",
            }
        )
        files[root / "manifest.json"] = _json(
            {
                "schema_version": "1.0",
                "synthetic": True,
                "generator": "financial-cases-v1",
                "seed": seed,
                "rows": len(rows),
                "target": spec["target"],
                "positive_rows": sum(int(row[spec["target"]]) for row in rows),
                "missing_values": {
                    name: sum(row[name] == "" for row in rows)
                    for name in spec["numeric"] + spec["categorical"]
                },
                "new_test_category": {"column": spec["channel"], "value": spec["new_category"]},
                "counts": _counts(rows),
                "feature_columns": spec["numeric"] + spec["categorical"],
                "expected_encoded_features": _feature_names(spec),
                "target_definition": spec["target_definition"],
                "miss_cost_units": spec["miss_cost"],
                "false_alert_cost_units": 1,
                "observation_cutoff_month": 202601,
                "portfolio_sha256": hashlib.sha256(csvs["portfolio"].encode()).hexdigest(),
            }
        )
        files[root / "dictionary.json"] = _json(
            {
                "columns": {
                    name: {
                        "role": "feature",
                        "as_of_snapshot": True,
                        "type": "numeric" if name in spec["numeric"] else "categorical",
                        "description": DESCRIPTIONS[name],
                    }
                    for name in spec["numeric"] + spec["categorical"]
                },
                "excluded_columns": {
                    spec["id"]: "Identifier; never a predictor",
                    "snapshot_month": "Cohort metadata",
                    "followup_months": "Label completeness; never a predictor",
                    "outcome_end_month": "Future observation metadata; never a predictor",
                    "event_month": "Future event metadata; never a predictor",
                    spec["target"]: "Target",
                },
            }
        )
        files[root / "README.md"] = (
            f"# {spec['title']}\n\nEntirely synthetic: {len(rows):,} rows, one observation per "
            "fictional entity, monthly cohorts from January 2018 to December 2024. "
            "No personal or real customer data is used.\n\n"
            f"Target: `{spec['target']}`. {spec['target_definition']} "
            f"There are {sum(int(row[spec['target']]) for row in rows):,} positive rows. "
            "Rates and relationships are invented and uncalibrated.\n\n"
            "`data/portfolio.csv` is the main dataset; `dictionary.json` describes units and "
            "predictor roles. `manifest.json` pins its hash, seed, counts and feature allowlist. "
            "Identifiers, future event/end dates and labels are excluded from predictors.\n\n"
            "The ten-cell procedural `workflow.ipynb` filters complete outcome windows, "
            "splits cohorts, fits training-only imputation/encoding, trains a seeded forest, "
            "chooses a threshold on validation and scores the untouched test cohort. "
            "Training uses 2018-2020, validation 2022 and test 2024; "
            "2021/2023 are embargo cohorts. "
            "Unknown test categories map to zero in the corresponding training dummy columns.\n\n"
            f"A missed event costs {spec['miss_cost']} illustrative units "
            "and a false alert one unit. "
            "These are declared demonstration assumptions, not estimated financial losses.\n\n"
            "`regression.json` supplies known cohort/feature expectations, a hand-calculated "
            "four-observation metric oracle and explicit empty/duplicate/incomplete/invalid-label "
            "failure cases. Ten shipped tests are expected. Model scores are not captured as "
            "golden expectations; model/node coverage gaps remain visible.\n\n"
            "`boundary_assertions.ipynb` keeps identical Python instructions "
            "with an assertion-only "
            "first business cell and must be refused with SA002. `boundary_catalog_reuse.ipynb` "
            "reads the raw catalog again for its final row count and must be refused with SA008. "
            "The working layout materializes that scalar once. No engine guard is relaxed.\n\n"
            "See the [corpus guide](../README.md) for commands, methodology and limitations.\n"
        )
    return files


def main() -> None:
    """Publish synthetic examples to a new directory through the shared writer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output", type=Path, help="New destination; existing directories are refused"
    )
    parser.add_argument("--seed", type=int, default=42)
    arguments = parser.parse_args()
    paths = write_project(arguments.output, build_files(arguments.seed))
    print(f"Wrote {len(paths)} synthetic case files to {arguments.output}")  # noqa: T201


if __name__ == "__main__":
    main()
