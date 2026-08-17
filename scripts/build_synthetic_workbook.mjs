import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "/Users/lz/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const outputDir = "outputs/01a00dd8-e16a-7eb1-a813-124071b37dc8";
const outputPath = `${outputDir}/employment_ai_demo.xlsx`;

const profiles = [
  { major: "数控加工", level: "中级", skills: "CNC操作|看图纸|卡尺", industry: "机械制造", salary: 6200, shift: "两班倒" },
  { major: "焊接技术", level: "高级", skills: "电焊|安全操作规程|工程图识读", industry: "装备制造", salary: 6800, shift: "白班" },
  { major: "机电设备", level: "中级", skills: "机修|电工维修|PLC编程", industry: "设备制造", salary: 7000, shift: "不限" },
  { major: "电气技术", level: "技师", skills: "维修电工|PLC|产线自动化", industry: "装备制造", salary: 7600, shift: "白班" },
  { major: "物流管理", level: "初级", skills: "仓储管理|Office|叉车", industry: "物流", salary: 4800, shift: "白班" },
  { major: "物流作业", level: "中级", skills: "叉车驾驶|生产安全|库存管理", industry: "物流仓储", salary: 5500, shift: "两班倒" },
  { major: "质量管理", level: "中级", skills: "质检|千分尺|机械识图", industry: "机械制造", salary: 5800, shift: "白班" },
  { major: "电子技术", level: "初级", skills: "组装|烙铁焊接|质量检测", industry: "电子装配", salary: 5000, shift: "两班倒" },
  { major: "电子商务", level: "初级", skills: "客服|Office|信息录入", industry: "客户服务", salary: 4700, shift: "白班" },
  { major: "计算机应用", level: "初级", skills: "数据录入|Excel|客户服务", industry: "现代服务", salary: 4600, shift: "白班" },
  { major: "电气自动化", level: "高级", skills: "自动化控制|PLC编程|电气检修", industry: "电子信息制造", salary: 7800, shift: "不限" },
  { major: "化工工艺", level: "中级", skills: "反应釜操作|安全生产|产品包装", industry: "化工", salary: 6500, shift: "三班倒" },
];

const regions = ["新区东片区", "新区西片区", "新区南片区"];
const towns = ["星河镇", "云岭镇", "青禾镇", "澄江街道"];
const villages = ["朝阳社区", "新桥村", "绿港社区", "和兴村", "明珠社区"];
const educations = ["初中", "高中", "中专", "大专", "本科"];
const statuses = ["求职中", "失业", "灵活就业", "求职中", "求职中", "在职"];

const personHeaders = [
  "person_id", "education", "major", "skill_level", "skills", "employment_status",
  "expected_salary_min", "expected_salary_max", "preferred_region",
  "preferred_industries", "special_tags", "town", "village", "years_experience",
  "available_shift", "source_updated_at",
];

const people = Array.from({ length: 1000 }, (_, offset) => {
  const index = offset + 1;
  const profile = profiles[offset % profiles.length];
  const salaryDelta = ((offset % 5) - 2) * 150;
  const region = regions[Math.floor(offset / profiles.length) % regions.length];
  const specialTags = index % 17 === 0 ? "转岗意愿" : index % 23 === 0 ? "返乡就业" : "普通模拟标签";
  return [
    `P${String(index).padStart(6, "0")}`,
    educations[(offset + (offset % 3)) % educations.length],
    profile.major,
    profile.level,
    profile.skills,
    statuses[offset % statuses.length],
    profile.salary - 700 + salaryDelta,
    profile.salary + 900 + salaryDelta,
    region,
    profile.industry,
    specialTags,
    towns[offset % towns.length],
    villages[offset % villages.length],
    Number((0.5 + (offset % 19) * 0.5).toFixed(1)),
    offset % 11 === 0 ? "不限" : profile.shift,
    new Date(Date.UTC(2026, 7, 1 + (offset % 15), 8, 0, 0)),
  ];
});

