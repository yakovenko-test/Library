#!/bin/bash
# Скрипт для поиска метрик контейнеров в Prometheus

echo "=== Поиск метрик для контейнеров benchmark ==="
echo ""

# Получаем ID контейнеров
APP_ID=$(docker ps --filter "name=benchmark_app" --format "{{.ID}}" | head -c 12)
POSTGRES_ID=$(docker ps --filter "name=benchmark_postgres" --format "{{.ID}}" | head -c 12)
MONGO_ID=$(docker ps --filter "name=benchmark_mongo" --format "{{.ID}}" | head -c 12)

echo "ID контейнеров:"
echo "  app: $APP_ID"
echo "  postgres: $POSTGRES_ID"
echo "  mongo: $MONGO_ID"
echo ""

echo ""
echo "=== Рабочие запросы для Prometheus ==="
echo ""
echo "CPU для app (замените ID на актуальный):"
echo "rate(container_cpu_usage_seconds_total{id=~\"/system.slice/docker-.*$APP_ID.*\"}[1m]) * 100"
echo ""
echo "Память для app:"
echo "container_memory_usage_bytes{id=~\"/system.slice/docker-.*$APP_ID.*\"} / 1024 / 1024"
echo ""




