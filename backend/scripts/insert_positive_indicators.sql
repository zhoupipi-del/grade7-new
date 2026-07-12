-- 迁移脚本 — 插入正向加分指标到 evaluation_indicators 表
-- 用法: mysql -h 127.0.0.1 -P 3307 -ugrade7 -p wings3 < scripts/insert_positive_indicators.sql
-- 作者: WorkBuddy AI
-- 日期: 2026-07-05

-- 设置字符集
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 插入正向加分指标（幂等：使用 INSERT IGNORE 避免重复）
-- 思想品德维度 — 品德表现加分
INSERT IGNORE INTO evaluation_indicators (school_id, name, parent_id, dimension, weight, max_score, sort_order, is_active, created_at)
VALUES
    (1, '品德之星', 1, 'moral', 0.25, 100.0, 23, 1, NOW()),
    (1, '助人为乐', 1, 'moral', 0.25, 100.0, 24, 1, NOW()),
    (1, '拾金不昧', 1, 'moral', 0.20, 100.0, 25, 1, NOW()),
    (1, '诚信守诺', 1, 'moral', 0.30, 100.0, 26, 1, NOW()),
    -- 身心健康维度 — 体育竞赛加分
    (1, '体育竞赛', 1, 'health', 0.30, 100.0, 27, 1, NOW()),
    -- 艺术素养维度 — 文体活动加分
    (1, '文体活动', 1, 'art', 0.25, 100.0, 28, 1, NOW()),
    (1, '文艺演出', 1, 'art', 0.25, 100.0, 29, 1, NOW()),
    (1, '艺术考级', 1, 'art', 0.20, 100.0, 30, 1, NOW()),
    -- 社会实践维度 — 志愿服务与劳动实践加分
    (1, '校园志愿', 1, 'social', 0.25, 100.0, 31, 1, NOW()),
    (1, '社区服务', 1, 'social', 0.30, 100.0, 32, 1, NOW()),
    (1, '公益捐赠', 1, 'social', 0.20, 100.0, 33, 1, NOW()),
    (1, '劳动实践', 1, 'social', 0.25, 100.0, 34, 1, NOW()),
    (1, '劳动技能', 1, 'social', 0.20, 100.0, 35, 1, NOW())
;

-- 验证：查询插入结果
SELECT
    id,
    name,
    dimension,
    weight,
    sort_order,
    is_active,
    created_at
FROM evaluation_indicators
WHERE school_id = 1
ORDER BY sort_order;

SET FOREIGN_KEY_CHECKS = 1;
