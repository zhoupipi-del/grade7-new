"""research_ai V2.2 tables (paper/analysis/comment)

Revision ID: b2c3d4researchai
Revises: a1b2c3researchai
Create Date: 2026-08-16

V2.2 新增三个功能的三张表：
  - paper_tasks       AI 试卷命制
  - analysis_tasks    AI 学情分析报告
  - comment_tasks     AI 学生评语生成

依赖：先执行 a1b2c3researchai（V2.1.x 的 4 张表）后，本迁移再执行。
down_revision 固定为 'a1b2c3researchai'（同包内链，无占位符）。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2c3d4researchai'
down_revision = 'a1b2c3researchai'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. AI 试卷命制任务表
    op.create_table(
        'paper_tasks',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('school_id', sa.BigInteger, nullable=False, comment='学校ID（租户隔离）'),
        sa.Column('created_by', sa.BigInteger, nullable=False, comment='创建人 user_id'),
        sa.Column('subject', sa.String(50), nullable=False, comment='学科'),
        sa.Column('grade', sa.String(50), nullable=False, comment='年级'),
        sa.Column('textbook', sa.String(100), nullable=True),
        sa.Column('unit', sa.String(200), nullable=True),
        sa.Column('topic', sa.String(200), nullable=False, comment='考查主题'),
        sa.Column('knowledge_points', sa.Text, nullable=True),
        sa.Column('question_types', sa.String(50), nullable=False, server_default='6-4-3'),
        sa.Column('total_score', sa.Integer, nullable=False, server_default='100'),
        sa.Column('difficulty', sa.String(20), nullable=False, server_default='4-4-2'),
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
    op.create_index('idx_paper_school_user', 'paper_tasks', ['school_id', 'created_by'])

    # 2. AI 学情分析报告任务表
    op.create_table(
        'analysis_tasks',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('school_id', sa.BigInteger, nullable=False, comment='学校ID（租户隔离）'),
        sa.Column('created_by', sa.BigInteger, nullable=False, comment='创建人 user_id'),
        sa.Column('scope_name', sa.String(100), nullable=False, comment='分析对象（班级/年级）'),
        sa.Column('subject', sa.String(50), nullable=False, comment='学科'),
        sa.Column('grade', sa.String(50), nullable=False, comment='年级'),
        sa.Column('exam_name', sa.String(200), nullable=True),
        sa.Column('data_summary', sa.Text, nullable=False, comment='学情数据摘要'),
        sa.Column('analysis_focus', sa.Text, nullable=True),
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
    op.create_index('idx_analysis_school_user', 'analysis_tasks', ['school_id', 'created_by'])

    # 3. AI 学生评语生成任务表
    op.create_table(
        'comment_tasks',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('school_id', sa.BigInteger, nullable=False, comment='学校ID（租户隔离）'),
        sa.Column('created_by', sa.BigInteger, nullable=False, comment='创建人 user_id'),
        sa.Column('class_name', sa.String(100), nullable=False, comment='班级名称'),
        sa.Column('term', sa.String(100), nullable=False, comment='学期'),
        sa.Column('comment_type', sa.String(50), nullable=False, server_default='semester'),
        sa.Column('students', sa.JSON, nullable=False, comment='学生名单（姓名+表现关键词）'),
        sa.Column('student_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('style', sa.Text, nullable=True),
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
    op.create_index('idx_comment_school_user', 'comment_tasks', ['school_id', 'created_by'])


def downgrade() -> None:
    op.drop_table('comment_tasks')
    op.drop_table('analysis_tasks')
    op.drop_table('paper_tasks')
