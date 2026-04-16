import streamlit as st
import pandas as pd
import zipfile
import gzip
import os
from io import BytesIO
import base64

st.set_page_config(page_title="CSV 列提取器 (云端预览+本地运行)", layout="wide")
st.title("📁 CSV 列提取工具（解决大文件卡死，推荐本地运行）")

# ---------- 初始化 ----------
if "uploaded_library" not in st.session_state:
    st.session_state.uploaded_library = {}
if "current_files" not in st.session_state:
    st.session_state.current_files = []
if "history" not in st.session_state:
    st.session_state.history = []

# ---------- 生成可下载的本地处理脚本 ----------
def generate_local_script(selected_columns, sample_interval=0, chunk_size=50000):
    """返回一个完整的 Python 脚本字符串，用户保存为 .py 文件后本地运行"""
    script = f'''"""
CSV 批量列提取工具 - 本地运行版
使用方法：
1. 将此脚本放在与你的 CSV 文件相同的文件夹（或修改下方 input_folder / output_folder 路径）
2. 安装依赖：pip install pandas
3. 运行：python this_script.py
"""

import pandas as pd
import os
from pathlib import Path

# ========== 用户配置 ==========
# 需要保留的列名（已根据你在网页上的选择自动生成）
SELECTED_COLUMNS = {selected_columns}

# 采样间隔，0 表示不采样，例如 10 表示每隔 10 行取一行
SAMPLE_INTERVAL = {sample_interval}

# 分块读取大小（行数），大文件可适当调小以节省内存
CHUNK_SIZE = {chunk_size}

# 输入文件夹（默认为脚本所在目录，可修改为具体路径）
INPUT_FOLDER = Path(__file__).parent

# 输出文件夹（提取后的文件将保存在这里）
OUTPUT_FOLDER = INPUT_FOLDER / "extracted"
# ==============================

def process_file(file_path):
    """处理单个 CSV 文件"""
    output_chunks = []
    total_rows = 0
    try:
        chunk_iter = pd.read_csv(
            file_path,
            usecols=SELECTED_COLUMNS,
            chunksize=CHUNK_SIZE,
            on_bad_lines='skip',  # 跳过损坏行
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
        print(f"处理文件 {{file_path.name}} 失败: {{e}}")
        return None, 0

def main():
    # 创建输出目录
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    
    # 获取所有 CSV 文件
    csv_files = list(INPUT_FOLDER.glob("*.csv"))
    if not csv_files:
        print("当前文件夹未找到 CSV 文件，请将脚本放在 CSV 文件所在目录，或修改 INPUT_FOLDER。")
        input("按回车键退出...")
        return
    
    print(f"找到 {{len(csv_files)}} 个 CSV 文件，开始处理...")
    for i, file_path in enumerate(csv_files, 1):
        print(f"[{{i}}/{{len(csv_files)}}] 处理 {{file_path.name}} ...")
        df, rows = process_file(file_path)
        if df is not None:
            out_path = OUTPUT_FOLDER / f"extracted_{{file_path.name}}"
            df.to_csv(out_path, index=False, encoding='utf-8')
            size_mb = out_path.stat().st_size / (1024*1024)
            print(f"    完成！提取 {{rows}} 行，输出大小 {{size_mb:.2f}} MB")
    
    print(f"\\n所有文件处理完毕！提取结果保存在: {{OUTPUT_FOLDER.resolve()}}")
    input("按回车键退出...")

if __name__ == "__main__":
    main()
'''
    return script

# ---------- 侧边栏：功能设置 ----------
st.sidebar.header("⚙️ 运行模式")
mode = st.sidebar.radio(
    "选择处理方式",
    ["🚀 推荐：下载本地脚本处理", "☁️ 云端尽力处理 (有行数限制)"],
    help="大文件强烈建议下载脚本到本地运行，速度快、无限制。"
)

