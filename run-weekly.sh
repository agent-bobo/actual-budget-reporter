#!/bin/bash
# Weekly Budget Reporter Cron Script
# 添加到 crontab: 0 10 * * 0 /path/to/run-weekly.sh

cd "$(dirname "$0")"

# 加载环境变量
export $(grep -v '^#' .env | xargs)

# 运行报告生成
docker-compose run --rm budget-reporter

# 记录日志
echo "[$(date)] Budget report triggered" >> /var/log/budget-reporter.log
