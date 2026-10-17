"""Command-line interface: `filing-assistant <command>`.

    filing-assistant download                      # FinanceBench questions + 84 PDFs (pinned)
    filing-assistant download --docs 3M_2018_10K PEPSICO_2022_10K
    filing-assistant ingest --embed lsa            # build index/ from data/financebench/pdfs
    filing-assistant ingest --pdfs my_filings/ --embed mistral
    filing-assistant ask "What was 3M's FY2018 capex?"
    filing-assistant eval-retrieval                # recall@k, MRR for every configuration
    filing-assistant eval-refusal
    filing-assistant eval-answers --judge          # needs MISTRAL_API_KEY
    filing-assistant mcp                           # MCP tool server on stdio
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from filing_assistant.config import get_settings


def _questions(args, index):
    from filing_assistant.financebench import load_questions, load_questions_file, split_of
    qs = (load_questions_file(Path(args.questions)) if getattr(args, "questions", None)
          else load_questions(Path(args.data_dir)))
    split = getattr(args, "split", "all")
    return [q for q in qs if q.doc in set(index.docs) and (split == "all"
                                                            or split_of(q.id) == split)]


def _index(args):
    from filing_assistant.index import load
    return load(Path(args.index_dir))


def cmd_download(args) -> int:
    from filing_assistant.financebench import download
    root = download(Path(args.data_dir), docs=args.docs)
    print(f"FinanceBench ready in {root} ({len(list((root / 'pdfs').glob('*.pdf')))} PDFs)")
    return 0


def cmd_ingest(args) -> int:
    from filing_assistant.demo import demo_doc_info, write_demo_corpus
    from filing_assistant.financebench import load_doc_info
    from filing_assistant.index import build

    data = Path(args.data_dir)
    folders: list[Path] = [Path(p) for p in args.pdfs or []]
    if args.demo:
        write_demo_corpus(data / "demo")
        folders.append(data / "demo")
    if args.financebench or not folders:
        folders.append(data / "financebench" / "pdfs")
    pdfs = sorted({p for folder in folders for p in folder.glob("*.pdf")})
    if args.docs:
        pdfs = [p for p in pdfs if p.stem in set(args.docs)]
    if not pdfs:
        print(f"no PDFs found in {', '.join(map(str, folders))}", file=sys.stderr)
        return 1
    doc_info = load_doc_info(data)
    for folder in folders:
        doc_info |= demo_doc_info(folder)        # any folder may carry a doc_info.json
    index = build(pdfs, Path(args.index_dir), ocr=not args.no_ocr, max_words=args.max_words,
                  overlap=args.overlap, embedders=args.embed or [], doc_info=doc_info,
                  guard=not args.no_guard,
                  progress=lambda n, t, d: print(f"  [{n}/{t}] {d}", flush=True))
    totals = index.manifest["totals"]
    print(f"indexed {totals['documents']} documents, {totals['pages']} pages "
          f"({totals['ocr_pages']} OCR), {totals['chunks']} chunks "
          f"({totals['table_chunks']} tables) in {index.manifest['ingest_seconds']}s "
          f"-> {args.index_dir}")
    if index.manifest.get("guarded"):
        print(f"guardrails: {totals['quarantined_sentences']} instruction-like sentences "
              f"quarantined, personal data masked on {totals['pii_masked_pages']} page(s); "
              "see manifest.json")
    return 0


def cmd_embed(args) -> int:
    from filing_assistant.index import add_embeddings
    index = _index(args)
    add_embeddings(index, args.name)
    print(f"added {args.name} vectors: {index.manifest['embedders'][args.name]}")
    return 0


def _assistant(args, index):
    from filing_assistant.pipeline import Assistant, AssistantConfig
    cfg = AssistantConfig(mode=args.mode, embedder=args.embedder, reranker=args.reranker,
                          answer_mode=args.answer_mode, route=not args.no_route,
                          min_coverage=args.min_coverage)
    return Assistant(index, cfg)


def cmd_ask(args) -> int:
    index = _index(args)
    assistant = _assistant(args, index)
    answer = assistant.ask(args.question, docs=args.docs or None)
    if args.json:
        print(json.dumps(answer.to_dict(), indent=2, default=str))
        return 0
    print(answer.answer)
    print()
    for c in answer.citations:
        print(f"  [{c['ref']}] {c['doc']} p.{c['page']}  {c['title']}")
    cost = f", USD {answer.cost_usd:.5f}" if answer.cost_usd is not None else ""
    print(f"\n({answer.mode}{', ' + answer.model if answer.model else ''}, "
          f"{answer.timings_ms['total']:.0f} ms{cost}"
          f"{', refused: ' + answer.refusal_reason if answer.refused else ''})")
    return 0


def _configs(index) -> list[dict]:
    dense = sorted(index.dense)
    out = [{"mode": "bm25", "embedder": None, "reranker": r, "rewrite": w}
           for w in (False, True) for r in ("none", "lexical")]
    for emb in dense:
        out += [{"mode": m, "embedder": emb, "reranker": r, "rewrite": True}
                for m in ("dense", "hybrid") for r in ("none", "lexical")]
    return out


def cmd_eval_retrieval(args) -> int:
    from filing_assistant.evaluate import eval_retrieval, provenance, write_json
    from filing_assistant.rerank import get_reranker
    from filing_assistant.retrieve import Retriever
    from filing_assistant.router import resolve_docs

    index = _index(args)
    questions = _questions(args, index)
    rows = []
    for cfg in _configs(index):
        if args.only and cfg["mode"] not in args.only:
            continue
        retriever = Retriever(index, mode=cfg["mode"], embedder=cfg["embedder"],
                              rewrite=cfg["rewrite"])
        reranker = get_reranker(cfg["reranker"])
        for scope in ("doc", "routed", "corpus"):
            if scope == "routed":
                res = _eval_routed(retriever, reranker, questions, index, resolve_docs)
            else:
                res = eval_retrieval(retriever, reranker, questions, scope=scope)
            rows.append({**cfg, **{k: v for k, v in res.items() if k != "misses"},
                         "misses_at_5": len(res["misses"]), "misses": res["misses"]})
            print(f"{cfg['mode']:<7} {str(cfg['embedder']):<8} rerank={cfg['reranker']:<8} "
                  f"rewrite={str(cfg['rewrite']):<5} {scope:<7} recall {res['recall']} "
                  f"MRR {res['mrr']}  p50 {res['latency_ms']['p50']} ms", flush=True)
    report = {**provenance(index), "kind": "retrieval", "results": rows}
    print(f"written {write_json(report, Path(args.out), 'financebench-retrieval')}")
    return 0


def _eval_routed(retriever, reranker, questions, index, resolve_docs):
    """Retrieval with the question routed to its company's filings (falls back to corpus)."""
    import statistics
    import time

    from filing_assistant.evaluate import recall_at_k, reciprocal_rank
    ks = (1, 3, 5, 10)
    found = {k: 0 for k in ks}
    rr, lat, misses = [], [], []
    for q in questions:
        t0 = time.perf_counter()
        docs = resolve_docs(q.question, index.doc_info, index.docs) or None
        hits = reranker.rerank(q.question, retriever.search(q.question, k=30, docs=docs))
        lat.append((time.perf_counter() - t0) * 1000)
        for k in ks:
            found[k] += recall_at_k(hits, q.doc, q.evidence_pages, k)
        rr.append(reciprocal_rank(hits, q.doc, q.evidence_pages))
        if not recall_at_k(hits, q.doc, q.evidence_pages, 5):
            misses.append({"id": q.id, "question": q.question[:160], "doc": q.doc,
                           "routed_to": docs, "evidence_pages": q.evidence_pages,
                           "top3": [h.citation for h in hits[:3]]})
    n = len(questions)
    lat.sort()
    return {"questions": n, "scope": "routed",
            "recall": {f"@{k}": round(found[k] / n, 4) for k in ks},
            "mrr": round(sum(rr) / n, 4),
            "latency_ms": {"p50": round(statistics.median(lat), 2),
                           "p95": round(lat[int(0.95 * (n - 1))], 2)},
            "misses": misses}