# 采样设置（两种模式共用）
st.sidebar.header("📊 采样设置")
enable_sampling = st.sidebar.checkbox("启用间隔采样", value=False)
sample_interval = 10
if enable_sampling:
    sample_interval = st.sidebar.number_input("采样间隔（行数）", min_value=1, value=10)

# 云端模式专属设置
if mode.startswith("☁️"):
    max_rows_limit = st.sidebar.number_input(
        "最大处理行数（防止卡死）",
        min_value=1000, max_value=200000, value=50000, step=10000,
        help="云端内存有限，超过此行数将自动截断。推荐使用本地脚本模式。"
    )
    chunk_size = st.sidebar.number_input(
        "分块大小", min_value=5000, max_value=50000, value=20000, step=5000
    )
    st.sidebar.warning("⚠️ 云端处理大文件极易卡死，仅建议处理 <5万行的文件。")

# ---------- 辅助函数：解压 ----------
def extract_csv_from_upload(uploaded_file):
    file_name = uploaded_file.name.lower()
    extracted = []
    try:
        if file_name.endswith('.csv'):
            extracted.append((uploaded_file.name, BytesIO(uploaded_file.getvalue())))
        elif file_name.endswith('.zip'):
            with zipfile.ZipFile(BytesIO(uploaded_file.getvalue())) as zf:
                for name in zf.namelist():
                    if name.lower().endswith('.csv'):
                        data = zf.read(name)
                        extracted.append((os.path.basename(name), BytesIO(data)))
        elif file_name.endswith('.gz'):
            with gzip.GzipFile(fileobj=BytesIO(uploaded_file.getvalue())) as gz:
                content = gz.read()
                base = uploaded_file.name[:-3] if uploaded_file.name.endswith('.gz') else uploaded_file.name
                if not base.endswith('.csv'):
                    base += '.csv'
                extracted.append((base, BytesIO(content)))
    except Exception as e:
        st.error(f"解压失败：{e}")
    return extracted

# ---------- 侧边栏：文件库 ----------
st.sidebar.header("📤 文件库")
if st.session_state.uploaded_library:
    for fname, info in list(st.session_state.uploaded_library.items()):
        col1, col2, col3 = st.sidebar.columns([3,1,1])
        with col1:
            st.write(f"📄 {fname} ({info['size_mb']:.1f} MB)")
        with col2:
            if st.button("📂", key=f"load_{fname}"):
                if fname not in st.session_state.current_files:
                    st.session_state.current_files.append(fname)
                st.rerun()
        with col3:
            if st.button("🗑️", key=f"del_{fname}"):
                del st.session_state.uploaded_library[fname]
                if fname in st.session_state.current_files:
                    st.session_state.current_files.remove(fname)
                st.rerun()
    if st.sidebar.button("清空文件库"):
        st.session_state.uploaded_library.clear()
        st.session_state.current_files.clear()
        st.rerun()

# ---------- 主界面：上传 ----------
st.markdown("### 第一步：上传 CSV 或压缩包")
uploaded_files = st.file_uploader(
    "支持 .csv, .zip, .gz，可多选",
    type=["csv","zip","gz"],
    accept_multiple_files=True
)

if uploaded_files:
    new_files = []
    for f in uploaded_files:
        if f.name in st.session_state.uploaded_library:
            continue
        # 解压并存入库
        extracted = extract_csv_from_upload(f)
        for csv_name, csv_io in extracted:
            data_bytes = csv_io.getvalue()
            size_mb = len(data_bytes) / (1024*1024)
            st.session_state.uploaded_library[csv_name] = {"data": data_bytes, "size_mb": size_mb}
            new_files.append(csv_name)
            st.toast(f"✅ {csv_name} 已保存")
    if new_files:
        st.session_state.current_files.extend(new_files)
        st.rerun()

