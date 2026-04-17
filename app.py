import streamlit as st
import pandas as pd
import zipfile
import os
from io import BytesIO

st.set_page_config(page_title="CSV 列提取器", layout="wide")
st.title("📁 CSV 列提取工具（修复死循环 · 稳定解压）")

# ---------- 初始化会话状态 ----------
if "uploaded_files_data" not in st.session_state:
    st.session_state.uploaded_files_data = {}
if "current_files" not in st.session_state:
    st.session_state.current_files = []
if "extract_history" not in st.session_state:
    st.session_state.extract_history = []
if "preview_sample_interval" not in st.session_state:
    st.session_state.preview_sample_interval = 0

# ---------- 侧边栏：采样设置 ----------
st.sidebar.header("📊 采样设置")
enable_sampling = st.sidebar.checkbox("启用间隔采样", value=False)
sample_interval = 10
if enable_sampling:
    sample_interval = st.sidebar.number_input("采样间隔（行数）", min_value=1, value=10)

if st.sidebar.button("🔄 刷新预览（应用当前采样）"):
    st.session_state.preview_sample_interval = sample_interval if enable_sampling else 0
    st.rerun()

chunk_size = st.sidebar.number_input(
    "分块读取行数", min_value=5000, max_value=100000, value=30000, step=5000,
    help="每次读取的行数，大文件可调小节省内存。"
)

# ---------- 解压安全设置 ----------
MAX_FILES_IN_ZIP = 100  # 硬性上限，防止异常压缩包导致无限循环
st.sidebar.info(f"💡 单个 ZIP 最多解压 {MAX_FILES_IN_ZIP} 个 CSV 文件。")

# ---------- 辅助函数：稳定解压 ----------
def extract_csv_from_zip_safe(zip_file, status_container):
    """
    安全解压 ZIP，强制上限保护，单个文件失败不影响整体。
    返回: (extracted_dict, total_in_zip, extracted_count)
    """
    extracted = {}
    try:
        with zipfile.ZipFile(BytesIO(zip_file.getvalue())) as zf:
            # 1. 获取所有有效 CSV 条目（过滤系统文件）
            entries = []
            for name in zf.namelist():
                if name.startswith('__MACOSX/') or name.startswith('._'):
                    continue
                if name.lower().endswith('.csv'):
                    fname = os.path.basename(name)
                    entries.append((name, fname))
            
            total_in_zip = len(entries)
            if total_in_zip == 0:
                status_container.warning("ZIP 中没有找到 CSV 文件。")
                return {}, 0, 0
            
            # 2. 应用上限
            extract_limit = min(total_in_zip, MAX_FILES_IN_ZIP)
            status_container.info(f"📦 ZIP 中共 {total_in_zip} 个 CSV，将解压前 {extract_limit} 个...")
            progress_bar = st.progress(0, text="准备解压...")
            
            # 用于避免内部重名
            used_names = set()
            success_count = 0
            
            # 3. 逐个解压（绝对有限循环）
            for idx, (arc_name, original_fname) in enumerate(entries[:extract_limit], 1):
                progress_bar.progress(idx / extract_limit, text=f"解压 {idx}/{extract_limit}: {original_fname}")
                try:
                    data = zf.read(arc_name)
                    # 处理重名
                    final_name = original_fname
                    counter = 1
                    while final_name in used_names:
                        base, ext = os.path.splitext(original_fname)
                        final_name = f"{base}_{counter}{ext}"
                        counter += 1
                    used_names.add(final_name)
                    extracted[final_name] = BytesIO(data)
                    success_count += 1
                except Exception as e:
                    st.warning(f"跳过文件 {original_fname}：读取失败 ({str(e)[:50]})")
                    continue
            
            progress_bar.progress(1.0, text="✅ 解压完成")
            if total_in_zip > MAX_FILES_IN_ZIP:
                status_container.success(f"✅ 已解压前 {MAX_FILES_IN_ZIP} 个文件（共 {total_in_zip} 个），达到安全上限自动停止。")
            else:
                status_container.success(f"✅ 成功解压 {success_count} 个 CSV 文件。")
            progress_bar.empty()
            return extracted, total_in_zip, success_count
    except Exception as e:
        status_container.error(f"解压 ZIP 失败：{e}")
        return {}, 0, 0

