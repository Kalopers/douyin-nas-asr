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
export PYTHONPATH=$PROJECT_ROOT

APP_HOST="$(python3 -c 'from src.server.settings import settings; print(settings.app_host)')"
APP_PORT="$(python3 -c 'from src.server.settings import settings; print(settings.app_port)')"

echo "使用配置: APP_HOST=$APP_HOST APP_PORT=$APP_PORT"

# 启动 uvicorn 服务
# host / port 默认值统一由 settings.py 定义
exec python3 -m uvicorn src.server.main:app --host "$APP_HOST" --port "$APP_PORT" --reload
