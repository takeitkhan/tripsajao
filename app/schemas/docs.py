from typing import Any

from pydantic import BaseModel


class ParamDoc(BaseModel):
    name: str
    required: bool
    type: str
    description: str | None = None


class EndpointDoc(BaseModel):
    method: str
    path: str
    summary: str | None
    description: str | None
    required_scopes: list[str]
    auth: str
    path_params: list[ParamDoc]
    query_params: list[ParamDoc]
    request_body_example: Any | None
    response_status: int
    response_example: Any | None
    snippets: dict[str, str]


class ModuleDocs(BaseModel):
    module: str
    description: str
    base_url: str
    auth_headers: dict[str, str]
    endpoints: list[EndpointDoc]


class ModuleSummary(BaseModel):
    module: str
    description: str
    endpoint_count: int
