import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="CSV 列提取器", layout="wide")
st.title("📁 CSV 列提取工具（多文件预览 + 提取历史保存）")

# ---------- 初始化会话状态 ----------
if "uploaded_files_data" not in st.session_state:
    st.session_state.uploaded_files_data = {}
if "current_files" not in st.session_state:
    st.session_state.current_files = []
if "extract_history" not in st.session_state:
    st.session_state.extract_history = []   # 提取历史列表，每个元素为字典

# ---------- 侧边栏：模式选择 ----------
st.sidebar.header("⚙️ 运行模式")
mode = st.sidebar.radio(
    "选择处理方式",
    ["🚀 推荐：下载本地脚本处理", "☁️ 云端尽力处理 (有行数限制)"],
    help="大文件强烈建议下载脚本到本地运行，无限制、不卡死。"
)

# 采样设置
st.sidebar.header("📊 采样设置")
enable_sampling = st.sidebar.checkbox("启用间隔采样", value=False)
sample_interval = 10
if enable_sampling:
    sample_interval = st.sidebar.number_input("采样间隔（行数）", min_value=1, value=10)

if mode.startswith("☁️"):
    max_rows_limit = st.sidebar.number_input(
        "最大处理行数（防止卡死）",
        min_value=1000, max_value=100000, value=30000, step=5000
    )
    chunk_size = st.sidebar.number_input(
        "分块读取行数", min_value=5000, max_value=50000, value=20000, step=5000
    )
    st.sidebar.warning("⚠️ 云端处理大文件极易超时，仅适合小文件或预览。")

# ---------- 生成本地脚本 ----------
def generate_local_script(selected_columns, sample_interval=0):
    script = f'''"""
CSV 批量列提取工具 - 本地运行版
使用方法：
1. 将此脚本放在与你的 CSV 文件相同的文件夹。
2. 安装依赖：pip install pandas
3. 双击运行或在终端执行：python 此脚本.py
"""

import pandas as pd
from pathlib import Path

SELECTED_COLUMNS = {selected_columns}
SAMPLE_INTERVAL = {sample_interval}
CHUNK_SIZE = 50000

INPUT_FOLDER = Path(__file__).parent
OUTPUT_FOLDER = INPUT_FOLDER / "extracted"

def process_file(file_path):
    output_chunks = []
    total_rows = 0
    try:
        chunk_iter = pd.read_csv(
            file_path,
            usecols=SELECTED_COLUMNS,
            chunksize=CHUNK_SIZE,
            on_bad_lines='skip',
            encoding='utf-8'
        )
        for chunk in chunk_iter:
            if SAMPLE_INTERVAL > 0:
                chunk = chunk.iloc[::SAMPLE_INTERVAL]
            total_rows += len(chunk)
            output_chunks.append(chunk)
        if output_chunks:
            result_df = pd.concat(output_chunks, ignore_index=True)
        else:
            result_df = pd.DataFrame(columns=SELECTED_COLUMNS)
        return result_df, total_rows
    except Exception as e:
        print(f"处理失败 {{file_path.name}}: {{e}}")
        return None, 0

def main():
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    csv_files = list(INPUT_FOLDER.glob("*.csv"))
    if not csv_files:
        print("当前文件夹未找到 CSV 文件。")
        input("按回车键退出...")
        return
    print(f"找到 {{len(csv_files)}} 个 CSV 文件，开始处理...")
    for i, fp in enumerate(csv_files, 1):
        print(f"[{{i}}/{{len(csv_files)}}] 处理 {{fp.name}} ...")
        df, rows = process_file(fp)
        if df is not None:
            out_path = OUTPUT_FOLDER / f"extracted_{{fp.name}}"
            df.to_csv(out_path, index=False, encoding='utf-8')
            size_mb = out_path.stat().st_size / (1024*1024)
            print(f"    完成！提取 {{rows}} 行，大小 {{size_mb:.2f}} MB")
    print(f"\\n所有文件处理完毕！结果保存在: {{OUTPUT_FOLDER.resolve()}}")
    input("按回车键退出...")

if __name__ == "__main__":
    main()
'''
    return script

# ---------- 主界面：上传纯 CSV ----------
st.markdown("### 第一步：上传 CSV 文件（仅支持 .csv）")
uploaded_files = st.file_uploader(
    "点击选择 CSV 文件，可多选",
    type=["csv"],
    accept_multiple_files=True
)

if uploaded_files:
    new_files = []
    for f in uploaded_files:
        if f.name not in st.session_state.uploaded_files_data:
            data_bytes = f.getvalue()
            size_mb = len(data_bytes) / (1024 * 1024)
            st.session_state.uploaded_files_data[f.name] = {
                "data": data_bytes,
                "size_mb": size_mb
            }
            new_files.append(f.name)
            st.toast(f"✅ {f.name} 已保存 ({size_mb:.1f} MB)")
    if new_files:
        st.session_state.current_files.extend(new_files)
        st.rerun()

