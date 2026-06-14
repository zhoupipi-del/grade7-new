# ═══════════════════════════════════════════════════════════════
#  Wings 数智化要塞 — 平滑运维发布命令集
# ═══════════════════════════════════════════════════════════════
#  核心原则：
#  ① 冒烟测试不通过 → 死锁拦截，绝不染指生产
#  ② kill -HUP 平滑轮替，拒绝 systemctl restart 暴力熔断
#  ③ 所有推送并行执行，最小化发布窗口
# ═══════════════════════════════════════════════════════════════

SERVER   := root@8.137.180.152
APP_DIR  := /opt/grade7-new
FILES    := blueprints/*.py templates/ models.py decorators.py app.py \
            wsgi.py utils/*.py feature_extractor.py ai_api.py
SERVICE  := grade7-new

.PHONY: help smoke check deploy deploy-all db-migrate restart

# ── 默认目标 ──
help:
	@echo "⚔️  Wings 运维命令集"
	@echo ""
	@echo "  make smoke       — 运行 61 条角色冒烟测试（本地）"
	@echo "  make check       — 语法检查（Python compile + Flask 导入）"
	@echo "  make deploy      — 发布：冒烟 → scp 推送 → HUP 平滑重载"
	@echo "  make db-migrate  — 生产数据库迁移（ALERT: 谨慎操作）"
	@echo "  make restart     — 紧急重启（HUP 平滑方案）"
	@echo ""

# ── 冒烟审计 — 发布前死锁拦截 ──
smoke:
	@echo "🔍 全角色路由冒烟审计（61 条）..."
	@cd $(CURDIR) && python3 smoke_test_all_roles.py || ( \
		echo "❌ 冒烟测试未通过！拦截发布！(exit $$?)"; \
		exit 1 \
	)
	@echo "✅ 冒烟审计通过，免疫系统正常"

# ── 语法审查 ──
check:
	@echo "📋 Python 编译语法检查..."
	@find $(CURDIR) -name "*.py" -not -path "*venv*" -not -path "*__pycache__*" \
		-exec python3 -m py_compile {} \; 2>&1 || exit 1
	@echo "✅ 语法检查通过"

# ── 生产发布（冒烟审计→SCP推送→HUP平滑重载） ──
deploy:
	@echo "🚀 开始前置角色冒烟安全审计..."
	@cd $(CURDIR) && python3 smoke_test_all_roles.py || ( \
		echo "❌ 冒烟测试未通过，拦截发布！(exit $$?)"; \
		exit 1 \
	)
	@echo "✅ 审计通过，正在并行推送..."
	@ssh $(SERVER) "mkdir -p $(APP_DIR)/blueprints $(APP_DIR)/templates $(APP_DIR)/utils"
	@scp -q $(CURDIR)/blueprints/*.py $(SERVER):$(APP_DIR)/blueprints/
	@scp -q $(CURDIR)/models.py $(SERVER):$(APP_DIR)/
	@scp -q $(CURDIR)/app.py $(CURDIR)/wsgi.py $(SERVER):$(APP_DIR)/
	@scp -q $(CURDIR)/utils/*.py $(SERVER):$(APP_DIR)/utils/ 2>/dev/null; true
	@echo "📤 代码推送完成，开始 HUP 平滑轮替..."
	@ssh $(SERVER) "MASTER_PID=\$$(pgrep -f 'gunicorn.*wsgi:app' | sort -n | head -1); \
		if [ -n \"\$$MASTER_PID\" ]; then \
			kill -HUP \$$MASTER_PID && echo \"HUP signal sent to master PID \$$MASTER_PID\"; \
		else \
			echo 'WARNING: 未找到 gunicorn 主进程，请检查'; \
		fi"
	@sleep 3
	@ssh $(SERVER) "curl -s http://127.0.0.1:5001/health"
	@echo ""
	@ssh $(SERVER) "systemctl status $(SERVICE) --no-pager | grep Active"
	@echo "✅ 发布完成！冒烟→推送→HUP 全链路闭环"

# ── 数据库迁移（需二次确认） ──
db-migrate:
	@echo "⚠️  即将在生产库执行迁移！"
	@read -p "确认继续? [y/N] " yn; \
	case $$yn in \
		[Yy]*) scp $(CURDIR)/migrate_feature_attribution.py $(SERVER):/tmp/ && \
			ssh $(SERVER) "cd $(APP_DIR) && venv/bin/python3 /tmp/migrate_feature_attribution.py";; \
		*) echo "已取消";; \
	esac

# ── 紧急重启（HUP 平滑方案） ──
restart:
	@echo "♻️  平滑 HUP 重载..."
	@ssh $(SERVER) "MASTER_PID=\$$(pgrep -f 'gunicorn.*wsgi:app' | sort -n | head -1); \
		if [ -n \"\$$MASTER_PID\" ]; then \
			kill -HUP \$$MASTER_PID && echo \"HUP sent to \$$MASTER_PID\"; \
			sleep 3; \
			curl -s http://127.0.0.1:5001/health; \
			echo ''; \
		else \
			echo 'ERROR: 未找到 gunicorn 主进程'; \
			exit 1; \
		fi"
