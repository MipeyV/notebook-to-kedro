"""Freeze the schema-1.0 canonical default representation for interchange consumers."""

from notebook_to_kedro import DEFAULT_KEDRO_PROFILE, KedroArchitectureProfile


def test_schema_1_default_representation_is_stable() -> None:
    assert DEFAULT_KEDRO_PROFILE.to_json() == (
        '{"node_name_prefix":"","pipeline_name":"notebook_pipeline",'
        '"profile_id":"notebook-to-kedro.default","profile_version":"1.0.0",'
        '"schema_version":"1.0"}'
    )
    assert (
        KedroArchitectureProfile.from_dict(
            {
                "schema_version": "1.0",
                "profile_id": "notebook-to-kedro.default",
                "profile_version": "1.0.0",
            }
        )
        == DEFAULT_KEDRO_PROFILE
    )
