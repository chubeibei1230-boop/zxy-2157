import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date
import services
import storage
import json
import uuid

from models import AppealCorrection


def _uid():
    return f"X{uuid.uuid4().hex[:6]}"


def test_bugfix_1_multiple_appeals_independent_changes():
    """Bug 1：同一条记录多次申诉，每次申诉的积分变化说明应该独立"""
    print("\n" + "=" * 60)
    print("Bug 修复 1：多次申诉的积分变化说明独立计算")
    print("=" * 60)

    uid = _uid()
    project = services.create_project("多次申诉测试", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record, _, _ = services.create_record(
        participant_name=f"多次申诉_{uid}", participant_id=uid,
        project_id=project.project_id, service_date=date(2024, 11, 1),
        start_time="09:00", end_time="12:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record.record_id, "登记员")
    record, _ = services.review_record(record.record_id, "复核员", True)

    appeal1, _ = services.submit_appeal(
        record_id=record.record_id,
        appeal_reason="第一次申诉：质量应为良好",
        submitted_by=uid
    )
    correction1 = AppealCorrection(quality="良好", note="第一次更正：确认为良好")
    services.approve_appeal(appeal1.appeal_id, "管理员", correction1, "第一次通过")

    appeal2, _ = services.submit_appeal(
        record_id=record.record_id,
        appeal_reason="第二次申诉：时长应为4小时",
        submitted_by=uid
    )
    correction2 = AppealCorrection(duration_hours=4.0, note="第二次更正：时长修改为4小时")
    services.approve_appeal(appeal2.appeal_id, "管理员", correction2, "第二次通过")

    services.run_monthly_settlement("2024-11", "核算员")

    result = services.get_monthly_reconciliation(month="2024-11", participant_id=uid)
    stmt = result["statements"][0]
    detail = stmt["details"][0]

    print(f"记录当前状态: 质量={detail['quality']}, 时长={detail['duration_hours']}h, 最终积分={detail['final_points']}")
    print(f"申诉次数: {len(detail['appeal_changes'])}")
    for i, ac in enumerate(detail['appeal_changes']):
        print(f"  申诉{i+1}: {ac['status']}, 变更: {ac['changes']}")

    assert len(detail["appeal_changes"]) == 2, "应该有2条申诉记录"

    first_changes = detail["appeal_changes"][0]["changes"]
    second_changes = detail["appeal_changes"][1]["changes"]

    first_has_quality = any("质量等级" in c for c in first_changes)
    first_has_duration = any("服务时长" in c for c in first_changes)
    second_has_quality = any("质量等级" in c for c in second_changes)
    second_has_duration = any("服务时长" in c for c in second_changes)

    print(f"  第1次申诉包含质量变更: {first_has_quality}")
    print(f"  第1次申诉包含时长变更: {first_has_duration}")
    print(f"  第2次申诉包含质量变更: {second_has_quality}")
    print(f"  第2次申诉包含时长变更: {second_has_duration}")

    assert first_has_quality == True, "第1次申诉应该只包含质量变更"
    assert first_has_duration == False, "第1次申诉不应该包含第2次的时长变更"
    assert second_has_duration == True, "第2次申诉应该包含时长变更"

    print("    ✓ 多次申诉的积分变化说明独立验证通过")


def test_bugfix_2_official_vs_auto_settlement():
    """Bug 2：未执行正式月度核算时，不应显示为已核算状态"""
    print("\n" + "=" * 60)
    print("Bug 修复 2：区分正式核算与自动更新")
    print("=" * 60)

    uid = _uid()
    project = services.create_project("核算类型测试", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record, _, _ = services.create_record(
        participant_name=f"核算类型_{uid}", participant_id=uid,
        project_id=project.project_id, service_date=date(2024, 12, 1),
        start_time="09:00", end_time="12:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record.record_id, "登记员")
    record, _ = services.review_record(record.record_id, "复核员", True)

    result_before = services.get_monthly_reconciliation(month="2024-12", participant_id=uid)
    stmt_before = result_before["statements"][0]

    print(f"未执行正式核算前:")
    print(f"  has_official_settlement: {stmt_before['has_official_settlement']}")
    print(f"  official_snapshot: {stmt_before['official_settlement_snapshot']}")
    print(f"  auto_snapshot: {stmt_before['auto_settlement_snapshot'] is not None}")
    print(f"  consistency_check: {stmt_before['consistency_check']}")

    assert stmt_before["has_official_settlement"] == False, "未执行正式核算时 should be False"
    assert stmt_before["official_settlement_snapshot"] is None, "正式核算快照应该为 None"
    assert stmt_before["consistency_check"] is None, "未正式核算时不应有一致性检查"

    services.run_monthly_settlement("2024-12", "核算员")

    result_after = services.get_monthly_reconciliation(month="2024-12", participant_id=uid)
    stmt_after = result_after["statements"][0]

    print(f"执行正式核算后:")
    print(f"  has_official_settlement: {stmt_after['has_official_settlement']}")
    print(f"  official_snapshot is not None: {stmt_after['official_settlement_snapshot'] is not None}")
    print(f"  consistency_check: {stmt_after['consistency_check']['is_consistent']}")

    assert stmt_after["has_official_settlement"] == True, "执行正式核算后 should be True"
    assert stmt_after["official_settlement_snapshot"] is not None, "应有正式核算快照"
    assert stmt_after["official_settlement_snapshot"]["is_official"] == True
    assert stmt_after["consistency_check"] is not None, "正式核算后应有一致性检查"
    assert stmt_after["consistency_check"]["is_consistent"] == True

    print("    ✓ 正式核算与自动更新区分验证通过")


def test_bugfix_3_summary_from_official_settlement():
    """Bug 3：对账单主汇总应以正式月度核算结果为准"""
    print("\n" + "=" * 60)
    print("Bug 修复 3：主汇总优先采用正式月度核算结果")
    print("=" * 60)

    uid = _uid()
    project = services.create_project("汇总基准测试", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record, _, _ = services.create_record(
        participant_name=f"汇总基准_{uid}", participant_id=uid,
        project_id=project.project_id, service_date=date(2025, 1, 1),
        start_time="09:00", end_time="12:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record.record_id, "登记员")
    services.review_record(record.record_id, "复核员", True)

    result_before = services.get_monthly_reconciliation(month="2025-01", participant_id=uid)
    stmt_before = result_before["statements"][0]
    summary_before = stmt_before["summary"]
    print(f"未正式核算时: 记录数={summary_before['total_records']}, 最终积分={summary_before['final_points']}")
    print(f"  has_official_settlement: {stmt_before['has_official_settlement']}")

    assert stmt_before["has_official_settlement"] == False, "未正式核算时 should be False"
    assert summary_before["total_records"] == 1
    assert summary_before["final_points"] == 30.0

    services.run_monthly_settlement("2025-01", "核算员")

    result_after = services.get_monthly_reconciliation(month="2025-01", participant_id=uid)
    stmt_after = result_after["statements"][0]
    summary_after = stmt_after["summary"]
    official_after = stmt_after["official_settlement_snapshot"]
    print(f"执行正式核算后:")
    print(f"  汇总: 记录数={summary_after['total_records']}, 最终积分={summary_after['final_points']}")
    print(f"  正式核算快照: 记录数={official_after['total_records']}, 最终积分={official_after['final_points']}")
    print(f"  has_official_settlement: {stmt_after['has_official_settlement']}")

    assert stmt_after["has_official_settlement"] == True
    assert summary_after["total_records"] == official_after["total_records"]
    assert summary_after["final_points"] == official_after["final_points"]
    assert summary_after["base_points"] == official_after["base_points"]
    assert summary_after["deduction_points"] == official_after["deduction_points"]
    assert summary_after["total_hours"] == official_after["total_hours"]
    assert stmt_after["consistency_check"]["is_consistent"] == True

    print(f"\n验证：有正式核算时，主汇总与正式核算快照完全一致")

    old_final = official_after["final_points"]
    record2, _, _ = services.create_record(
        participant_name=f"汇总基准_{uid}", participant_id=uid,
        project_id=project.project_id, service_date=date(2025, 1, 15),
        start_time="14:00", end_time="17:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record2.record_id, "登记员")
    services.review_record(record2.record_id, "复核员", True)

    result_2 = services.get_monthly_reconciliation(month="2025-01", participant_id=uid)
    stmt_2 = result_2["statements"][0]
    summary_2 = stmt_2["summary"]
    official_2 = stmt_2["official_settlement_snapshot"]
    detail_count_2 = len(stmt_2["details"])
    print(f"\n新增一条记录后:")
    print(f"  明细数: {detail_count_2}")
    print(f"  正式核算快照: 记录数={official_2['total_records']}, 最终积分={official_2['final_points']}")
    print(f"  汇总: 记录数={summary_2['total_records']}, 最终积分={summary_2['final_points']}")

    assert summary_2["total_records"] == official_2["total_records"], "主汇总应与正式核算快照一致"
    assert summary_2["final_points"] == official_2["final_points"], "主汇总应与正式核算快照一致"

    print("    ✓ 主汇总优先采用正式月度核算结果验证通过")


def test_bugfix_4_latest_participant_name():
    """Bug 4：同一参与人ID同月有不同姓名时，对账单顶部应显示最新姓名"""
    print("\n" + "=" * 60)
    print("Bug 修复 4：对账单顶部显示最新姓名")
    print("=" * 60)

    uid = _uid()
    old_name = f"旧姓名_{uid}"
    new_name = f"新姓名_{uid}"
    project = services.create_project("姓名变更测试", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record1, _, _ = services.create_record(
        participant_name=old_name, participant_id=uid,
        project_id=project.project_id, service_date=date(2025, 2, 1),
        start_time="09:00", end_time="12:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record1.record_id, "登记员")
    services.review_record(record1.record_id, "复核员", True)

    record2, _, _ = services.create_record(
        participant_name=new_name, participant_id=uid,
        project_id=project.project_id, service_date=date(2025, 2, 15),
        start_time="14:00", end_time="17:00", duration_hours=3.0,
        registered_by="登记员", quality="合格"
    )
    services.submit_record(record2.record_id, "登记员")
    services.review_record(record2.record_id, "复核员", True)

    services.run_monthly_settlement("2025-02", "核算员")

    result = services.get_monthly_reconciliation(month="2025-02", participant_id=uid)
    stmt = result["statements"][0]

    print(f"旧姓名: {old_name}")
    print(f"新姓名: {new_name}")
    print(f"对账单顶部显示姓名: {stmt['participant_name']}")

    assert stmt["participant_name"] == new_name, "对账单顶部应该显示最新的姓名"
    assert len(stmt["details"]) == 2

    print("    ✓ 对账单顶部显示最新姓名验证通过")

    result_by_name = services.get_monthly_reconciliation(month="2025-02", participant_name=new_name[:4])
    print(f"按新姓名模糊查询，找到参与人数: {result_by_name['total_participants']}")
    assert result_by_name["total_participants"] >= 1, "按新姓名查询应该能查到"

    print("    ✓ 按新姓名查询验证通过")


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("# 开始验证 4 个 Bug 修复")
    print("#" * 60)

    try:
        test_bugfix_1_multiple_appeals_independent_changes()
        test_bugfix_2_official_vs_auto_settlement()
        test_bugfix_3_summary_from_official_settlement()
        test_bugfix_4_latest_participant_name()

        print("\n" + "=" * 60)
        print("所有 4 个 Bug 修复验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
