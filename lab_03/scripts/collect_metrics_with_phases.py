#!/usr/bin/env python3
"""
Скрипт для сбора метрик с разметкой фаз для разных сценариев.

Для сценария 1: размечает фазы по уровням RPS
Для сценариев 2 и 3: обычный график с меткой времени начала теста

Использование:
    # Перед запуском теста, укажи сценарий:
    python3 scripts/collect_metrics_with_phases.py --scenario 1 --duration 600 &
    
    # Запусти Gatling тест
    cd gatling && sbt -Dscenario=1 gatling:test
    
    # После завершения, построй графики:
    python3 scripts/collect_metrics_with_phases.py --plot-only --scenario 1 --output results/metrics_scenario1.json
"""

import argparse
import time
import json
import requests
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import re
import os

PROMETHEUS_URL = "http://localhost:9090/api/v1/query"

# Параметры сценария 1 (должны совпадать с DbBenchmarkSimulation.scala)
SCENARIO1_RPS_LEVELS = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
SCENARIO1_RAMP_DURATION_SEC = 10
SCENARIO1_LEVEL_DURATION_SEC = 30

def get_db_type_from_compose():
    """Определяет тип БД из docker-compose.yml"""
    compose_path = Path(__file__).parent.parent / "docker-compose.yml"
    if compose_path.exists():
        with open(compose_path, 'r') as f:
            content = f.read()
            match = re.search(r'DB_TYPE=(\w+)', content)
            if match:
                return match.group(1).lower()
    return None

def get_container_ids():
    """Получает ID контейнеров benchmark."""
    import subprocess
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=benchmark", "--format", "{{.Names}} {{.ID}}"],
        capture_output=True,
        text=True
    )
    
    containers = {}
    for line in result.stdout.strip().split('\n'):
        if line:
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                container_id = parts[1][:12]
                containers[name] = container_id
    
    return containers

