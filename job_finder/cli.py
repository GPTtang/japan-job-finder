from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .rerank.merge import merge_reviews
from .rerank.packet import DEFAULT_TOP_K, MAX_TOP_K
from .rerank.profile import load_profile_json
from .rerank.report import format_reviewed_report
from .skill import job_finder, prepare_review, run_job_finder


def _top_k(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是整数：{value!r}") from None
    if not 1 <= number <= MAX_TOP_K:
        raise argparse.ArgumentTypeError(f"必须在 1 到 {MAX_TOP_K} 之间：{number}")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-finder",
        description="Single-run job finder Skill CLI",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Natural-language job search query. If omitted, use --query-file or --profile-json.",
    )
    parser.add_argument(
        "--query-file",
        type=str,
        help="Path to a text file containing the natural-language query.",
    )
    parser.add_argument(
        "--profile-json",
        type=str,
        help="Candidate profile as JSON (path, or - for stdin); replaces the keyword parser.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to sources config JSON.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of ranked jobs to return.",
    )
    parser.add_argument(
        "--top-k",
        type=_top_k,
        default=DEFAULT_TOP_K,
        help=f"With --output review: postings to hand to reviewers (1-{MAX_TOP_K}).",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json", "review"],
        default="text",
        help="text/json report, or review = packet JSON for the LLM rerank step.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--merge-reviews",
        type=str,
        help="Reviewer verdicts (JSON array file); merges them with --packet into the final report.",
    )
    parser.add_argument(
        "--packet",
        type=str,
        help="Review packet produced earlier by --output review (used with --merge-reviews).",
    )
    return parser


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"无法读取 {path}：{exc}") from exc


def _read_json(path: str, what: str) -> Any:
    try:
        return json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{what} JSON 无法解析：{exc}") from exc


def _read_query(args: argparse.Namespace, profile: Dict[str, Any] | None) -> str:
    if args.query:
        return args.query.strip()
    if args.query_file:
        return _read_text(args.query_file).strip()
    if profile is not None:
        return str(profile.get("raw_query") or "")
    raise ValueError("必须提供 query、--query-file 或 --profile-json。")


def _dump(data: Any, pretty: bool) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2 if pretty else None))


def _merge(args: argparse.Namespace) -> int:
    if not args.packet:
        raise ValueError("--merge-reviews 需要同时提供 --packet。")
    packet = _read_json(args.packet, "评审包")
    if not isinstance(packet, dict) or not isinstance(packet.get("jobs"), list):
        raise ValueError("评审包格式不正确：缺少 jobs 数组。")
    merged = merge_reviews(packet, _read_json(args.merge_reviews, "评审结果"))
    if args.output == "json":
        _dump(merged, args.pretty)
    else:
        print(format_reviewed_report(packet.get("profile") or {}, merged))
    return 0


def _run(args: argparse.Namespace) -> int:
    profile = load_profile_json(_read_text(args.profile_json)) if args.profile_json else None
    query = _read_query(args, profile)

    if args.output == "review":
        result = prepare_review(query, top_k=args.top_k, config_path=args.config, profile=profile)
        _dump(result["packet"] if result.get("ok") else result, args.pretty)
        return 0 if result.get("ok") else 1
    if args.output == "json":
        payload = run_job_finder(query, top_n=args.top_n, config_path=args.config, profile=profile)
        _dump(payload, args.pretty)
        return 0 if payload.get("ok", False) else 1

    print(job_finder(query, top_n=args.top_n, config_path=args.config, profile=profile))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return _merge(args) if args.merge_reviews else _run(args)
    except ValueError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
