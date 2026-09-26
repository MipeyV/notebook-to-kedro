"""Provider-neutral node code proposals, validated without execution or file I/O."""

from notebook_to_kedro.generation.code.contracts import (
    NODE_CODE_SCHEMA_VERSION,
    NodeCodeRequest,
    NodeCodeResponse,
    build_node_code_request,
)
from notebook_to_kedro.generation.code.ollama import OllamaNodeCodeProvider
from notebook_to_kedro.generation.code.prompting import (
    NODE_CODE_PROMPT_VERSION,
    render_node_code_prompt,
)
from notebook_to_kedro.generation.code.providers import FakeNodeCodeProvider, NodeCodeProvider
from notebook_to_kedro.generation.code.schemas import NODE_CODE_RESPONSE_JSON_SCHEMA
from notebook_to_kedro.generation.code.service import NodeCodeResult, request_node_code
from notebook_to_kedro.generation.code.validation import validate_node_code

__all__ = [
    "NODE_CODE_PROMPT_VERSION",
    "NODE_CODE_RESPONSE_JSON_SCHEMA",
    "NODE_CODE_SCHEMA_VERSION",
    "FakeNodeCodeProvider",
    "NodeCodeProvider",
    "NodeCodeRequest",
    "NodeCodeResponse",
    "NodeCodeResult",
    "OllamaNodeCodeProvider",
    "build_node_code_request",
    "render_node_code_prompt",
    "request_node_code",
    "validate_node_code",
]