def query_prometheus(query):
    """Выполняет запрос к Prometheus API."""
    try:
        response = requests.get(PROMETHEUS_URL, params={'query': query}, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data['status'] == 'success' and data['data']['result']:
            return data['data']['result']
        return []
    except Exception as e:
        return []

def get_container_metrics_by_id(container_id_short):
    """Получает метрики контейнера по короткому ID."""
    metrics = {}
    
    cpu_query = f'rate(container_cpu_usage_seconds_total{{id=~"/system.slice/docker-.*{container_id_short}.*"}}[1m]) * 100'
    cpu_result = query_prometheus(cpu_query)
    if cpu_result:
        metrics['cpu_percent'] = float(cpu_result[0]['value'][1])
    
    mem_query = f'container_memory_usage_bytes{{id=~"/system.slice/docker-.*{container_id_short}.*"}} / 1024 / 1024'
    mem_result = query_prometheus(mem_query)
    if mem_result:
        metrics['memory_mb'] = float(mem_result[0]['value'][1])
    
    return metrics

def collect_metrics():
    """Собирает метрики для всех контейнеров."""
    containers = get_container_ids()
    if not containers:
        print("Предупреждение: не найдено контейнеров с именем 'benchmark'")
        return None
    
    all_metrics = {
        'timestamp': datetime.now().isoformat(),
        'timestamp_unix': time.time(),
        'containers': {}
    }
    
    found_any = False
    for name, container_id in containers.items():
        metrics = get_container_metrics_by_id(container_id)
        if metrics and (metrics.get('cpu_percent') is not None or metrics.get('memory_mb') is not None):
            all_metrics['containers'][name] = metrics
            found_any = True
    
    if not found_any:
        print(f"Предупреждение: не удалось собрать метрики для контейнеров: {list(containers.keys())}")
        print("Проверьте, что Prometheus доступен на http://localhost:9090")
    
    return all_metrics

def calculate_scenario1_phase_boundaries(start_time_unix, rps_levels, ramp_duration, level_duration):
    """Вычисляет границы фаз для сценария 1."""
    phases = []
    current_time = start_time_unix
    
    for rps in rps_levels:
        phase_start = current_time
        # Разгон + удержание
        phase_end = current_time + ramp_duration + level_duration
        phases.append({
            'rps': rps,
            'start_time': phase_start,
            'end_time': phase_end,
            'start_label': f'RPS {rps}',
            'end_label': f'RPS {rps} end'
        })
        current_time = phase_end
    
    return phases

def plot_scenario1_metrics(data, output_path, phases, db_type=None):
    """Строит графики для сценария 1 с разметкой фаз."""
    if not isinstance(data, list):
        data = [data]
    
    if not data:
        print("Нет данных для построения графиков!")
        return
    
    # Группируем по контейнерам
    containers_data = {}
    start_time_unix = data[0].get('timestamp_unix', 0)
    
    for entry in data:
        timestamp_unix = entry.get('timestamp_unix', 0)
        
        for container_name, metrics in entry.get('containers', {}).items():
            if container_name not in containers_data:
                containers_data[container_name] = {
                    'cpu': [],
                    'memory': [],
                    'timestamps': []
                }
            
            containers_data[container_name]['cpu'].append(metrics.get('cpu_percent', 0))
            containers_data[container_name]['memory'].append(metrics.get('memory_mb', 0))
            containers_data[container_name]['timestamps'].append(timestamp_unix - start_time_unix)
    
    if not containers_data:
        print("Нет данных для построения графиков!")
        return
    
    # Строим графики
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10))
    
    # CPU
    for container_name, data_dict in containers_data.items():
        if data_dict['cpu']:
            ax1.plot(data_dict['timestamps'], data_dict['cpu'], marker='o', 
                    label=container_name, linewidth=2, markersize=4)
    
    # Размечаем фазы
    for phase in phases:
        phase_start_rel = phase['start_time'] - start_time_unix
        phase_end_rel = phase['end_time'] - start_time_unix
        
        # Вертикальные линии для границ фаз
        ax1.axvline(x=phase_start_rel, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        ax1.axvline(x=phase_end_rel, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        
        # Подписи фаз
        mid_time = (phase_start_rel + phase_end_rel) / 2
        ax1.text(mid_time, ax1.get_ylim()[1] * 0.95, f"RPS {phase['rps']}", 
                ha='center', va='top', fontsize=9, 
                bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
    
    title_suffix = f" ({db_type})" if db_type else ""
    ax1.set_xlabel('Время от начала теста (секунды)', fontsize=12)
    ax1.set_ylabel('CPU использование (%)', fontsize=12, fontweight='bold')
    ax1.set_title(f'Сценарий 1: CPU по фазам нагрузки{title_suffix}', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # Memory
    for container_name, data_dict in containers_data.items():
        if data_dict['memory']:
            ax2.plot(data_dict['timestamps'], data_dict['memory'], marker='o', 
                    label=container_name, linewidth=2, markersize=4)
    
    # Размечаем фазы для памяти
    for phase in phases:
        phase_start_rel = phase['start_time'] - start_time_unix
        phase_end_rel = phase['end_time'] - start_time_unix
        
        ax2.axvline(x=phase_start_rel, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        ax2.axvline(x=phase_end_rel, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        
        mid_time = (phase_start_rel + phase_end_rel) / 2
        ax2.text(mid_time, ax2.get_ylim()[1] * 0.95, f"RPS {phase['rps']}", 
                ha='center', va='top', fontsize=9, 
                bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
    
    ax2.set_xlabel('Время от начала теста (секунды)', fontsize=12)
    ax2.set_ylabel('Использование памяти (MB)', fontsize=12, fontweight='bold')
    ax2.set_title(f'Сценарий 1: Память по фазам нагрузки{title_suffix}', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nГрафики сохранены: {output_path}")

def plot_scenario2_3_metrics(data, output_path, scenario_num, test_start_time=None, db_type=None):
    """Строит обычные графики для сценариев 2 и 3."""
    if not isinstance(data, list):
        data = [data]
    
    if not data:
        print("Нет данных для построения графиков!")
        return
    
    containers_data = {}
    start_time_unix = test_start_time if test_start_time else data[0].get('timestamp_unix', 0)
    
    for entry in data:
        timestamp_unix = entry.get('timestamp_unix', 0)
        
        for container_name, metrics in entry.get('containers', {}).items():
            if container_name not in containers_data:
                containers_data[container_name] = {
                    'cpu': [],
                    'memory': [],
                    'timestamps': []
                }
            
            containers_data[container_name]['cpu'].append(metrics.get('cpu_percent', 0))
            containers_data[container_name]['memory'].append(metrics.get('memory_mb', 0))
            containers_data[container_name]['timestamps'].append(timestamp_unix - start_time_unix)
    
    title_suffix = f" ({db_type})" if db_type else ""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # CPU
    for container_name, data_dict in containers_data.items():
        if data_dict['cpu']:
            ax1.plot(data_dict['timestamps'], data_dict['cpu'], marker='o', 
                    label=container_name, linewidth=2, markersize=4)
    
    ax1.set_xlabel('Время от начала теста (секунды)', fontsize=12)
    ax1.set_ylabel('CPU использование (%)', fontsize=12, fontweight='bold')
    ax1.set_title(f'Сценарий {scenario_num}: CPU использование{title_suffix}', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # Memory
    for container_name, data_dict in containers_data.items():
        if data_dict['memory']:
            ax2.plot(data_dict['timestamps'], data_dict['memory'], marker='o', 
                    label=container_name, linewidth=2, markersize=4)
    
    ax2.set_xlabel('Время от начала теста (секунды)', fontsize=12)
    ax2.set_ylabel('Использование памяти (MB)', fontsize=12, fontweight='bold')
    ax2.set_title(f'Сценарий {scenario_num}: Использование памяти{title_suffix}', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nГрафики сохранены: {output_path}")

def plot_comparison(data_by_db, output_path, scenario_num, is_scenario1=False):
    """Строит сравнительные графики для разных БД."""
    if not data_by_db:
        print("Нет данных для сравнения!")
        return
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10))
    
    # Определяем общее время начала
    all_start_times = []
    for db_type, db_data in data_by_db.items():
        if isinstance(db_data, list) and len(db_data) > 0:
            all_start_times.append(db_data[0].get('timestamp_unix', 0))
    
    if not all_start_times:
        print("Нет валидных данных для сравнения!")
        return
    
    global_start_time = min(all_start_times)
    
    # Инициализируем словари для данных
    cpu_data = {}
    mem_data = {}
    
    # Собираем данные для каждого типа БД
    for db_type, db_data in data_by_db.items():
        if not isinstance(db_data, list):
            db_data = [db_data]
        
        if not db_data:
            continue
        
        # Пробуем разные варианты имен контейнеров
        possible_container_names = [
            f"benchmark_{db_type}",
            f"benchmark_{db_type}_1",  # если есть суффикс
            db_type,  # просто имя БД
        ]
        
        # Инициализируем списки для этого типа БД
        cpu_data[db_type] = {'times': [], 'values': []}
        mem_data[db_type] = {'times': [], 'values': []}
        
        found_containers = set()
        for entry in db_data:
            timestamp_unix = entry.get('timestamp_unix', 0)
            containers = entry.get('containers', {})
            
            # Собираем все доступные имена контейнеров для отладки
            if containers:
                found_containers.update(containers.keys())
            
            # Ищем контейнер БД по разным вариантам имен
            db_container = None
            for possible_name in possible_container_names:
                if possible_name in containers:
                    db_container = possible_name
                    break
            
            # Если не нашли точное совпадение, ищем по частичному совпадению
            if db_container is None and containers:
                for container_name in containers.keys():
                    if db_type.lower() in container_name.lower():
                        db_container = container_name
                        break
            
            if db_container and db_container in containers:
                metrics = containers[db_container]
                time_rel = timestamp_unix - global_start_time
                
                cpu_val = metrics.get('cpu_percent', 0)
                mem_val = metrics.get('memory_mb', 0)
                
                # Добавляем только если есть валидные значения
                if cpu_val is not None and cpu_val != 0:
                    cpu_data[db_type]['times'].append(time_rel)
                    cpu_data[db_type]['values'].append(cpu_val)
                
                if mem_val is not None and mem_val != 0:
                    mem_data[db_type]['times'].append(time_rel)
                    mem_data[db_type]['values'].append(mem_val)
        
        # Отладочная информация
        if not found_containers:
            print(f"Ошибка: для {db_type} не найдено контейнеров в данных!")
            print(f"  Это означает, что при сборе метрик контейнеры не были обнаружены.")
            print(f"  Пересоберите данные, убедившись, что контейнеры запущены и Prometheus доступен.")
        elif db_type not in [c.lower().replace('benchmark_', '') for c in found_containers]:
            print(f"Предупреждение: для {db_type} найдены контейнеры: {found_containers}, но не найден контейнер БД")
    
    # Проверяем, есть ли данные для построения
    has_cpu_data = any(cpu_data[db]['times'] for db in cpu_data.keys())
    has_mem_data = any(mem_data[db]['times'] for db in mem_data.keys())
    
    if not has_cpu_data and not has_mem_data:
        print("Ошибка: не найдено данных для построения графиков!")
        print("Проверьте, что в JSON файлах есть данные в поле 'containers'")
        return
    
    # Рисуем графики для всех БД
    for db_type in cpu_data.keys():
        if cpu_data[db_type]['times']:
            ax1.plot(cpu_data[db_type]['times'], cpu_data[db_type]['values'], 
                    marker='o', label=f'{db_type.upper()}', linewidth=2, markersize=4)
    
    for db_type in mem_data.keys():
        if mem_data[db_type]['times']:
            ax2.plot(mem_data[db_type]['times'], mem_data[db_type]['values'], 
                    marker='o', label=f'{db_type.upper()}', linewidth=2, markersize=4)
    
    # Настройка графиков CPU
    ax1.set_xlabel('Время от начала теста (секунды)', fontsize=12)
    ax1.set_ylabel('CPU использование (%)', fontsize=12, fontweight='bold')
    ax1.set_title(f'Сценарий {scenario_num}: Сравнение CPU использования', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    if has_cpu_data:
        ax1.legend()
    
    # Настройка графиков Memory
    ax2.set_xlabel('Время от начала теста (секунды)', fontsize=12)
    ax2.set_ylabel('Использование памяти (MB)', fontsize=12, fontweight='bold')
    ax2.set_title(f'Сценарий {scenario_num}: Сравнение использования памяти', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    if has_mem_data:
        ax2.legend()
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nСравнительные графики сохранены: {output_path}")

def main():
    parser = argparse.ArgumentParser(description='Сбор метрик с разметкой фаз')
    parser.add_argument('--scenario', type=int, required=True, choices=[1, 2, 3],
                       help='Номер сценария (1, 2 или 3)')
    parser.add_argument('--duration', type=int, default=0,
                       help='Длительность сбора в секундах (0 = одно измерение)')
    parser.add_argument('--interval', type=int, default=5,
                       help='Интервал между запросами в секундах')
    parser.add_argument('--output', type=str, default=None,
                       help='Путь к выходному JSON-файлу')
    parser.add_argument('--plot-only', action='store_true',
                       help='Только построить графики из существующего JSON')
    parser.add_argument('--test-start-time', type=float, default=None,
                       help='Unix timestamp начала теста (для сценариев 2 и 3)')
    parser.add_argument('--db-type', type=str, default=None, choices=['postgres', 'mongo'],
                       help='Тип БД (postgres/mongo). Если не указан, определяется из docker-compose.yml')
    parser.add_argument('--compare', action='store_true',
                       help='Построить сравнительные графики для всех доступных БД')
    
    args = parser.parse_args()
    
    # Определяем тип БД
    db_type = args.db_type
    if db_type is None:
        db_type = get_db_type_from_compose()
        if db_type is None:
            print("Предупреждение: не удалось определить тип БД. Используйте --db-type")
            db_type = "unknown"
    
    if args.output is None:
        # Сохраняем в структуру results/metrics/{db_type}/scenario_{scenario}.json
        output_path = Path(f'results/metrics/{db_type}/scenario_{args.scenario}.json')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output = str(output_path)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if args.plot_only:
        if args.compare:
            # Сравнительный режим - загружаем данные для всех БД
            data_by_db = {}
            metrics_dir = Path('results/metrics')
            
            for db in ['postgres', 'mongo']:
                db_file = metrics_dir / db / f'scenario_{args.scenario}.json'
                if db_file.exists():
                    with open(db_file, 'r') as f:
                        data_by_db[db] = json.load(f)
                        print(f"Загружены данные для {db}: {db_file}")
            
            if not data_by_db:
                print("Не найдены данные для сравнения!")
                return
            
            comparison_path = metrics_dir / f'scenario_{args.scenario}_comparison.png'
            plot_comparison(data_by_db, str(comparison_path), args.scenario, 
                          is_scenario1=(args.scenario == 1))
            return
        
        if not output_path.exists():
            print(f"Файл {output_path} не найден!")
            return
        
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        if args.scenario == 1:
            # Для сценария 1 нужны фазы
            if isinstance(data, list) and len(data) > 0:
                start_time = data[0].get('timestamp_unix', time.time())
                phases = calculate_scenario1_phase_boundaries(
                    start_time, SCENARIO1_RPS_LEVELS, 
                    SCENARIO1_RAMP_DURATION_SEC, SCENARIO1_LEVEL_DURATION_SEC
                )
                plot_path = str(output_path).replace('.json', '_plot.png')
                # Определяем тип БД из данных или пути
                db_type_from_data = data[0].get('db_type') if isinstance(data, list) and len(data) > 0 else None
                if db_type_from_data is None:
                    # Пытаемся определить из пути
                    path_parts = str(output_path).split('/')
                    if 'postgres' in path_parts:
                        db_type_from_data = 'postgres'
                    elif 'mongo' in path_parts:
                        db_type_from_data = 'mongo'
                plot_scenario1_metrics(data, plot_path, phases, db_type_from_data)
        else:
            plot_path = str(output_path).replace('.json', '_plot.png')
            plot_scenario2_3_metrics(data, plot_path, args.scenario, args.test_start_time, db_type)
        return
    
    # Сбор метрик
    all_metrics_list = []
    start_time = time.time()
    iteration = 0
    
    # Сохраняем время начала сбора как время начала теста
    test_start_time = time.time()
    
    print(f"Начало сбора метрик для сценария {args.scenario}")
    print(f"Тип БД: {db_type}")
    print(f"Время начала: {datetime.fromtimestamp(test_start_time).isoformat()}")
    print(f"Сохраняй это время для --test-start-time при построении графиков!")
    
    try:
        while True:
            iteration += 1
            metrics = collect_metrics()
            
            if metrics:
                # Добавляем информацию о типе БД в метрики
                metrics['db_type'] = db_type
                all_metrics_list.append(metrics)
                
                # Сохраняем промежуточные результаты
                with open(output_path, 'w') as f:
                    json.dump(all_metrics_list, f, indent=2)
                
                if iteration % 10 == 0 or args.duration == 0:
                    print(f"[{iteration}] {metrics['timestamp']}")
            
            if args.duration > 0 and (time.time() - start_time) >= args.duration:
                break
            
            if args.duration == 0:
                break
            
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        print("\nСбор метрик прерван пользователем")
    
    print(f"\nСобрано {len(all_metrics_list)} записей")
    print(f"Данные сохранены в: {output_path}")
    print(f"\nДля построения графиков используй:")
    print(f"  python3 scripts/collect_metrics_with_phases.py --plot-only --scenario {args.scenario} --output {output_path}")
    if args.scenario in [2, 3]:
        print(f"  --test-start-time {test_start_time}")
    print(f"\nДля сравнения с другими БД используй:")
    print(f"  python3 scripts/collect_metrics_with_phases.py --plot-only --scenario {args.scenario} --compare")

if __name__ == "__main__":
    main()


