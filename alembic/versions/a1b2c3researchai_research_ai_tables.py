"""research_ai tables

Revision ID: a1b2c3researchai
Revises: <DEPLOY_REPLACE>
Create Date: 2026-08-16

⚠️ V2.1.2/V2.2.x 部署前必须完成（V2.2.1 定稿规则）：
  1. 在生产服务器执行：cd /opt/wings3/current/backend && .venv/bin/alembic heads
  2. 将下方 down_revision 的 '<DEPLOY_REPLACE>' 替换为输出的当前 head revision ID
  3. ★ revision = 'a1b2c3researchai' 保持固定，禁止改名/改 revision ID——
     V2.2 的 b2c3d4researchai 已固定 down_revision = 'a1b2c3researchai'，
     改掉本文件 revision 会立刻断掉 V2.2 迁移链。
  4. 执行 .venv/bin/alembic upgrade head
  5. upgrade 成功后，再单独执行模块启用 SQL（见 03_deploy_steps.md），
     按目标学校 school_id 插入/更新 school_modules

本 migration 只负责 schema DDL：
  - 创建 4 张表 + 索引 + FK
  - downgrade 删除 4 张表

模块开关（school_modules）属于租户业务数据，不放在 schema migration 中，
由部署阶段按目标学校单独执行，避免 downgrade 误关其他学校功能。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# ★ V2.2.1 定稿：此值固定，禁止修改。只允许替换下方 down_revision。
revision = 'a1b2c3researchai'
# ⚠️ 部署前必须替换为生产当前 head（执行 alembic heads 获取）
down_revision = '20260815_1200'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 教案批量任务表
    op.create_table(
        'lesson_plan_tasks',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('school_id', sa.BigInteger, nullable=False, comment='学校ID（租户隔离）'),
        sa.Column('created_by', sa.BigInteger, nullable=False, comment='创建人 user_id'),
        sa.Column('task_name', sa.String(200), nullable=False, comment='任务名称'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('total_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('success_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('fail_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime, nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_lpt_school_created', 'lesson_plan_tasks', ['school_id', 'created_at'])

    # 2. 单篇教案表
    op.create_table(
        'lesson_plan_items',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('task_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('school_id', sa.BigInteger, nullable=False),
        sa.Column('subject', sa.String(50), nullable=False),
        sa.Column('textbook', sa.String(100), nullable=True),
        sa.Column('grade', sa.String(50), nullable=False),
        sa.Column('unit', sa.String(200), nullable=True),
        sa.Column('topic', sa.String(200), nullable=False),
        sa.Column('periods', sa.Integer, nullable=False, server_default='1'),
        sa.Column('key_point', sa.String(500), nullable=True),
        sa.Column('diff_point', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_name', sa.String(255), nullable=True),
        sa.Column('ai_raw_json', sa.JSON, nullable=True),
        sa.Column('prompt_tokens', sa.Integer, nullable=True),
        sa.Column('completion_tokens', sa.Integer, nullable=True),
        sa.Column('error_msg', sa.Text, nullable=True),
        sa.Column('elapsed_sec', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime, nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['lesson_plan_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_lpi_school_task', 'lesson_plan_items', ['school_id', 'task_id'])

    # 3. 作文批改记录表
    op.create_table(
        'essay_grade_records',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('school_id', sa.BigInteger, nullable=False),
        sa.Column('teacher_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('student_id', sa.BigInteger, nullable=True),
        sa.Column('student_name', sa.String(100), nullable=True),
        sa.Column('subject', sa.String(20), nullable=False),
        sa.Column('grade', sa.String(20), nullable=False),
        sa.Column('total_score_config', sa.SmallInteger, nullable=False, server_default='60'),
        sa.Column('essay_prompt', sa.Text, nullable=False),
        sa.Column('essay_text', sa.Text, nullable=False),
        sa.Column('rubric', sa.Text, nullable=True),
        sa.Column('ai_total_score', sa.SmallInteger, nullable=True),
        sa.Column('ai_grade_label', sa.String(50), nullable=True),
        sa.Column('ai_dimensions', sa.JSON, nullable=True),
        sa.Column('ai_annotations', sa.JSON, nullable=True),
        sa.Column('ai_grammar_errors', sa.JSON, nullable=True),
        sa.Column('ai_comment', sa.Text, nullable=True),
        sa.Column('ai_chinese_summary', sa.Text, nullable=True),
        sa.Column('ai_refined_essay', sa.Text, nullable=True),
        sa.Column('ai_tips', sa.JSON, nullable=True),
        sa.Column('ai_raw_json', sa.JSON, nullable=True),
        sa.Column('prompt_tokens', sa.Integer, nullable=True),
        sa.Column('completion_tokens', sa.Integer, nullable=True),
        sa.Column('review_status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('final_score', sa.SmallInteger, nullable=True),
        sa.Column('teacher_comment', sa.Text, nullable=True),
        sa.Column('reviewed_by', sa.BigInteger, nullable=True),
        sa.Column('reviewed_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ondelete='CASCADE'),
    )
    # [V2.1.2 P1] 索引名对齐 ORM：models_essay.py 中 Index("idx_essay_school_teacher", ...)
    # 此前 migration 写 idx_egr_school_teacher 与 ORM metadata 不一致，
    # 会导致后续 autogenerate 误判索引漂移。统一为 idx_essay_school_teacher。
    op.create_index('idx_essay_school_teacher', 'essay_grade_records', ['school_id', 'teacher_id'])

    # 4. 分层作业任务表
    op.create_table(
        'homework_tasks',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('school_id', sa.BigInteger, nullable=False),
        sa.Column('created_by', sa.BigInteger, nullable=False, index=True),
        sa.Column('subject', sa.String(50), nullable=False),
        sa.Column('grade', sa.String(50), nullable=False),
        sa.Column('textbook', sa.String(100), nullable=True),
        sa.Column('unit', sa.String(200), nullable=True),
        sa.Column('topic', sa.String(200), nullable=False),
        sa.Column('knowledge_points', sa.Text, nullable=True),
        sa.Column('class_profile', sa.Text, nullable=True),
        sa.Column('question_counts', sa.String(20), nullable=False, server_default='8-5-3'),
        sa.Column('difficulty_distribution', sa.String(20), nullable=False, server_default='4-4-2'),
        sa.Column('estimated_minutes', sa.Integer, nullable=False, server_default='40'),
        sa.Column('include_answers', sa.Boolean, nullable=False, server_default=sa.text('1')),
        sa.Column('extra_requirements', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_name', sa.String(255), nullable=True),
        sa.Column('ai_raw_json', sa.JSON, nullable=True),
        sa.Column('prompt_tokens', sa.Integer, nullable=True),
        sa.Column('completion_tokens', sa.Integer, nullable=True),
        sa.Column('error_msg', sa.Text, nullable=True),
        sa.Column('elapsed_sec', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime, nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_hw_school_user', 'homework_tasks', ['school_id', 'created_by'])


def downgrade() -> None:
    """
    [V2.1.1] downgrade 只删除 4 张表，不触碰 school_modules。
    模块开关由部署/回滚脚本按目标学校单独管理。
    """
    op.drop_table('homework_tasks')
    op.drop_table('essay_grade_records')
    op.drop_table('lesson_plan_items')
    op.drop_table('lesson_plan_tasks')
