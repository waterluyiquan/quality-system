from __future__ import annotations

from pathlib import Path
from datetime import datetime

import streamlit as st

from fill_form import batch_fill_folder, fill_excel, iter_excel_files, pending_excel_files, reset_batch_manifest
from ingest import SUPPORTED_EXTENSIONS, get_collection, ingest_folder
from rag import answer_question, check_llm_connection, format_source
from settings import ensure_folder, load_settings, save_settings


st.set_page_config(page_title="资料问答与自动填表", layout="wide")

settings = load_settings()
settings_signature = tuple(settings[key] for key in ("source_dir", "export_dir", "db_dir"))
if st.session_state.get("settings_signature") != settings_signature:
    st.session_state.source_dir_input = settings["source_dir"]
    st.session_state.export_dir_input = settings["export_dir"]
    st.session_state.db_dir_input = settings["db_dir"]
    st.session_state.settings_signature = settings_signature


def select_folder(initial_dir: str) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=initial_dir or ".")
        root.destroy()
        return selected
    except Exception as exc:
        st.warning(f"无法打开文件夹选择窗口：{exc}")
        return ""


with st.sidebar:
    st.header("文件夹设置")
    source_dir_input = st.text_input("原始资料库文件夹", key="source_dir_input")
    if st.button("选择原始资料库文件夹", use_container_width=True):
        selected = select_folder(st.session_state.source_dir_input)
        if selected:
            settings["source_dir"] = selected
            save_settings(settings)
            st.rerun()
    export_dir_input = st.text_input("转换结果文件夹", key="export_dir_input")
    if st.button("选择转换结果文件夹", use_container_width=True):
        selected = select_folder(st.session_state.export_dir_input)
        if selected:
            settings["export_dir"] = selected
            save_settings(settings)
            st.rerun()
    db_dir_input = st.text_input("索引数据库文件夹", key="db_dir_input")
    if st.button("保存文件夹设置", use_container_width=True):
        settings = {
            "source_dir": st.session_state.source_dir_input.strip() or "docs",
            "export_dir": st.session_state.export_dir_input.strip() or "exports",
            "db_dir": st.session_state.db_dir_input.strip() or "db",
        }
        save_settings(settings)
        st.success("已保存。")
        st.rerun()
    st.caption("可以填写绝对路径，例如 C:\\\\Users\\\\water\\\\Desktop\\\\资料库。")

    st.divider()
    if st.button("检测 DeepSeek 连接", use_container_width=True):
        ok, message = check_llm_connection()
        if ok:
            st.success(message)
        else:
            st.error(message)

DOCS_DIR = ensure_folder(settings["source_dir"])
EXPORTS_DIR = ensure_folder(settings["export_dir"])
DB_DIR = ensure_folder(settings["db_dir"])


def collection_count() -> int:
    try:
        return get_collection(reset=False, db_dir=DB_DIR).count()
    except Exception:
        return 0


st.title("资料问答与自动填表")
st.caption("本地资料入库、可追溯问答、Excel 文字自动填表")

tab_library, tab_query, tab_form = st.tabs(["资料库", "手动查询", "自动填表"])

