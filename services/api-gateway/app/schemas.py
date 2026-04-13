from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RenderSynthesisRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str = Field(..., description="Text to synthesize with Fish Speech render runtime.")
    reference_id: str | None = Field(default=None, description="Saved reference id from the references library.")
    references: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional explicit reference payload list supported by Fish Speech ServeTTSRequest.",
    )
    chunk_length: int | None = None
    top_p: float | None = None
    repetition_penalty: float | None = None
    temperature: float | None = None
    seed: int | None = None
    normalize: bool | None = None
    use_memory_cache: str | None = None


class RenderBenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    target: Literal["render", "live"] = "render"
    text: str = Field(...)
    reference_id: str | None = None
    references: list[dict[str, Any]] | None = None
    chunk_length: int | None = None
    top_p: float | None = None
    repetition_penalty: float | None = None
    temperature: float | None = None
    seed: int | None = None
    normalize: bool | None = None
    use_memory_cache: str | None = None


class ModelActivateRequest(BaseModel):
    name: str = Field(...)
    target: Literal["render", "live"] = "render"


class ReferenceRecord(BaseModel):
    name: str
    path: str
    audio_file: str | None = None
    transcript: str = ""
    reference_meta: dict[str, Any] = Field(default_factory=dict)


class ReferenceListResponse(BaseModel):
    references: list[ReferenceRecord]


class ModelRecord(BaseModel):
    name: str
    kind: str
    engine: str
    path: str
    ready: bool


class RuntimeStatusRecord(BaseModel):
    active_model_path: str = ""
    ready: bool = False
    engine: str
    compile_enabled: bool | None = None
    dtype: str | None = None
    device: str | None = None
    detail: str | None = None


class ModelStatusResponse(BaseModel):
    render: ModelRecord | None = None
    live: ModelRecord | None = None
    models: list[ModelRecord]
    render_runtime: RuntimeStatusRecord | dict[str, Any]
    live_runtime: RuntimeStatusRecord | dict[str, Any] | None = None


class RenderCapabilitiesResponse(BaseModel):
    engine: Literal["fish"] = "fish"
    ready: bool
    active_model_path: str
    active_model_name: str | None = None
    device: str | None = None
    dtype: str | None = None
    compile_enabled: bool | None = None
    supports_reference_id: bool = True
    supports_explicit_references: bool = True
    supported_output_formats: list[str] = Field(default_factory=lambda: ["wav"])
    supported_request_fields: list[str] = Field(default_factory=list)
    defaults: dict[str, Any] = Field(default_factory=dict)
    limits: dict[str, Any] = Field(default_factory=dict)
    detail: str | None = None


class OpenAIAudioSpeechRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    input: str = Field(..., description="Input text to synthesize.")
    model: str | None = Field(default=None, description="Optional active render model name.")
    voice: str | None = Field(
        default=None,
        description="Maps to Fish Speech reference_id. Use a saved reference name for voice cloning.",
    )
    reference_id: str | None = Field(default=None, description="Explicit reference id. Overrides voice when provided.")
    response_format: Literal["wav"] = "wav"
    speed: float | None = Field(default=None, description="Not supported by Fish render; only 1.0 is accepted.")
    references: list[dict[str, Any]] | None = None
    chunk_length: int | None = None
    top_p: float | None = None
    repetition_penalty: float | None = None
    temperature: float | None = None
    seed: int | None = None
    normalize: bool | None = None
    use_memory_cache: str | None = None


class SampleRecord(BaseModel):
    name: str
    audio_file: str | None = None
    transcript: str = ""


class FileRecord(BaseModel):
    name: str
    size: int


class DatasetSummaryRecord(BaseModel):
    name: str
    path: str
    samples: int
    paired: int


class DatasetDetailRecord(BaseModel):
    name: str
    path: str
    samples: list[SampleRecord]
    paired: int
    files: list[FileRecord]


class DatasetListResponse(BaseModel):
    datasets: list[DatasetSummaryRecord]


class DatasetDeleteResponse(BaseModel):
    deleted: bool
    dataset: DatasetSummaryRecord


class DatasetCreateRequest(BaseModel):
    name: str = Field(...)


class TranscriptUpdateRequest(BaseModel):
    transcript: str = Field(...)


class EventRecord(BaseModel):
    kind: str
    payload: dict[str, Any]
    timestamp: str


class EventHistoryResponse(BaseModel):
    events: list[EventRecord]


class JobRecord(BaseModel):
    id: str
    kind: str
    status: str
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class JobListResponse(BaseModel):
    jobs: list[JobRecord]


class FineTuneConfigRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_name: str | None = None
    train_data_dir: str | None = None
    output_model_dir: str | None = None
    base_model_path: str | None = None
    vq_batch_size: int | None = None
    vq_num_workers: int | None = None
    build_dataset_workers: int | None = None
    lora_config: str | None = None
    model_repo: str | None = None
    hf_endpoint: str | None = None


class FineTuneStepRecord(BaseModel):
    label: str
    state: str


class FineTuneDefaultsResponse(BaseModel):
    defaults: dict[str, Any]
    presets: dict[str, list[str]]
    datasets: list[DatasetSummaryRecord]


class FineTuneValidationResponse(BaseModel):
    config: dict[str, Any]
    valid: bool
    pairs: int
    errors: list[str]
    issues: list[str]
    warnings: list[str]


class FineTuneStatusResponse(BaseModel):
    state: str
    config: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    steps: list[FineTuneStepRecord]
    log_tail: str
    job: JobRecord | None = None


class FineTuneStopRequest(BaseModel):
    job_id: str | None = None
