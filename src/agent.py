import time
import sqlite3
from datetime import datetime, timezone

from .domain import validate_request
from .tools import Tools, ToolError


def run(req, world, db, model, max_steps=10, max_tools=8):
    started = time.monotonic()
    provider_start = len(getattr(model, "events", []))
    trace = []
    output = {"request": req, "mode": model.mode, "model": model.name, "started_at": datetime.now(timezone.utc).isoformat(), "status": "incomplete", "review_status": "not_checked", "risks": [], "suggested_at": None, "pending_items": [], "confirmation_status": "not_checked", "draft": {"saved": False}, "published": False, "trace": trace}
    tools = None
    saved = None
    message = "执行次数达到上限，任务未完成"
    try:
        validate_request(req)
        if not 1 <= max_steps <= 30 or not 1 <= max_tools <= 30:
            raise ValueError("Limits must be between 1 and 30")
        tools = Tools(req, world, db)
        previous = tools.existing()
        if previous:
            saved = {**previous, "duplicate": True, "availability_revalidated": False}
            output["status"] = "completed" if previous["confirmation_status"] == "confirmed" else "needs_confirmation"
            output["review_status"] = "previously_passed_not_revalidated"
            message = "返回同一历史草稿；未重新校验当前时段或规则，可用性需复核"
            trace.append({"event": "idempotent_replay", "result": saved})
        else:
            calls = 0
            for step in range(1, max_steps + 1):
                try:
                    decision = model.decide(req, trace)
                except Exception as exc:
                    output["status"] = "failed"
                    message = "模型调用失败: " + type(exc).__name__ + ": " + str(exc)[:100]
                    # Known provider errors are credential-free; no HTTP response bodies logged.
                    trace.append({"event": "model_error", "error": message})
                    break
                if not isinstance(decision, dict) or not isinstance(decision.get("args"), dict) or not isinstance(decision.get("reason"), str):
                    output["status"] = "failed"
                    message = "模型返回无效动作结构"
                    trace.append({"event": "invalid_decision"})
                    break
                name, args = decision.get("action"), decision["args"]
                if name == "finish":
                    desired = args.get("status")
                    if saved:
                        output["status"] = "completed" if saved["confirmation_status"] == "confirmed" else "needs_confirmation"
                    elif tools.checked and tools.checked["status"] in ("blocked", "needs_info"):
                        output["status"] = tools.checked["status"]
                    elif desired in ("failed", "incomplete", "needs_info"):
                        output["status"] = desired
                    else:
                        output["status"] = "incomplete"
                    # Do not expose a free-form model claim as a trusted save/approval status.
                    message = {"completed": "草稿保存成功，未发布", "needs_confirmation": "建议已保存为待确认草稿，未发布", "blocked": "规则风险阻断，未保存", "needs_info": "资料不足，未保存", "failed": "执行失败，未完成", "incomplete": "任务未完成"}[output["status"]]
                    trace.append({"step": step, "decision": decision, "result": {"ok": True, "data": {"status": output["status"]}}})
                    break
                if calls >= max_tools:
                    message = "工具调用次数达到上限，任务未完成"
                    break
                calls += 1
                try:
                    value = tools.execute(name, args)
                    observation = {"ok": True, "data": value}
                    if name == "save_draft":
                        saved = value
                except (ToolError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                    observation = {"ok": False, "error": "STORAGE_ERROR" if isinstance(exc, sqlite3.Error) else str(exc)}
                trace.append({"step": step, "decision": decision, "result": observation})
            if tools.checked:
                output["review_status"] = tools.checked["status"]
                output["risks"] = tools.checked["risks"]
    except (ValueError, ToolError) as exc:
        output["status"] = "needs_info" if isinstance(exc, ValueError) else "failed"
        message = str(exc)
    except Exception as exc:
        output["status"] = "failed"
        message = "执行失败: " + type(exc).__name__
    if saved:
        output["draft"] = saved
        output["suggested_at"] = saved["suggested_at"]
        output["confirmation_status"] = saved["confirmation_status"]
        if saved["confirmation_status"] != "confirmed":
            output["pending_items"].append("请确认是否将要求时段改为 " + saved["suggested_at"])
    if output["status"] == "needs_info":
        output["pending_items"].append("请补充缺失输入或素材元数据，见 message / risks")
    output["message"] = message
    output["elapsed_seconds"] = round(time.monotonic() - started, 3)
    output["provider_events"] = getattr(model, "events", [])[provider_start:]
    output["draft_count"] = tools.count() if tools else 0
    return output
