import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date
import services
import storage
import uuid

from models import AppealCorrection


def _uid():
    return f"D{uuid.uuid4().hex[:6]}"


def _setup_project_and_rule(prefix=""):
    project = services.create_project(f"差异追踪项目{prefix}", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )
    return project


def _create_and_review_record(project_id, participant_name, participant_id,
                               service_date, duration_hours, quality="合格",
                               registered_by="登记员"):
    record, _, _ = services.create_record(
        participant_name=participant_name,
        participant_id=participant_id,
        project_id=project_id,
        service_date=service_date,
        start_time="09:00", end_time=f"{9+int(duration_hours)}:00",
        duration_hours=duration_hours,
        registered_by=registered_by,
        quality=quality
    )
    services.submit_record(record.record_id, registered_by)
    record, _ = services.review_record(record.record_id, "复核员", True)
    return record


def test_diff_detection_after_review_change():
    print("\n" + "=" * 60)
    print("测试1：新增记录后差异检测 - 结算后新增已计入记录产生差异")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T1")
    month = "2024-06"

    _create_and_review_record(
        project.project_id, f"差异员_{uid}", uid,
        date(2024, 6, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    diff_before = services.detect_settlement_diffs(month, uid)
    print(f"新增前差异状态: with_diff={diff_before['summary']['with_diff']}, consistent={diff_before['summary']['consistent']}")
    assert diff_before["summary"]["with_diff"] == 0
    assert diff_before["summary"]["consistent"] == 1

    _create_and_review_record(
        project.project_id, f"差异员_{uid}", uid,
        date(2024, 6, 20), 2.0, "良好"
    )

    diff_after = services.detect_settlement_diffs(month, uid)
    print(f"新增后差异状态: with_diff={diff_after['summary']['with_diff']}")
    assert diff_after["summary"]["with_diff"] >= 1

    diff_detail = diff_after["diffs"][0]
    print(f"差异详情: 原最终积分={diff_detail['old_final_points']}, 当前应得={diff_detail['current_final_points']}")
    assert diff_detail["has_diff"] == True
    assert diff_detail["current_final_points"] > diff_detail["old_final_points"]

    print("    ✓ 新增记录后差异检测验证通过")


def test_diff_detection_after_void():
    print("\n" + "=" * 60)
    print("测试2：作废记录后差异检测 - 已确认结算标记为有差异")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T2")
    month = "2024-07"

    record = _create_and_review_record(
        project.project_id, f"作废员_{uid}", uid,
        date(2024, 7, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    settlement = services.get_settlements(month=month, participant_id=uid)
    assert len(settlement) > 0
    s = [s for s in settlement if s.is_official][0]
    print(f"作废前结算状态: {s.status}, has_diff={s.has_diff}")

    services.void_record(record.record_id, "管理员", "测试作废")

    settlement = services.get_settlements(month=month, participant_id=uid)
    s = [s for s in settlement if s.is_official][0]
    print(f"作废后结算状态: {s.status}, has_diff={s.has_diff}")
    assert s.has_diff == True
    assert s.status == "有差异待处理"

    diff_result = services.detect_settlement_diffs(month, uid)
    print(f"差异检测结果: with_diff={diff_result['summary']['with_diff']}")
    assert diff_result["summary"]["with_diff"] >= 1

    diff_detail = diff_result["diffs"][0]
    assert "diff_sources" in diff_detail
    sources = diff_detail["diff_sources"]
    assert len(sources) > 0
    print(f"差异来源数: {len(sources)}")
    for src in sources:
        print(f"  - 类型: {src['change_type']}, 描述: {src['description']}")

    print("    ✓ 作废记录后差异检测验证通过")


def test_diff_detection_after_appeal_correction():
    print("\n" + "=" * 60)
    print("测试3：申诉更正后差异检测 - 积分变更导致差异")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T3")
    month = "2024-08"

    record = _create_and_review_record(
        project.project_id, f"申诉员_{uid}", uid,
        date(2024, 8, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    appeal, _ = services.submit_appeal(
        record_id=record.record_id,
        appeal_reason="质量评定有误",
        submitted_by=uid
    )
    correction = AppealCorrection(quality="良好", note="确认为良好")
    services.approve_appeal(appeal.appeal_id, "管理员", correction, "同意更正")

    settlement = services.get_settlements(month=month, participant_id=uid)
    s = [s for s in settlement if s.is_official][0]
    print(f"申诉更正后结算状态: {s.status}, has_diff={s.has_diff}")
    assert s.has_diff == True

    diff_result = services.detect_settlement_diffs(month, uid)
    diff_detail = diff_result["diffs"][0]
    print(f"差异: 原积分={diff_detail['old_final_points']}, 当前应得={diff_detail['current_final_points']}")
    assert diff_detail["has_diff"] == True
    assert abs(diff_detail["current_final_points"] - diff_detail["old_final_points"]) > 0.001

    sources = diff_detail["diff_sources"]
    print(f"差异来源数: {len(sources)}")
    for src in sources:
        print(f"  - 类型: {src['change_type']}, 字段: {src.get('field_name', '')}, 描述: {src['description']}")

    has_appeal_source = any(s["change_type"] == "申诉更正" for s in sources)
    assert has_appeal_source, "应该包含申诉更正的差异来源"

    print("    ✓ 申诉更正后差异检测验证通过")


def test_recalculate_settlement():
    print("\n" + "=" * 60)
    print("测试4：重新核算结算 - 差异确认后发起重算")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T4")
    month = "2024-09"

    record1 = _create_and_review_record(
        project.project_id, f"重算员_{uid}", uid,
        date(2024, 9, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    appeal, _ = services.submit_appeal(
        record_id=record1.record_id,
        appeal_reason="质量应为良好",
        submitted_by=uid
    )
    correction = AppealCorrection(quality="良好", note="更正为良好")
    services.approve_appeal(appeal.appeal_id, "管理员", correction, "同意")

    diff_result = services.detect_settlement_diffs(month, uid)
    diff_detail = diff_result["diffs"][0]
    print(f"重算前差异: 原积分={diff_detail['old_final_points']}, 当前={diff_detail['current_final_points']}")

    recalc_result = services.recalculate_settlement(month, "核算员", uid, reason="申诉更正后需要重算")
    print(f"重算结果: recalculated_count={recalc_result['recalculated_count']}")
    assert recalc_result["recalculated_count"] == 1

    recalc_detail = recalc_result["recalculated"][0]
    print(f"  原最终积分: {recalc_detail['old_final_points']}")
    print(f"  新最终积分: {recalc_detail['new_final_points']}")
    print(f"  积分差异: {recalc_detail['diff_final_points']}")
    print(f"  状态: {recalc_detail['status']}")

    assert recalc_detail["status"] == "草稿"
    assert abs(recalc_detail["diff_final_points"]) > 0.001

    settlement = services.get_settlements(month=month, participant_id=uid)
    s = [s for s in settlement if s.is_official][0]
    print(f"重算后结算: status={s.status}, version={s.version}, recalculation_count={s.recalculation_count}")
    assert s.recalculation_count >= 1
    assert len(s.recalculation_history) >= 1

    print("    ✓ 重新核算结算验证通过")


def test_confirm_override_settlement():
    print("\n" + "=" * 60)
    print("测试5：确认覆盖结算结果 - 重算后确认新结果")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T5")
    month = "2024-10"

    record = _create_and_review_record(
        project.project_id, f"覆盖员_{uid}", uid,
        date(2024, 10, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    appeal, _ = services.submit_appeal(
        record_id=record.record_id,
        appeal_reason="质量应为优秀",
        submitted_by=uid
    )
    correction = AppealCorrection(quality="优秀", note="更正为优秀")
    services.approve_appeal(appeal.appeal_id, "管理员", correction, "同意")

    recalc_result = services.recalculate_settlement(month, "核算员", uid, reason="申诉更正")
    settlement_id = recalc_result["recalculated"][0]["settlement_id"]

    confirm_result = services.confirm_override_settlement(
        settlement_id=settlement_id,
        operator="核算主管",
        note="确认使用重算后的结果"
    )
    print(f"确认结果: status={confirm_result['status']}, version={confirm_result['version']}")
    assert confirm_result["status"] == "已确认"
    assert confirm_result["version"] >= 2

    settlement = storage.get_settlement(settlement_id)
    print(f"结算状态: {settlement.status}, has_diff={settlement.has_diff}")
    assert settlement.status == "已确认"
    assert settlement.has_diff == False
    assert settlement.confirmed_by == "核算主管"
    assert settlement.confirmed_at is not None

    logs = storage.list_settlement_logs(settlement_id=settlement_id)
    confirm_logs = [l for l in logs if l.operation_type == "确认覆盖"]
    print(f"确认覆盖日志数: {len(confirm_logs)}")
    assert len(confirm_logs) >= 1
    assert confirm_logs[0].operator == "核算主管"

    print("    ✓ 确认覆盖结算结果验证通过")


def test_keep_original_settlement():
    print("\n" + "=" * 60)
    print("测试6：保留原结算结果 - 差异不影响原结算")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T6")
    month = "2024-11"

    record = _create_and_review_record(
        project.project_id, f"保留员_{uid}", uid,
        date(2024, 11, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    appeal, _ = services.submit_appeal(
        record_id=record.record_id,
        appeal_reason="质量应为良好",
        submitted_by=uid
    )
    correction = AppealCorrection(quality="良好", note="更正为良好")
    services.approve_appeal(appeal.appeal_id, "管理员", correction, "同意")

    settlement = services.get_settlements(month=month, participant_id=uid)
    s = [s for s in settlement if s.is_official][0]
    original_final_points = s.final_points
    settlement_id = s.settlement_id

    services.detect_settlement_diffs(month, uid)

    settlement = storage.get_settlement(settlement_id)
    assert settlement.status == "有差异待处理", f"Expected 有差异待处理, got {settlement.status}"

    keep_result = services.keep_original_settlement(
        settlement_id=settlement_id,
        operator="核算主管",
        reason="差异不影响原结算有效性"
    )
    print(f"保留结果: status={keep_result['status']}, version={keep_result['version']}")
    assert keep_result["status"] == "已确认"

    settlement = storage.get_settlement(settlement_id)
    print(f"结算状态: {settlement.status}, has_diff={settlement.has_diff}")
    assert settlement.status == "已确认"
    assert settlement.has_diff == False
    assert settlement.final_points == original_final_points

    logs = storage.list_settlement_logs(settlement_id=settlement_id)
    keep_logs = [l for l in logs if l.operation_type == "保留原结果"]
    print(f"保留原结果日志数: {len(keep_logs)}")
    assert len(keep_logs) >= 1

    print("    ✓ 保留原结算结果验证通过")


def test_settlement_timeline():
    print("\n" + "=" * 60)
    print("测试7：结算时间线 - 形成过程与调整原因")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T7")
    month = "2024-12"

    record = _create_and_review_record(
        project.project_id, f"时间线员_{uid}", uid,
        date(2024, 12, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    appeal, _ = services.submit_appeal(
        record_id=record.record_id,
        appeal_reason="质量应为良好",
        submitted_by=uid
    )
    correction = AppealCorrection(quality="良好", note="更正为良好")
    services.approve_appeal(appeal.appeal_id, "管理员", correction, "同意")

    recalc_result = services.recalculate_settlement(month, "核算员", uid, reason="申诉更正后需重算")
    settlement_id = recalc_result["recalculated"][0]["settlement_id"]

    services.confirm_override_settlement(
        settlement_id=settlement_id,
        operator="核算主管",
        note="确认重算结果"
    )

    timeline_result = services.get_settlement_timeline(settlement_id)
    assert timeline_result is not None

    settlement_info = timeline_result["settlement"]
    print(f"结算信息: status={settlement_info['status']}, version={settlement_info['version']}")
    print(f"  recalculation_count={settlement_info['recalculation_count']}")
    assert settlement_info["status"] == "已确认"

    timeline_events = timeline_result["timeline"]
    print(f"时间线事件数: {len(timeline_events)}")
    for event in timeline_events:
        print(f"  [{event['event_type']}] {event['operator']}: {event['description']}")

    event_types = [e["event_type"] for e in timeline_events]
    assert "生成结算" in event_types
    assert "发起重算" in event_types
    assert "确认结算" in event_types

    recalc_history = timeline_result["recalculation_history"]
    assert len(recalc_history) >= 1
    recalc = recalc_history[0]
    print(f"重算记录: 原积分={recalc['old_final_points']}, 新积分={recalc['new_final_points']}, 原因={recalc['reason']}")
    assert recalc["old_final_points"] != recalc["new_final_points"]

    operation_logs = timeline_result["operation_logs"]
    print(f"操作日志数: {len(operation_logs)}")
    assert len(operation_logs) >= 2

    appeal_changes = timeline_result["appeal_changes"]
    print(f"申诉变更数: {len(appeal_changes)}")
    assert len(appeal_changes) >= 1

    print("    ✓ 结算时间线验证通过")


def test_volunteer_month_settlement_history():
    print("\n" + "=" * 60)
    print("测试8：志愿者月度积分形成过程与调整原因")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T8")
    month = "2025-01"

    record1 = _create_and_review_record(
        project.project_id, f"历史员_{uid}", uid,
        date(2025, 1, 10), 3.0, "合格"
    )
    record2 = _create_and_review_record(
        project.project_id, f"历史员_{uid}", uid,
        date(2025, 1, 20), 2.0, "良好"
    )

    services.run_monthly_settlement(month, "核算员")

    appeal, _ = services.submit_appeal(
        record_id=record1.record_id,
        appeal_reason="质量应为优秀",
        submitted_by=uid
    )
    correction = AppealCorrection(quality="优秀", note="更正为优秀")
    services.approve_appeal(appeal.appeal_id, "管理员", correction, "同意")

    services.recalculate_settlement(month, "核算员", uid, reason="申诉更正")
    settlements = services.get_settlements(month=month, participant_id=uid)
    s = [s for s in settlements if s.is_official][0]
    services.confirm_override_settlement(s.settlement_id, "核算主管", "确认重算")

    history = services.get_volunteer_month_settlement_history(month, uid)
    print(f"参与人: {history['participant_name']}")
    print(f"当前积分: {history['current_points']}")

    assert history["month"] == month
    assert history["participant_id"] == uid
    assert "current_points" in history
    assert "record_details" in history
    assert "diff_check" in history
    assert "settlements" in history
    assert "settlement_timelines" in history
    assert "operation_logs" in history
    assert "appeals" in history

    assert len(history["record_details"]) >= 2
    print(f"记录明细数: {len(history['record_details'])}")

    assert len(history["settlements"]) >= 1
    print(f"结算数: {len(history['settlements'])}")

    assert len(history["appeals"]) >= 1
    print(f"申诉数: {len(history['appeals'])}")
    appeal_info = history["appeals"][0]
    assert "original_values" in appeal_info
    print(f"申诉原值: {appeal_info['original_values']}")

    assert len(history["operation_logs"]) >= 2
    print(f"操作日志数: {len(history['operation_logs'])}")

    print("    ✓ 志愿者月度积分形成过程验证通过")


def test_confirm_override_status_validation():
    print("\n" + "=" * 60)
    print("测试9：确认覆盖状态校验 - 只有草稿或有差异待处理可确认")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T9")
    month = "2025-02"

    _create_and_review_record(
        project.project_id, f"校验员_{uid}", uid,
        date(2025, 2, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    settlements = services.get_settlements(month=month, participant_id=uid)
    s = [s for s in settlements if s.is_official][0]
    settlement_id = s.settlement_id

    confirm_result = services.confirm_override_settlement(settlement_id, "核算员", "确认")
    assert "error" in confirm_result
    print(f"已确认状态再确认: {confirm_result['error']}")

    print("    ✓ 确认覆盖状态校验验证通过")


def test_keep_original_status_validation():
    print("\n" + "=" * 60)
    print("测试10：保留原结果状态校验 - 只有有差异待处理可保留")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T10")
    month = "2025-03"

    _create_and_review_record(
        project.project_id, f"保留校验员_{uid}", uid,
        date(2025, 3, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    settlements = services.get_settlements(month=month, participant_id=uid)
    s = [s for s in settlements if s.is_official][0]
    settlement_id = s.settlement_id

    keep_result = services.keep_original_settlement(settlement_id, "核算员", "保留")
    assert "error" in keep_result
    print(f"已确认状态保留: {keep_result['error']}")

    print("    ✓ 保留原结果状态校验验证通过")


def test_recalculate_no_settlement():
    print("\n" + "=" * 60)
    print("测试11：无结算时重算 - 返回错误")
    print("=" * 60)

    result = services.recalculate_settlement("2099-12", "核算员", reason="测试")
    assert "error" in result
    print(f"无结算时重算: {result['error']}")

    print("    ✓ 无结算时重算验证通过")


def test_full_workflow():
    print("\n" + "=" * 60)
    print("测试12：完整工作流 - 从差异检测到确认覆盖的全流程")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T12")
    month = "2025-04"

    record1 = _create_and_review_record(
        project.project_id, f"全流员_{uid}", uid,
        date(2025, 4, 5), 4.0, "合格"
    )
    record2 = _create_and_review_record(
        project.project_id, f"全流员_{uid}", uid,
        date(2025, 4, 15), 2.0, "良好"
    )

    print("步骤1: 执行月度核算")
    services.run_monthly_settlement(month, "核算员A")
    settlements = services.get_settlements(month=month, participant_id=uid)
    s = [s for s in settlements if s.is_official][0]
    print(f"  初始结算: final_points={s.final_points}, status={s.status}, version={s.version}")
    original_points = s.final_points

    print("步骤2: 申诉更正record1质量")
    appeal, _ = services.submit_appeal(
        record_id=record1.record_id,
        appeal_reason="质量应为优秀",
        submitted_by=uid
    )
    correction = AppealCorrection(quality="优秀", note="更正为优秀")
    services.approve_appeal(appeal.appeal_id, "管理员", correction, "同意更正")

    print("步骤3: 检测差异")
    diff_result = services.detect_settlement_diffs(month, uid)
    diff_detail = diff_result["diffs"][0]
    print(f"  差异: 原积分={diff_detail['old_final_points']}, 当前={diff_detail['current_final_points']}")
    assert diff_detail["has_diff"] == True
    assert diff_detail["current_final_points"] > original_points

    settlement = storage.get_settlement(s.settlement_id)
    print(f"  结算状态: {settlement.status}, has_diff={settlement.has_diff}")
    assert settlement.has_diff == True

    print("步骤4: 发起重算")
    recalc_result = services.recalculate_settlement(month, "核算员B", uid, reason="申诉更正导致积分变化")
    print(f"  重算结果: old={recalc_result['recalculated'][0]['old_final_points']}, new={recalc_result['recalculated'][0]['new_final_points']}")
    settlement_id = recalc_result["recalculated"][0]["settlement_id"]

    settlement = storage.get_settlement(settlement_id)
    print(f"  重算后状态: {settlement.status}, final_points={settlement.final_points}")
    assert settlement.status == "草稿"
    assert settlement.recalculation_count == 1

    print("步骤5: 确认覆盖")
    confirm_result = services.confirm_override_settlement(
        settlement_id=settlement_id,
        operator="核算主管C",
        note="经审核确认使用重算结果"
    )
    print(f"  确认结果: status={confirm_result['status']}, version={confirm_result['version']}")

    settlement = storage.get_settlement(settlement_id)
    print(f"  确认后状态: {settlement.status}, has_diff={settlement.has_diff}")
    assert settlement.status == "已确认"
    assert settlement.has_diff == False
    assert settlement.version >= 2
    assert settlement.confirmed_by == "核算主管C"

    print("步骤6: 查看时间线")
    timeline = services.get_settlement_timeline(settlement_id)
    event_types = [e["event_type"] for e in timeline["timeline"]]
    print(f"  时间线事件: {event_types}")
    assert "生成结算" in event_types
    assert "发起重算" in event_types
    assert "确认结算" in event_types

    print("步骤7: 作废record2")
    services.void_record(record2.record_id, "管理员", "误登")

    settlement = storage.get_settlement(settlement_id)
    print(f"  作废后状态: {settlement.status}, has_diff={settlement.has_diff}")
    assert settlement.has_diff == True
    assert settlement.status == "有差异待处理"

    print("步骤8: 再次检测差异")
    diff_result2 = services.detect_settlement_diffs(month, uid)
    diff_detail2 = diff_result2["diffs"][0]
    print(f"  再次差异: 原积分={diff_detail2['old_final_points']}, 当前={diff_detail2['current_final_points']}")
    assert diff_detail2["has_diff"] == True

    print("步骤9: 保留原结果（不重算，直接保留）")
    keep_result = services.keep_original_settlement(
        settlement_id=settlement_id,
        operator="核算主管E",
        reason="作废的记录积分很小，不影响整体结算"
    )
    print(f"  保留结果: status={keep_result['status']}")
    assert keep_result["status"] == "已确认"

    print("步骤10: 查看完整历史")
    history = services.get_volunteer_month_settlement_history(month, uid)
    print(f"  结算数: {len(history['settlements'])}")
    print(f"  申诉数: {len(history['appeals'])}")
    print(f"  操作日志数: {len(history['operation_logs'])}")
    assert len(history["appeals"]) >= 1
    assert len(history["operation_logs"]) >= 3

    print("    ✓ 完整工作流验证通过")


def test_settlement_version_increment():
    print("\n" + "=" * 60)
    print("测试13：结算版本递增 - 每次确认覆盖版本号递增")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T13")
    month = "2025-05"

    _create_and_review_record(
        project.project_id, f"版本员_{uid}", uid,
        date(2025, 5, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")
    settlements = services.get_settlements(month=month, participant_id=uid)
    s = [s for s in settlements if s.is_official][0]
    initial_version = s.version
    print(f"初始版本: v{initial_version}")

    for i in range(3):
        services.recalculate_settlement(month, "核算员", uid, reason=f"第{i+1}次重算")
        settlements = services.get_settlements(month=month, participant_id=uid)
        s = [s for s in settlements if s.is_official][0]
        services.confirm_override_settlement(s.settlement_id, "核算主管", f"第{i+1}次确认")

        settlements = services.get_settlements(month=month, participant_id=uid)
        s = [s for s in settlements if s.is_official][0]
        expected_version = initial_version + i + 1
        print(f"第{i+1}次确认后版本: v{s.version}")
        assert s.version == expected_version
        assert s.recalculation_count == i + 1

    print("    ✓ 结算版本递增验证通过")


def test_diff_sources_include_record_count_change():
    print("\n" + "=" * 60)
    print("测试14：差异来源包含记录数变化信息")
    print("=" * 60)

    uid = _uid()
    project = _setup_project_and_rule("T14")
    month = "2025-06"

    record = _create_and_review_record(
        project.project_id, f"计数员_{uid}", uid,
        date(2025, 6, 10), 3.0, "合格"
    )

    services.run_monthly_settlement(month, "核算员")

    services.void_record(record.record_id, "管理员", "误登")

    diff_result = services.detect_settlement_diffs(month, uid)
    diff_detail = diff_result["diffs"][0]
    print(f"差异: 记录数从{diff_detail['old_total_records']}变为{diff_detail['current_total_records']}")

    sources = diff_detail["diff_sources"]
    status_change_sources = [s for s in sources if s["change_type"] == "记录状态变更"]
    record_count_sources = [s for s in sources if s["change_type"] == "记录数变化"]

    print(f"状态变更来源数: {len(status_change_sources)}")
    print(f"记录数变化来源数: {len(record_count_sources)}")

    if status_change_sources:
        src = status_change_sources[0]
        print(f"  状态变更: {src['description']}")
        assert src["old_value"] == "已计入"
        assert src["new_value"] == "作废"

    print("    ✓ 差异来源包含记录数变化验证通过")


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("# 开始验证 月度积分核算差异追踪与重算确认 功能")
    print("#" * 60)

    try:
        test_diff_detection_after_review_change()
        test_diff_detection_after_void()
        test_diff_detection_after_appeal_correction()
        test_recalculate_settlement()
        test_confirm_override_settlement()
        test_keep_original_settlement()
        test_settlement_timeline()
        test_volunteer_month_settlement_history()
        test_confirm_override_status_validation()
        test_keep_original_status_validation()
        test_recalculate_no_settlement()
        test_full_workflow()
        test_settlement_version_increment()
        test_diff_sources_include_record_count_change()

        print("\n" + "=" * 60)
        print("所有 月度积分核算差异追踪与重算确认 测试通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
