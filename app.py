import streamlit as st
import pandas as pd
import zipfile
import os
from io import BytesIO

st.set_page_config(page_title="CSV 列提取器", layout="wide")
st.title("📁 CSV 列提取工具（稳定缓存版）")

# ---------- 缓存函数：读取上传文件内容并解压 ----------
@st.cache_data(show_spinner=False)
def load_uploaded_files(uploaded_files):
    """
    处理上传的文件，返回两个字典：
    - file_data: {文件名: {"data": bytes, "size_mb": float}}
    - csv_names: 所有提取出的 CSV 文件名列表
    """
    file_data = {}
    csv_names = []
    
    for f in uploaded_files:
        fname_lower = f.name.lower()
        if fname_lower.endswith('.csv'):
            data = f.getvalue()
            file_data[f.name] = {
                "data": data,
                "size_mb": len(data) / (1024 * 1024)
            }
            csv_names.append(f.name)
            
        elif fname_lower.endswith('.zip'):
            try:
                with zipfile.ZipFile(BytesIO(f.getvalue())) as zf:
                    # 过滤出 CSV 文件（排除 macOS 系统文件）
                    entries = []
                    for name in zf.namelist():
                        if name.startswith('__MACOSX/') or name.startswith('._'):
                            continue
                        if name.lower().endswith('.csv'):
                            entries.append((name, os.path.basename(name)))
                    
                    # 硬上限 100 个，防止极端情况
                    for arc_name, base_name in entries[:100]:
                        data = zf.read(arc_name)
                        # 处理重名（添加序号）
                        final_name = base_name
                        counter = 1
                        while final_name in file_data:
                            stem, ext = os.path.splitext(base_name)
                            final_name = f"{stem}_{counter}{ext}"
                            counter += 1
                        file_data[final_name] = {
                            "data": data,
                            "size_mb": len(data) / (1024 * 1024)
                        }
                        csv_names.append(final_name)
            except Exception as e:
                st.error(f"解压 {f.name} 失败：{e}")
                
    return file_data, csv_names

# ---------- 缓存函数：获取文件预览（前 50 行）----------
@st.cache_data(show_spinner=False)
def get_preview(file_bytes, sample_interval=0):
    """返回预览用的 DataFrame 和列名列表"""
    try:
        if sample_interval > 0:
            # 读取足够多行以保证采样后仍有内容
            df = pd.read_csv(BytesIO(file_bytes), nrows=sample_interval * 50, engine='c')
            df = df.iloc[::sample_interval].head(50)
        else:
            df = pd.read_csv(BytesIO(file_bytes), nrows=50, engine='c')
        return df, df.columns.tolist()
    except Exception as e:
        st.error(f"预览失败：{e}")
        return None, []

# ---------- 处理全量数据（无缓存，因为每次选择的列可能不同）----------
def process_full_data(file_bytes, selected_cols, chunk_size, sample_interval, progress_callback=None):
    """分块处理全量数据，返回结果 DataFrame"""
    chunks = []
    total_rows = 0
    try:
        chunk_iter = pd.read_csv(
            BytesIO(file_bytes),
            usecols=selected_cols,
            chunksize=chunk_size,
            on_bad_lines='skip',
            encoding='utf-8',
            engine='c'
        )
        for chunk in chunk_iter:
            if sample_interval > 0:
                chunk = chunk.iloc[::sample_interval]
            total_rows += len(chunk)
            chunks.append(chunk)
            if progress_callback:
                progress_callback(total_rows)
        if chunks:
            return pd.concat(chunks, ignore_index=True), total_rows
        else:
            return pd.DataFrame(columns=selected_cols), 0
    except Exception as e:
        st.error(f"处理失败：{e}")
        return None, 0

# ---------- 侧边栏设置 ----------
st.sidebar.header("📊 采样设置")
enable_sampling = st.sidebar.checkbox("启用间隔采样", value=False)
sample_interval = 10
if enable_sampling:
    sample_interval = st.sidebar.number_input("采样间隔（行数）", min_value=1, value=10)

chunk_size = st.sidebar.number_input(
    "分块读取行数", min_value=5000, max_value=100000, value=30000, step=5000,
    help="每次读取的行数，大文件可调小节省内存。"
)

