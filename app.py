import streamlit as st
import pandas as pd
import zipfile
import time
from io import BytesIO

st.set_page_config(page_title="CSV 多文件批量提取器", layout="wide")
st.title("📁 CSV 多文件批量提取工具（支持大文件、采样提取、历史保存）")

# ---------- 侧边栏：功能设置 ----------
st.sidebar.header("⚙️ 功能设置")
enable_sampling = st.sidebar.checkbox("启用间隔采样", value=False)
sample_interval = 10
if enable_sampling:
    sample_interval = st.sidebar.number_input("采样间隔（行数）", min_value=1, value=10)

pack_zip = st.sidebar.checkbox("将所有结果打包为 ZIP 下载", value=True)

# ---------- 主界面 ----------
st.markdown("### 第一步：上传 CSV 文件")
st.caption("💡 大文件（如 200MB）上传时浏览器可能需要几十秒，请留意浏览器底部的上传进度，不要关闭页面。")

uploaded_files = st.file_uploader(
    "点击上传一个或多个 CSV 文件",
    type=["csv"],
    accept_multiple_files=True,
    key="file_uploader"
)

# ---------- 上传成功提示 ----------
if uploaded_files and "upload_success_shown" not in st.session_state:
    st.session_state.upload_success_shown = True
    total_size_mb = sum(len(f.getvalue()) / (1024 * 1024) for f in uploaded_files)
    st.toast(f"✅ 上传成功！已接收 {len(uploaded_files)} 个文件，总大小 {total_size_mb:.2f} MB", icon="✅")
    # 可选：播放一个短暂的庆祝音效（仅本地有效，云端可能无声，但无害）
    # st.balloons()

# 重置上传成功标记（当文件列表变化时）
if not uploaded_files and "upload_success_shown" in st.session_state:
    del st.session_state.upload_success_shown

if uploaded_files:
    file_sizes = [len(f.getvalue()) for f in uploaded_files]
    total_size_bytes = sum(file_sizes)
    total_size_mb = total_size_bytes / (1024 * 1024)
    st.info(f"📦 已加载 {len(uploaded_files)} 个文件，总大小约 {total_size_mb:.2f} MB")

    # 预览第一个文件
    first_file = uploaded_files[0]
    first_file.seek(0)
    try:
        df_preview = pd.read_csv(first_file, nrows=100)
    except Exception as e:
        st.error(f"预览失败：{e}")
        st.stop()

    st.subheader("📊 数据预览（第一个文件的前100行）")
    st.dataframe(df_preview, use_container_width=True)

    all_columns = df_preview.columns.tolist()
    st.write(f"共有 {len(all_columns)} 列")

    st.subheader("🔧 第二步：选择要保留的列")
    if "selected_cols" not in st.session_state:
        st.session_state.selected_cols = all_columns[: min(3, len(all_columns))]

    selected_cols = st.multiselect(
        "勾选需要保留的列",
        options=all_columns,
        default=st.session_state.selected_cols
    )
    st.session_state.selected_cols = selected_cols

    # ---------- 处理按钮 ----------
    if st.button("🚀 开始批量提取", type="primary"):
        if not selected_cols:
            st.warning("请至少选择一列！")
        else:
            if "history" not in st.session_state:
                st.session_state.history = []

            extracted_files = []

            with st.status("正在处理文件...", expanded=True) as status:
                progress_bar = st.progress(0, text="初始化...")
                percent_text = st.empty()

                processed_bytes = 0
                total_files = len(uploaded_files)

                for idx, uploaded_file in enumerate(uploaded_files):
                    file_name = uploaded_file.name
                    file_size = file_sizes[idx]

                    status.update(label=f"⏳ 正在处理 {file_name} ({idx+1}/{total_files})")

                    try:
                        uploaded_file.seek(0)
                        output_chunks = []
                        total_rows = 0
                        chunk_size = 50000

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

                            current_pos = uploaded_file.tell()
                            file_progress = current_pos / file_size if file_size > 0 else 1.0
                            global_progress = (processed_bytes + current_pos) / total_size_bytes

                            progress_bar.progress(
                                min(global_progress, 1.0),
                                text=f"📄 {file_name} - 已读取 {total_rows:,} 行"
                            )
                            percent_text.markdown(f"**当前文件完成度：{int(file_progress * 100)}%**")

                        processed_bytes += file_size

                        if output_chunks:
                            result_df = pd.concat(output_chunks, ignore_index=True)
                        else:
                            result_df = pd.DataFrame(columns=selected_cols)

                        csv_buffer = BytesIO()
                        result_df.to_csv(csv_buffer, index=False)
                        extracted_data = csv_buffer.getvalue()

                        extracted_mb = len(extracted_data) / (1024 * 1024)
                        extracted_rows = len(result_df)

                        out_name = f"extracted_{file_name}"
                        extracted_files.append((out_name, extracted_data, extracted_mb, extracted_rows))

                        time.sleep(0.2)  # 让进度条停留片刻

                    except Exception as e:
                        st.error(f"❌ 处理 {file_name} 出错：{e}")
                        processed_bytes += file_size
                        continue

                progress_bar.progress(1.0, text="✅ 所有文件处理完成！")
                percent_text.markdown("**完成度：100%**")
                status.update(label="✅ 处理完成", state="complete")
                time.sleep(0.5)

            st.success(f"✅ 批量提取完成！共处理 {total_files} 个文件。")
            st.balloons()  # 庆祝动画

            # ---------- 结果展示 ----------
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
                    if st.button("💾 保存", key=f"save_{fname}"):
                        st.session_state.history.append({
                            "name": fname, "data": fdata,
                            "size_mb": fmbs, "rows": frows
                        })
                        st.toast(f"已保存 {fname}")

            if pack_zip and len(extracted_files) > 1:
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for fname, fdata, _, _ in extracted_files:
                        zf.writestr(fname, fdata)
                st.download_button(
                    label="📦 下载 ZIP 压缩包",
                    data=zip_buffer.getvalue(),
                    file_name="extracted_all.zip",
                    mime="application/zip"
                )

            # 自动保存历史
            for fname, fdata, fmbs, frows in extracted_files:
                st.session_state.history.append({
                    "name": fname, "data": fdata, "size_mb": fmbs, "rows": frows
                })

# ---------- 历史记录侧边栏 ----------
st.sidebar.header("📂 已保存的文件历史")
if "history" not in st.session_state:
    st.session_state.history = []

if st.session_state.history:
    for i, item in enumerate(reversed(st.session_state.history)):
        idx = len(st.session_state.history) - 1 - i
        with st.sidebar.expander(f"{item['name']} ({item['size_mb']:.2f} MB)"):
            st.write(f"行数：{item['rows']:,}")
            st.download_button("⬇️ 下载", data=item['data'],
                               file_name=item['name'], key=f"hist_dl_{idx}")
            if st.button("🗑️ 删除", key=f"hist_del_{idx}"):
                del st.session_state.history[idx]
                st.rerun()
    if st.sidebar.button("清空历史"):
        st.session_state.history = []
        st.rerun()
else:
    st.sidebar.write("暂无保存的文件。")