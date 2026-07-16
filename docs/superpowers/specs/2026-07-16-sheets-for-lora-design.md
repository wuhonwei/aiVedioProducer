# Sheets as LoRA training source

三视图 + 表情表单独生成到 `sheets/`，并带 `.txt` caption，可勾选进入 `curated/` 作为 LoRA 主训练集。

## Flow

1. 「生成角色表（LoRA）」→ `visual_sheets` job  
2. UI 默认全选角色表；也可「角色表全选入训」  
3. 「确认训练集」提交 `keep` + `keep_sheets` → 复制到 `curated/`  
4. 「训练 / 导出包」读取 curated png+txt  

候选图仍可作补充，但角色表是微调主来源。
