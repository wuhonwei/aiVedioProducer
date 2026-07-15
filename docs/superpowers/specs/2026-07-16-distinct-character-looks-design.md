# Distinct Character Looks（硬校验）设计

**日期:** 2026-07-16  
**状态:** 已实施  
**相关:** 青渡川-回归中 major 角色共用同一套兜底定妆（清俊/黑发/青灰布衣）

## Goal

保证每个 **major** 角色外貌与 `prompt_zh` 可区分：禁止全员同一模板；校验不通过则 **`06_enrich_assets` 失败**（方案 B）。

## Non-goals

- 不保证 LLM 艺术级定妆质量（只保证彼此可区分、尽量贴 evidence）
- 不强制改写 minor 角色（默认不校验）
- 不在本轮改前端 UI

## Current root cause

`ensure_character_card` 在 LLM 未返回字段时，对所有 `tier=major` 使用相同默认：

- face / hair / body / wardrobe / age_look 固定文案  
- `prompt_zh` 仅前缀名字不同 → UI 上看起来「所有人 prompt 一样」

## Approach（已选定：方案 1）

1. **启发式种子定妆**：每张卡从 entity `evidence`、aliases、name 生成可区分种子（年龄感、发式、服饰、标志物）。  
2. **LLM 批 enrich**：payload 附带每人 evidence；系统提示要求角色之间外貌/服装不得雷同。  
3. **合并**：LLM 字段优先；缺失处用该角色种子，**禁止**回退到「全体共用」的 major 模板。  
4. **硬校验**：major 角色两两比较外观签名与归一化 `prompt_zh`；冲突或空 → `raise`，enrich 失败。

## Heuristic rules（最小集）

从 name / aliases / evidence 推断（可叠加）：

| 信号 | 倾向 |
|------|------|
| 婆/奶/老/白发/苍苍 | 老年；白发/花白；粗布或家常衣 |
| 大人/知县/官服/衙役 | 中年吏员；官袍乌纱意象 |
| 伯/翁/老 | 中老年；布衣/笠帽 |
| 黑衣/蒙面 | 劲装黑袍；面罩可选 |
| 包袱/蓝布 | 行装；蓝布包/行囊作为标志 |
| 女名常见后缀（卿/娘等）且无老年信号 | 青年女性；发型/襦与男主种子不同默认 |
| 无信号 | 用 **角色名稳定哈希** 从小型服饰/发色池选，保证同批稳定且互不相同 |

种子必须写入 `inferred_fields`（如 `appearance.face`）并保留 `evidence` 列表。

## Distinctness validation

对 `assets["characters"]` 中 `tier == "major"`：

**签名** `look_signature(card)`（归一化拼接，去空白标点）：

- `age_look` + `appearance.face` + `appearance.hair` + `wardrobe.default` + `prompt_zh`（可去掉开头角色名再比）

规则：

- 每个 major 必须有非空 `prompt_zh` 与非空 `wardrobe.default` 或 `appearance.face`
- 任意两人 `look_signature` 相同，或「去掉名字后的 prompt 主干」相同 → **失败**
- 错误信息列出冲突的 `(name_a, name_b)` 与签名摘要

配置：默认开启硬校验；可用 `AIVP_ENRICH_REQUIRE_DISTINCT_CHARACTERS=true`（默认 true）。若设为 false，仅写 warning（调试用，产品默认不关）。

与既有 `enrich_strict`：硬校验失败始终视为 enrich 失败（产品选择 B），不依赖 `enrich_strict`。

## Pipeline 行为

- `build_assets` / `run_enrich` 在写盘前跑校验；失败不写半成品 `assets.json`（或写 `enrich_report.json` 记录失败原因后抛错，便于排查）。
- 用户可「强制重 enrich」重跑；人工在 overlay 改角色不在本校验路径（assembled bible overlay 另论）。

## Tests

1. 无 LLM：林砚之（蓝布包袱）/ 苏婆婆（白发粗布）/ 周大人（官服）→ 三套签名不同且 enrich 成功。  
2. 人为塞两张相同 appearance+prompt 的 major → 校验抛错。  
3. 既有 `test_build_assets_fills_major_prompt` 仍通过。

## Out of scope

Redis/Celery；locations/props 去重；前端展示 inferred 标签。