# ---------- 当前工作区 ----------
if st.session_state.current_files:
    work_files = []
    for fname in st.session_state.current_files:
        info = st.session_state.uploaded_library.get(fname)
        if info:
            fobj = BytesIO(info["data"])
            fobj.name = fname
            work_files.append((fobj, info["size_mb"]))
        else:
            st.session_state.current_files.remove(fname)

    if work_files:
        st.markdown("### 📂 已加载文件")
        st.info(f"共 {len(work_files)} 个文件，总大小 {sum(sz for _,sz in work_files):.2f} MB")

        # 预览第一个文件的前1000行（用于列选择）
        first_file = work_files[0][0]
        first_file.seek(0)
        try:
            df_preview = pd.read_csv(first_file, nrows=1000)
        except Exception as e:
            st.error(f"预览失败：{e}")
            st.stop()

        with st.expander(f"🔎 预览 {first_file.name} (前1000行)"):
            st.dataframe(df_preview, use_container_width=True)

        all_columns = df_preview.columns.tolist()
        if "selected_cols" not in st.session_state:
            st.session_state.selected_cols = all_columns[: min(3, len(all_columns))]

        selected_cols = st.multiselect(
            "选择要保留的列",
            options=all_columns,
            default=st.session_state.selected_cols
        )
        st.session_state.selected_cols = selected_cols

        # ---------- 根据模式显示不同操作按钮 ----------
        if mode.startswith("🚀"):
            st.markdown("### 第二步：下载本地处理脚本")
            st.success("✅ 请将下载的 `.py` 脚本放在 CSV 文件所在文件夹，双击运行即可（需安装 Python 和 pandas）。")
            if selected_cols:
                script_content = generate_local_script(selected_cols, sample_interval if enable_sampling else 0)
                st.download_button(
                    label="⬇️ 下载本地处理脚本 (csv_extractor.py)",
                    data=script_content,
                    file_name="csv_extractor.py",
                    mime="text/x-python"
                )
            else:
                st.warning("请至少选择一列。")

        else:  # 云端尽力模式
            st.markdown("### 第二步：云端处理（有行数限制）")
            if st.button("☁️ 开始云端提取", type="primary"):
                if not selected_cols:
                    st.warning("请选择列")
                else:
                    extracted_files = []
                    total_bytes = sum(info["size_mb"]*1024*1024 for info in st.session_state.uploaded_library.values())
                    progress_bar = st.progress(0, "准备...")
                    status_text = st.empty()

                    processed_bytes = 0
                    for idx, (fobj, _) in enumerate(work_files):
                        fname = fobj.name
                        fsize = len(st.session_state.uploaded_library[fname]["data"])
                        status_text.text(f"处理 {fname} ...")
                        try:
                            fobj.seek(0)
                            output_chunks = []
                            total_rows = 0
                            chunk_iter = pd.read_csv(
                                fobj, usecols=selected_cols, chunksize=chunk_size,
                                on_bad_lines='skip', nrows=max_rows_limit
                            )
                            for chunk in chunk_iter:
                                if enable_sampling:
                                    chunk = chunk.iloc[::sample_interval]
                                total_rows += len(chunk)
                                output_chunks.append(chunk)
                                # 简单进度估算
                                processed_bytes += len(chunk) * 100  # 粗略
                                prog = min(processed_bytes / total_bytes, 0.99)
                                progress_bar.progress(prog, f"{fname} 已读 {total_rows} 行")
                            if output_chunks:
                                result_df = pd.concat(output_chunks, ignore_index=True)
                            else:
                                result_df = pd.DataFrame(columns=selected_cols)
                            buf = BytesIO()
                            result_df.to_csv(buf, index=False)
                            data = buf.getvalue()
                            extracted_files.append((f"extracted_{fname}", data, len(data)/1024/1024, len(result_df)))
                        except Exception as e:
                            st.error(f"{fname} 失败: {e}")
                        processed_bytes += fsize

                    progress_bar.progress(1.0, "完成")
                    status_text.empty()
                    st.success("处理完成！")
                    for fname, fdata, fmbs, frows in extracted_files:
                        st.download_button(f"⬇️ {fname} ({fmbs:.2f} MB)", fdata, fname, key=fname)

# ---------- 历史记录侧边栏（略，保持简洁）----------