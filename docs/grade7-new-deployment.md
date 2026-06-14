# 梨江中学德育管理平台 (grade7-new) — 部署运维文档

> 版本: 1.0 | 最后更新: 2026-06-07

---

## 一、当前生产环境

| 项目 | 信息 |
|------|------|
| 服务器 | 8.137.180.152 (Ubuntu) |
| 内存 | 8GB |
| 项目路径 | `/opt/grade7-new/` |
| 虚拟环境 | `/opt/grade7-new/venv/` |
| 日志 | `journalctl -u grade7-new` |
| 数据库容器 | `grade7-new-db` (MySQL 8.0) |
| 网络 | `grade7-new-network` (172.30.0.0/16) |
| 数据库端口 | 3307 (映射容器 3306) |

---

## 二、服务管理命令

### 2.1 Gunicorn (systemd)

```bash
# 启停服务
systemctl start grade7-new
systemctl stop grade7-new
systemctl restart grade7-new
systemctl status grade7-new

# 查看实时日志
journalctl -u grade7-new -f
# 查看最近 50 条
journalctl -u grade7-new --no-pager -n 50
# 启用开机自启
systemctl enable grade7-new
```

### 2.2 MySQL 容器

```bash
# 容器管理
docker start grade7-new-db
docker stop grade7-new-db
docker restart grade7-new-db
docker logs grade7-new-db

# 连接数据库
mysql -h 127.0.0.1 -P 3307 -ugrade7 -p'waOPKoyFf4ByQD1h' grade7_new
```

### 2.3 Nginx

```bash
# 测试配置
nginx -t
# 重载配置（不停服）
nginx -s reload
# 查看错误日志
tail -f /var/log/nginx/error.log
```

---

## 三、Gunicorn 配置详情

```ini
# /etc/systemd/system/grade7-new.service
[Unit]
Description=grade7-new Gunicorn
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/grade7-new
Environment="PATH=/opt/grade7-new/venv/bin"
ExecStart=/opt/grade7-new/venv/bin/gunicorn \
    --bind 127.0.0.1:5001 \
    --worker-class gthread \
    --threads 4 \
    --workers 2 \
    --timeout 120 \
    --preload \
    --access-logfile /var/log/grade7-new-access.log \
    --error-logfile /var/log/grade7-new-error.log \
    wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**关键参数说明**:
- `gthread`: 必须使用此 worker 类型，sync worker 不支持 SSE 长连接
- `--preload`: 预加载应用，减少内存占用
- `--threads 4`: 每 worker 4 个线程，共 8 并发
- `--timeout 120`: 120 秒超时（SSE 长连接需要）

---

## 四、Nginx 配置要点

```nginx
# 限流配置（在 nginx.conf 的 http 块中）
limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;

# 站点配置关键部分
server {
    listen 80;
    server_name _;

    # 登录限流
    location = /login {
        limit_req zone=login_limit burst=3 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # SSE 端点 - 禁用缓冲
    location /common/api/events {
        proxy_pass http://127.0.0.1:5001;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 120s;
    }

    # 一般代理
    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # 静态文件
    location /static/ {
        alias /opt/grade7-new/static/;
        expires 7d;
    }

    # 上传限制
    client_max_body_size 16M;
    gzip on;
    gzip_types text/css application/javascript text/html;
}
```

---

## 五、数据库配置

### 5.1 Docker 容器创建命令

```bash
docker run -d \
  --name grade7-new-db \
  --network grade7-new-network \
  --ip 172.30.0.2 \
  -p 3307:3306 \
  -e MYSQL_ROOT_PASSWORD=root_secure_pass \
  -e MYSQL_DATABASE=grade7_new \
  -e MYSQL_USER=grade7 \
  -e MYSQL_PASSWORD='waOPKoyFf4ByQD1h' \
  --memory=400m \
  -v grade7-new-db-data:/var/lib/mysql \
  mysql:8.0 \
  --performance_schema=OFF \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci
```

### 5.2 SQLAlchemy 连接池配置

```python
# config.py
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 5,
    'max_overflow': 10,
    'pool_recycle': 300,      # 5 分钟回收连接
    'pool_pre_ping': True,    # 使用前检测连接有效性
    'pool_timeout': 30,
    'echo': False,
    'connect_args': {
        'connect_timeout': 10,
    }
}
```

### 5.3 备份命令

```bash
# 全库备份
mysqldump -h 127.0.0.1 -P 3307 -ugrade7 -p'waOPKoyFf4ByQD1h' \
  --single-transaction --routines --triggers \
  grade7_new > backup_$(date +%Y%m%d).sql

# 恢复
mysql -h 127.0.0.1 -P 3307 -ugrade7 -p'waOPKoyFf4ByQD1h' \
  grade7_new < backup_20260607.sql
