import streamlit as st
import pandas as pd
import zipfile
import gzip
import time
import os
from io import BytesIO

st.set_page_config(page_title="CSV 多文件批量提取器", layout="wide")
st.title("📁 CSV 多文件批量提取工具（支持压缩包上传、大文件优化）")

# ---------- 初始化会话状态 ----------
if "uploaded_library" not in st.session_state:
    st.session_state.uploaded_library = {}
if "current_files" not in st.session_state:
    st.session_state.current_files = []
if "history" not in st.session_state:
    st.session_state.history = []

# ---------- 侧边栏：功能设置 ----------
st.sidebar.header("⚙️ 功能设置")
enable_sampling = st.sidebar.checkbox("启用间隔采样", value=False)
sample_interval = 10
if enable_sampling:
    sample_interval = st.sidebar.number_input("采样间隔（行数）", min_value=1, value=10)

chunk_size = st.sidebar.number_input(
    "分块读取行数（大文件建议减小）",
    min_value=1000, max_value=100000, value=30000, step=5000,
    help="每次读取的行数，内存不足或处理卡顿时请调低此值"
)
pack_zip = st.sidebar.checkbox("将所有结果打包为 ZIP 下载", value=True)

# ---------- 辅助函数：解压上传的文件 ----------
def extract_csv_from_upload(uploaded_file):
    file_name = uploaded_file.name.lower()
    extracted_files = []
    try:
        if file_name.endswith('.csv'):
            extracted_files.append((uploaded_file.name, BytesIO(uploaded_file.getvalue())))
        elif file_name.endswith('.zip'):
            with zipfile.ZipFile(BytesIO(uploaded_file.getvalue())) as zf:
                for name in zf.namelist():
                    if name.lower().endswith('.csv'):
                        data = zf.read(name)
                        extracted_files.append((os.path.basename(name), BytesIO(data)))
        elif file_name.endswith('.gz'):
            with gzip.GzipFile(fileobj=BytesIO(uploaded_file.getvalue())) as gz:
                content = gz.read()
                base = uploaded_file.name[:-3] if uploaded_file.name.endswith('.gz') else uploaded_file.name
                if not base.endswith('.csv'):
                    base += '.csv'
                extracted_files.append((base, BytesIO(content)))
        else:
            st.warning(f"不支持的文件类型：{uploaded_file.name}")
    except Exception as e:
        st.error(f"解压文件 {uploaded_file.name} 失败：{e}")
    return extracted_files

# ---------- 侧边栏：已上传文件库 ----------
st.sidebar.header("📤 已上传文件库")
if st.session_state.uploaded_library:
    for fname, info in list(st.session_state.uploaded_library.items()):
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
        st.session_state.uploaded_library.clear()
        st.session_state.current_files.clear()
        st.rerun()
else:
    st.sidebar.caption("暂无已保存的文件。")

# ---------- 主界面：上传 ----------
st.markdown("### 第一步：上传 CSV 或压缩包（支持 .zip / .gz）")
st.caption("💡 推荐压缩后上传。文件会自动保存到左侧库中，处理大文件请耐心等待。")

uploaded_files = st.file_uploader(
    "点击选择文件（可多选）",
    type=["csv", "zip", "gz"],
    accept_multiple_files=True,
    key="file_uploader"
)

if uploaded_files:
    new_files = []
    for f in uploaded_files:
        if f.name in st.session_state.uploaded_library:
            continue
        with st.status(f"正在处理 {f.name} ...", expanded=True) as upload_status:
            progress_bar = st.progress(0, text="接收文件中...")
            for p in range(0, 101, 25):
                time.sleep(0.05)
                progress_bar.progress(p, text=f"处理进度 {p}%")
            
            extracted = extract_csv_from_upload(f)
            for csv_name, csv_io in extracted:
                data_bytes = csv_io.getvalue()
                size_mb = len(data_bytes) / (1024 * 1024)
                st.session_state.uploaded_library[csv_name] = {
                    "data": data_bytes,
                    "size_mb": size_mb
                }
                new_files.append(csv_name)
                st.toast(f"✅ {csv_name} 已保存 ({size_mb:.1f} MB)")
            progress_bar.progress(100, text="完成！")
            upload_status.update(label=f"✅ {f.name} 处理完成", state="complete")
    if new_files:
        st.session_state.current_files.extend(new_files)
        st.rerun()