# ---------- 显示当前已加载文件 ----------
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

        # ---- 多文件直接预览 ----
        st.subheader("📄 文件预览（每个文件前100行，点击展开）")
        for idx, (fobj, size_mb) in enumerate(work_files):
            with st.expander(f"📄 {fobj.name} ({size_mb:.2f} MB)", expanded=(idx == 0)):
                try:
                    fobj.seek(0)
                    df_preview = pd.read_csv(fobj, nrows=100)
                    st.dataframe(df_preview, use_container_width=True)
                    st.caption(f"共 {len(df_preview.columns)} 列，显示前 100 行")
                except Exception as e:
                    st.error(f"预览失败：{e}")

        st.markdown("---")

        # ---- 列选择 ----
        first_file = work_files[0][0]
        first_file.seek(0)
        try:
            df_first = pd.read_csv(first_file, nrows=0)
            all_columns = df_first.columns.tolist()
        except Exception as e:
            st.error(f"读取列名失败：{e}")
            st.stop()

        st.subheader("🔧 选择要保留的列（应用于所有文件）")
        if "selected_cols" not in st.session_state:
            st.session_state.selected_cols = all_columns[: min(3, len(all_columns))]

        selected_cols = st.multiselect(
            "勾选需要保留的列",
            options=all_columns,
            default=st.session_state.selected_cols
        )
        st.session_state.selected_cols = selected_cols

        # ---------- 根据模式显示操作 ----------
        if mode.startswith("🚀"):
            st.markdown("### 第二步：下载本地处理脚本")
            if selected_cols:
                script_content = generate_local_script(
                    selected_cols,
                    sample_interval if enable_sampling else 0
                )
                st.download_button(
                    label="⬇️ 下载本地脚本 (csv_extractor.py)",
                    data=script_content,
                    file_name="csv_extractor.py",
                    mime="text/x-python"
                )
                st.success("✅ 将脚本放在 CSV 文件夹中，双击运行即可（需安装 Python 和 pandas）。")
            else:
                st.warning("请至少选择一列。")

        else:  # 云端模式
            st.markdown("### 第二步：云端处理（有限制）")
            if st.button("☁️ 开始云端提取", type="primary"):
                if not selected_cols:
                    st.warning("请选择列")
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
                            chunk_iter = pd.read_csv(
                                fobj,
                                usecols=selected_cols,
                                chunksize=chunk_size,
                                nrows=max_rows_limit,
                                on_bad_lines='skip',
                                encoding='utf-8'
                            )
                            for chunk in chunk_iter:
                                if enable_sampling:
                                    chunk = chunk.iloc[::sample_interval]
                                total_rows += len(chunk)
                                output_chunks.append(chunk)
                                prog = min((idx + len(output_chunks)/10) / len(work_files), 0.99)
                                progress_bar.progress(prog, f"{fname} 已读 {total_rows} 行")
                            if output_chunks:
                                result_df = pd.concat(output_chunks, ignore_index=True)
                            else:
                                result_df = pd.DataFrame(columns=selected_cols)
                            buf = BytesIO()
                            result_df.to_csv(buf, index=False)
                            data = buf.getvalue()
                            file_mb = len(data) / (1024 * 1024)
                            extracted_files.append({
                                "name": f"extracted_{fname}",
                                "data": data,
                                "size_mb": file_mb,
                                "rows": len(result_df)
                            })
                        except Exception as e:
                            st.error(f"{fname} 处理失败：{str(e)[:200]}")

                    progress_bar.progress(1.0, "完成")
                    status_text.empty()

                    if extracted_files:
                        st.success("✅ 云端提取完成！")
                        st.subheader("📦 本次提取结果")
                        for item in extracted_files:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"📄 {item['name']}  |  {item['rows']:,} 行  |  {item['size_mb']:.2f} MB")
                            with col2:
                                st.download_button(
                                    label="⬇️ 下载",
                                    data=item['data'],
                                    file_name=item['name'],
                                    mime="text/csv",
                                    key=f"dl_{item['name']}"
                                )
                            # 自动保存到提取历史
                            st.session_state.extract_history.append(item)
                            st.toast(f"已保存 {item['name']} 到提取历史")
                    else:
                        st.warning("没有成功处理的文件。")

# ---------- 侧边栏：文件库管理 ----------
st.sidebar.header("📤 文件库")
if st.session_state.uploaded_files_data:
    for fname, info in list(st.session_state.uploaded_files_data.items()):
        col1, col2, col3 = st.sidebar.columns([3, 1, 1])
        with col1:
            st.write(f"📄 {fname} ({info['size_mb']:.1f} MB)")
        with col2:
            if st.button("📂", key=f"load_{fname}", help="加载到工作区"):
                if fname not in st.session_state.current_files:
                    st.session_state.current_files.append(fname)
                st.rerun()
        with col3:
            if st.button("🗑️", key=f"del_{fname}", help="从库中删除"):
                del st.session_state.uploaded_files_data[fname]
                if fname in st.session_state.current_files:
                    st.session_state.current_files.remove(fname)
                st.rerun()
    if st.sidebar.button("清空文件库"):
        st.session_state.uploaded_files_data.clear()
        st.session_state.current_files.clear()
        st.rerun()
else:
    st.sidebar.write("暂无已保存文件。")

# ---------- 侧边栏：提取历史记录 ----------
st.sidebar.header("📂 提取历史")
if st.session_state.extract_history:
    # 倒序显示，最新的在前面
    for i, item in enumerate(reversed(st.session_state.extract_history)):
        idx = len(st.session_state.extract_history) - 1 - i
        with st.sidebar.expander(f"{item['name']} ({item['size_mb']:.2f} MB)"):
            st.write(f"行数：{item['rows']:,}")
            st.download_button(
                label="⬇️ 下载",
                data=item['data'],
                file_name=item['name'],
                mime="text/csv",
                key=f"hist_dl_{idx}"
            )
            if st.button("🗑️ 删除", key=f"hist_del_{idx}"):
                del st.session_state.extract_history[idx]
                st.rerun()
    if st.sidebar.button("清空提取历史"):
        st.session_state.extract_history.clear()
        st.rerun()
else:
    st.sidebar.write("暂无提取记录。")