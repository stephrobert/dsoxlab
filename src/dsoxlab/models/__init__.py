"""Package models."""

from ._contract import ContractError, LabYamlError
from .course import CourseManifest, CourseSection
from .lab import LabDefinition, ValidationConfig
from .repo import (
    HostDefinition,
    InfraDefinition,
    ProviderUnresolved,
    RepoMetadata,
    SectionDefinition,
)
from .runtime import RuntimeConfig, RuntimeType, Target
from .schema_version import (
    DEFAULT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSION,
    UnsupportedSchemaVersion,
    read_schema_version,
)

__all__ = [
    "DEFAULT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSION",
    "ContractError",
    "CourseManifest",
    "CourseSection",
    "HostDefinition",
    "InfraDefinition",
    "LabDefinition",
    "LabYamlError",
    "ProviderUnresolved",
    "RepoMetadata",
    "RuntimeConfig",
    "RuntimeType",
    "SectionDefinition",
    "Target",
    "UnsupportedSchemaVersion",
    "ValidationConfig",
    "read_schema_version",
]
