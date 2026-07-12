# -*- coding: utf-8 -*-
"""
tests/test_legacy_etl.py — 旧数据 ETL 脚本测试

覆盖：影子存储/字段映射/性别转换/血缘标记/按需激活等核心逻辑。

运行方式：
    cd backend
    python -m pytest tests/test_legacy_etl.py -v
"""

import pytest
import json
import os
import tempfile
from datetime import datetime

# ── 测试血缘标记 ──

class TestLineageMarker:

    def test_lineage_marker_creation(self):
        from scripts.legacy_data_etl import LineageMarker

        marker = LineageMarker(
            source_system="legacy_flask",
            source_table="students",
            source_id="S001",
            target_table="students",
            target_id="101",
            batch_id="20260710_001",
        )

        assert marker.source_system == "legacy_flask"
        assert marker.sync_status == "legacy"
        assert marker.to_lineage_ref() == "legacy_flask:students:S001"

    def test_lineage_marker_to_dict(self):
        from scripts.legacy_data_etl import LineageMarker

        marker = LineageMarker(
            source_system="legacy_flask",
            source_table="classes",
            source_id="C001",
        )
        d = marker.to_dict()
        assert d["source_system"] == "legacy_flask"
        assert d["sync_status"] == "legacy"
        assert "imported_at" in d


# ── 测试影子存储 ──

class TestShadowStore:

    def test_save_and_load_students(self):
        from scripts.legacy_data_etl import ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShadowStore(tmpdir)

            students = [
                {"name": "张三", "student_no": "S001", "sync_status": "legacy"},
                {"name": "李四", "student_no": "S002", "sync_status": "legacy"},
            ]

            store.save_students(students, "batch001")

            loaded = store.load_students("batch001")
            assert len(loaded) == 2
            assert loaded[0]["name"] == "张三"

    def test_find_student(self):
        from scripts.legacy_data_etl import ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShadowStore(tmpdir)

            students = [
                {"name": "张三", "student_no": "S001"},
                {"name": "李四", "student_no": "S002"},
            ]
            store.save_students(students, "batch001")

            # 按学号查找
            found = store.find_student("S002")
            assert found is not None
            assert found["name"] == "李四"

            # 按姓名查找
            found = store.find_student("张三")
            assert found is not None
            assert found["student_no"] == "S001"

            # 查找不存在
            found = store.find_student("不存在")
            assert found is None


# ── 测试数据转换 ──

class TestDataTransform:

    def test_transform_students_gender(self):
        """性别字段转换"""
        from scripts.legacy_data_etl import ETLPipeline, ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShadowStore(tmpdir)
            etl = ETLPipeline(store)

            raw = [
                {"姓名": "张三", "性别": "男", "学号": "S001"},
                {"姓名": "李四", "性别": "女", "学号": "S002"},
                {"姓名": "王五", "性别": "M", "学号": "S003"},
            ]

            transformed = etl.transform_students(raw)

            assert transformed[0]["gender"] == "M"
            assert transformed[1]["gender"] == "F"
            assert transformed[2]["gender"] == "M"

    def test_transform_students_field_mapping(self):
        """字段名映射"""
        from scripts.legacy_data_etl import ETLPipeline, ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShadowStore(tmpdir)
            etl = ETLPipeline(store)

            raw = [
                {"姓名": "张三", "学号": "S001", "班级": "2501", "民族": "汉"},
            ]

            transformed = etl.transform_students(raw)

            assert transformed[0]["name"] == "张三"
            assert transformed[0]["student_no"] == "S001"
            assert transformed[0]["class_name"] == "2501"
            assert transformed[0]["nationality"] == "汉"

    def test_transform_students_skip_empty_name(self):
        """姓名为空的记录跳过"""
        from scripts.legacy_data_etl import ETLPipeline, ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShadowStore(tmpdir)
            etl = ETLPipeline(store)

            raw = [
                {"姓名": "张三", "学号": "S001"},
                {"姓名": "", "学号": "S002"},  # 空姓名
                {"姓名": None, "学号": "S003"},  # None姓名
            ]

            transformed = etl.transform_students(raw)
            assert len(transformed) == 1
            assert transformed[0]["name"] == "张三"

    def test_transform_students_lineage_marking(self):
        """血缘标记"""
        from scripts.legacy_data_etl import ETLPipeline, ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShadowStore(tmpdir)
            etl = ETLPipeline(store)

            raw = [{"姓名": "张三", "学号": "S001"}]
            transformed = etl.transform_students(raw)

            assert transformed[0]["sync_status"] == "legacy"
            assert "lineage_ref" in transformed[0]
            assert "legacy_flask:students:" in transformed[0]["lineage_ref"]
            assert "batch_id" in transformed[0]

    def test_transform_students_date_parsing(self):
        """日期格式解析"""
        from scripts.legacy_data_etl import ETLPipeline, ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShadowStore(tmpdir)
            etl = ETLPipeline(store)

            raw = [
                {"姓名": "张三", "出生日期": "2010-03-15"},
                {"姓名": "李四", "出生日期": "2010/03/16"},
            ]

            transformed = etl.transform_students(raw)
            assert transformed[0]["birth_date"] == "2010-03-15"
            assert transformed[1]["birth_date"] == "2010-03-16"


# ── 测试按需激活 ──

class TestActivateStudent:

    def test_activate_student_found(self):
        from scripts.legacy_data_etl import ETLPipeline, ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShadowStore(tmpdir)
            etl = ETLPipeline(store)

            students = [{"name": "张三", "student_no": "S001", "sync_status": "legacy"}]
            store.save_students(students, etl.batch_id)

            result = etl.activate_student("S001")

            assert result is not None
            assert result["name"] == "张三"
            assert result["sync_status"] == "legacy"
            assert "activated_at" in result
            assert "lineage_ref" in result

    def test_activate_student_not_found(self):
        from scripts.legacy_data_etl import ETLPipeline, ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShadowStore(tmpdir)
            etl = ETLPipeline(store)

            result = etl.activate_student("NOT_EXIST")
            assert result is None


# ── 测试完整 ETL 流程 ──

class TestFullETL:

    def test_full_etl_with_csv(self):
        """CSV 完整 ETL 流程"""
        from scripts.legacy_data_etl import ETLPipeline, ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试 CSV
            csv_path = os.path.join(tmpdir, "test_students.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("姓名,学号,性别,班级\n")
                f.write("张三,S001,男,2501\n")
                f.write("李四,S002,女,2501\n")
                f.write("王五,S003,男,2502\n")

            store = ShadowStore(os.path.join(tmpdir, "shadow"))
            etl = ETLPipeline(store)

            report = etl.run_full_etl(csv_path, "students")

            assert report["raw_count"] == 3
            assert report["transformed_count"] == 3
            assert os.path.exists(report["shadow_path"])

            # 验证影子存储
            loaded = store.load_students(etl.batch_id)
            assert len(loaded) == 3
            assert loaded[0]["name"] == "张三"
            assert loaded[0]["gender"] == "M"

    def test_verify_import(self):
        """验证导入"""
        from scripts.legacy_data_etl import ETLPipeline, ShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("姓名,学号\n")
                f.write("张三,S001\n")
                f.write("李四,S002\n")

            store = ShadowStore(os.path.join(tmpdir, "shadow"))
            etl = ETLPipeline(store)

            etl.run_full_etl(csv_path, "students")

            result = etl.verify_import(etl.batch_id)

            assert result["match"] == True
            assert result["all_marked_legacy"] == True
