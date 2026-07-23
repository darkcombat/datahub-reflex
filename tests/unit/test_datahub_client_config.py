from reflex.datahub.read_client import DataHubReadClient
from reflex.datahub.write_client import DataHubWriteClient


def test_datahub_clients_use_environment_configuration(monkeypatch):
    monkeypatch.setenv("DATAHUB_GMS_URL", "http://datahub-gms:8080/")
    monkeypatch.setenv("DATAHUB_TOKEN", "test-token")

    read = DataHubReadClient()
    write = DataHubWriteClient()

    assert read._gms_url == "http://datahub-gms:8080"
    assert write._gms_url == "http://datahub-gms:8080"
    assert read._headers["Authorization"] == "Bearer test-token"
    assert write._headers["Authorization"] == "Bearer test-token"


def test_explicit_datahub_client_configuration_wins(monkeypatch):
    monkeypatch.setenv("DATAHUB_GMS_URL", "http://wrong-host:8080")
    monkeypatch.setenv("DATAHUB_TOKEN", "wrong-token")

    read = DataHubReadClient("http://explicit-host:8080/", "explicit-token")
    write = DataHubWriteClient("http://explicit-host:8080/", "explicit-token")

    assert read._gms_url == "http://explicit-host:8080"
    assert write._gms_url == "http://explicit-host:8080"
    assert read._headers["Authorization"] == "Bearer explicit-token"
    assert write._headers["Authorization"] == "Bearer explicit-token"
