"""Command-line interface for Notebook to Kedro."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.api import (
    create_semantic_planner,
    generate_kedro_project,
    plan_notebook_path,
    render_conversion_report,
    validate_conversion_plan,
)
from notebook_to_kedro.evaluation import (
    BehavioralBenchmarkConfiguration,
    BehavioralExecutionConfig,
    CorpusBoundCodeBenchmarkArtifact,
    CorpusBoundCodeBenchmarkReport,
    behavioral_benchmark_artifact_sha256,
    collect_environment_provenance,
    compare_behavioral_benchmark_artifacts,
    compare_generation_formats,
    compare_node_body_benchmark_artifacts,
    corpus_bound_code_artifact_sha256,
    create_behavioral_benchmark_artifact,
    create_corpus_bound_code_artifact,
    create_node_body_benchmark_artifact,
    load_behavioral_benchmark_artifact,
    load_behavioral_corpus,
    load_corpus_bound_code_artifact,
    load_node_body_benchmark_artifact,
    load_node_code_corpus,
    load_planning_corpus,
    node_body_benchmark_artifact_sha256,
    planning_benchmark_to_json,
    replay_behavioral_benchmark,
    replay_corpus_bound_code_benchmark,
    replay_node_body_benchmark,
    run_behavioral_code_benchmark,
    run_corpus_bound_code_benchmark,
    run_node_body_benchmark,
    run_planning_benchmark,
    write_behavioral_benchmark_artifact,
    write_corpus_bound_code_artifact,
    write_json_exclusive,
    write_node_body_benchmark_artifact,
)
from notebook_to_kedro.exceptions import (
    BehavioralBenchmarkArtifactError,
    ConversionPlanValidationError,
    NotebookLoadError,
    PlannerConfigurationError,
    PlanningBenchmarkError,
    ProjectGenerationError,
)
from notebook_to_kedro.generation.code import OllamaNodeBodyProvider, OllamaNodeCodeProvider
from notebook_to_kedro.semantic import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    PlannerMode,
)

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan

ERROR_EXIT_CODE = 1


def main(argv: list[str] | None = None) -> int:
    """Run the Notebook to Kedro command-line interface."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            return _plan(args)
        if args.command == "generate":
            return _generate(args)
        if args.command == "benchmark":
            return _benchmark(args)
        if args.command == "behavioral-benchmark":
            return _behavioral_benchmark(args)
    except (
        BehavioralBenchmarkArtifactError,
        ConversionPlanValidationError,
        NotebookLoadError,
        PlannerConfigurationError,
        PlanningBenchmarkError,
        ProjectGenerationError,
    ) as error:
        sys.stderr.write(f"Error: {error}\n")
        return ERROR_EXIT_CODE
    parser.error("missing command")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notebook-to-kedro",
        description="Analyze structured notebooks and render Kedro conversion plans.",
    )
    subparsers = parser.add_subparsers(dest="command")
    plan_parser = subparsers.add_parser(
        "plan",
        help="render a Markdown conversion report for a notebook",
    )
    plan_parser.add_argument("notebook", type=Path, help="path to the source notebook")
    plan_parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="root used to normalize notebook-relative paths",
    )
    _add_planner_arguments(plan_parser)
    generate_parser = subparsers.add_parser(
        "generate",
        help="generate a minimal Kedro project from a notebook",
    )
    generate_parser.add_argument("notebook", type=Path, help="path to the source notebook")
    generate_parser.add_argument("output_dir", type=Path, help="destination directory to create")
    generate_parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="root used to normalize notebook-relative paths",
    )
    generate_parser.add_argument(
        "--package-name",
        default="generated_notebook",
        help="Python package name for the generated Kedro project",
    )
    _add_planner_arguments(generate_parser)
    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="compare planners over a reviewed planning corpus",
    )
    benchmark_parser.add_argument(
        "corpus",
        type=Path,
        help="directory containing reviewed planning case JSON files",
    )
    benchmark_parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(),
        help="root used to resolve case notebook paths",
    )
    benchmark_parser.add_argument(
        "--planners",
        type=PlannerMode,
        choices=tuple(PlannerMode),
        nargs="+",
        default=(PlannerMode.DETERMINISTIC,),
        help="planning modes to compare (default: deterministic)",
    )
    _add_ollama_arguments(benchmark_parser)
    behavioral_parser = subparsers.add_parser(
        "behavioral-benchmark",
        help="run, replay or compare behavioral node-code benchmark artifacts",
    )
    behavioral_actions = behavioral_parser.add_subparsers(dest="behavioral_action", required=True)
    behavioral_run = behavioral_actions.add_parser(
        "run", help="run a local Ollama model and write a reproducible artifact"
    )
    _add_behavioral_corpus_arguments(behavioral_run)
    behavioral_run.add_argument("output", type=Path, help="new artifact path to create")
    behavioral_run.add_argument(
        "--ollama-model", required=True, metavar="MODEL", help="downloaded local Ollama model"
    )
    behavioral_run.add_argument(
        "--ollama-base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        metavar="URL",
        help="local Ollama server URL",
    )
    behavioral_run.add_argument(
        "--ollama-timeout",
        type=float,
        default=DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="Ollama request timeout in seconds",
    )
    behavioral_run.add_argument(
        "--include-parameter-evidence",
        action="store_true",
        help="include deterministic parameter evidence in node-code prompts",
    )
    _add_behavioral_execution_arguments(behavioral_run)
    behavioral_replay = behavioral_actions.add_parser(
        "replay", help="revalidate and re-execute recorded responses without Ollama"
    )
    behavioral_replay.add_argument("artifact", type=Path, help="source artifact to replay")
    _add_behavioral_corpus_arguments(behavioral_replay)
    behavioral_replay.add_argument("output", type=Path, help="new replay artifact path to create")
    _add_behavioral_execution_arguments(behavioral_replay)
    behavioral_compare = behavioral_actions.add_parser(
        "compare", help="compare acceptance, behavior and latency across two artifacts"
    )
    behavioral_compare.add_argument("baseline", type=Path, help="baseline artifact")
    behavioral_compare.add_argument("candidate", type=Path, help="candidate artifact")
    behavioral_compare.add_argument(
        "--output", type=Path, default=None, help="new comparison JSON path to create"
    )
    for action in (behavioral_run, behavioral_replay):
        action.add_argument(
            "--proposal-format",
            choices=("full-code", "node-body", "bound-full-code"),
            default="full-code",
            help="explicit response/artifact format (default: full-code)",
        )
    behavioral_compare.add_argument(
        "--proposal-format",
        choices=("full-code", "node-body"),
        default="full-code",
        help="explicit response/artifact format (default: full-code)",
    )
    format_compare = behavioral_actions.add_parser(
        "compare-formats", help="compare corpus-bound full code with body-only evidence"
    )
    format_compare.add_argument("full_code", type=Path, help="corpus-bound full-code artifact")
    format_compare.add_argument("node_body", type=Path, help="body-only candidate artifact")
    format_compare.add_argument(
        "--output", type=Path, default=None, help="new comparison JSON path"
    )
    return parser