with tab_library:
    st.subheader("资料库")
    uploaded_docs = st.file_uploader(
        "上传资料文件",
        type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
        accept_multiple_files=True,
    )
    if uploaded_docs:
        for uploaded in uploaded_docs:
            (DOCS_DIR / uploaded.name).write_bytes(uploaded.getbuffer())
        st.success(f"已保存 {len(uploaded_docs)} 个文件到 {DOCS_DIR}。")

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("已入库 chunk", collection_count())
    col_b.metric("资料文件数", len([path for path in DOCS_DIR.rglob("*") if path.is_file()]))
    col_c.metric("结果文件数", len([path for path in EXPORTS_DIR.rglob("*") if path.is_file()]))
    rebuild = col_d.button("重建索引", type="primary", use_container_width=True)
    if rebuild:
        with st.spinner("正在解析资料并写入向量库..."):
            count = ingest_folder(DOCS_DIR, reset=True, db_dir=DB_DIR)
        st.success(f"入库完成，共 {count} 个 chunk。")

    st.divider()
    st.write("批量处理")
    excel_files = iter_excel_files(DOCS_DIR)
    pending_files = pending_excel_files(DOCS_DIR, EXPORTS_DIR)
    st.caption(f"发现 {len(excel_files)} 个 Excel 文件，待处理 {len(pending_files)} 个。批量转换会跳过已经处理过的文件。")
    batch_col_a, batch_col_b, batch_col_c = st.columns(3)
    max_files = batch_col_a.number_input("本次最多转换文件数", min_value=1, max_value=max(len(pending_files), 1), value=min(30, max(len(pending_files), 1)))
    max_fields = batch_col_b.number_input("每个文件最多填写字段数", min_value=1, max_value=300, value=30)
    batch_overwrite = batch_col_c.checkbox("批量覆盖已有值", value=False)

    batch_col_d, batch_col_e, batch_col_f = st.columns(3)
    rebuild_only = batch_col_d.button("只重建索引", type="primary", use_container_width=True)
    batch_convert = batch_col_e.button("批量转换 Excel", type="primary", use_container_width=True)
    reset_history = batch_col_f.button("清空批处理记录", use_container_width=True)

    if rebuild_only:
        with st.spinner("正在重建索引..."):
            count = ingest_folder(DOCS_DIR, reset=True, db_dir=DB_DIR)
        st.success(f"入库完成，共 {count} 个 chunk。")

    if reset_history:
        reset_batch_manifest(EXPORTS_DIR)
        st.success("已清空批处理记录。下次批量转换会从头开始。")
        st.rerun()

    if batch_convert:
        progress = st.progress(0, text="准备批量转换...")
        current_file = st.empty()
        total = min(int(max_files), len(pending_files))

        def update_progress(index, file_total, path):
            percent = index / file_total if file_total else 1
            progress.progress(percent, text=f"正在转换 {index}/{file_total}: {path.name}")
            current_file.caption(str(path))

        with st.spinner("正在批量转换 Excel..."):
            batch_rows = batch_fill_folder(
                DOCS_DIR,
                EXPORTS_DIR,
                mode="auto",
                overwrite=batch_overwrite,
                max_files=int(max_files),
                max_fields_per_file=int(max_fields),
                skip_done=True,
                progress_callback=update_progress,
            )
        progress.progress(1.0, text=f"批量转换完成：{total}/{total}")
        if batch_rows:
            st.dataframe(batch_rows, use_container_width=True)
            done = len([row for row in batch_rows if row["状态"] == "完成"])
            skipped = len([row for row in batch_rows if row["状态"] == "跳过"])
            failed = len([row for row in batch_rows if row["状态"] == "失败"])
            st.info(f"批量转换结束：完成 {done} 个，跳过 {skipped} 个，失败 {failed} 个。")
        else:
            st.warning("没有找到可转换的 Excel 文件。")

    st.divider()
    st.write("当前资料文件")
    files = sorted(path.relative_to(DOCS_DIR) for path in DOCS_DIR.rglob("*") if path.is_file())
    if files:
        st.dataframe([{"文件": str(path)} for path in files], use_container_width=True)
    else:
        st.info("请先上传或放入 PDF、Excel、Word、TXT、Markdown 文件。")

with tab_query:
    st.subheader("手动查询")
    question = st.text_area("问题", height=100, placeholder="例如：设备验收标准是什么？")
    top_k = st.slider("检索条数", 1, 10, 5)
    if st.button("查询", type="primary") and question.strip():
        with st.spinner("正在检索资料..."):
            answer, hits = answer_question(question.strip(), top_k=top_k)
        st.markdown("#### 答案")
        st.write(answer)
        st.markdown("#### 来源")
        for index, hit in enumerate(hits, start=1):
            with st.expander(f"来源 {index}: {format_source(hit['metadata'])}"):
                st.write(hit["text"])

with tab_form:
    st.subheader("自动填表")
    form_mode = st.radio(
        "字段映射规则",
        options=["auto", "fixed"],
        format_func=lambda value: "自动识别复杂模板" if value == "auto" else "固定模板：第一列字段、第二列填写",
        horizontal=True,
    )
    overwrite = st.checkbox("覆盖已有填写值", value=False)
    template = st.file_uploader("上传待填写 Excel", type=["xlsx", "xlsm"])
    if template and st.button("执行填表", type="primary"):
        with st.spinner("正在逐字段检索并填表..."):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"filled_{timestamp}_{template.name}"
            output_path = EXPORTS_DIR / output_name
            output_bytes, rows = fill_excel(template, output_path=output_path, mode=form_mode, overwrite=overwrite)
        st.success(f"填表完成，已保存到：{output_path}")
        if rows:
            st.dataframe(rows, use_container_width=True)
        st.download_button(
            "下载填表结果",
            data=output_bytes,
            file_name=output_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.divider()
    st.write("最近转换结果")
    exports = sorted(
        [path for path in EXPORTS_DIR.rglob("*.xls*") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:10]
    if exports:
        st.dataframe(
            [{"文件": path.name, "路径": str(path)} for path in exports],
            use_container_width=True,
        )
    else:
        st.info("还没有转换结果。")
