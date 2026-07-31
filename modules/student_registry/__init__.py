"""
modules/student_registry/__init__.py — 学籍管理模块

学籍管理是 WINGS 3.0 全系统的数据源头。
所有模块的学生数据均从此处引用，通过 core.models.Student 基类实现。

核心功能：
- 学籍全生命周期管理（注册/转学/休学/复学/退学/毕业）
- 学号自动生成（统一规则：入学年+年级+班序+序号）
- 批量导入（Excel -> data_adapter）
- 学籍状态机（active -> suspended -> active / transferred / graduated）
- 旧数据迁移支持（sync_status + lineage 标记）
"""
