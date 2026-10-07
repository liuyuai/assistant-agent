# -*- coding: utf-8 -*-
"""启动入口：python run.py"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.server:app", host="127.0.0.1", port=8000, reload=False)
