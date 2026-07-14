"""
AI 智能定向弱科诊断与细颗粒度学业处方持久化引擎 (Task #1396)

职责:
  1. 从 student_risk_alerts 捞出活动状态学业预警
  2. 解析 lineage_graph 中的 aggregation_metrics 层节点
  3. 对 Z-Score <= -1.0 的单科调用 DeepSeek 生成定向诊断与处方
  4. 幂等写入 student_weakness_prescriptions 表

调用契约:
  - 输入: 硬性注入学生的真实指标 (Z-Score / 原始分 / 赋分 / 排名)
  - 边界: 严禁套话, 必须给出可执行的 weakness_analysis + action_prescription
  - 输出: 严格 JSON, 可被 json.loads() 解析
"""

import json
import logging
import os

import httpx
from modules.data_adapter.models import StudentRiskAlert, StudentWeaknessPrescription
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# DeepSeek 配置 (从 systemd 环境变量读取, 与 ai_prescription/tasks.py 一致)
# ─────────────────────────────────────────────
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = os.environ.get(
    "LLM_API_URL",
    "https://api.deepseek.com/v1/chat/completions",
)
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

# 学科代码 -> 中文名称映射 (增强 LLM 上下文理解)
SUBJECT_CODE_TO_CN = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "history": "历史",
    "chemistry": "化学",
    "biology": "生物",
    "politics": "政治",
    "geography": "地理",
}

# 学科高考常见痛点 (辅助 LLM 精准归因)
SUBJECT_PAIN_POINTS = {
    "chinese": "阅读理解深层意蕴把握不足、文言文翻译断层、作文素材积累匮乏与结构松散",
    "math": "函数与导数综合应用薄弱、几何证明逻辑链断裂、概率统计建模能力缺失",
    "english": "听力信息捕捉滞后、完形填空上下文逻辑断裂、书面表达高级句式与词汇贫乏",
    "physics": "受力分析多体系统混乱、电磁场综合模型构建困难、实验设计变量控制意识淡薄",
    "history": "史料实证能力薄弱、历史阶段特征混淆、大题材料与课本知识迁移断裂",
    "chemistry": "氧化还原反应配平与电子转移计算困难、有机合成路径推导断层、实验现象归因偏差",
    "biology": "遗传系谱图概率计算混乱、光合呼吸综合模型理解不足、实验设计变量控制缺失",
    "politics": "时政热点与教材原理迁移薄弱、主观题逻辑层次混乱、经济计算题模型选择困难",
    "geography": "区域自然特征综合分析断裂、等值线判读与空间思维薄弱、人文地理因果关系倒置",
}


async def _call_deepseek_async(
    prompt: str,
    system_prompt: str,
    timeout: float = 30.0,
) -> dict:
    """
    异步调用 DeepSeek API, 返回解析后的 JSON dict

    与 ai_prescription/tasks.py 的 _call_deepseek() 保持一致的调用契约:
      - response_format: json_object
      - temperature: 0.3
      - max_tokens: 2048
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            LLM_API_URL,
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
                "max_tokens": 2048,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    result = json.loads(content)

    # 附带 token 消耗元数据
    usage = data.get("usage", {})
    result["_meta"] = {
        "model": LLM_MODEL,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }
    return result


async def run_ai_prescription_pipeline(
    db: AsyncSession,
    exam_id: int,
    school_id: int,
) -> dict:
    """
    【AI 智能弱科处方自动机】

    流程:
      1. 拉取当前考试所有活动状态学业预警
      2. 解析 lineage_graph 中 aggregation_metrics 层节点
      3. 对 Z-Score <= -1.0 的单科调用 DeepSeek 生成定向处方
      4. 幂等写入 student_weakness_prescriptions

    返回:
      {status, prescriptions_generated, errors, msg}
    """
    # 1. 拉取所有活动状态学业预警
    stmt = select(StudentRiskAlert).where(
        StudentRiskAlert.exam_id == exam_id,
        StudentRiskAlert.school_id == school_id,
        StudentRiskAlert.status == "active",
    )
    res = await db.execute(stmt)
    alerts = res.scalars().all()

    if not alerts:
        return {
            "status": "success",
            "prescriptions_generated": 0,
            "errors": 0,
            "msg": "未发现需要开启 AI 处方的学业危机样本",
        }

    generated_count = 0
    error_count = 0

    # 2. 遍历每个有学业风险的学生
    for alert in alerts:
        graph = alert.lineage_graph
        if not graph or "nodes" not in graph:
            continue

        # 提取 Layer 2 的所有学科聚合节点
        agg_nodes = [node for node in graph["nodes"] if node.get("layer") == "aggregation_metrics"]

        for node in agg_nodes:
            node_data = node.get("data", {})
            z_score = node_data.get("computed_z_score", 0.0)

            # 只有处于劣势区 (Z-Score <= -1.0) 的单科才值得开具 AI 处方
            if z_score > -1.0:
                continue

            # 从节点 ID 提取学科代码 (格式: L2_AGG_{stu_id}_{sub_code})
            node_id = node.get("id", "")
            parts = node_id.split("_")
            sub_code = parts[-1] if parts else "unknown"
            student_id = alert.student_id

            raw_score = node_data.get("raw_score")
            scaled_score = node_data.get("scaled_score")
            cohort_rank = node_data.get("cohort_rank")
            percentile = node_data.get("percentile")
            grade_level = node_data.get("grade_level")

            sub_cn = SUBJECT_CODE_TO_CN.get(sub_code, sub_code)
            pain_points = SUBJECT_PAIN_POINTS.get(sub_code, "该学科核心能力断层")

            # 3. 构建硬核数据锁定提示词
            system_prompt = (
                "你是 Wings 新高考数字化智能教研专家, "
                "擅长基于标准分(Z-Score)精确定位学生知识坍塌带并开具可执行处方。"
                "严格输出 JSON, 不要 Markdown 代码块。"
            )

            rank_str = f"第{cohort_rank}名" if cohort_rank else "未知"
            pct_str = f"{percentile:.1%}" if percentile else "未知"
            scaled_str = str(scaled_score) if scaled_score is not None else "该科不涉及等级赋分"
            grade_str = grade_level if grade_level else "不涉及"

            prompt = f"""\
