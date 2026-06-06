.PHONY: help install test run preview clean

help:
	@echo "Daily Trending Report - 常用命令"
	@echo ""
	@echo "  make install   安装依赖"
	@echo "  make test      跑单元测试"
	@echo "  make run       跑抓取 + 发邮件 (需要 .env)"
	@echo "  make preview   跑抓取 + 渲染 HTML 到 output/preview.html (不发邮件)"
	@echo "  make clean     清理缓存和临时文件"

install:
	pip install -r requirements.txt
	pip install pytest

test:
	pytest tests/ -v

run:
	python -m src.main

preview:
	mkdir -p output
	python scripts/run_local.py --out output/preview.html
	@echo ""
	@echo "open output/preview.html in your browser"

clean:
	rm -rf src/__pycache__ tests/__pycache__ .pytest_cache output
	find . -name "*.pyc" -delete
