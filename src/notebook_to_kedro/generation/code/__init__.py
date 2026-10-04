"""Provider-neutral node code proposals, validated without execution or file I/O."""

from notebook_to_kedro.generation.code.assembly import (
    NODE_BODY_ASSEMBLY_VERSION,
    assemble_node_body,
)
from notebook_to_kedro.generation.code.contracts import (
    NODE_BODY_SCHEMA_VERSION,
    NODE_CODE_SCHEMA_VERSION,
    NodeBodyResponse,
    NodeCodeRequest,
    NodeCodeResponse,
    build_node_code_request,
)
from notebook_to_kedro.generation.code.evidence import (
    NODE_CODE_PARAMETER_EVIDENCE_VERSION,
    build_parameter_evidence,
)
from notebook_to_kedro.generation.code.ollama import OllamaNodeCodeProvider
from notebook_to_kedro.generation.code.prompting import (
    NODE_CODE_PARAMETER_PROMPT_VERSION,
    NODE_CODE_PROMPT_VERSION,
    render_node_code_prompt,
)
from notebook_to_kedro.generation.code.providers import FakeNodeCodeProvider, NodeCodeProvider
from notebook_to_kedro.generation.code.schemas import (
    NODE_BODY_RESPONSE_JSON_SCHEMA,
    NODE_CODE_RESPONSE_JSON_SCHEMA,
)
from notebook_to_kedro.generation.code.service import NodeCodeResult, request_node_code
from notebook_to_kedro.generation.code.validation import (
    NODE_CODE_VALIDATOR_VERSION,
    validate_node_code,
)
from notebook_to_kedro.generation.parameters import ParameterReplacement

__all__ = [
    "NODE_BODY_ASSEMBLY_VERSION",
    "NODE_BODY_RESPONSE_JSON_SCHEMA",
    "NODE_BODY_SCHEMA_VERSION",
    "NODE_CODE_PARAMETER_EVIDENCE_VERSION",
    "NODE_CODE_PARAMETER_PROMPT_VERSION",
    "NODE_CODE_PROMPT_VERSION",
    "NODE_CODE_RESPONSE_JSON_SCHEMA",
    "NODE_CODE_SCHEMA_VERSION",
    "NODE_CODE_VALIDATOR_VERSION",
    "FakeNodeCodeProvider",
    "NodeBodyResponse",
    "NodeCodeProvider",
    "NodeCodeRequest",
    "NodeCodeResponse",
    "NodeCodeResult",
    "OllamaNodeCodeProvider",
    "ParameterReplacement",
    "assemble_node_body",
    "build_node_code_request",
    "build_parameter_evidence",
    "render_node_code_prompt",
    "request_node_code",
    "validate_node_code",
]
