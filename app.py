import streamlit as st
import pandas as pd
import zipfile
import time
from io import BytesIO

st.set_page_config(page_title="CSV 多文件批量提取器", layout="wide")
st.title("📁 CSV 多文件批量提取工具（支持大文件、采样提取、历史保存）")

# ---------- 初始化会话状态 ----------
if "uploaded_library" not in st.session_state:
    st.session_state.uploaded_library = {}  # {文件名: {"data": bytes, "size_mb": float}}
if "current_files" not in st.session_state:
    st.session_state.current_files = []  # 当前工作区的文件列表（名称）
if "history" not in st.session_state:
    st.session_state.history = []  # 提取历史

# ---------- 侧边栏：功能设置 ----------
st.sidebar.header("⚙️ 功能设置")
enable_sampling = st.sidebar.checkbox("启用间隔采样", value=False)
sample_interval = 10
if enable_sampling:
    sample_interval = st.sidebar.number_input("采样间隔（行数）", min_value=1, value=10)
pack_zip = st.sidebar.checkbox("将所有结果打包为 ZIP 下载", value=True)

# ---------- 侧边栏：已上传文件库（保存的地方）----------
st.sidebar.header("📤 已上传文件库")
if st.session_state.uploaded_library:
    for fname, info in st.session_state.uploaded_library.items():
        col1, col2, col3 = st.sidebar.columns([3, 1, 1])
        with col1:
            st.write(f"📄 {fname} ({info['size_mb']:.1f} MB)")
        with col2:
            if st.button("📂", key=f"load_{fname}", help="加载到当前工作区"):
                if fname not in st.session_state.current_files:
                    st.session_state.current_files.append(fname)
                st.rerun()
        with col3:
            if st.button("🗑️", key=f"del_lib_{fname}", help="从库中删除"):
                del st.session_state.uploaded_library[fname]
                if fname in st.session_state.current_files:
                    st.session_state.current_files.remove(fname)
                st.rerun()
    if st.sidebar.button("清空文件库"):
        st.session_state.uploaded_library = {}
        st.session_state.current_files = []
        st.rerun()
else:
    st.sidebar.caption("暂无已保存的文件，上传后会自动保存到这里。")

# ---------- 主界面：第一步 上传文件 ----------
st.markdown("### 第一步：上传 CSV 文件到文件库")
st.caption("上传的文件会自动保存到左侧「已上传文件库」，可随时加载使用。")

uploaded_files = st.file_uploader(
    "点击选择 CSV 文件（可多选）",
    type=["csv"],
    accept_multiple_files=True,
    key="file_uploader"
)

# 处理新上传的文件：保存到库并显示上传进度模拟
if uploaded_files:
    new_files = []
    for f in uploaded_files:
        if f.name not in st.session_state.uploaded_library:
            # 模拟上传进度
            with st.status(f"正在上传 {f.name} ...", expanded=True) as upload_status:
                progress_bar = st.progress(0, text="接收数据中...")
                # 模拟进度增长（实际上文件已在内存，但给用户视觉反馈）
                for percent in range(0, 101, 20):
                    time.sleep(0.1)
                    progress_bar.progress(percent, text=f"上传进度 {percent}%")
                # 保存到库
                data_bytes = f.getvalue()
                size_mb = len(data_bytes) / (1024 * 1024)
                st.session_state.uploaded_library[f.name] = {
                    "data": data_bytes,
                    "size_mb": size_mb
                }
                progress_bar.progress(100, text="上传完成！")
                upload_status.update(label=f"✅ {f.name} 上传成功", state="complete")
                new_files.append(f.name)
                st.toast(f"✅ {f.name} 已保存到文件库")
    if new_files:
        st.session_state.current_files.extend(new_files)
        st.rerun()