```

---

## 六、首次部署步骤

### 6.1 服务器准备

```bash
# 安装依赖
sudo apt update
sudo apt install -y python3.12-venv nginx docker.io

# 创建目录
sudo mkdir -p /opt/grade7-new
sudo chown ubuntu:ubuntu /opt/grade7-new
```

### 6.2 部署代码

```bash
cd /opt/grade7-new
# 上传代码文件（scp 或 git clone）

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 6.3 启动数据库

```bash
# 创建独立网络
docker network create --subnet=172.30.0.0/16 grade7-new-network

# 启动 MySQL 容器（见上方命令）
```

### 6.4 初始化数据库

```bash
cd /opt/grade7-new
source venv/bin/activate
python -c "
from app import create_app
app = create_app()
with app.app_context():
    from models import db
    db.create_all()
    print('All tables created.')
"
```

### 6.5 启动应用

```bash
# 安装 systemd 服务
sudo cp grade7-new.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable grade7-new
sudo systemctl start grade7-new

# 配置 Nginx
sudo cp nginx/nginx.conf /etc/nginx/sites-enabled/grade7
sudo nginx -t && sudo systemctl reload nginx
```

---

## 七、故障排查

### 7.1 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 页面响应极慢（7秒+） | N+1 查询问题 / 暴力破解攻击 | 检查 ai_analysis 批量查询 / 检查 Nginx access log |
| MySQL 连接断开 | Gunicorn --preload 导致连接过期 | 确保 pool_pre_ping=True, pool_recycle=300 |
| SSE 连接崩溃 | sync worker 不支持长连接 | 必须使用 gthread worker |
| 502 Bad Gateway | Gunicorn 未启动 | `systemctl status grade7-new` |
| 模板变量未定义 | render_template 参数名与模板不一致 | 检查视图函数参数名与模板变量名 |
| 端点 404 | url_for 端点名与蓝图注册名不匹配 | 检查蓝图注册端点名 |

### 7.2 诊断命令

```bash
# 检查 Gunicorn 状态
systemctl status grade7-new
ps aux | grep gunicorn

# 检查 MySQL 连接
docker exec grade7-new-db mysqladmin -uroot -p'root_secure_pass' status

# 检查 Nginx 日志
tail -100 /var/log/nginx/access.log
tail -100 /var/log/nginx/error.log

# 检查系统资源
free -h
df -h
top -bn1 | head -20

# 检查端口监听
ss -tlnp | grep -E '80|5001|3307'

# 测试端点
curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/health
```

### 7.3 暴力破解防护

```bash
# 检查登录暴力攻击
grep "POST /login" /var/log/nginx/access.log | awk '{print $1}' | sort | uniq -c | sort -rn | head -20

# 封禁攻击 IP
iptables -I INPUT -s <IP> -j DROP

# 保存 iptables 规则
iptables-save > /etc/iptables/rules.v4
```

---

## 八、更新部署流程

```bash
# 1. 停止服务
sudo systemctl stop grade7-new

# 2. 备份数据库
mysqldump -h 127.0.0.1 -P 3307 -ugrade7 -p'waOPKoyFf4ByQD1h' \
  grade7_new > backup_pre_update_$(date +%Y%m%d_%H%M).sql

# 3. 更新代码
cd /opt/grade7-new
# scp/git pull 新代码

# 4. 更新依赖（如有变化）
source venv/bin/activate
pip install -r requirements.txt

# 5. 数据库迁移（如有新表）
python -c "
from app import create_app
app = create_app()
with app.app_context():
    from models import db
    db.create_all()
    print('Migration complete.')
"

# 6. 重启服务
sudo systemctl start grade7-new
sudo systemctl status grade7-new

# 7. 验证
curl -s http://localhost:5001/health
```

---

## 九、监控检查清单

### 日常检查项

- [ ] `systemctl status grade7-new` — Gunicorn 运行中
- [ ] `docker ps | grep grade7-new-db` — MySQL 容器运行中
- [ ] `curl -s http://localhost:5001/health` — 返回 200
- [ ] `df -h` — 磁盘空间充足
- [ ] `free -h` — 内存充足
- [ ] `tail -20 /var/log/nginx/error.log` — 无异常错误

### 安全审计

- [ ] `last -20` — 检查异常登录
- [ ] `grep "Failed password" /var/log/auth.log | tail -20` — SSH 暴力破解
- [ ] `grep "POST /login" /var/log/nginx/access.log | tail -20` — 登录频率
- [ ] `iptables -L -n` — 防火墙规则完整

---

## 十、联系信息

| 角色 | 默认账号 | 默认密码 |
|------|----------|----------|
| 德育处管理员 | admin | admin123 |
| 年级组长 | (需创建) | — |
| 班主任 | (需创建) | — |
| 家长 | (需创建) | — |

---

*文档生成时间: 2026-06-07 | 基于 grade7-new 生产环境*
