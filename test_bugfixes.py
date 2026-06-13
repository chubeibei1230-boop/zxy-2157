import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date
import services
import storage


def test_bugfix_1_anomaly_must_have_review_note():
    print("\n" + "=" * 60)
    print("Bug 1 验证：异常记录复核时必须填写处理原因")
    print("=" * 60)

    project = services.create_project("测试项目1", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record, warnings, error = services.create_record(
        participant_name="测试人员1",
        participant_id="T001",
        project_id=project.project_id,
        service_date=date(2024, 6, 1),
        start_time="09:00",
        end_time="12:00",
        duration_hours=3.0,
        registered_by="登记员",
        quality="良好"
    )

    record.warnings = ["疑似重复登记: 与其他记录时间重叠"]
    storage.save_record(record)
    services.submit_record(record.record_id, "登记员")

    print(f"\n记录ID: {record.record_id}")
    print(f"异常警告: {record.warnings}")

    record1, error1 = services.review_record(
        record_id=record.record_id,
        reviewer="复核员",
        approved=True,
        review_note=None
    )
    print(f"\n测试1：异常记录不填备注直接通过")
    print(f"    预期：失败，返回错误信息")
    print(f"    实际：{'失败: ' + error1 if error1 else '成功（BUG存在！）'}")
    assert error1 is not None, "BUG 1 未修复：异常记录应该需要填写复核备注"
    assert "必须填写复核备注" in error1
    print("    ✓ 验证通过：异常记录必须填写复核备注")

    record2, error2 = services.review_record(
        record_id=record.record_id,
        reviewer="复核员",
        approved=False,
        rejection_reason=None
    )
    print(f"\n测试2：退回记录不填原因")
    print(f"    预期：失败，返回错误信息")
    print(f"    实际：{'失败: ' + error2 if error2 else '成功（BUG存在！）'}")
    assert error2 is not None, "BUG 1 未修复：退回记录应该需要填写退回原因"
    assert "必须填写退回原因" in error2
    print("    ✓ 验证通过：退回记录必须填写退回原因")

    record3, error3 = services.review_record(
        record_id=record.record_id,
        reviewer="复核员",
        approved=True,
        review_note="经核实为不同服务地点，非重复登记，正常通过"
    )
    print(f"\n测试3：异常记录填写备注后通过")
    print(f"    预期：成功，状态变为已计入")
    print(f"    实际：{'成功，状态: ' + record3.status if record3 else '失败: ' + error3}")
    assert record3 is not None
    assert record3.status == "已计入"
    assert record3.review_note is not None
    print("    ✓ 验证通过：填写备注后可以正常通过")


def test_bugfix_2_change_project_clears_rules():
    print("\n" + "=" * 60)
    print("Bug 2 验证：退回后修改项目时，重新计算积分规则")
    print("=" * 60)

    project1 = services.create_project("旧项目", "")
    project2 = services.create_project("新项目（无规则）", "")
    services.create_point_rule(
        project_id=project1.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record, warnings, error = services.create_record(
        participant_name="测试人员2",
        participant_id="T002",
        project_id=project1.project_id,
        service_date=date(2024, 6, 2),
        start_time="09:00",
        end_time="12:00",
        duration_hours=3.0,
        registered_by="登记员",
        quality="良好"
    )
    services.submit_record(record.record_id, "登记员")

    record, error = services.review_record(
        record_id=record.record_id,
        reviewer="复核员",
        approved=False,
        rejection_reason="项目选择错误，需要修改"
    )
    print(f"\n记录ID: {record.record_id}")
    print(f"退回前项目: {project1.project_name}")
    print(f"退回前积分规则: {record.applicable_point_rule_id}")
    print(f"退回前预估积分: {record.calculated_points}")
    print(f"退回后状态: {record.status}")

    updated_record, error = services.update_record(
        record_id=record.record_id,
        project_id=project2.project_id
    )
    print(f"\n修改后项目: {project2.project_name}")
    print(f"修改后积分规则: {updated_record.applicable_point_rule_id}")
    print(f"修改后预估积分: {updated_record.calculated_points}")
    print(f"修改后警告: {updated_record.warnings}")

    assert updated_record.applicable_point_rule_id is None, "BUG 2 未修复：修改项目后应该清除旧的积分规则"
    assert updated_record.calculated_points is None, "BUG 2 未修复：修改项目后应该清除旧的预估积分"
    assert any("规则缺失" in w for w in updated_record.warnings), "BUG 2 未修复：新项目无规则应该有警告"
    print("    ✓ 验证通过：修改项目后正确清除旧积分规则并添加警告")


def test_bugfix_3_void_clears_empty_settlement():
    print("\n" + "=" * 60)
    print("Bug 3 验证：作废已计入记录后，清理无有效记录的月度核算")
    print("=" * 60)

    project = services.create_project("测试项目3", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    record, warnings, error = services.create_record(
        participant_name="测试人员3",
        participant_id="T003",
        project_id=project.project_id,
        service_date=date(2024, 6, 3),
        start_time="09:00",
        end_time="12:00",
        duration_hours=3.0,
        registered_by="登记员",
        quality="合格"
    )
    services.submit_record(record.record_id, "登记员")
    record, error = services.review_record(
        record_id=record.record_id,
        reviewer="复核员",
        approved=True
    )

    services.run_monthly_settlement("2024-06", "核算员")

    settlements_before = services.get_settlements(month="2024-06", participant_id="T003")
    print(f"\n作废前该月份核算记录数: {len(settlements_before)}")
    if settlements_before:
        s = settlements_before[0]
        print(f"    记录数: {s.total_records}, 总积分: {s.final_points}")

    voided_record = services.void_record(record.record_id, "复核员", "重复登记，作废处理")
    print(f"\n作废后记录状态: {voided_record.status}")

    settlements_after = services.get_settlements(month="2024-06", participant_id="T003")
    print(f"\n作废后该月份核算记录数: {len(settlements_after)}")
    if settlements_after:
        s = settlements_after[0]
        print(f"    记录数: {s.total_records}, 总积分: {s.final_points}")

    assert len(settlements_after) == 0, "BUG 3 未修复：作废后应该删除无有效记录的核算数据"
    print("    ✓ 验证通过：作废后正确删除无有效记录的月度核算数据")


def test_bugfix_4_anomaly_stats_filtered():
    print("\n" + "=" * 60)
    print("Bug 4 验证：待复核列表异常统计基于筛选后的结果")
    print("=" * 60)

    project = services.create_project("测试项目4", "")
    services.create_point_rule(
        project_id=project.project_id,
        base_points_per_hour=10.0,
        quality_multiplier={"优秀": 1.5, "良好": 1.2, "合格": 1.0, "不合格": 0.0},
        effective_date=date(2024, 1, 1),
        created_by="admin"
    )

    for i in range(3):
        record, _, _ = services.create_record(
            participant_name=f"测试人员{i+4}",
            participant_id=f"T00{i+4}",
            project_id=project.project_id,
            service_date=date(2024, 6, 10 + i),
            start_time="09:00",
            end_time="12:00",
            duration_hours=3.0,
            registered_by="登记员",
            quality="合格"
        )
        if i == 0:
            record.warnings = ["疑似重复登记: 测试"]
        elif i == 1:
            record.warnings = ["时长异常: 测试"]
        storage.save_record(record)
        services.submit_record(record.record_id, "登记员")

    record_july, _, _ = services.create_record(
        participant_name="7月测试人员",
        participant_id="T007",
        project_id=project.project_id,
        service_date=date(2024, 7, 1),
        start_time="09:00",
        end_time="12:00",
        duration_hours=3.0,
        registered_by="登记员",
        quality="合格"
    )
    record_july.warnings = ["疑似重复登记: 7月"]
    storage.save_record(record_july)
    services.submit_record(record_july.record_id, "登记员")

    result_all = services.query_pending_review()
    print(f"\n全部待复核:")
    print(f"    total: {result_all['total']}")
    print(f"    anomaly_stats: {result_all['anomaly_stats']}")

    result_june = services.query_pending_review(month="2024-06")
    print(f"\n筛选6月份:")
    print(f"    total: {result_june['total']}")
    print(f"    anomaly_stats: {result_june['anomaly_stats']}")

    assert result_june['anomaly_stats']['filtered_total'] == 3, "BUG 4 未修复：filtered_total 应该等于筛选后的总数"
    assert result_june['anomaly_stats']['duplicate_count'] == 1, "BUG 4 未修复：6月份应该只有1条重复登记"
    assert result_june['anomaly_stats']['duration_anomaly_count'] == 1, "BUG 4 未修复：6月份应该只有1条时长异常"
    assert result_june['anomaly_stats']['total_pending'] == 4, "total_pending 应该是全部待复核数"
    print("    ✓ 验证通过：异常统计正确基于筛选后的结果")


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("# 开始验证所有 Bug 修复")
    print("#" * 60)

    try:
        test_bugfix_1_anomaly_must_have_review_note()
        test_bugfix_2_change_project_clears_rules()
        test_bugfix_3_void_clears_empty_settlement()
        test_bugfix_4_anomaly_stats_filtered()

        print("\n" + "=" * 60)
        print("🎉 所有 Bug 修复验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