# ---------- 显示当前工作区文件 ----------
if st.session_state.current_files:
    st.markdown("### 📂 当前工作区文件")
    # 准备文件数据对象列表
    work_files = []
    for fname in st.session_state.current_files:
        info = st.session_state.uploaded_library.get(fname)
        if info:
            # 从库中取出数据并包装成 BytesIO 对象（模拟上传文件）
            file_obj = BytesIO(info["data"])
            file_obj.name = fname
            work_files.append((file_obj, info["size_mb"]))
        else:
            # 如果库中不存在，从列表中移除
            st.session_state.current_files.remove(fname)

    if work_files:
        total_size_mb = sum(sz for _, sz in work_files)
        st.info(f"已加载 {len(work_files)} 个文件，总大小约 {total_size_mb:.2f} MB")

        # ---------- 文件预览 ----------
        st.subheader("📊 文件预览（每个文件的前 100 行）")
        for idx, (file_obj, size_mb) in enumerate(work_files):
            with st.expander(f"📄 {file_obj.name}  ({size_mb:.2f} MB)", expanded=(idx == 0)):
                try:
                    file_obj.seek(0)
                    df_preview = pd.read_csv(file_obj, nrows=100)
                    st.dataframe(df_preview, use_container_width=True)
                    st.caption(f"共 {len(df_preview.columns)} 列")
                except Exception as e:
                    st.error(f"预览失败：{e}")

        # ---------- 列选择 ----------
        first_file_obj = work_files[0][0]
        first_file_obj.seek(0)
        df_first = pd.read_csv(first_file_obj, nrows=0)
        all_columns = df_first.columns.tolist()

        st.subheader("🔧 第二步：选择要保留的列（应用于所有文件）")
        if "selected_cols" not in st.session_state:
            st.session_state.selected_cols = all_columns[: min(3, len(all_columns))]

        selected_cols = st.multiselect(
            "勾选需要保留的列",
            options=all_columns,
            default=st.session_state.selected_cols
        )
        st.session_state.selected_cols = selected_cols

        # ---------- 批量处理 ----------
        if st.button("🚀 开始批量提取", type="primary"):
            if not selected_cols:
                st.warning("请至少选择一列！")
            else:
                extracted_files = []
                total_files = len(work_files)
                total_bytes = sum(len(info["data"]) for info in st.session_state.uploaded_library.values() if info)

                with st.status("正在处理文件...", expanded=True) as status_container:
                    progress_bar = st.progress(0, text="总进度 0%")
                    file_status_placeholders = [st.empty() for _ in work_files]
                    for i, (file_obj, _) in enumerate(work_files):
                        file_status_placeholders[i].markdown(f"⏳ **{file_obj.name}** - 等待处理")

                    processed_bytes = 0

                    for idx, (file_obj, file_size_mb) in enumerate(work_files):
                        file_name = file_obj.name
                        file_size = len(st.session_state.uploaded_library[file_name]["data"])

                        file_status_placeholders[idx].markdown(f"⏳ **{file_name}** - 处理中 (0%)")

                        try:
                            file_obj.seek(0)
                            output_chunks = []
                            total_rows = 0
                            chunk_size = 50000

                            chunk_iter = pd.read_csv(
                                file_obj,
                                usecols=selected_cols,
                                chunksize=chunk_size
                            )

                            for chunk in chunk_iter:
                                if enable_sampling:
                                    chunk = chunk.iloc[::sample_interval]
                                total_rows += len(chunk)
                                output_chunks.append(chunk)

                                current_pos = file_obj.tell()
                                file_progress = current_pos / file_size if file_size > 0 else 1.0
                                global_progress = (processed_bytes + current_pos) / total_bytes

                                progress_bar.progress(
                                    min(global_progress, 1.0),
                                    text=f"总进度 {int(global_progress * 100)}%"
                                )
                                file_status_placeholders[idx].markdown(
                                    f"⏳ **{file_name}** - 已读取 {total_rows:,} 行 ({int(file_progress * 100)}%)"
                                )

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

                            file_status_placeholders[idx].markdown(
                                f"✅ **{file_name}** - 完成！ {extracted_rows:,} 行，{extracted_mb:.2f} MB"
                            )

                        except Exception as e:
                            st.error(f"❌ 处理 {file_name} 出错：{e}")
                            file_status_placeholders[idx].markdown(f"❌ **{file_name}** - 处理失败")
                            processed_bytes += file_size
                            continue

                    progress_bar.progress(1.0, text="总进度 100%")
                    status_container.update(label="✅ 所有文件处理完成", state="complete")
                    time.sleep(0.5)

                st.success(f"✅ 批量提取完成！共处理 {total_files} 个文件。")
                st.balloons()

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
                        if st.button("💾 保存到历史", key=f"save_{fname}"):
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

                # 自动保存到历史
                for fname, fdata, fmbs, frows in extracted_files:
                    st.session_state.history.append({
                        "name": fname, "data": fdata, "size_mb": fmbs, "rows": frows
                    })

# ---------- 侧边栏：提取历史记录 ----------
st.sidebar.header("📂 提取历史记录")
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
    if st.sidebar.button("清空提取历史"):
        st.session_state.history = []
        st.rerun()
else:
    st.sidebar.write("暂无提取记录。")