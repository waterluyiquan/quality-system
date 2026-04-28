# 技术实现路径

## 第一阶段：本地入库

技术：

- `PyMuPDF` 解析 PDF。
- `openpyxl` 解析 Excel。
- `python-docx` 解析 Word。
- ChromaDB 保存向量和 metadata。

处理流程：

```text
docs 文件夹
  ↓
按文件类型解析文本
  ↓
切分 chunk
  ↓
生成 embedding
  ↓
写入 ChromaDB
```

## 第二阶段：手动查询

技术：

- Streamlit 做页面。
- ChromaDB 做相似度检索。
- LLM API 做回答生成。

处理流程：

```text
用户问题
  ↓
向量检索 top_k chunks
  ↓
拼接上下文
  ↓
LLM 生成回答
  ↓
展示答案和来源
```

约束 prompt：

```text
你只能根据提供的资料回答。
如果资料不足，回答“未在资料中找到”。
回答后必须列出来源文件和原文摘录。
```

## 第三阶段：文字自动填表

技术：

- `openpyxl` 读取和写入 Excel。
- 复用 RAG 检索能力。
- LLM 从检索片段中抽取字段值。

处理流程：

```text
上传待填写 Excel
  ↓
读取第一列字段名
  ↓
逐字段生成查询
  ↓
检索资料库
  ↓
抽取填写值
  ↓
写入第二列
  ↓
新增填写依据 Sheet
  ↓
导出结果 Excel
```

## UI 页面

建议一个 Streamlit 应用包含三个标签页：

- `资料库`：入库、查看文件数量、清空重建。
- `手动查询`：输入问题，显示答案和来源。
- `自动填表`：上传 Excel，执行填表，导出结果。

## 实现难度

| 模块 | 难度 | 说明 |
|---|---:|---|
| PDF 文本解析 | 低 | PyMuPDF 成熟 |
| Word 文本解析 | 低 | python-docx 足够 |
| Excel 文本解析 | 中 | 合并单元格和空行要处理 |
| ChromaDB 检索 | 低 | 本地部署简单 |
| Streamlit 页面 | 低 | 适合个人工具 |
| 自动填表 | 中 | 字段匹配需要调试 |
| 来源追踪 | 低 | metadata 设计好即可 |

整体预计：1-2 天可完成可用原型。