def _add_behavioral_corpus_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("behavioral_corpus", type=Path, help="reviewed behavioral case directory")
    parser.add_argument("node_code_corpus", type=Path, help="reviewed node-code case directory")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(),
        help="root used to resolve reviewed notebook paths",
    )


def _add_behavioral_execution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--allow-untrusted-code-execution",
        action="store_true",
        help="explicitly authorize validated proposal execution in local subprocesses",
    )
    parser.add_argument(
        "--execution-timeout",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="timeout for each isolated behavioral scenario",
    )


def _add_planner_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--planner",
        type=PlannerMode,
        choices=tuple(PlannerMode),
        default=PlannerMode.DETERMINISTIC,
        help="planning mode (default: deterministic)",
    )
    _add_ollama_arguments(parser)


def _add_ollama_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ollama-model",
        default=None,
        metavar="MODEL",
        help="downloaded local Ollama model required by the hybrid planner",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        metavar="URL",
        help="local Ollama server URL",
    )
    parser.add_argument(
        "--ollama-timeout",
        type=float,
        default=DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="Ollama request timeout in seconds",
    )


def _plan_from_args(args: argparse.Namespace) -> ConversionPlan:
    return plan_notebook_path(
        args.notebook,
        project_root=args.project_root,
        planner=args.planner,
        ollama_model=args.ollama_model,
        ollama_base_url=args.ollama_base_url,
        ollama_timeout_seconds=args.ollama_timeout,
    )


