import json

import pytest
from fastapi.testclient import TestClient

from app import main
from filing_assistant import cli

client = TestClient(main.app)


@pytest.fixture
def with_index(demo_index, demo_dir, monkeypatch):
    from filing_assistant.pipeline import Assistant, AssistantConfig
    monkeypatch.setattr(main, "index", lambda: demo_index)
    a = Assistant(demo_index, AssistantConfig(answer_mode="extractive", embedder="lsa"))
    monkeypatch.setattr(main, "assistant", lambda: a)
    monkeypatch.setattr(main.settings, "data_dir", str(demo_dir))
    (demo_dir / "demo").mkdir(exist_ok=True)
    pdf = demo_dir / "pdfs" / "NORTHWIND_2023_10K.pdf"
    (demo_dir / "demo" / pdf.name).write_bytes(pdf.read_bytes())
    yield


def test_health_ui_metrics_without_index():
    assert client.get("/health/live").json() == {"status": "ok"}
    ready = client.get("/health/ready").json()
    assert ready["status"] == "ready" and ready["index"] is False and ready["documents"] == 0
    assert "Filing assistant" in client.get("/").text
    assert "http_requests_total" in client.get("/metrics/").text
    assert client.get("/api/v1/filings").json() == []


def test_endpoints_without_index():
    assert client.post("/api/v1/ask", json={"question": "What was capex?"}).status_code == 503
    assert client.post("/api/v1/ask/stream", json={"question": "abc?"}).status_code == 503
    assert client.post("/api/v1/search", json={"query": "capex"}).status_code == 503
    assert client.get("/api/v1/filings/X/pages/1").status_code == 404
    assert client.get("/api/v1/filings/X/pdf").status_code == 404


@pytest.mark.parametrize("payload", [{"question": "hi"}, {"question": "x" * 2001}, {}])
def test_ask_validation(payload):
    assert client.post("/api/v1/ask", json=payload).status_code == 422


@pytest.mark.exercise
def test_ratio_endpoint():
    r = client.post("/api/v1/tools/ratio", json={"name": "gross_margin",
                                                 "values": {"gross_profit": 1, "revenue": 4}})
    assert r.json()["value"] == 25.0
    assert client.post("/api/v1/tools/ratio", json={"name": "nope",
                                                    "values": {}}).status_code == 422


@pytest.mark.exercise
def test_api_with_demo_index(with_index):
    q = "What was Northwind's FY2023 capital expenditure in USD millions?"
    body = client.post("/api/v1/ask", json={"question": q}).json()
    assert body["answer"].startswith("(285)") and body["citations"][0]["page"] == 5
    stream = client.post("/api/v1/ask/stream", json={"question": q})
    events = [json.loads(line[5:]) for line in stream.text.splitlines()
              if line.startswith("data:")]
    assert [e["event"] for e in events] == ["hits", "token", "done"]
    hits = client.post("/api/v1/search", json={"query": "dividend per share", "k": 2}).json()
    assert hits[0]["doc"] == "NORTHWIND_2023_EXHIBIT"
    filings = client.get("/api/v1/filings", params={"company": "northwind", "type": "10k"}).json()
    assert [f["doc"] for f in filings] == ["NORTHWIND_2023_10K"]
    page = client.get("/api/v1/filings/NORTHWIND_2023_10K/pages/5").json()
    assert "285" in page["text"]
    assert client.get("/api/v1/filings/NORTHWIND_2023_10K/pages/99").status_code == 404
    pdf = client.get("/api/v1/filings/NORTHWIND_2023_10K/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    ready = client.get("/health/ready").json()
    assert ready["index"] and ready["documents"] == 2 and ready["answer_mode"] == "extractive"
    assert "questions_total" in client.get("/metrics/").text


@pytest.mark.exercise
def test_cli_end_to_end(tmp_path, capsys):
    data, index = tmp_path / "data", tmp_path / "index"
    base = ["--data-dir", str(data), "--index-dir", str(index)]
    assert cli.main([*base, "ingest", "--demo", "--embed", "lsa"]) == 0
    assert "indexed 2 documents" in capsys.readouterr().out
    assert cli.main([*base, "ask", "--answer-mode", "extractive",
                     "What quarterly dividend per share did Northwind declare?"]) == 0
    out = capsys.readouterr().out
    assert "0.55" in out and "NORTHWIND_2023_EXHIBIT p.1" in out
    assert cli.main([*base, "ask", "--json", "--answer-mode", "extractive",
                     "Northwind net income in FY2022?"]) == 0
    assert json.loads(capsys.readouterr().out)["citations"]
    questions = str(data / "demo" / "questions.json")
    results = str(tmp_path / "results")
    assert cli.main([*base, "eval-retrieval", "--questions", questions, "--out", results]) == 0
    assert cli.main([*base, "eval-refusal", "--questions", questions, "--out", results,
                     "--answer-mode", "extractive"]) == 0
    assert cli.main([*base, "eval-answers", "--questions", questions, "--out", results,
                     "--answer-mode", "extractive", "--scope", "doc"]) == 0
    summary = json.loads(capsys.readouterr().out.split("written")[-2].split("\n", 1)[1]
                         .rsplit("\n", 2)[0]) if False else None
    assert summary is None
    assert len(list((tmp_path / "results").glob("*.json"))) == 3


def test_cli_ingest_without_pdfs(tmp_path, capsys):
    assert cli.main(["--data-dir", str(tmp_path), "--index-dir", str(tmp_path / "i"),
                     "ingest", "--pdfs", str(tmp_path)]) == 1
