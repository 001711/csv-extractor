import streamlit as st
import pandas as pd
import zipfile
from io import BytesIO

st.set_page_config(page_title="CSV 多文件批量提取器", layout="wide")
st.title("📁 CSV 多文件批量提取工具（支持大文件、采样提取、历史保存）")

# ---------- 侧边栏：功能设置 ----------
st.sidebar.header("⚙️ 功能设置")
enable_sampling = st.sidebar.checkbox("启用间隔采样", value=False, help="每隔N行提取一行，减少数据量")
sample_interval = 10
if enable_sampling:
    sample_interval = st.sidebar.number_input("采样间隔（行数）", min_value=1, value=10, step=1)

pack_zip = st.sidebar.checkbox("将所有结果打包为 ZIP 下载", value=True)

# ---------- 主界面：多文件上传 ----------
uploaded_files = st.file_uploader(
    "点击上传一个或多个 CSV 文件",
    type=["csv"],
    accept_multiple_files=True
)

if uploaded_files:
    # 计算总大小
    file_sizes = [len(f.getvalue()) for f in uploaded_files]
    total_size_bytes = sum(file_sizes)
    total_size_mb = total_size_bytes / (1024 * 1024)
    st.info(f"已上传 {len(uploaded_files)} 个文件，总大小约 {total_size_mb:.2f} MB")
    if total_size_mb > 100:
        st.warning("📢 大文件处理需要较长时间，请耐心等待，不要关闭页面。")

    # 读取第一个文件的前100行用于列选择和预览
    first_file = uploaded_files[0]
    first_file.seek(0)
    try:
        df_preview = pd.read_csv(first_file, nrows=100)
    except Exception as e:
        st.error(f"读取文件 {first_file.name} 失败：{e}")
        st.stop()

    st.subheader("📊 数据预览（基于第一个文件的前 100 行）")
    st.dataframe(df_preview, use_container_width=True)

    all_columns = df_preview.columns.tolist()
    st.write(f"文件共有 {len(all_columns)} 列")

    st.subheader("🔧 选择要保留的列（应用于所有文件）")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("全选所有列"):
            st.session_state.selected_cols = all_columns
    with col2:
        if st.button("清空选择"):
            st.session_state.selected_cols = []
    if "selected_cols" not in st.session_state:
        st.session_state.selected_cols = all_columns[: min(3, len(all_columns))]

    selected_cols = st.multiselect(
        "勾选需要保留的列（可多选、搜索）",
        options=all_columns,
        default=st.session_state.selected_cols
    )
    st.session_state.selected_cols = selected_cols

    # ---------- 批量处理按钮 ----------
    if st.button("🚀 开始批量提取", type="primary"):
        if not selected_cols:
            st.warning("请至少选择一列！")
        else:
            if "history" not in st.session_state:
                st.session_state.history = []

            extracted_files = []
            progress_bar = st.progress(0, text="准备处理...")
            status_text = st.empty()

            # 记录每个文件的已处理字节数
            processed_bytes = 0

            for idx, uploaded_file in enumerate(uploaded_files):
                file_name = uploaded_file.name
                file_size = file_sizes[idx]
                file_size_mb = file_size / (1024 * 1024)

                status_text.text(f"⏳ 正在处理 {file_name} ({file_size_mb:.1f} MB)")

                try:
                    uploaded_file.seek(0)
                    chunk_size = 50000
                    output_chunks = []
                    total_rows = 0

                    chunk_iter = pd.read_csv(
                        uploaded_file,
                        usecols=selected_cols,
                        chunksize=chunk_size
                    )

                    for chunk in chunk_iter:
                        if enable_sampling:
                            chunk = chunk.iloc[::sample_interval]
                        total_rows += len(chunk)
                        output_chunks.append(chunk)

                        # 更新进度：基于当前文件已读取的字节数
                        current_pos = uploaded_file.tell()
                        # 当前文件进度 = 当前文件已读字节数 / 当前文件总大小
                        file_progress = current_pos / file_size if file_size > 0 else 1.0
                        # 全局进度 = (之前文件总字节 + 当前文件已读字节) / 所有文件总字节
                        global_progress = (processed_bytes + current_pos) / total_size_bytes

                        progress_bar.progress(
                            min(global_progress, 1.0),
                            text=f"📄 {file_name} - 已读取约 {total_rows:,} 行 ({int(file_progress * 100)}%)"
                        )

                    # 当前文件处理完成，累加已处理字节数
                    processed_bytes += file_size

                    if output_chunks:
                        result_df = pd.concat(output_chunks, ignore_index=True)
                    else:
                        result_df = pd.DataFrame(columns=selected_cols)

                    csv_buffer = BytesIO()
                    result_df.to_csv(csv_buffer, index=False, encoding='utf-8')
                    extracted_data = csv_buffer.getvalue()

                    extracted_mb = len(extracted_data) / (1024 * 1024)
                    extracted_rows = len(result_df)

                    out_name = f"extracted_{file_name}"
                    extracted_files.append((out_name, extracted_data, extracted_mb, extracted_rows))

                except Exception as e:
                    st.error(f"❌ 处理文件 {file_name} 时出错：{e}")
                    # 即使出错，也要将文件大小计入已处理，避免进度条卡住
                    processed_bytes += file_size
                    continue

            progress_bar.progress(1.0, text="✅ 所有文件处理完成！")
            status_text.empty()
            st.success(f"✅ 批量提取完成！共处理 {len(uploaded_files)} 个文件。")

            # ---------- 展示提取结果 ----------
            st.subheader("📦 提取结果")
            for fname, fdata, fmbs, frows in extracted_files:
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    st.write(f"📄 {fname}  |  {frows:,} 行  |  {fmbs:.2f} MB")
                with col2:
                    st.download_button(
                        label="⬇️ 下载",
                        data=fdata,
                        file_name=fname,
                        mime="text/csv",
                        key=f"dl_{fname}"
                    )
                with col3:
                    if st.button("💾 保存到历史", key=f"save_{fname}"):
                        st.session_state.history.append({
                            "name": fname,
                            "data": fdata,
                            "size_mb": fmbs,
                            "rows": frows
                        })
                        st.toast(f"已保存 {fname} 到历史记录")

            # ---------- 打包 ZIP 下载 ----------
            if pack_zip and len(extracted_files) > 1:
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for fname, fdata, _, _ in extracted_files:
                        zf.writestr(fname, fdata)
                zip_data = zip_buffer.getvalue()
                st.download_button(
                    label="📦 下载所有文件（ZIP 压缩包）",
                    data=zip_data,
                    file_name="extracted_all.zip",
                    mime="application/zip"
                )

            # 自动保存到历史
            for fname, fdata, fmbs, frows in extracted_files:
                st.session_state.history.append({
                    "name": fname,
                    "data": fdata,
                    "size_mb": fmbs,
                    "rows": frows
                })

# ---------- 侧边栏：历史记录管理 ----------
st.sidebar.header("📂 已保存的文件历史")
if "history" not in st.session_state:
    st.session_state.history = []

if st.session_state.history:
    for i, item in enumerate(reversed(st.session_state.history)):
        idx = len(st.session_state.history) - 1 - i
        with st.sidebar.expander(f"{item['name']} ({item['size_mb']:.2f} MB)", expanded=False):
            st.write(f"行数：{item['rows']:,}")
            st.download_button(
                label="⬇️ 下载",
                data=item['data'],
                file_name=item['name'],
                mime="text/csv",
                key=f"hist_dl_{idx}"
            )
            if st.button("🗑️ 删除", key=f"hist_del_{idx}"):
                del st.session_state.history[idx]
                st.rerun()
    if st.sidebar.button("清空所有历史"):
        st.session_state.history = []
        st.rerun()
else:
    st.sidebar.write("暂无保存的文件。")