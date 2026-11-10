"""Launch live evaluation with BigModel's documented free GLM-4.7-Flash.

No OpenAI key is needed. Credentials are passed only to a child process.
Provider policy and account rate limits still apply; see README for sources.
"""
import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="智谱 GLM-4.7-Flash 免费模型真实验收入口")
    parser.add_argument("--cases", nargs="+", default=["normal", "slot_conflict", "missing_metadata", "rule_risk", "duplicate", "save_failure", "changed_occupancy", "supplement_recovery", "confirmed_alternative", "read_failure"])
    args = parser.parse_args()
    key = os.environ.get("BIGMODEL_API_KEY", "").strip()
    if not key:
        key = getpass.getpass("BigModel API Key (hidden; not saved): ").strip()
    if not key:
        print("未输入智谱 API Key，未发出请求。", file=sys.stderr)
        return 2
    env = os.environ.copy()
    # The existing adapter's legacy variable name does not imply an OpenAI key.
    # Never fall back to a pre-existing OpenAI credential for another provider.
    env["OPENAI_API_KEY"] = key
    env["AGENT_BASE_URL"] = "https://open.bigmodel.cn/api/paas/v4"
    env["AGENT_MODEL"] = "glm-4.7-flash"
    print("Provider: BigModel | Model: glm-4.7-flash | Mode: live", flush=True)
    return subprocess.call([sys.executable, str(ROOT / "scripts/evaluate.py"), "--mode", "live", "--cases", *args.cases], cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
