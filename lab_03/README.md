## Проект: Benchmark MongoDB vs PostgreSQL (SELECT под нагрузкой)

### Структура проекта

- **`docker-compose.yml`** – поднимает:
  - `app` – REST‑сервис (FastAPI), делает SELECT в Mongo или Postgres;
  - `postgres` – база PostgreSQL + скрипт инициализации данных;
  - `mongo` – база MongoDB + скрипт инициализации данных;
  - `prometheus` – сбор метрик контейнеров;
  - `cadvisor` – экспорт метрик Docker‑контейнеров в Prometheus.
- **`app/`** – исходники REST‑сервиса
- **`db/postgres/init.sql`** – создаёт таблицу `users` и наполняет 100k строк.
- **`db/mongo/mongo-init.js`** – создаёт БД/коллекцию `users` и наполняет ~100k документов.
- **`prometheus/prometheus.yml`** – конфигурация Prometheus для сбора метрик с `cadvisor`.
- **`gatling/`** – проект с Gatling‑симуляцией для трёх сценариев нагрузки.

### Быстрый старт

1. **Собрать и запустить Docker‑окружение**:

   ```bash
   cd /home/artem/learning/BMSTU_STD/lab_03_01
   docker compose up -d --build
   ```

   По умолчанию приложение запускается с `DB_TYPE=postgres`. Для переключения на Mongo см. раздел *Переключение между Mongo и Postgres* ниже.

2. **Проверить, что сервис работает**:

   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/users/1
   ```

3. **Запустить Gatling‑тесты**:

   ```bash
   cd gatling
   sbt -Dscenario=1 gatling:test  # для сценария 1
   sbt -Dscenario=2 gatling:test  # для сценария 2
   sbt -Dscenario=3 gatling:test  # для сценария 3
   ```

### Переключение между Mongo и Postgres

Приложение читает тип БД из переменной окружения `DB_TYPE` в `docker-compose.yml`:

1. Остановить текущие контейнеры:
   ```bash
   docker compose down -v
   ```

2. Отредактировать `docker-compose.yml`, установить `DB_TYPE=postgres` или `DB_TYPE=mongo` в секции `app`.

3. Поднять окружение заново:
   ```bash
   docker compose up -d --build
   ```

### Изменение количества записей в БД

По умолчанию БД инициализируется с **100,000 записей**. Для тестирования на разном уровне заполненности БД:

```bash
# Перезаполнить PostgreSQL с 50,000 записей
python3 scripts/refill_database.py --db-type postgres --records 50000

# Перезаполнить MongoDB с 200,000 записей
python3 scripts/refill_database.py --db-type mongo --records 200000

# После перезаполнения можно сразу запускать тесты
cd gatling && sbt -Dscenario=1 gatling:test
```

**Рекомендуемые уровни заполненности для тестирования:**
- Малая БД: 10,000 - 50,000 записей
- Средняя БД: 100,000 записей (по умолчанию)
- Большая БД: 200,000 - 500,000 записей
- Очень большая БД: 1,000,000+ записей

### Построение графиков результатов Gatling

Скрипт берет данные последнего gatling тестирования. Поэтому для получения графиков для всех сценариев необходимо сначала провести тестирование для одного сценария и построить графики, затем переходить к следующему сценарию.

**Универсальный скрипт для всех сценариев:**

```bash
# Установи зависимости
pip3 install -r scripts/requirements.txt

# После запуска Gatling теста, построй графики:
python3 scripts/parse_gatling_results.py --scenario 1  # для сценария 1
python3 scripts/parse_gatling_results.py --scenario 2  # для сценария 2
python3 scripts/parse_gatling_results.py --scenario 3  # для сценария 3
```

**Что делает скрипт:**

- **Автоматически определяет тип БД** (postgres/mongo) из docker-compose.yml или API
- **Для сценария 1** строит:
  - График RPS vs p95 (поиск точки деградации)
  - График времени ответа во времени с разметкой фаз
  - Распределение по перцентилям (p50, p75, p90, p95, p99)
  - Гистограмма распределения
  - Таблица с перцентилями
- **Для сценариев 2 и 3** строит:
  - График времени ответа во времени (для сценария отмечает время восстановления системы)
  - Гистограмма распределения
  - Таблица с перцентилями

_Результаты сохраняются в `results/`._

### Метрики ресурсов контейнеров (Prometheus + cAdvisor)

_Note: Чтобы в Prometheus увидеть графики используемых ресурсов, необходимо знать id соответствующего контейнера. Используй скрипт `find_prometheus_metrics.sh`, чтобы получить id и необходимые запросы._  

**Использование Prometheus напрямую:**

1. Открой **http://localhost:9090** → вкладка **"Graph"**
2. Используй рабочие запросы из `scripts/PROMETHEUS_WORKING_QUERIES.md`:
   - **CPU:** `rate(container_cpu_usage_seconds_total{id=~"/system.slice/docker-.*"}[1m]) * 100`
   - **Память:** `container_memory_usage_bytes{id=~"/system.slice/docker-.*"} / 1024 / 1024`
3. Нажми **"Execute"** → **"Graph"** для визуализации

### Gatling: сценарии нагрузки

В `gatling/src/test/scala/dbbenchmark/DbBenchmarkSimulation.scala` реализованы три сценария:

1. **Сценарий 1: Поиск точки деградации** – серия прогонов с увеличением RPS (50, 100, 150, ...), пока `p95` не станет > 0.5s.
2. **Сценарий 2: Работа на предмаксимальной нагрузке** – длительный прогон на `PREV_RPS_MAX` (максимальный RPS, при котором p95 ≤ 0.5s).
3. **Сценарий 3: Перегрузка и восстановление** – фазы с перегрузкой и последующим снижением нагрузки для анализа времени восстановления.

Параметры (RPS, длительности фаз) задаются константами в Simulation и легко меняются под твою методику.

### Просмотр результатов Gatling

После запуска Gatling HTML-отчёты находятся в:
```
gatling/target/gatling/<название_симуляции>-<timestamp>/index.html
```

В отчёте ты увидишь:
- **Таблицы с перцентилями** (p50, p75, p90, p95, p99)
- **График Response Time over Time** (время ответа по времени)
- **Гистограмму Response Time Distribution**
- **Response Time Percentiles over Time** (перцентили по времени)