# ---------- 主界面：上传文件 ----------
st.markdown("### 第一步：上传 CSV 或 ZIP 压缩包")
uploaded_files = st.file_uploader(
    "支持 .csv 和 .zip（可多选）",
    type=["csv", "zip"],
    accept_multiple_files=True,
    key="uploader"
)

if uploaded_files:
    # 使用缓存加载文件（同一个文件不会重复解压）
    with st.spinner("正在处理上传文件..."):
        file_data, csv_names = load_uploaded_files(uploaded_files)
    
    if not csv_names:
        st.warning("未找到有效的 CSV 文件。")
    else:
        # 保存到 session_state 以便后续使用（但实际处理仍从缓存读取）
        st.session_state.file_data = file_data
        st.session_state.current_files = csv_names
        
        # 显示已加载文件信息
        total_size = sum(info["size_mb"] for info in file_data.values())
        st.success(f"✅ 已加载 {len(csv_names)} 个文件，总大小 {total_size:.2f} MB")
        
        # 文件预览（每个文件一个折叠卡片）
        st.subheader("📄 文件预览（前 50 行）")
        preview_interval = sample_interval if enable_sampling else 0
        for idx, fname in enumerate(csv_names):
            file_bytes = file_data[fname]["data"]
            size_mb = file_data[fname]["size_mb"]
            with st.expander(f"📄 {fname} ({size_mb:.2f} MB)", expanded=(idx == 0)):
                df_preview, cols = get_preview(file_bytes, preview_interval)
                if df_preview is not None:
                    st.dataframe(df_preview, width='stretch')
                    st.caption(f"共 {len(cols)} 列")
        
        # 列选择（基于第一个文件）
        first_file = csv_names[0]
        _, all_columns = get_preview(file_data[first_file]["data"], 0)
        if all_columns:
            st.subheader("🔧 选择要保留的列（应用于所有文件）")
            if "selected_cols" not in st.session_state:
                st.session_state.selected_cols = all_columns[: min(3, len(all_columns))]
            selected_cols = st.multiselect(
                "勾选需要保留的列",
                options=all_columns,
                default=st.session_state.selected_cols
            )
            st.session_state.selected_cols = selected_cols
            
            # ---------- 云端全量处理 ----------
            st.markdown("### 第二步：云端全量提取")
            if st.button("☁️ 开始云端提取", type="primary"):
                if not selected_cols:
                    st.warning("请至少选择一列。")
                else:
                    results = []
                    progress_bar = st.progress(0, "准备处理...")
                    status_text = st.empty()
                    
                    for idx, fname in enumerate(csv_names):
                        status_text.text(f"正在处理 {fname} ...")
                        file_bytes = file_data[fname]["data"]
                        
                        # 定义进度回调
                        def update_progress(rows_read):
                            prog = min((idx + rows_read / 100000) / len(csv_names), 0.99)
                            progress_bar.progress(prog, f"{fname} 已读 {rows_read} 行")
                        
                        df, rows = process_full_data(
                            file_bytes,
                            selected_cols,
                            chunk_size,
                            sample_interval if enable_sampling else 0,
                            progress_callback=update_progress
                        )
                        
                        if df is not None:
                            buf = BytesIO()
                            df.to_csv(buf, index=False)
                            data = buf.getvalue()
                            results.append({
                                "name": f"extracted_{fname}",
                                "data": data,
                                "size_mb": len(data) / (1024 * 1024),
                                "rows": rows
                            })
                    
                    progress_bar.progress(1.0, "完成")
                    status_text.empty()
                    
                    if results:
                        st.success("✅ 提取完成！")
                        st.subheader("📦 下载结果")
                        for item in results:
                            col1, col2 = st.columns([3, 1])
                            col1.write(f"📄 {item['name']}  |  {item['rows']:,} 行  |  {item['size_mb']:.2f} MB")
                            col2.download_button("⬇️ 下载", data=item['data'], file_name=item['name'], key=item['name'])
                    else:
                        st.warning("没有成功处理的文件。")

# ---------- 侧边栏：提取历史（可选，保留简洁版）----------
st.sidebar.header("📂 提取历史")
if "extract_history" not in st.session_state:
    st.session_state.extract_history = []
# 这里可以保留历史功能，但为简化代码先省略，有需要再加。