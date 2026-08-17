# Excel数据契约 V1

导入文件必须是 `.xlsx`，且包含且仅依赖以下两个工作表。系统不会静默修复阻断错误；错误会定位到 Sheet、行、字段和错误码。

## person_snapshot

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `person_id` | 文本 | 是 | 脱敏稳定ID，批次内唯一 |
| `education` | 枚举 | 是 | 小学/初中/高中/中专/大专/本科/硕士/博士 |
| `major` | 文本 | 否 | 专业或培训方向 |
| `skill_level` | 枚举 | 否 | 无/初级/中级/高级/技师/高级技师 |
| `skills` | 文本 | 是 | 多技能用 `|` 分隔 |
| `employment_status` | 枚举 | 是 | 在职/求职中/失业/灵活就业 |
| `expected_salary_min/max` | 整数 | 是 | 月薪下限/上限，单位元 |
| `preferred_region` | 文本 | 是 | 期望工作区域 |
| `preferred_industries` | 文本 | 否 | 多行业用 `|` 分隔 |
| `special_tags` | 文本 | 否 | 仅模拟标签，不含真实特殊身份数据 |
| `town` / `village` | 文本 | 是/否 | 虚构属地 |
| `years_experience` | 数值 | 是 | 相关经验年限 |
| `available_shift` | 枚举 | 是 | 白班/两班倒/三班倒/不限 |
| `source_updated_at` | 时间 | 是 | 源快照更新时间 |

## job_snapshot

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `job_id` | 文本 | 是 | 岗位ID，批次内唯一 |
| `employer_name` | 文本 | 是 | 虚构企业名称 |
| `job_title` | 文本 | 是 | 岗位名称 |
| `region` | 文本 | 是 | 工作区域 |
| `salary_min/max` | 整数 | 是 | 月薪范围，单位元 |
| `education_min` | 枚举 | 是 | 最低学历 |
| `experience_min` | 数值 | 是 | 最低相关经验年限 |
| `required_skills` | 文本 | 是 | 多技能用 `|` 分隔 |
| `industry` | 文本 | 是 | 行业 |
| `shift` | 枚举 | 是 | 白班/两班倒/三班倒/不限 |
| `headcount` | 整数 | 是 | 招聘人数 |
| `valid_until` | 日期 | 是 | 岗位有效期 |
| `status` | 枚举 | 是 | active/closed |

## 安全边界

- 姓名、身份证、手机不进入本MVP数据契约，也不参与匹配。
- 模拟数据中的企业、地区、人员ID和业务结果均为虚构。
- 上传文件最大10MB；不接受含宏的 `.xlsm`、旧版 `.xls` 或其他格式。