# ---------- 主界面：上传 ----------
st.markdown("### 第一步：上传 CSV 或 ZIP 压缩包")
uploaded_files = st.file_uploader(
    "支持 .csv 和 .zip（可多选）",
    type=["csv", "zip"],
    accept_multiple_files=True
)

if uploaded_files:
    new_files = []
    for f in uploaded_files:
        fname_lower = f.name.lower()
        if fname_lower.endswith('.csv'):
            data_bytes = f.getvalue()
            size_mb = len(data_bytes) / (1024 * 1024)
            st.session_state.uploaded_files_data[f.name] = {"data": data_bytes, "size_mb": size_mb}
            new_files.append(f.name)
            st.toast(f"✅ {f.name} 已保存 ({size_mb:.1f} MB)")
        elif fname_lower.endswith('.zip'):
            with st.status(f"处理 {f.name} ...", expanded=True) as zip_status:
                extracted_dict, total, success = extract_csv_from_zip_safe(f, zip_status)
                for csv_name, csv_io in extracted_dict.items():
                    data_bytes = csv_io.getvalue()
                    size_mb = len(data_bytes) / (1024 * 1024)
                    st.session_state.uploaded_files_data[csv_name] = {"data": data_bytes, "size_mb": size_mb}
                    new_files.append(csv_name)
                    st.toast(f"✅ {csv_name} 已提取 ({size_mb:.1f} MB)")
                zip_status.update(label=f"✅ {f.name} 完成", state="complete")
    if new_files:
        st.session_state.current_files.extend(new_files)
        st.rerun()

