import pytest
from backend.app.analyzers import backend_adapter
from backend.app.analyzers.semgrep_adapter import ScanResult


@pytest.mark.parametrize('status', ['complete', 'partial', 'error'])
def test_backend_hook_preserves_failures(monkeypatch, status):
    result = ScanResult(status)
    monkeypatch.setattr(backend_adapter, '_scan_repository', lambda path: result)
    payload = backend_adapter.scan_repository('validated-path')
    assert payload['findings'] == []
    assert payload['status'] == status
    assert bool(payload['errors']) == (status != 'complete')
