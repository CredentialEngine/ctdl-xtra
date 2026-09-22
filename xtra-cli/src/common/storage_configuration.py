from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AzureStorageConfiguration:
    connection_string: str
