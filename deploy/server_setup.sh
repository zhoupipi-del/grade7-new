#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
#  服务器初始化脚本 — 让 /opt/grade7-new 成为 Git 仓库
#  在生产服务器上以 root 身份执行一次即可
# ──────────────────────────────────────────────────────────
set -e

DEPLOY_DIR="/opt/grade7-new"
REPO_URL="$1"  # 传入仓库地址，如 https://gitee.com/xxx/grade7-new.git

if [ -z "$REPO_URL" ]; then
    echo "用法: bash server_setup.sh <仓库地址>"
    echo "示例: bash server_setup.sh https://gitee.com/yourname/grade7-new.git"
    exit 1
fi

echo "=== 1/5 备份当前生产环境 ==="
if [ -d "$DEPLOY_DIR" ]; then
    cp -a "$DEPLOY_DIR" "${DEPLOY_DIR}.bak.$(date +%Y%m%d%H%M%S)"
    echo "已备份到 ${DEPLOY_DIR}.bak.*"
fi

echo "=== 2/5 清空并克隆仓库 ==="
rm -rf "$DEPLOY_DIR"
git clone "$REPO_URL" "$DEPLOY_DIR"

echo "=== 3/5 恢复 .env 配置 ==="
if [ -f "${DEPLOY_DIR}.bak."*"/.env" ]; then
    # 找到最新的备份
    BAK_DIR=$(ls -dt ${DEPLOY_DIR}.bak.* 2>/dev/null | head -1)
    if [ -f "$BAK_DIR/.env" ]; then
        cp "$BAK_DIR/.env" "$DEPLOY_DIR/.env"
        chmod 600 "$DEPLOY_DIR/.env"
        echo "已恢复 .env"
    fi
fi

# .env 不存在则从 systemd 提取
if [ ! -f "$DEPLOY_DIR/.env" ]; then
    cat > "$DEPLOY_DIR/.env" << 'ENVEOF'
# 由 server_setup.sh 生成
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ENVEOF
    # 从 systemd override 中提取 LLM 配置
    if [ -f /etc/systemd/system/grade7-new.service.d/override.conf ]; then
        grep -E '^Environment=' /etc/systemd/system/grade7-new.service.d/override.conf \
            | sed 's/Environment=//' >> "$DEPLOY_DIR/.env"
    fi
    chmod 600 "$DEPLOY_DIR/.env"
    echo "已从 systemd 生成 .env"
fi

echo "=== 4/5 安装 Python 依赖 ==="
cd "$DEPLOY_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
/opt/grade7-new/venv/bin/pip install -q -r requirements.txt 2>/dev/null \
    || /opt/grade7-new/venv/bin/pip install -q flask sqlalchemy pymysql openpyxl redis requests gunicorn

echo "=== 5/5 验证服务 ==="
systemctl restart grade7-new
sleep 3
STATUS=$(systemctl is-active grade7-new)
echo "服务状态: $STATUS"

if [ "$STATUS" = "active" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5001/health || echo "000")
    echo "健康检查: HTTP $HTTP_CODE"
    echo ""
    echo "✅ 服务器初始化完成！"
    echo "后续 push 到 main 分支即可自动部署。"
else
    echo "❌ 服务启动失败，请检查日志:"
    echo "  journalctl -u grade7-new --no-pager -n 30"
fi
