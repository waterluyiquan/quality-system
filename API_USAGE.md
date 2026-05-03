# Quality System API

本 API 用于给 OpenClaw 或其他自动化工具调用本地质量资料库。

## 启动

```powershell
.\启动API服务.bat
```

服务地址：

```text
http://127.0.0.1:8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

## 常用接口

### 健康检查

```http
GET /health
```

返回 DeepSeek 连接状态、当前文件夹设置、已入库 chunk 数。

### 问答

```http
POST /query
Content-Type: application/json

{
  "q": "TO247 外观检验标准是什么？",
  "top_k": 5
}
```

返回：

```json
{
  "answer_text": "...",
  "sources": []
}
```

### 重新入库

```http
POST /ingest
Content-Type: application/json

{
  "background": true,
  "reset": true
}
```

后台任务进度：

```http
GET /status
```

### 单个 Excel 填表

```http
POST /fill-excel
Content-Type: application/json

{
  "template_path": "D:/LanShareFiles/模板.xlsx",
  "mode": "auto",
  "overwrite": false,
  "max_fields": 30
}
```

### 批量填表

```http
POST /batch-fill
Content-Type: application/json

{
  "max_files": 30,
  "max_fields_per_file": 30,
  "skip_done": true,
  "background": true
}
```

查询待处理文件：

```http
GET /batch-pending
```

清空批处理记录：

```http
POST /batch-reset
```

### 下载结果

```http
GET /download?path=E:/file/filled_xxx.xlsx
```

## OpenClaw 建议工具映射

- `quality_query` -> `POST /query`
- `quality_ingest` -> `POST /ingest`
- `quality_status` -> `GET /status`
- `quality_fill_excel` -> `POST /fill-excel`
- `quality_batch_fill` -> `POST /batch-fill`
- `quality_pending` -> `GET /batch-pending`
