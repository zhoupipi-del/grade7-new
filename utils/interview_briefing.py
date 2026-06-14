"""
AI 面谈战术简报生成器 — Phase 2 里子模块
供声呐大屏一键生成心理攻防约谈脚本
"""
import requests as _requests
from datetime import datetime
from flask import current_app
from models import db, Student, WingsScore, DisciplineRecord, RiskRecord, MentalHealthAssessment
from utils.llm_client import call_llm


def generate_student_briefing(student_id: int, class_id: int = None) -> dict:
    """
    生成学生面谈战术简报
    
    Args:
        student_id: 学生 ID
        class_id: 班级 ID（可选，用于权限校验）
    
    Returns:
        {
            "status": "success" | "error",
            "data": "简报内容（Markdown 格式）",
            "msg": "错误信息（如果存在）"
        }
    """
    # 1. 精准提取学生档案
    student = Student.query.get(student_id)
    if not student:
        return {"status": "error", "msg": f"学生档案不存在（ID: {student_id}）"}
    
    # 2. 多维特征向量采集
    # 2.1 五翼德育积分趋势（最近 5 条）
    wings_logs = WingsScore.query.filter_by(student_id=student_id)\
        .order_by(WingsScore.id.desc())\
        .limit(5)\
        .all()
    
    # 2.2 违纪记录（最近 3 条）
    disciplines = DisciplineRecord.query.filter_by(student_id=student_id)\
        .order_by(DisciplineRecord.id.desc())\
        .limit(3)\
        .all()
    
    # 2.3 AI 风险预警（最新一条）
    risk = RiskRecord.query.filter_by(student_id=student_id)\
        .order_by(RiskRecord.scan_date.desc())\
        .first()
    
    # 2.4 心理健康评估（最新一条）
    mental_health = MentalHealthAssessment.query.filter_by(student_id=student_id)\
        .order_by(MentalHealthAssessment.created_at.desc())\
        .first()
    
    # 3. 特征向量序列化（脱敏处理）
    wings_trend = [round(float(w.score), 1) for w in reversed(wings_logs)] if wings_logs else [0.0]
    wings_dimensions = {}
    for w in wings_logs:
        dim = w.dimension
        if dim not in wings_dimensions:
            wings_dimensions[dim] = []
        wings_dimensions[dim].append(round(float(w.score), 1))
    
    discipline_list = []
    for d in disciplines:
        discipline_list.append({
            "type": d.type,
            "category": d.category or "未分类",
            "description": d.description[:50] if d.description else "",
            "date": d.created_at.strftime("%m-%d") if d.created_at else ""
        })
    
    feature_vector = {
        "student_name": student.name,
        "class_name": student.class_.name if student.class_ else "未知",
        "wings_score_trend": wings_trend,
        "wings_dimensions": wings_dimensions,
        "discipline_count": len(disciplines),
        "recent_disciplines": discipline_list,
        "risk_level": risk.risk_level if risk else "green",
        "risk_score": round(float(risk.risk_probability), 4) if risk and risk.risk_probability else 0.0,
        "mental_health_level": mental_health.risk_level if mental_health else "unknown",
        "mental_health_score": round(float(mental_health.total_score), 1) if mental_health and mental_health.total_score else 0.0
    }
    
    # 4. 注入硬核的"资深德育专家"对抗性 Prompt
    system_prompt = """你是一位精通初中生心理学与行为修正的资深德育专家，拥有 15 年一线班主任经验。
    
你的核心能力：
1. 通过五翼德育积分的微小波动，精准判断学生的心理状态变化
2. 根据违纪类型与频率，识别学生的"心理防御机制"（高焦虑型 / 冷漠型 / 对抗型 / 表演型）
3. 设计"破冰切入点话术"，让班主任在前 5 分钟不提任何违纪与成绩，就能瓦解学生心理防线
4. 给出"家校共振熔断台阶"，让家长和学生的面子都能保住，达成行为修正闭环

输出要求：
- 直接输出核心话术与攻防策略，不要任何客套废话
- 话术要具体、可操作、有压迫感
- 用 Markdown 格式输出，包含三级标题
- 总字数控制在 500-800 字"""

    user_prompt = f"""## 学生基本信息
- 姓名：{feature_vector['student_name']}
- 班级：{feature_vector['class_name']}
- 五翼德育积分趋势（最近 5 次）：{feature_vector['wings_score_trend']}
- 各维度积分：{feature_vector['wings_dimensions']}
- 最近违纪记录（{feature_vector['discipline_count']} 条）：{feature_vector['recent_disciplines']}
- AI 风险预警等级：{feature_vector['risk_level']}
- AI 风险评分：{feature_vector['risk_score']}
- 心理健康评估等级：{feature_vector['mental_health_level']}
- 心理健康评分：{feature_vector['mental_health_score']}

## 任务
请基于以上硬核行为特征数据，为班主任量身定制一份高阶约谈战术简报。

要求包含以下三板块（用 Markdown 格式）：

### 1. 心理防御机制诊断
（分析该生当前是高焦虑型、冷漠型、对抗型还是表演型情绪，并给出判断依据）

### 2. 破冰切入点话术
（前 5 分钟不提任何违纪与成绩，如何用五翼积分中的"体/美/劳"维度快速切入并瓦解防线，给出具体话术示例）

### 3. 家校共振熔断台阶
（如何给家长和学生留足台阶，让家长会不变成"批斗会"，达成错题本与行为修正的闭环共识，给出具体话术示例）

---
请直接输出战术简报，不要有任何开场白或结尾客套。"""

    # 5. 安全调用大模型
    try:
        current_app.logger.info(f"开始为 student_id={student_id} 生成 AI 面谈简报")
        
        briefing_text = call_llm(
            system_prompt=system_prompt,
            user_content=user_prompt,
            temperature=0.3,  # 低随机性，确保战术脚本硬核且具备强可复制性
            max_tokens=1500,
            timeout=20
        )
        
        current_app.logger.info(f"student_id={student_id} 的 AI 面谈简报生成成功（长度: {len(briefing_text)} 字）")
        
        return {
            "status": "success",
            "data": briefing_text,
            "feature_vector": feature_vector  # 返回特征向量供前端展示
        }
    
    except _requests.exceptions.Timeout:
        current_app.logger.error(f"LLM 调用超时（student_id={student_id}）")
        return {"status": "error", "msg": "AI 战情推演超时，请稍后重试"}
    
    except Exception as e:
        current_app.logger.error(f"LLM 调用失败（student_id={student_id}）: {str(e)}")
        return {"status": "error", "msg": f"AI 战情推演失败: {str(e)}"}


def batch_generate_briefings(student_ids: list) -> dict:
    """
    批量生成面谈简报（后台任务使用）
    
    Args:
        student_ids: 学生 ID 列表
    
    Returns:
        {
            "total": 总数,
            "success": 成功数,
            "failed": 失败数,
            "results": [{"student_id": ..., "status": ..., "data": ...}, ...]
        }
    """
    results = []
    success_count = 0
    failed_count = 0
    
    for sid in student_ids:
        result = generate_student_briefing(sid)
        results.append({
            "student_id": sid,
            "status": result["status"],
            "data": result.get("data", ""),
            "msg": result.get("msg", "")
        })
        
        if result["status"] == "success":
            success_count += 1
        else:
            failed_count += 1
    
    return {
        "total": len(student_ids),
        "success": success_count,
        "failed": failed_count,
        "results": results
    }
