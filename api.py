from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from fill_form import batch_fill_folder, fill_excel, pending_excel_files, reset_batch_manifest
from ingest import get_collection, ingest_folder
from rag import answer_question, check_llm_connection, format_source, search
from settings import ensure_folder, load_settings, save_settings


app = FastAPI(title="Quality System Knowledge API", version="1.0")

task_lock = Lock()
task_state: dict[str, Any] = {
    "running": False,
    "task": "",
    "started_at": "",
    "finished_at": "",
    "progress": 0,
    "message": "idle",
    "result": None,
    "error": "",
}


class SettingsPayload(BaseModel):
    source_dir: str | None = None
    export_dir: str | None = None
    db_dir: str | None = None


class QueryPayload(BaseModel):
    q: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)


class IngestPayload(BaseModel):
    source_dir: str | None = None
    db_dir: str | None = None
    reset: bool = True
    background: bool = True


class FillPathPayload(BaseModel):
    template_path: str
    output_path: str | None = None
    mode: Literal["auto", "fixed"] = "auto"
    overwrite: bool = False
    max_fields: int | None = Field(30, ge=1, le=500)


class BatchFillPayload(BaseModel):
    source_dir: str | None = None
    export_dir: str | None = None
    mode: Literal["auto", "fixed"] = "auto"
    overwrite: bool = False
    max_files: int = Field(30, ge=1, le=500)
    max_fields_per_file: int = Field(30, ge=1, le=500)
    skip_done: bool = True
    background: bool = True


def current_settings() -> dict[str, str]:
    settings = load_settings()
    for key in ("source_dir", "export_dir", "db_dir"):
        ensure_folder(settings[key])
    return settings


def set_task(task: str, message: str, progress: int = 0) -> None:
    with task_lock:
        task_state.update(
            {
                "running": True,
                "task": task,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": "",
                "progress": progress,
                "message": message,
                "result": None,
                "error": "",
            }
        )


def update_task(message: str, progress: int | None = None, result: Any = None) -> None:
    with task_lock:
        task_state["message"] = message
        if progress is not None:
            task_state["progress"] = progress
        if result is not None:
            task_state["result"] = result


def finish_task(result: Any = None, error: str = "") -> None:
    with task_lock:
        task_state.update(
            {
                "running": False,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "progress": 100 if not error else task_state.get("progress", 0),
                "result": result,
                "error": error,
                "message": "failed" if error else "done",
            }
        )


def reject_if_running() -> None:
    if task_state.get("running"):
        raise HTTPException(status_code=409, detail="已有后台任务正在运行，请先调用 /status 查看进度。")


