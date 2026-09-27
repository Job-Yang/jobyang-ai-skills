#!/usr/bin/env python3
"""为设计罗盘原型提供静态预览与本地评审意见持久化。

用法：
  python3 review_server.py --root <prototype目录> --port 8833

接口：
  GET   /api/health
  GET   /api/comments
  POST  /api/comments
  PATCH /api/comments/<id>
  GET   /api/workflow
  PATCH /api/workflow

评审意见和关卡状态默认写入 <prototype目录>/review-data/。
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


SCHEMA = "design-review-comments/v1"
WORKFLOW_SCHEMA = "design-review-workflow/v1"
LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def empty_store() -> dict:
    return {
        "schema": SCHEMA,
        "updated_at": now_iso(),
        "comments": [],
    }


def empty_workflow() -> dict:
    return {
        "schema": WORKFLOW_SCHEMA,
        "updatedAt": now_iso(),
        "projectId": "",
        "activeStageId": "",
        "stages": {},
        "selections": {},
    }


class ReviewHandler(SimpleHTTPRequestHandler):
    server_version = "DesignReviewServer/1.0"

    def __init__(
        self,
        *args,
        directory: str,
        data_file: Path,
        workflow_file: Path,
        **kwargs,
    ):
        self.data_file = data_file
        self.workflow_file = workflow_file
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return value

    def _load_store(self) -> dict:
        if not self.data_file.exists():
            return empty_store()
        try:
            value = json.loads(self.data_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return empty_store()
        if not isinstance(value, dict) or not isinstance(value.get("comments"), list):
            return empty_store()
        value["schema"] = SCHEMA
        return value

    def _save_store(self, store: dict) -> None:
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        store["schema"] = SCHEMA
        store["updated_at"] = now_iso()
        temp = self.data_file.with_suffix(self.data_file.suffix + ".tmp")
        temp.write_text(
            json.dumps(store, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, self.data_file)

    def _load_workflow(self) -> dict:
        if not self.workflow_file.exists():
            return empty_workflow()
        try:
            value = json.loads(self.workflow_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return empty_workflow()
        if not isinstance(value, dict):
            return empty_workflow()
        value["schema"] = WORKFLOW_SCHEMA
        value.setdefault("stages", {})
        value.setdefault("selections", {})
        return value

    def _save_workflow(self, workflow: dict) -> None:
        self.workflow_file.parent.mkdir(parents=True, exist_ok=True)
        workflow["schema"] = WORKFLOW_SCHEMA
        workflow["updatedAt"] = now_iso()
        temp = self.workflow_file.with_suffix(self.workflow_file.suffix + ".tmp")
        temp.write_text(
            json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, self.workflow_file)

    def _api_path(self) -> str:
        return unquote(urlparse(self.path).path)

    def do_GET(self) -> None:  # noqa: N802
        path = self._api_path()
        if path == "/api/health":
            self._send_json(
                {
                    "status": "ok",
                    "schema": SCHEMA,
                    "data_file": str(self.data_file),
                    "workflow_schema": WORKFLOW_SCHEMA,
                    "workflow_file": str(self.workflow_file),
                }
            )
            return
        if path == "/api/comments":
            with LOCK:
                self._send_json(self._load_store())
            return
        if path == "/api/workflow":
            with LOCK:
                self._send_json(self._load_workflow())
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self._api_path() != "/api/comments":
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            comment = self._read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json({"error": "invalid_json", "message": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        required = ("id", "projectId", "stageId", "pageId", "anchor", "text")
        missing = [key for key in required if not comment.get(key)]
        if missing:
            self._send_json(
                {"error": "missing_fields", "fields": missing},
                HTTPStatus.BAD_REQUEST,
            )
            return

        comment["status"] = comment.get("status") or "open"
        comment["createdAt"] = comment.get("createdAt") or now_iso()
        comment["updatedAt"] = now_iso()

        with LOCK:
            store = self._load_store()
            if any(item.get("id") == comment["id"] for item in store["comments"]):
                self._send_json({"error": "duplicate_id"}, HTTPStatus.CONFLICT)
                return
            store["comments"].append(comment)
            self._save_store(store)
        self._send_json(comment, HTTPStatus.CREATED)

    def do_PATCH(self) -> None:  # noqa: N802
        path = self._api_path()
        if path == "/api/workflow":
            try:
                workflow = self._read_json()
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json(
                    {"error": "invalid_json", "message": str(error)},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            stages = workflow.get("stages", {})
            selections = workflow.get("selections", {})
            if not isinstance(stages, dict) or not isinstance(selections, dict):
                self._send_json(
                    {"error": "invalid_workflow"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            with LOCK:
                stored = self._load_workflow()
                stored.update(workflow)
                stored["stages"] = stages
                stored["selections"] = selections
                self._save_workflow(stored)
            self._send_json(stored)
            return

        prefix = "/api/comments/"
        if not path.startswith(prefix):
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        comment_id = path[len(prefix):]
        try:
            patch = self._read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json({"error": "invalid_json", "message": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        allowed = {"status", "text", "severity", "reply"}
        patch = {key: value for key, value in patch.items() if key in allowed}
        patch["updatedAt"] = now_iso()

        with LOCK:
            store = self._load_store()
            updated = None
            for item in store["comments"]:
                if item.get("id") == comment_id:
                    item.update(patch)
                    updated = item
                    break
            if updated is None:
                self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            self._save_store(store)
        self._send_json(updated)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, PATCH, OPTIONS")
        self.end_headers()

    def log_message(self, format_string: str, *args) -> None:
        print(f"[review-server] {self.address_string()} {format_string % args}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="原型目录")
    parser.add_argument("--port", type=int, default=8833)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--data", help="评审意见 JSON 路径")
    parser.add_argument("--workflow-data", help="关卡状态与方案选择 JSON 路径")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"[review-server] 原型目录不存在：{root}")
    data_file = (
        Path(args.data).expanduser().resolve()
        if args.data
        else root / "review-data" / "comments.json"
    )
    workflow_file = (
        Path(args.workflow_data).expanduser().resolve()
        if args.workflow_data
        else root / "review-data" / "workflow.json"
    )

    def handler(*handler_args, **handler_kwargs):
        return ReviewHandler(
            *handler_args,
            directory=str(root),
            data_file=data_file,
            workflow_file=workflow_file,
            **handler_kwargs,
        )

    server = ThreadingHTTPServer((args.bind, args.port), handler)
    print(f"[review-server] root={root}")
    print(f"[review-server] comments={data_file}")
    print(f"[review-server] workflow={workflow_file}")
    print(f"[review-server] url=http://{args.bind}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
