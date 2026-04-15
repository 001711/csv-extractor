import streamlit as st
import pandas as pd
import tempfile
import os

# 页面设置
st.set_page_config(page_title="大文件列提取器", layout="wide")
st.title("📁 CSV 列提取工具（支持 190MB+ 大文件）")
st.markdown("上传一个 CSV 文件，选择你要保留的列，然后下载精简后的新文件。")

# 文件上传组件
uploaded_file = st.file_uploader("点击上传 CSV 文件", type=["csv"])

if uploaded_file is not None:
    # 显示文件大小
    file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
    st.info(f"文件名：{uploaded_file.name}，大小：{file_size_mb:.2f} MB")

    # 读取前 100 行用于预览和列选择
    uploaded_file.seek(0)  # 重置文件指针
    df_preview = pd.read_csv(uploaded_file, nrows=100)
    st.subheader("📊 数据预览（前 100 行）")
    st.dataframe(df_preview, use_container_width=True)

    # 获取所有列名
    all_columns = df_preview.columns.tolist()
    st.write(f"文件共有 {len(all_columns)} 列")

    # 多选框选择要保留的列
    st.subheader("🔧 选择要保留的列")
    selected_cols = st.multiselect(
        "勾选你需要保留的列（可多选、搜索）",
        options=all_columns,
        default=all_columns[: min(3, len(all_columns))]  # 默认选前 3 列
    )

    # 提取按钮
    if st.button("🚀 开始提取并下载", type="primary"):
        if not selected_cols:
            st.warning("请至少选择一列！")
        else:
            with st.spinner("正在处理大文件，请稍候... 根据文件大小可能需要几十秒。"):
                # 重置指针，准备分块读取
                uploaded_file.seek(0)

                # 创建临时文件用于流式写入结果
                with tempfile.NamedTemporaryFile(
                    mode="w+", suffix=".csv", delete=False, encoding="utf-8"
                ) as tmp_file:
                    output_path = tmp_file.name
                    first_chunk = True
                    total_rows = 0

                    # 分块读取（每次 5 万行）
                    chunk_iter = pd.read_csv(
                        uploaded_file,
                        usecols=selected_cols,
                        chunksize=50000
                    )

                    # 逐个块追加写入临时文件
                    for chunk in chunk_iter:
                        chunk.to_csv(
                            tmp_file,
                            index=False,
                            header=first_chunk,
                            mode="a"
                        )
                        first_chunk = False
                        total_rows += len(chunk)

                # 读取临时文件内容
                with open(output_path, "rb") as f:
                    extracted_data = f.read()

                # 删除临时文件
                os.unlink(output_path)

                # 计算提取后文件大小
                extracted_mb = len(extracted_data) / (1024 * 1024)

                st.success(f"✅ 提取完成！共处理 {total_rows:,} 行，新文件大小约 {extracted_mb:.2f} MB")

                # 提供下载按钮
                st.download_button(
                    label="⬇️ 点击下载提取后的 CSV 文件",
                    data=extracted_data,
                    file_name=f"extracted_{uploaded_file.name}",
                    mime="text/csv"
                )