const jobHeaders = [
  "job_id", "employer_name", "job_title", "region", "salary_min", "salary_max",
  "education_min", "experience_min", "required_skills", "industry", "shift",
  "headcount", "valid_until", "status",
];

const jobs = [
  ["J001", "星澜精工有限公司", "CNC操作员", "新区东片区", 5800, 7800, "中专", 1, "数控机床操作|工程图识读|量具使用", "设备制造", "两班倒", 8],
  ["J002", "星澜精工有限公司", "电焊工", "新区东片区", 6200, 8500, "初中", 1, "气保焊|生产安全|看图纸", "装备制造", "白班", 6],
  ["J003", "星澜精工有限公司", "机修工", "新区东片区", 6500, 8800, "中专", 2, "机械维修|电气维修|PLC", "机械制造", "不限", 4],
  ["J004", "星澜精工有限公司", "电工", "新区西片区", 7000, 9200, "中专", 2, "电工维修|PLC编程|自动化控制", "装备制造", "白班", 3],
  ["J005", "云帆供应链有限公司", "仓管员", "新区西片区", 4300, 6000, "高中", 0.5, "仓储管理|Office|数据录入", "仓储物流", "白班", 10],
  ["J006", "云帆供应链有限公司", "叉车驾驶员", "新区西片区", 5000, 6800, "初中", 1, "叉车|安全操作规程|库存管理", "物流", "两班倒", 7],
  ["J007", "星澜精工有限公司", "质检员", "新区南片区", 5200, 7000, "中专", 1, "质量检测|卡尺|工程图识读", "机械制造", "白班", 5],
  ["J008", "青禾电子科技有限公司", "组装工", "新区南片区", 4500, 6200, "初中", 0, "生产装配|锡焊|质检", "电子装配", "两班倒", 18],
  ["J009", "云帆供应链有限公司", "客服代表", "新区南片区", 4200, 5800, "高中", 0, "电话客服|Office|信息录入", "商贸服务", "白班", 12],
  ["J010", "云帆供应链有限公司", "录入文员", "新区东片区", 4100, 5600, "高中", 0, "文员录入|Excel|客服", "现代服务", "白班", 9],
  ["J011", "青禾电子科技有限公司", "电气自动化技术员", "新区南片区", 6800, 9500, "大专", 1, "工业自动化|PLC编程|电气检修", "电子信息制造", "不限", 4],
  ["J012", "青禾电子科技有限公司", "化工生产操作员", "新区西片区", 5700, 7900, "高中", 1, "化工生产操作|生产安全|产品包装", "新材料", "三班倒", 6],
].map((row) => [...row, new Date(Date.UTC(2027, 11, 31)), "active"]);

function styleSheet(sheet, usedRange, headerRange, widths, dateRange, currencyRange) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  usedRange.format.font = { name: "Microsoft YaHei", size: 10, color: "#14213D" };
  usedRange.format.verticalAlignment = "center";
  headerRange.format = {
    fill: "#4338A8",
    font: { name: "Microsoft YaHei", size: 10, bold: true, color: "#FFFFFF" },
    rowHeight: 42,
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "medium", color: "#33218F" },
  };
  widths.forEach(([range, width]) => { sheet.getRange(range).format.columnWidth = width; });
  if (dateRange) sheet.getRange(dateRange).format.numberFormat = "yyyy-mm-dd hh:mm";
  if (currencyRange) sheet.getRange(currencyRange).format.numberFormat = "#,##0";
  usedRange.format.borders = {
    insideHorizontal: { style: "thin", color: "#E5EAF1" },
    bottom: { style: "thin", color: "#CBD5E2" },
  };
}

await fs.mkdir(outputDir, { recursive: true });
const workbook = Workbook.create();
const personSheet = workbook.worksheets.add("person_snapshot");
const jobSheet = workbook.worksheets.add("job_snapshot");

personSheet.getRange(`A1:P${people.length + 1}`).values = [personHeaders, ...people];
jobSheet.getRange(`A1:N${jobs.length + 1}`).values = [jobHeaders, ...jobs];

