"""核心引擎：抓取、解析、认证、存储、调度。

本层禁止 import FastAPI、uvicorn 或任何传输/推送实现。
传输层通过 `core.engine.Publisher` 协议接入。
"""
