import streamlit as st
import pandas as pd
import tempfile
import os
from io import BytesIO

st.set_page_config(page_title="CSV 智能提取器", layout="wide")
st.title("📁 CSV 智能提取工具（支持大文件、采样提取）")

# ---------- 侧边栏：功能开关 ----------
st.sidebar.header("⚙️ 功能设置")
enable_sampling = st.sidebar.checkbox("启用间隔采样", value=False, help="每隔N行提取一行，减少数据量")
sample_interval = 10
if enable_sampling:
    sample_interval = st.sidebar.number_input("采样间隔（行数）", min_value=1, value=10, step=1)

# ---------- 主界面 ----------
uploaded_file = st.file_uploader("点击上传 CSV 文件", type=["csv"])

if uploaded_file is not None:
    file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
    st.info(f"文件名：{uploaded_file.name}  |  大小：{file_size_mb:.2f} MB")

    # 重置指针并预览前100行
    uploaded_file.seek(0)
    df_preview = pd.read_csv(uploaded_file, nrows=100)
    st.subheader("📊 数据预览（前 100 行）")
    st.dataframe(df_preview, use_container_width=True)

    all_columns = df_preview.columns.tolist()
    st.write(f"文件共有 {len(all_columns)} 列")

    st.subheader("🔧 选择要保留的列")
    selected_cols = st.multiselect(
        "勾选你需要保留的列（可多选、搜索）",
        options=all_columns,
        default=all_columns[: min(3, len(all_columns))]
    )

    # ---------- 提取按钮 ----------
    if st.button("🚀 开始提取并下载", type="primary"):
        if not selected_cols:
            st.warning("请至少选择一列！")
        else:
            with st.spinner("正在处理大文件，请稍候..."):
                uploaded_file.seek(0)

                # 分块读取设置
                chunk_size = 50000
                first_chunk = True
                total_rows = 0
                output_chunks = []

                # 创建分块迭代器（直接指定 usecols 减少内存）
                chunk_iter = pd.read_csv(
                    uploaded_file,
                    usecols=selected_cols,
                    chunksize=chunk_size
                )

                # 逐块处理
                for chunk in chunk_iter:
                    # 如果需要采样，则在当前块内应用间隔提取
                    if enable_sampling:
                        # 保留每隔 sample_interval 行的数据（注意：每个块独立计数，这里用全局行号会更准）
                        # 简单实现：在当前块内每隔 interval 取一行
                        chunk = chunk.iloc[::sample_interval]

                    total_rows += len(chunk)
                    output_chunks.append(chunk)

                # 合并所有处理后的块（此时数据量已大幅减少，合并安全）
                if output_chunks:
                    result_df = pd.concat(output_chunks, ignore_index=True)
                else:
                    result_df = pd.DataFrame(columns=selected_cols)

                # 转换为 CSV 字节流
                csv_buffer = BytesIO()
                result_df.to_csv(csv_buffer, index=False, encoding='utf-8')
                extracted_data = csv_buffer.getvalue()

                extracted_mb = len(extracted_data) / (1024 * 1024)
                st.success(f"✅ 提取完成！共处理 {total_rows:,} 行，采样后剩余 {len(result_df):,} 行，新文件大小约 {extracted_mb:.2f} MB")

                # 下载按钮
                st.download_button(
                    label="⬇️ 点击下载提取后的 CSV 文件",
                    data=extracted_data,
                    file_name=f"extracted_{uploaded_file.name}",
                    mime="text/csv"
                )

                # ---------- 可选：保存到会话历史（模拟“上传保存”功能）----------
                if "history" not in st.session_state:
                    st.session_state.history = []
                st.session_state.history.append({
                    "name": f"extracted_{uploaded_file.name}",
                    "data": extracted_data,
                    "size_mb": extracted_mb,
                    "rows": len(result_df)
                })

# ---------- 侧边栏：历史记录管理（上传保存功能）----------
st.sidebar.header("📂 已保存的文件")
if "history" not in st.session_state:
    st.session_state.history = []

if st.session_state.history:
    for i, item in enumerate(st.session_state.history):
        col1, col2 = st.sidebar.columns([3, 1])
        with col1:
            st.write(f"📄 {item['name']} ({item['size_mb']:.2f} MB, {item['rows']} 行)")
        with col2:
            # 提供再次下载的按钮
            st.download_button(
                label="⬇️",
                data=item['data'],
                file_name=item['name'],
                mime="text/csv",
                key=f"download_{i}"
            )
    if st.sidebar.button("清空历史记录"):
        st.session_state.history = []
        st.rerun()
else:
    st.sidebar.write("暂无保存的文件，提取后会自动出现在这里。")