# ---------- 显示工作区 ----------
if st.session_state.current_files:
    work_files = []
    for fname in st.session_state.current_files:
        info = st.session_state.uploaded_files_data.get(fname)
        if info:
            fobj = BytesIO(info["data"])
            fobj.name = fname
            work_files.append((fobj, info["size_mb"]))
        else:
            st.session_state.current_files.remove(fname)

    if work_files:
        total_size = sum(sz for _, sz in work_files)
        st.markdown("### 📂 已加载文件")
        st.info(f"共 {len(work_files)} 个文件，总大小 {total_size:.2f} MB")

        st.subheader("📄 文件预览（前 50 行）")
        preview_interval = st.session_state.preview_sample_interval
        for idx, (fobj, size_mb) in enumerate(work_files):
            with st.expander(f"📄 {fobj.name} ({size_mb:.2f} MB)", expanded=(idx == 0)):
                try:
                    fobj.seek(0)
                    if preview_interval > 0:
                        read_rows = preview_interval * 50
                        df_raw = pd.read_csv(fobj, nrows=read_rows, engine='c')
                        df_preview = df_raw.iloc[::preview_interval].head(50)
                        caption = f"应用采样间隔 {preview_interval}，显示前 {len(df_preview)} 行"
                    else:
                        df_preview = pd.read_csv(fobj, nrows=50, engine='c')
                        caption = f"共 {len(df_preview.columns)} 列，显示前 50 行"
                    st.dataframe(df_preview, width='stretch')
                    st.caption(caption)
                except Exception as e:
                    st.error(f"预览失败：{e}")

        st.markdown("---")
        first_file = work_files[0][0]
        first_file.seek(0)
        try:
            df_first = pd.read_csv(first_file, nrows=0)
            all_columns = df_first.columns.tolist()
        except Exception as e:
            st.error(f"读取列名失败：{e}")
            st.stop()

        st.subheader("🔧 选择要保留的列")
        if "selected_cols" not in st.session_state:
            st.session_state.selected_cols = all_columns[: min(3, len(all_columns))]
        selected_cols = st.multiselect("勾选需要保留的列", options=all_columns, default=st.session_state.selected_cols)
        st.session_state.selected_cols = selected_cols

        # ---------- 云端全量处理 ----------
        st.markdown("### 第二步：云端全量提取")
        if st.button("☁️ 开始云端提取", type="primary"):
            if not selected_cols:
                st.warning("请至少选择一列。")
            else:
                extracted_files = []
                progress_bar = st.progress(0, "准备处理...")
                status_text = st.empty()
                for idx, (fobj, _) in enumerate(work_files):
                    fname = fobj.name
                    status_text.text(f"正在处理 {fname} ...")
                    try:
                        fobj.seek(0)
                        output_chunks = []
                        total_rows = 0
                        chunk_iter = pd.read_csv(fobj, usecols=selected_cols, chunksize=chunk_size,
                                                 on_bad_lines='skip', encoding='utf-8', engine='c')
                        for chunk in chunk_iter:
                            if enable_sampling:
                                chunk = chunk.iloc[::sample_interval]
                            total_rows += len(chunk)
                            output_chunks.append(chunk)
                            prog = min((idx + len(output_chunks) / 20) / len(work_files), 0.99)
                            progress_bar.progress(prog, f"{fname} 已读 {total_rows} 行")
                        if output_chunks:
                            result_df = pd.concat(output_chunks, ignore_index=True)
                        else:
                            result_df = pd.DataFrame(columns=selected_cols)
                        buf = BytesIO()
                        result_df.to_csv(buf, index=False)
                        data = buf.getvalue()
                        file_mb = len(data) / (1024 * 1024)
                        extracted_files.append({"name": f"extracted_{fname}", "data": data,
                                                "size_mb": file_mb, "rows": len(result_df)})
                    except Exception as e:
                        st.error(f"{fname} 处理失败：{str(e)[:200]}")
                progress_bar.progress(1.0, "完成")
                status_text.empty()
                if extracted_files:
                    st.success("✅ 提取完成！")
                    st.subheader("📦 本次结果")
                    for item in extracted_files:
                        col1, col2 = st.columns([3, 1])
                        col1.write(f"📄 {item['name']}  |  {item['rows']:,} 行  |  {item['size_mb']:.2f} MB")
                        col2.download_button("⬇️ 下载", data=item['data'], file_name=item['name'], key=f"dl_{item['name']}")
                        st.session_state.extract_history.append(item)
                else:
                    st.warning("没有成功处理的文件。")

# ---------- 侧边栏：文件库 & 历史 ----------
st.sidebar.header("📤 文件库")
if st.session_state.uploaded_files_data:
    for fname, info in list(st.session_state.uploaded_files_data.items()):
        col1, col2, col3 = st.sidebar.columns([3,1,1])
        col1.write(f"📄 {fname} ({info['size_mb']:.1f} MB)")
        if col2.button("📂", key=f"load_{fname}"):
            if fname not in st.session_state.current_files:
                st.session_state.current_files.append(fname)
            st.rerun()
        if col3.button("🗑️", key=f"del_{fname}"):
            del st.session_state.uploaded_files_data[fname]
            if fname in st.session_state.current_files:
                st.session_state.current_files.remove(fname)
            st.rerun()
    if st.sidebar.button("清空文件库"):
        st.session_state.uploaded_files_data.clear()
        st.session_state.current_files.clear()
        st.rerun()

st.sidebar.header("📂 提取历史")
if st.session_state.extract_history:
    for i, item in enumerate(reversed(st.session_state.extract_history)):
        idx = len(st.session_state.extract_history) - 1 - i
        with st.sidebar.expander(f"{item['name']} ({item['size_mb']:.2f} MB)"):
            st.write(f"行数：{item['rows']:,}")
            st.download_button("⬇️ 下载", data=item['data'], file_name=item['name'], key=f"hist_dl_{idx}")
            if st.button("🗑️ 删除", key=f"hist_del_{idx}"):
                del st.session_state.extract_history[idx]
                st.rerun()
    if st.sidebar.button("清空提取历史"):
        st.session_state.extract_history.clear()
        st.rerun()