def cmd_eval_refusal(args) -> int:
    from filing_assistant.evaluate import eval_refusal, provenance, write_json

    index = _index(args)
    assistant = _assistant(args, index)
    questions = _questions(args, index)
    res = eval_refusal(assistant, questions, scope=args.scope)
    report = {**provenance(index, {"split": args.split}), "kind": "refusal",
              "config": vars(assistant.config), **res}
    print(json.dumps(res, indent=2))
    stem = f"financebench-refusal-{args.scope}-{args.split}"
    print(f"written {write_json(report, Path(args.out), stem)}")
    return 0


def cmd_eval_answers(args) -> int:
    from filing_assistant.evaluate import eval_answers, provenance, write_json

    index = _index(args)
    assistant = _assistant(args, index)
    questions = _questions(args, index)
    if args.limit:
        questions = questions[: args.limit]
    judge_client = None
    if args.judge:
        from filing_assistant.llm import client_for
        judge_client = client_for(args.judge_provider)
    res = eval_answers(assistant, questions, scope=args.scope, judge_client=judge_client,
                       judge_role=args.judge_role)
    mode = assistant.answer_mode()
    report = {**provenance(index, {"split": args.split}), "kind": "answers",
              "config": vars(assistant.config), **res}
    print(json.dumps(res["summary"], indent=2))
    stem = f"financebench-answers-{mode}-{args.scope}-{args.split}"
    print(f"written {write_json(report, Path(args.out), stem)}")
    return 0


