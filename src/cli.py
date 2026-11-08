import argparse
import json
from pathlib import Path

from .agent import run
from .model import LiveModel, MockModel


def main():
    parser = argparse.ArgumentParser(description="素材审核与排期草稿 Agent（不发布）")
    parser.add_argument("--input", required=True, help="JSON containing request and world")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--db", default="runtime/drafts.db")
    parser.add_argument("--output")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--max-tools", type=int, default=8)
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        model = LiveModel() if args.mode == "live" else MockModel()
        result = run(data["request"], data["world"], args.db, model, args.max_steps, args.max_tools)
    except Exception as exc:
        result = {"status": "failed", "message": "启动失败: " + type(exc).__name__, "mode": args.mode, "draft": {"saved": False}, "published": False}
    content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8")
    print(content)
    return 0 if result["status"] in ("completed", "needs_confirmation") else 2


if __name__ == "__main__":
    raise SystemExit(main())