styleSheet(
  personSheet,
  personSheet.getRange(`A1:P${people.length + 1}`),
  personSheet.getRange("A1:P1"),
  [["A:A", 13], ["B:B", 9], ["C:C", 15], ["D:D", 10], ["E:E", 33], ["F:F", 13], ["G:H", 15], ["I:I", 15], ["J:J", 18], ["K:K", 16], ["L:M", 13], ["N:N", 14], ["O:O", 13], ["P:P", 20]],
  `P2:P${people.length + 1}`,
  `G2:H${people.length + 1}`,
);
styleSheet(
  jobSheet,
  jobSheet.getRange(`A1:N${jobs.length + 1}`),
  jobSheet.getRange("A1:N1"),
  [["A:A", 11], ["B:B", 24], ["C:C", 20], ["D:D", 15], ["E:F", 13], ["G:G", 11], ["H:H", 13], ["I:I", 34], ["J:J", 16], ["K:K", 11], ["L:L", 10], ["M:M", 15], ["N:N", 11]],
  "M2:M13",
  "E2:F13",
);
jobSheet.getRange("M2:M13").format.numberFormat = "yyyy-mm-dd";

personSheet.tables.add(`A1:P${people.length + 1}`, true, "PersonSnapshotTable").style = "TableStyleMedium4";
jobSheet.tables.add(`A1:N${jobs.length + 1}`, true, "JobSnapshotTable").style = "TableStyleMedium4";

personSheet.getRange("B2:B1001").dataValidation = { rule: { type: "list", values: ["小学", "初中", "高中", "中专", "大专", "本科", "硕士", "博士"] } };
personSheet.getRange("D2:D1001").dataValidation = { rule: { type: "list", values: ["无", "初级", "中级", "高级", "技师", "高级技师"] } };
personSheet.getRange("F2:F1001").dataValidation = { rule: { type: "list", values: ["在职", "求职中", "失业", "灵活就业"] } };
personSheet.getRange("O2:O1001").dataValidation = { rule: { type: "list", values: ["白班", "两班倒", "三班倒", "不限"] } };
jobSheet.getRange("G2:G13").dataValidation = { rule: { type: "list", values: ["小学", "初中", "高中", "中专", "大专", "本科", "硕士", "博士"] } };
jobSheet.getRange("K2:K13").dataValidation = { rule: { type: "list", values: ["白班", "两班倒", "三班倒", "不限"] } };
jobSheet.getRange("N2:N13").dataValidation = { rule: { type: "list", values: ["active", "closed"] } };

personSheet.getRange("F2:F1001").conditionalFormats.add("containsText", { text: "在职", format: { fill: "#FFF2CC", font: { color: "#8A5A00" } } });
jobSheet.getRange("N2:N13").conditionalFormats.add("containsText", { text: "closed", format: { fill: "#FCE8ED", font: { color: "#A61B42" } } });

const formulaAudit = await workbook.inspect({ kind: "formula", maxChars: 2500, options: { maxResults: 20 } });
const personAudit = await workbook.inspect({ kind: "region", sheetId: "person_snapshot", range: "A1:P8", maxChars: 5000 });
const jobAudit = await workbook.inspect({ kind: "region", sheetId: "job_snapshot", range: "A1:N13", maxChars: 7000 });

const personPreview = await workbook.render({ sheetName: "person_snapshot", range: "A1:P18", scale: 0.8, format: "png" });
const jobPreview = await workbook.render({ sheetName: "job_snapshot", range: "A1:N13", scale: 0.9, format: "png" });
await fs.writeFile(`${outputDir}/person_snapshot_preview.png`, new Uint8Array(await personPreview.arrayBuffer()));
await fs.writeFile(`${outputDir}/job_snapshot_preview.png`, new Uint8Array(await jobPreview.arrayBuffer()));

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

console.log(JSON.stringify({
  outputPath,
  people: people.length,
  jobs: jobs.length,
  formulaAudit: formulaAudit.ndjson || formulaAudit,
  personAudit: personAudit.ndjson || personAudit,
  jobAudit: jobAudit.ndjson || jobAudit,
}, null, 2));