def cmd_mcp(args) -> int:
    from filing_assistant.mcp_server import build_server
    server = build_server(index_dir=Path(args.index_dir), data_dir=Path(args.data_dir))
    server.run(transport=args.transport)
    return 0


def build_parser() -> argparse.ArgumentParser:
    s = get_settings()
    p = argparse.ArgumentParser(prog="filing-assistant", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", default=s.data_dir)
    p.add_argument("--index-dir", default=s.index_dir)
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("download", help="download FinanceBench (pinned commit)")
    d.add_argument("--docs", nargs="*", help="only these filings (default: all 84)")

    i = sub.add_parser("ingest", help="build the index from PDFs")
    i.add_argument("--pdfs", nargs="*", help="folders of PDFs (a doc_info.json inside is used)")
    i.add_argument("--financebench", action="store_true",
                   help="include downloaded FinanceBench PDFs (default when no other source)")
    i.add_argument("--demo", action="store_true",
                   help="generate and include the fictional offline demo corpus")
    i.add_argument("--docs", nargs="*", help="only these filings")
    i.add_argument("--embed", nargs="*", choices=["lsa", "mistral"], help="dense vectors to add")
    i.add_argument("--no-ocr", action="store_true")
    i.add_argument("--no-guard", action="store_true",
                   help="skip injection quarantine and PII masking (v1.0 behaviour)")
    i.add_argument("--max-words", type=int, default=200)
    i.add_argument("--overlap", type=int, default=40)

    e = sub.add_parser("embed", help="add dense vectors to an existing index")
    e.add_argument("name", choices=["lsa", "mistral"])

    def retrieval_args(sp):
        sp.add_argument("--mode", default=s.retrieval_mode, choices=["bm25", "dense", "hybrid"])
        sp.add_argument("--embedder", default=s.embedder or None)
        sp.add_argument("--reranker", default=s.reranker, choices=["none", "lexical", "llm"])
        sp.add_argument("--answer-mode", default=s.answer_mode,
                        choices=["auto", "llm", "extractive"])
        sp.add_argument("--no-route", action="store_true")
        sp.add_argument("--min-coverage", type=float, default=s.min_coverage,
                        help="refusal gate: minimum share of question terms in a passage")

    a = sub.add_parser("ask", help="ask a question")
    a.add_argument("question")
    a.add_argument("--docs", nargs="*")
    a.add_argument("--json", action="store_true")
    retrieval_args(a)

    er = sub.add_parser("eval-retrieval", help="recall@k and MRR for every configuration")
    er.add_argument("--out", default="evals/results")
    er.add_argument("--questions", help="JSON questions file (default: FinanceBench)")
    er.add_argument("--split", default="all", choices=["all", "dev", "test"],
                    help="FinanceBench half: dev (tuning) or test (reporting)")
    er.add_argument("--only", nargs="*", choices=["bm25", "dense", "hybrid"])

    rf = sub.add_parser("eval-refusal", help="refusal gate on answerable vs unanswerable")
    rf.add_argument("--out", default="evals/results")
    rf.add_argument("--questions", help="JSON questions file (default: FinanceBench)")
    rf.add_argument("--split", default="all", choices=["all", "dev", "test"],
                    help="FinanceBench half: dev (tuning) or test (reporting)")
    rf.add_argument("--scope", default="routed", choices=["doc", "routed", "corpus"])
    retrieval_args(rf)

    ea = sub.add_parser("eval-answers", help="answer accuracy, citations, latency, cost")
    ea.add_argument("--out", default="evals/results")
    ea.add_argument("--questions", help="JSON questions file (default: FinanceBench)")
    ea.add_argument("--split", default="all", choices=["all", "dev", "test"],
                    help="FinanceBench half: dev (tuning) or test (reporting)")
    ea.add_argument("--scope", default="routed", choices=["doc", "routed", "corpus"])
    ea.add_argument("--limit", type=int)
    ea.add_argument("--judge", action="store_true", help="grade with an LLM judge")
    ea.add_argument("--judge-provider", default="mistral")
    ea.add_argument("--judge-role", default="strong")
    retrieval_args(ea)

    m = sub.add_parser("mcp", help="run the MCP tool server")
    m.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http", "sse"])
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"download": cmd_download, "ingest": cmd_ingest, "embed": cmd_embed,
                "ask": cmd_ask, "eval-retrieval": cmd_eval_retrieval,
                "eval-refusal": cmd_eval_refusal, "eval-answers": cmd_eval_answers,
                "mcp": cmd_mcp}
    if args.command in {"eval-refusal", "eval-answers"} and args.scope != "routed":
        args.no_route = True
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
