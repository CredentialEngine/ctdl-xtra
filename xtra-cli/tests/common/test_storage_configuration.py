from __future__ import annotations

from common.storage_configuration import AzureStorageConfiguration


def test_azure_storage_configuration_holds_connection_string() -> None:
    config = AzureStorageConfiguration(connection_string="UseDevelopmentStorage=true")
    assert config.connection_string == "UseDevelopmentStorage=true"
