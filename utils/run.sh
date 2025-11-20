#!/bin/bash

# 获取脚本所在目录的上一级目录 (即项目根目录)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 切换到项目根目录
cd "$PROJECT_ROOT" || exit 1
echo "工作目录已切换至: $PROJECT_ROOT"

# 检查是否在虚拟环境中 (可选)
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "警告: 未检测到激活的虚拟环境 (Virtualenv/Conda)。"
    echo "建议在虚拟环境中运行以避免依赖冲突。"
    # 可以在这里尝试自动 source venv/bin/activate
fi

# 确保依赖已安装 (可选，如果通过 Docker 运行则不需要)
# pip install -r requirements.txt

echo "正在启动 uvicorn 服务..."
# 启动 uvicorn 服务
# --host 0.0.0.0 允许局域网访问
export PYTHONPATH=$PROJECT_ROOT
python3 -m uvicorn src.server.main:app --host 0.0.0.0 --port 17650 --reload