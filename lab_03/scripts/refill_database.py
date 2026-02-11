#!/usr/bin/env python3
"""
Скрипт для перезаполнения БД нужным количеством записей без пересоздания контейнеров.

Использование:
    python3 scripts/refill_database.py --db-type postgres --records 50000
    python3 scripts/refill_database.py --db-type mongo --records 200000
"""

import argparse
import subprocess
import sys
from pathlib import Path

def refill_postgres(records_count):
    """Перезаполняет PostgreSQL."""
    print(f"Перезаполнение PostgreSQL с {records_count} записями...")
    
    # Создаем SQL-скрипт
    sql_script = f"""
TRUNCATE TABLE users;

INSERT INTO users (id, name, email, created_at, last_login_at)
SELECT
    g AS id,
    'User ' || g AS name,
    'user' || g || '@example.com' AS email,
    NOW() - (random() * INTERVAL '365 days') AS created_at,
    NOW() - (random() * INTERVAL '365 days') AS last_login_at
FROM generate_series(1, {records_count}) AS g;

SELECT COUNT(*) as total_records FROM users;
"""
    
    try:
        # Выполняем SQL через psql
        cmd = [
            "docker", "exec", "-i", "benchmark_postgres",
            "psql", "-U", "benchmark", "-d", "benchmark"
        ]
        result = subprocess.run(cmd, input=sql_script, capture_output=True, text=True, check=True)
        print(result.stdout)
        
        # Извлекаем количество записей из вывода
        lines = result.stdout.strip().split('\n')
        for line in reversed(lines):
            if line.strip().isdigit():
                print(f"✓ PostgreSQL перезаполнен. Записей в таблице: {line.strip()}")
                break
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при перезаполнении PostgreSQL:")
        print(e.stderr)
        print(e.stdout)
        return False

def refill_mongo(records_count):
    """Перезаполняет MongoDB."""
    print(f"Перезаполнение MongoDB с {records_count} записями...")
    
    # Создаем временный JS-файл
    js_content = f"""
db = db.getSiblingDB("benchmark");

var recordsCount = {records_count};
print("Перезаполнение MongoDB с " + recordsCount + " записями...");

db.users.drop();

var bulk = db.users.initializeUnorderedBulkOp();
var batchSize = 1000;

for (var i = 1; i <= recordsCount; i++) {{
  bulk.insert({{
    _id: i,
    name: "User " + i,
    email: "user" + i + "@example.com",
    created_at: new Date(Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000),
    last_login_at: new Date(Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000),
  }});

  if (i % batchSize === 0) {{
    bulk.execute();
    bulk = db.users.initializeUnorderedBulkOp();
  }}
}}

try {{
  bulk.execute();
}} catch (e) {{
  // игнорируем
}}

db.users.createIndex({{ email: 1 }}, {{ unique: true }});
db.users.createIndex({{ last_login_at: 1 }});

var count = db.users.count();
print("Перезаполнение завершено. Записей в коллекции: " + count);
"""
    
    # Сохраняем во временный файл
    temp_file = Path("/tmp/mongo_refill.js")
    temp_file.write_text(js_content)
    
    try:
        # Копируем файл в контейнер
        subprocess.run([
            "docker", "cp", str(temp_file), "benchmark_mongo:/tmp/mongo_refill.js"
        ], check=True)
        
        # Выполняем скрипт (пробуем mongosh, если не работает - mongo)
        try:
            result = subprocess.run([
                "docker", "exec", "benchmark_mongo",
                "mongosh", "benchmark", "/tmp/mongo_refill.js"
            ], capture_output=True, text=True, check=True, timeout=300)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback на старый mongo клиент
            result = subprocess.run([
                "docker", "exec", "benchmark_mongo",
                "mongo", "benchmark", "/tmp/mongo_refill.js"
            ], capture_output=True, text=True, check=True, timeout=300)
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        print(f"✓ MongoDB перезаполнен.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при перезаполнении MongoDB:")
        print(e.stderr)
        print(e.stdout)
        return False
    except subprocess.TimeoutExpired:
        print("Ошибка: таймаут при перезаполнении MongoDB (возможно, слишком много записей)")
        return False
    finally:
        if temp_file.exists():
            temp_file.unlink()

def main():
    parser = argparse.ArgumentParser(description='Перезаполнение БД нужным количеством записей')
    parser.add_argument('--db-type', type=str, required=True, choices=['postgres', 'mongo'],
                       help='Тип БД (postgres или mongo)')
    parser.add_argument('--records', type=int, required=True,
                       help='Количество записей для создания')
    
    args = parser.parse_args()
    
    # Проверяем, что контейнеры запущены
    if args.db_type == 'postgres':
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=benchmark_postgres", "--format", "{{.Names}}"],
            capture_output=True, text=True
        )
        if "benchmark_postgres" not in result.stdout:
            print("Ошибка: контейнер benchmark_postgres не запущен!")
            sys.exit(1)
        success = refill_postgres(args.records)
    else:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=benchmark_mongo", "--format", "{{.Names}}"],
            capture_output=True, text=True
        )
        if "benchmark_mongo" not in result.stdout:
            print("Ошибка: контейнер benchmark_mongo не запущен!")
            sys.exit(1)
        success = refill_mongo(args.records)
    
    if success:
        print(f"\n✓ БД успешно перезаполнена с {args.records} записями")
        print("Теперь можно запускать тесты Gatling")
    else:
        print("\n✗ Ошибка при перезаполнении БД")
        sys.exit(1)

if __name__ == "__main__":
    main()