def resolve_output_path(input_name: str, export_dir: str, output_path: str | None = None) -> Path:
    if output_path:
        path = Path(output_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(export_dir) / f"filled_{timestamp}_{Path(input_name).with_suffix('.xlsx').name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def run_ingest(source_dir: str, db_dir: str, reset: bool) -> None:
    try:
        set_task("ingest", f"正在入库：{source_dir}", 1)
        count = ingest_folder(source_dir, reset=reset, db_dir=db_dir)
        finish_task({"chunks": count, "source_dir": source_dir, "db_dir": db_dir})
    except Exception as exc:
        finish_task(error=str(exc))


def run_batch_fill(payload: BatchFillPayload, settings: dict[str, str]) -> None:
    source_dir = payload.source_dir or settings["source_dir"]
    export_dir = payload.export_dir or settings["export_dir"]
    try:
        set_task("batch_fill", f"准备批量转换：{source_dir}", 1)

        def on_progress(index: int, total: int, path: Path) -> None:
            progress = int(index / total * 100) if total else 100
            update_task(f"正在转换 {index}/{total}: {path.name}", progress)

        rows = batch_fill_folder(
            source_dir,
            export_dir,
            mode=payload.mode,
            overwrite=payload.overwrite,
            max_files=payload.max_files,
            max_fields_per_file=payload.max_fields_per_file,
            skip_done=payload.skip_done,
            progress_callback=on_progress,
        )
        finish_task({"rows": rows, "count": len(rows), "source_dir": source_dir, "export_dir": export_dir})
    except Exception as exc:
        finish_task(error=str(exc))


@app.get("/health")
def health() -> dict[str, Any]:
    ok, message = check_llm_connection()
    settings = current_settings()
    collection_count = 0
    try:
        collection_count = get_collection(reset=False, db_dir=settings["db_dir"]).count()
    except Exception:
        pass
    return {"ok": True, "llm_ok": ok, "llm_message": message, "settings": settings, "chunks": collection_count}


@app.get("/status")
def status() -> dict[str, Any]:
    return dict(task_state)


@app.get("/settings")
def get_settings() -> dict[str, str]:
    return current_settings()


@app.post("/settings")
def update_settings(payload: SettingsPayload) -> dict[str, str]:
    settings = load_settings()
    if payload.source_dir:
        settings["source_dir"] = payload.source_dir
    if payload.export_dir:
        settings["export_dir"] = payload.export_dir
    if payload.db_dir:
        settings["db_dir"] = payload.db_dir
    for value in settings.values():
        ensure_folder(value)
    save_settings(settings)
    return settings


@app.post("/query")
def query(payload: QueryPayload) -> dict[str, Any]:
    answer, hits = answer_question(payload.q, top_k=payload.top_k)
    return {
        "answer_text": answer,
        "sources": [
            {"source": format_source(hit["metadata"]), "metadata": hit["metadata"], "text": hit["text"], "distance": hit.get("distance")}
            for hit in hits
        ],
    }


@app.post("/search")
def semantic_search(payload: QueryPayload) -> dict[str, Any]:
    hits = search(payload.q, top_k=payload.top_k)
    return {"hits": hits}


@app.post("/ingest")
def ingest(payload: IngestPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    reject_if_running()
    settings = current_settings()
    source_dir = payload.source_dir or settings["source_dir"]
    db_dir = payload.db_dir or settings["db_dir"]
    if payload.background:
        background_tasks.add_task(run_ingest, source_dir, db_dir, payload.reset)
        return {"status": "started", "task": "ingest", "source_dir": source_dir, "db_dir": db_dir}
    count = ingest_folder(source_dir, reset=payload.reset, db_dir=db_dir)
    return {"status": "done", "chunks": count, "source_dir": source_dir, "db_dir": db_dir}


@app.post("/fill-excel")
def fill_excel_by_path(payload: FillPathPayload) -> dict[str, Any]:
    settings = current_settings()
    template_path = Path(payload.template_path)
    if not template_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在：{template_path}")
    output_path = resolve_output_path(template_path.name, settings["export_dir"], payload.output_path)
    _, rows = fill_excel(
        template_path,
        output_path=output_path,
        mode=payload.mode,
        overwrite=payload.overwrite,
        max_fields=payload.max_fields,
    )
    return {"status": "done", "output_path": str(output_path), "rows": rows, "filled_count": len(rows)}


@app.post("/fill-excel-upload")
async def fill_excel_upload(
    file: UploadFile = File(...),
    mode: Literal["auto", "fixed"] = "auto",
    overwrite: bool = False,
    max_fields: int = 30,
) -> dict[str, Any]:
    settings = current_settings()
    upload_dir = ensure_folder(Path(settings["export_dir"]) / "_api_uploads")
    input_path = upload_dir / file.filename
    input_path.write_bytes(await file.read())
    output_path = resolve_output_path(file.filename, settings["export_dir"])
    _, rows = fill_excel(input_path, output_path=output_path, mode=mode, overwrite=overwrite, max_fields=max_fields)
    return {"status": "done", "input_path": str(input_path), "output_path": str(output_path), "rows": rows, "filled_count": len(rows)}


@app.post("/batch-fill")
def batch_fill(payload: BatchFillPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    reject_if_running()
    settings = current_settings()
    if payload.background:
        background_tasks.add_task(run_batch_fill, payload, settings)
        return {"status": "started", "task": "batch_fill", "max_files": payload.max_files}
    rows = batch_fill_folder(
        payload.source_dir or settings["source_dir"],
        payload.export_dir or settings["export_dir"],
        mode=payload.mode,
        overwrite=payload.overwrite,
        max_files=payload.max_files,
        max_fields_per_file=payload.max_fields_per_file,
        skip_done=payload.skip_done,
    )
    return {"status": "done", "rows": rows, "count": len(rows)}


@app.get("/batch-pending")
def batch_pending() -> dict[str, Any]:
    settings = current_settings()
    files = pending_excel_files(Path(settings["source_dir"]), Path(settings["export_dir"]))
    return {"count": len(files), "files": [str(path) for path in files[:200]]}


@app.post("/batch-reset")
def batch_reset() -> dict[str, str]:
    settings = current_settings()
    reset_batch_manifest(settings["export_dir"])
    return {"status": "done", "message": "批处理记录已清空"}


@app.get("/download")
def download(path: str):
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在：{path}")
    return FileResponse(file_path, filename=file_path.name)
