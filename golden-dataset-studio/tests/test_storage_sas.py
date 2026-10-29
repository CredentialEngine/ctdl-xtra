"""A deployed Studio authenticates to Azure with one SAS token per container (storage.sas_env)."""

from golden_datasets.storage import sas_env


def test_sas_env_names_one_variable_per_container():
    assert sas_env("xtra-cli-output") == "AZURE_STORAGE_SAS_XTRA_CLI_OUTPUT"
    assert sas_env("xtra-golden-sets") == "AZURE_STORAGE_SAS_XTRA_GOLDEN_SETS"