def _plan(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    sys.stdout.write(render_conversion_report(plan))
    return 0


def _generate(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    validate_conversion_plan(plan)
    created_files = generate_kedro_project(
        plan,
        args.output_dir,
        package_name=args.package_name,
    )
    sys.stdout.write(f"Created Kedro project at `{args.output_dir}`\n")
    for path in created_files:
        sys.stdout.write(f"- `{path}`\n")
    return 0


def _benchmark(args: argparse.Namespace) -> int:
    modes = tuple(dict.fromkeys(args.planners))
    includes_hybrid = PlannerMode.HYBRID in modes
    planners = {}
    for mode in modes:
        uses_ollama_settings = mode is PlannerMode.HYBRID or not includes_hybrid
        planner_name = (
            mode.value if mode is PlannerMode.DETERMINISTIC else f"hybrid:{args.ollama_model}"
        )
        planners[planner_name] = create_semantic_planner(
            mode,
            ollama_model=args.ollama_model if uses_ollama_settings else None,
            ollama_base_url=(
                args.ollama_base_url if uses_ollama_settings else DEFAULT_OLLAMA_BASE_URL
            ),
            ollama_timeout_seconds=(
                args.ollama_timeout if uses_ollama_settings else DEFAULT_OLLAMA_TIMEOUT_SECONDS
            ),
        )
    try:
        cases = load_planning_corpus(args.corpus)
    except ValueError as error:
        raise PlanningBenchmarkError(str(error)) from error
    report = run_planning_benchmark(cases, planners, project_root=args.project_root)
    sys.stdout.write(planning_benchmark_to_json(report))
    return 0


def _behavioral_benchmark(args: argparse.Namespace) -> int:
    try:
        if args.behavioral_action == "run":
            return _run_behavioral_benchmark(args)
        if args.behavioral_action == "replay":
            return _replay_behavioral_benchmark(args)
        if args.behavioral_action == "compare":
            return _compare_behavioral_benchmarks(args)
        if args.behavioral_action == "compare-formats":
            comparison = compare_generation_formats(
                load_corpus_bound_code_artifact(args.full_code),
                load_node_body_benchmark_artifact(args.node_body),
            )
            return _write_comparison(args.output, comparison)
    except ValueError as error:
        if isinstance(error, BehavioralBenchmarkArtifactError):
            raise
        raise BehavioralBenchmarkArtifactError(str(error)) from error
    raise BehavioralBenchmarkArtifactError(
        f"unsupported behavioral benchmark action: {args.behavioral_action!r}"
    )


def _run_behavioral_benchmark(args: argparse.Namespace) -> int:
    if args.proposal_format == "node-body":
        return _run_node_body_benchmark(args)
    behaviors = load_behavioral_corpus(args.behavioral_corpus)
    nodes = load_node_code_corpus(args.node_code_corpus)
    execution = BehavioralExecutionConfig(timeout_seconds=args.execution_timeout)
    provider = OllamaNodeCodeProvider(
        args.ollama_model,
        base_url=args.ollama_base_url,
        timeout_seconds=args.ollama_timeout,
        include_parameter_evidence=args.include_parameter_evidence,
    )
    runner = (
        run_corpus_bound_code_benchmark
        if args.proposal_format == "bound-full-code"
        else run_behavioral_code_benchmark
    )
    report = runner(
        behaviors,
        nodes,
        provider,
        allow_untrusted_code_execution=args.allow_untrusted_code_execution,
        project_root=args.project_root,
        prompt_version=provider.prompt_version,
        execution_config=execution,
    )
    configuration = BehavioralBenchmarkConfiguration(
        ollama_base_url=args.ollama_base_url,
        provider_timeout_seconds=args.ollama_timeout,
        include_parameter_evidence=args.include_parameter_evidence,
        execution=execution,
    )
    provenance = collect_environment_provenance(
        project_root=args.project_root,
        ollama_base_url=args.ollama_base_url,
        model_name=args.ollama_model,
    )
    if isinstance(report, CorpusBoundCodeBenchmarkReport):
        bound_artifact = create_corpus_bound_code_artifact(report, provenance, configuration)
        write_corpus_bound_code_artifact(args.output, bound_artifact)
        digest = corpus_bound_code_artifact_sha256(bound_artifact)
    else:
        artifact = create_behavioral_benchmark_artifact(report, provenance, configuration)
        write_behavioral_benchmark_artifact(args.output, artifact)
        digest = behavioral_benchmark_artifact_sha256(artifact)
    sys.stdout.write(f"Created behavioral benchmark artifact `{args.output}` ({digest})\n")
    return 0


def _replay_behavioral_benchmark(args: argparse.Namespace) -> int:
    if args.proposal_format == "node-body":
        return _replay_node_body_benchmark(args)
    source = (
        load_corpus_bound_code_artifact(args.artifact)
        if args.proposal_format == "bound-full-code"
        else load_behavioral_benchmark_artifact(args.artifact)
    )
    original = source.benchmark if isinstance(source, CorpusBoundCodeBenchmarkArtifact) else source
    behaviors = load_behavioral_corpus(args.behavioral_corpus)
    nodes = load_node_code_corpus(args.node_code_corpus)
    execution = BehavioralExecutionConfig(
        timeout_seconds=args.execution_timeout,
        max_request_bytes=original.configuration.execution.max_request_bytes,
        max_result_bytes=original.configuration.execution.max_result_bytes,
        max_capture_bytes=original.configuration.execution.max_capture_bytes,
    )
    configuration = BehavioralBenchmarkConfiguration(
        ollama_base_url=original.configuration.ollama_base_url,
        provider_timeout_seconds=original.configuration.provider_timeout_seconds,
        include_parameter_evidence=original.configuration.include_parameter_evidence,
        execution=execution,
    )
    if isinstance(source, CorpusBoundCodeBenchmarkArtifact):
        bound_report = replay_corpus_bound_code_benchmark(
            source,
            behaviors,
            nodes,
            allow_untrusted_code_execution=args.allow_untrusted_code_execution,
            project_root=args.project_root,
            execution_config=execution,
        )
        bound_artifact = create_corpus_bound_code_artifact(
            bound_report,
            collect_environment_provenance(project_root=args.project_root),
            configuration,
            mode="replay",
            source_artifact_sha256=corpus_bound_code_artifact_sha256(source),
        )
        write_corpus_bound_code_artifact(args.output, bound_artifact)
        digest = corpus_bound_code_artifact_sha256(bound_artifact)
    else:
        report = replay_behavioral_benchmark(
            source,
            behaviors,
            nodes,
            allow_untrusted_code_execution=args.allow_untrusted_code_execution,
            project_root=args.project_root,
            execution_config=execution,
        )
        artifact = create_behavioral_benchmark_artifact(
            report,
            collect_environment_provenance(project_root=args.project_root),
            configuration,
            mode="replay",
            source_artifact_sha256=behavioral_benchmark_artifact_sha256(source),
        )
        write_behavioral_benchmark_artifact(args.output, artifact)
        digest = behavioral_benchmark_artifact_sha256(artifact)
    sys.stdout.write(f"Created behavioral benchmark replay `{args.output}` ({digest})\n")
    return 0


def _compare_behavioral_benchmarks(args: argparse.Namespace) -> int:
    if args.proposal_format == "node-body":
        comparison = compare_node_body_benchmark_artifacts(
            load_node_body_benchmark_artifact(args.baseline),
            load_node_body_benchmark_artifact(args.candidate),
        )
    else:
        comparison = compare_behavioral_benchmark_artifacts(
            load_behavioral_benchmark_artifact(args.baseline),
            load_behavioral_benchmark_artifact(args.candidate),
        )
    return _write_comparison(args.output, comparison)


def _write_comparison(output: Path | None, comparison: dict[str, object]) -> int:
    if output is not None:
        write_json_exclusive(output, comparison)
        sys.stdout.write(f"Created behavioral benchmark comparison `{output}`\n")
    else:
        sys.stdout.write(
            json.dumps(
                comparison,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        )
    return 0


def _run_node_body_benchmark(args: argparse.Namespace) -> int:
    behaviors = load_behavioral_corpus(args.behavioral_corpus)
    nodes = load_node_code_corpus(args.node_code_corpus)
    execution = BehavioralExecutionConfig(timeout_seconds=args.execution_timeout)
    provider = OllamaNodeBodyProvider(
        args.ollama_model,
        base_url=args.ollama_base_url,
        timeout_seconds=args.ollama_timeout,
    )
    report = run_node_body_benchmark(
        behaviors,
        nodes,
        provider,
        allow_untrusted_code_execution=args.allow_untrusted_code_execution,
        project_root=args.project_root,
        execution_config=execution,
    )
    configuration = BehavioralBenchmarkConfiguration(
        ollama_base_url=args.ollama_base_url,
        provider_timeout_seconds=args.ollama_timeout,
        include_parameter_evidence=True,
        execution=execution,
    )
    artifact = create_node_body_benchmark_artifact(
        report,
        collect_environment_provenance(
            project_root=args.project_root,
            ollama_base_url=args.ollama_base_url,
            model_name=args.ollama_model,
        ),
        configuration,
    )
    write_node_body_benchmark_artifact(args.output, artifact)
    sys.stdout.write(
        f"Created node-body benchmark artifact `{args.output}` "
        f"({node_body_benchmark_artifact_sha256(artifact)})\n"
    )
    return 0


def _replay_node_body_benchmark(args: argparse.Namespace) -> int:
    source = load_node_body_benchmark_artifact(args.artifact)
    behaviors = load_behavioral_corpus(args.behavioral_corpus)
    nodes = load_node_code_corpus(args.node_code_corpus)
    original = source.benchmark.configuration
    execution = BehavioralExecutionConfig(
        timeout_seconds=args.execution_timeout,
        max_request_bytes=original.execution.max_request_bytes,
        max_result_bytes=original.execution.max_result_bytes,
        max_capture_bytes=original.execution.max_capture_bytes,
    )
    configuration = BehavioralBenchmarkConfiguration(
        ollama_base_url=original.ollama_base_url,
        provider_timeout_seconds=original.provider_timeout_seconds,
        include_parameter_evidence=True,
        execution=execution,
    )
    report = replay_node_body_benchmark(
        source,
        behaviors,
        nodes,
        allow_untrusted_code_execution=args.allow_untrusted_code_execution,
        project_root=args.project_root,
        execution_config=execution,
    )
    artifact = create_node_body_benchmark_artifact(
        report,
        collect_environment_provenance(project_root=args.project_root),
        configuration,
        mode="replay",
        source_artifact_sha256=node_body_benchmark_artifact_sha256(source),
    )
    write_node_body_benchmark_artifact(args.output, artifact)
    sys.stdout.write(
        f"Created node-body benchmark replay `{args.output}` "
        f"({node_body_benchmark_artifact_sha256(artifact)})\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
