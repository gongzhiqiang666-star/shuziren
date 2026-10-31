import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location("shuziren_bge_worker", Path(__file__).with_name("app.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
KEY = "local-test-bge-token-not-a-real-secret"
HEADERS = {"Authorization": "Bearer " + KEY}


def test_missing_model_does_not_fabricate_vectors(tmp_path):
    engine = worker.Engine(str(tmp_path))
    with TestClient(worker.create_app(KEY, engine)) as client:
        assert client.get("/health").status_code == 401
        status = client.get("/health", headers=HEADERS)
        assert status.status_code == 503 and status.json()["ready"] is False
        assert client.post("/embed", headers=HEADERS, json={"texts": ["退换货规则"]}).status_code == 503


def test_validation_never_reflects_user_text(tmp_path):
    with TestClient(worker.create_app(KEY, worker.Engine(str(tmp_path)))) as client:
        for payload in ({"texts": []}, {"texts": ["x"] * 33}, {"texts": ["  "]}, {"texts": ["private\x00text"]}, {"texts": ["x"], "path": "/tmp/untrusted"}, {"texts": ["x"], "query": "yes"}):
            r = client.post("/embed", headers=HEADERS, json=payload)
            assert r.status_code == 422
            assert r.json() == {"detail": "invalid_request"}
        assert client.post("/embed", headers=HEADERS, content=b"x" * 600001).status_code == 413


def test_wrong_auth_cannot_probe_models(tmp_path):
    with TestClient(worker.create_app(KEY, worker.Engine(str(tmp_path)))) as client:
        assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/docs").status_code == 404


def test_fingerprint_covers_fast_tokenizer_special_tokens_and_algorithm(tmp_path):
    for name in ("config.json", "tokenizer.json", "special_tokens_map.json", "vocab.txt", "model.safetensors"):
        (tmp_path / name).write_text("initial")
    files = worker.artifact_files(tmp_path)
    first = worker.fingerprint(tmp_path, files, {"pooling": "CLS"})
    before = worker.signatures(files)
    (tmp_path / "tokenizer.json").write_text("changed fast tokenizer")
    assert first != worker.fingerprint(tmp_path, files, {"pooling": "CLS"})
    assert before != worker.signatures(files)
    second = worker.fingerprint(tmp_path, files, {"pooling": "CLS"})
    (tmp_path / "special_tokens_map.json").write_text("changed special tokens")
    assert second != worker.fingerprint(tmp_path, files, {"pooling": "CLS"})
    assert worker.fingerprint(tmp_path, files, {"pooling": "mean"}) != worker.fingerprint(tmp_path, files, {"pooling": "CLS"})