# AI 智能定向弱科诊断请求

## 学生客观学业指标数据 (数据血缘硬锁)
- 学生匿名ID: {student_id}
- 诊断危机学科: {sub_cn} ({sub_code})
- 学科原始分: {raw_score}
- 走班赋分(若有): {scaled_str}
- 全校单科排名: {rank_str}
- 百分比排位: {pct_str}
- 等级(若有): {grade_str}
- 全校大盘标尺 Z-Score: {z_score} (注: 该指标表示该生偏离全校平均线的标准差, 负值越小代表越薄弱)

## 该学科高考常见痛点参考
{pain_points}

## 硬性生成契约
请严格按照以下 JSON 结构输出, 不要包含任何 markdown 块或多余文本, 确保能被 Python json.loads() 完美解析:
{{
  "weakness_analysis": "一句话指明由于该生的Z分跌至{z_score}, 暴露了他在{sub_cn}科目的核心能力断层与知识面坍塌点(结合该学科常见痛点作深度科学归因, 拒绝大话空话, 80-150字)",
  "action_prescription": "针对该生的具体指标, 开具3条具有强烈可执行性的、细颗粒度的补偿性学习行动处方。每条以'第一步:'/'第二步:'/'第三步:'开头, 精确到如何突破核心知识点断层, 200-350字"
}}
"""

            # 4. 调用 DeepSeek
            try:
                ai_data = await _call_deepseek_async(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    timeout=30.0,
                )

                # 提取代币消耗
                meta = ai_data.pop("_meta", {})

                weakness_analysis = ai_data.get("weakness_analysis", "诊断生成异常")
                action_prescription = ai_data.get("action_prescription", "处方生成异常")

                # 5. 幂等写入: 先删旧处方, flush, 再插入
                del_stmt = delete(StudentWeaknessPrescription).where(
                    StudentWeaknessPrescription.student_id == student_id,
                    StudentWeaknessPrescription.school_id == school_id,
                    StudentWeaknessPrescription.subject_code == sub_code,
                    StudentWeaknessPrescription.alert_id == alert.id,
                )
                await db.execute(del_stmt)
                await db.flush()

                prescription_obj = StudentWeaknessPrescription(
                    school_id=school_id,
                    alert_id=alert.id,
                    student_id=student_id,
                    subject_code=sub_code,
                    raw_score=raw_score,
                    scaled_score=scaled_score,
                    z_score=z_score,
                    weakness_analysis=weakness_analysis,
                    action_prescription=action_prescription,
                    model_metadata=meta,
                )
                db.add(prescription_obj)
                generated_count += 1

                logger.info(
                    "[AI-Prescription] 处方生成成功 | student=%s subject=%s Z=%.2f tokens=%s",
                    student_id,
                    sub_code,
                    z_score,
                    meta.get("total_tokens", 0),
                )

            except Exception as e:
                error_count += 1
                logger.warning(
                    "[AI-Prescription] 局部溃缩 | student=%s subject=%s: %s",
                    student_id,
                    sub_code,
                    str(e),
                )
                continue

    await db.commit()

    return {
        "status": "success",
        "prescriptions_generated": generated_count,
        "errors": error_count,
        "msg": (
            f"AI 智能定向学业处方派发完毕, "
            f"成功在数据血缘底座上长出 {generated_count} 条诊断决策资产"
            + (f", {error_count} 条局部溃缩" if error_count else "")
        ),
    }