# ---------- 显示当前工作区文件 ----------
if st.session_state.current_files:
    st.markdown("### 📂 当前工作区文件")
    work_files = []
    for fname in st.session_state.current_files:
        info = st.session_state.uploaded_library.get(fname)
        if info:
            file_obj = BytesIO(info["data"])
            file_obj.name = fname
            work_files.append((file_obj, info["size_mb"]))
        else:
            st.session_state.current_files.remove(fname)
    
    if work_files:
        total_size_mb = sum(sz for _, sz in work_files)
        st.info(f"已加载 {len(work_files)} 个文件，总大小约 {total_size_mb:.2f} MB")
        
        # ---------- 预览 ----------
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
        try:
            df_first = pd.read_csv(first_file_obj, nrows=0)
            all_columns = df_first.columns.tolist()
        except Exception as e:
            st.error(f"读取列名失败：{e}")
            st.stop()
        
        st.subheader("🔧 第二步：选择要保留的列")
        if "selected_cols" not in st.session_state:
            st.session_state.selected_cols = all_columns[: min(3, len(all_columns))]
        selected_cols = st.multiselect(
            "勾选需要保留的列（应用于所有文件）",
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
                total_bytes = sum(len(info["data"]) for info in st.session_state.uploaded_library.values())
                
                with st.status("正在处理文件...", expanded=True) as status_container:
                    progress_bar = st.progress(0, text="总进度 0%")
                    file_status_placeholders = [st.empty() for _ in work_files]
                    for i, (fobj, _) in enumerate(work_files):
                        file_status_placeholders[i].markdown(f"⏳ **{fobj.name}** - 等待处理")
                    
                    processed_bytes = 0
                    
                    for idx, (file_obj, _) in enumerate(work_files):
                        file_name = file_obj.name
                        file_size = len(st.session_state.uploaded_library[file_name]["data"])
                        
                        file_status_placeholders[idx].markdown(f"⏳ **{file_name}** - 处理中 (0%)")
                        
                        try:
                            file_obj.seek(0)
                            output_chunks = []
                            total_rows = 0
                            
                            # 使用 chunksize，并捕获解析错误
                            chunk_iter = pd.read_csv(
                                file_obj,
                                usecols=selected_cols,
                                chunksize=chunk_size,
                                on_bad_lines='warn',  # 跳过损坏行
                                encoding='utf-8',
                                engine='python'  # Python引擎更宽容
                            )
                            
                            # 限制最大迭代次数防止死循环（每文件最多处理500万行，可根据需要调整）
                            max_iterations = 5000000 // chunk_size + 10
                            iter_count = 0
                            
                            for chunk in chunk_iter:
                                iter_count += 1
                                if iter_count > max_iterations:
                                    st.warning(f"文件 {file_name} 行数过多，已中断处理。请尝试采样或减小文件。")
                                    break
                                    
                                if enable_sampling:
                                    chunk = chunk.iloc[::sample_interval]
                                total_rows += len(chunk)
                                output_chunks.append(chunk)
                                
                                # 基于已处理字节估算进度（使用行数估算百分比）
                                # 避免使用不稳定的 tell()
                                approx_progress = min(iter_count * chunk_size / 10000, 0.99)  # 粗糙估计，到99%后直接跳到100%
                                global_progress = (processed_bytes + file_size * approx_progress) / total_bytes
                                progress_bar.progress(min(global_progress, 1.0), text=f"总进度 {int(global_progress*100)}%")
                                file_status_placeholders[idx].markdown(
                                    f"⏳ **{file_name}** - 已读取 {total_rows:,} 行 (~{int(approx_progress*100)}%)"
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
                            st.error(f"❌ 处理 {file_name} 出错：{str(e)[:200]}")
                            file_status_placeholders[idx].markdown(f"❌ **{file_name}** - 处理失败")
                            processed_bytes += file_size
                            continue
                    
                    progress_bar.progress(1.0, text="总进度 100%")
                    status_container.update(label="✅ 所有文件处理完成", state="complete")
                
                st.success(f"✅ 批量提取完成！共处理 {total_files} 个文件。")
                st.balloons()
                
                # ---------- 结果展示 ----------
                st.subheader("📦 提取结果")
                for fname, fdata, fmbs, frows in extracted_files:
                    col1, col2, col3 = st.columns([4, 1, 1])
                    with col1:
                        st.write(f"📄 {fname}  |  {frows:,} 行  |  {fmbs:.2f} MB")
                    with col2:
                        st.download_button(label="⬇️ 下载", data=fdata, file_name=fname, mime="text/csv", key=f"dl_{fname}")
                    with col3:
                        if st.button("💾 保存", key=f"save_{fname}"):
                            st.session_state.history.append({"name": fname, "data": fdata, "size_mb": fmbs, "rows": frows})
                            st.toast(f"已保存 {fname}")
                
                if pack_zip and len(extracted_files) > 1:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        for fname, fdata, _, _ in extracted_files:
                            zf.writestr(fname, fdata)
                    st.download_button(label="📦 下载 ZIP 压缩包", data=zip_buffer.getvalue(), file_name="extracted_all.zip", mime="application/zip")
                
                for fname, fdata, fmbs, frows in extracted_files:
                    st.session_state.history.append({"name": fname, "data": fdata, "size_mb": fmbs, "rows": frows})

# ---------- 侧边栏：提取历史 ----------
st.sidebar.header("📂 提取历史记录")
if st.session_state.history:
    for i, item in enumerate(reversed(st.session_state.history)):
        idx = len(st.session_state.history) - 1 - i
        with st.sidebar.expander(f"{item['name']} ({item['size_mb']:.2f} MB)"):
            st.write(f"行数：{item['rows']:,}")
            st.download_button("⬇️ 下载", data=item['data'], file_name=item['name'], key=f"hist_dl_{idx}")
            if st.button("🗑️ 删除", key=f"hist_del_{idx}"):
                del st.session_state.history[idx]
                st.rerun()
    if st.sidebar.button("清空提取历史"):
        st.session_state.history.clear()
        st.rerun()
else:
    st.sidebar.write("暂无提取记录。")