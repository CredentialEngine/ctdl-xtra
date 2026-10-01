"""Built-in environment definitions.

An xTRA environment names *where a run is written*, not a Keycloak realm:
the storage account/container and which variable holds its secret.

Only `dev` ships with a usable default (Azurite). The shared environments are
deliberately blank so nobody guesses a production account name; supply the
container once with `xtra environment set <env> --data-uri ...`.
"""

DEFAULT_CONNECTION_STRING_ENV = "AZURE_STORAGE_CONNECTION_STRING"

AZURITE_DATA_URI = "azure://http://127.0.0.1:10000/devstoreaccount1/xtra"
AZURITE_CONNECTION_STRING = "UseDevelopmentStorage=true"

ENVIRONMENTS: dict[str, dict[str, str]] = {
    "dev": {
        "data_uri": AZURITE_DATA_URI,
        "connection_string_env": DEFAULT_CONNECTION_STRING_ENV,
        "fallback_connection_string": AZURITE_CONNECTION_STRING,
    },
    "test": {
        "data_uri": "",
        "connection_string_env": DEFAULT_CONNECTION_STRING_ENV,
        "fallback_connection_string": "",
    },
    "sandbox": {
        "data_uri": "",
        "connection_string_env": DEFAULT_CONNECTION_STRING_ENV,
        "fallback_connection_string": "",
    },
    "prod": {
        "data_uri": "",
        "connection_string_env": DEFAULT_CONNECTION_STRING_ENV,
        "fallback_connection_string": "",
    },
}

ENV_NAMES: tuple[str, ...] = tuple(ENVIRONMENTS.keys())
