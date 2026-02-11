#!/usr/bin/env python3
"""
Универсальный скрипт для парсинга результатов Gatling и построения всех требуемых графиков.

Поддерживает все три сценария:
- Сценарий 1: с разметкой фаз по RPS + график поиска точки деградации
- Сценарии 2 и 3: обычные графики без поиска точки деградации

Результаты сохраняются в структуру папок: results/<db_type>/scenario_<N>/

Использование:
    python3 scripts/parse_gatling_results.py --scenario 1
    python3 scripts/parse_gatling_results.py --scenario 2
    python3 scripts/parse_gatling_results.py --scenario 3
"""

import sys
import re
import argparse
import requests
from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt
import numpy as np
import json

# Параметры сценария 1 (должны совпадать с DbBenchmarkSimulation.scala)
SCENARIO1_RPS_LEVELS = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600]
SCENARIO1_RAMP_DURATION_SEC = 10
SCENARIO1_LEVEL_DURATION_SEC = 30

# Параметры сценария 3 (должны совпадать с DbBenchmarkSimulation.scala)
SCENARIO3_RPS_MAX = 500
SCENARIO3_OVERLOAD_RPS = 500  # overloadRps = RPS_MAX
SCENARIO3_RECOVERY_RPS = 250  # RPS_MAX / 2
SCENARIO3_OVERLOAD_RAMP_DURATION_SEC = 30
SCENARIO3_OVERLOAD_HOLD_DURATION_SEC = 60  # 1 minute
SCENARIO3_RECOVERY_RAMP_DURATION_SEC = 30
SCENARIO3_RECOVERY_HOLD_DURATION_SEC = 120  # 2 minutes


def get_db_type():
    """Автоматически определяет тип БД из docker-compose или API."""
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code == 200:
            data = response.json()
            db_type = data.get('db_type', 'postgres')
            print(f"Тип БД определен через API: {db_type}")
            return db_type
    except:
        pass

    try:
        compose_path = Path("docker-compose.yml")
        if compose_path.exists():
            with open(compose_path, 'r') as f:
                content = f.read()
                match = re.search(r'DB_TYPE=(\w+)', content)
                if match:
                    db_type = match.group(1).lower()
                    print(f"Тип БД определен из docker-compose.yml: {db_type}")
                    return db_type
    except:
        pass

    print("Не удалось определить тип БД, используем postgres по умолчанию")
    return "postgres"


def find_latest_simulation_log(gatling_dir="gatling/target/gatling"):
    """Находит последний simulation.log."""
    gatling_path = Path(gatling_dir)
    if not gatling_path.exists():
        return None

    reports = sorted([d for d in gatling_path.iterdir() if d.is_dir()],
                     key=lambda x: x.stat().st_mtime, reverse=True)

    if not reports:
        return None

    for report_dir in reports:
        log_file = report_dir / "simulation.log"
        if log_file.exists():
            return str(log_file)

    return None


def parse_simulation_log(log_path):
    """Парсит simulation.log и возвращает список запросов с временными метками."""
    requests = []

    with open(log_path, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) >= 6 and parts[0] == 'REQUEST':
                try:
                    start_ms = None
                    end_ms = None
                    status = None

                    for i, part in enumerate(parts):
                        if start_ms is None and part.isdigit():
                            start_ms = int(part)
                            if i + 1 < len(parts) and parts[i + 1].isdigit():
                                end_ms = int(parts[i + 1])
                                if i + 2 < len(parts):
                                    status = parts[i + 2]
                            break

                    if start_ms is not None and end_ms is not None and status:
                        response_time = end_ms - start_ms
                        requests.append({
                            'start_ms': start_ms,
                            'end_ms': end_ms,
                            'response_time_ms': response_time,
                            'status': status
                        })
                except (ValueError, IndexError, AttributeError):
                    continue

    return requests


def split_scenario1_into_phases(requests, rps_levels, ramp_duration_sec, level_duration_sec):
    """Разбивает запросы сценария 1 на фазы по уровням RPS."""
    if not requests:
        return []

    start_time_ms = min(r['start_ms'] for r in requests)
    phases = []
    current_time_ms = start_time_ms

    for rps in rps_levels:
        ramp_end_ms = current_time_ms + (ramp_duration_sec * 1000)
        ramp_requests = [
            r for r in requests
            if ramp_end_ms >= r['start_ms'] >= current_time_ms and r['status'] == 'OK'
        ]

        constant_end_ms = ramp_end_ms + (level_duration_sec * 1000)
        constant_requests = [
            r for r in requests
            if constant_end_ms >= r['start_ms'] >= ramp_end_ms and r['status'] == 'OK'
        ]

        phase_requests = ramp_requests + constant_requests

        if phase_requests:
            response_times = sorted([r['response_time_ms'] for r in phase_requests])
            n = len(response_times)

            phases.append({
                'rps': rps,
                'start_time_ms': current_time_ms,
                'end_time_ms': constant_end_ms,
                'total_requests': len(phase_requests),
                'response_times': response_times,
                'p50_ms': response_times[int(n * 0.50)] if n > 0 else 0,
                'p75_ms': response_times[int(n * 0.75)] if n > 0 else 0,
                'p90_ms': response_times[int(n * 0.90)] if n > 0 else 0,
                'p95_ms': response_times[int(n * 0.95)] if n > 0 else 0,
                'p99_ms': response_times[int(n * 0.99)] if n > 0 else 0,
                'mean_ms': np.mean(response_times) if response_times else 0
            })

        current_time_ms = constant_end_ms

    return phases


def build_all_charts_scenario1(phases, requests, output_dir, db_type):
    """Строит все графики для сценария 1."""
    # output_dir уже является специфической папкой

    # 1. График RPS vs p95 (поиск точки деградации)
    build_rps_vs_p95_chart(phases, str(output_dir / f"rps_vs_p95.png"), db_type)

    # 2. График времени ответа во времени
    build_response_time_over_time(requests, str(output_dir / f"response_time_over_time.png"), phases)

    # 3. Распределение по перцентилям
    build_percentiles_distribution(phases, str(output_dir / f"percentiles_distribution.png"), db_type)

    # 4. Гистограмма
    build_response_time_histogram(requests, str(output_dir / f"histogram.png"), db_type)

    # 5. JSON
    save_json(phases, str(output_dir / f"data.json"))


def calculate_recovery_time_scenario3(requests):
    """Вычисляет время восстановления для сценария 3.
    
    Возвращает время (в секундах) от момента начала снижения RPS до момента,
    когда p95 становится < 0.5 секунды.
    """
    if not requests:
        return None
    
    ok_requests = [r for r in requests if r['status'] == 'OK']
    if not ok_requests:
        return None
    
    start_time_ms = min(r['start_ms'] for r in ok_requests)
    
    # Вычисляем моменты времени фаз сценария 3
    # Фаза 1: Разгон до перегрузки (0 -> overloadRampDuration)
    # Фаза 2: Удержание перегрузки (overloadRampDuration -> overloadRampDuration + overloadHoldDuration)
    # Фаза 3: Снижение нагрузки (overloadRampDuration + overloadHoldDuration -> overloadRampDuration + overloadHoldDuration + recoveryRampDuration)
    # Фаза 4: Восстановление (после recoveryRampDuration)
    
    overload_ramp_end_ms = start_time_ms + (SCENARIO3_OVERLOAD_RAMP_DURATION_SEC * 1000)
    overload_hold_end_ms = overload_ramp_end_ms + (SCENARIO3_OVERLOAD_HOLD_DURATION_SEC * 1000)
    recovery_ramp_end_ms = overload_hold_end_ms + (SCENARIO3_RECOVERY_RAMP_DURATION_SEC * 1000)
    
    # Момент начала снижения RPS (начало фазы 3)
    recovery_start_ms = overload_hold_end_ms
    
    # Разбиваем запросы после начала снижения на временные окна (по 5 секунд)
    window_size_sec = 5
    window_size_ms = window_size_sec * 1000
    
    recovery_requests = [r for r in ok_requests if r['start_ms'] >= recovery_start_ms]
    
    if not recovery_requests:
        return None
    
    # Вычисляем p95 для каждого окна после начала снижения
    current_window_start = recovery_start_ms
    recovery_time_sec = None
    
    while current_window_start < max(r['start_ms'] for r in recovery_requests):
        window_end = current_window_start + window_size_ms
        window_requests = [
            r for r in recovery_requests
            if current_window_start <= r['start_ms'] < window_end
        ]
        
        if len(window_requests) >= 10:  # Минимум 10 запросов для статистики
            response_times = sorted([r['response_time_ms'] for r in window_requests])
            n = len(response_times)
            p95_ms = response_times[int(n * 0.95)] if n > 0 else 0
            p95_sec = p95_ms / 1000.0
            
            # Если p95 < 0.5s, это момент восстановления
            if p95_sec < 0.5:
                recovery_time_sec = (current_window_start - recovery_start_ms) / 1000.0
                break
        
        current_window_start = window_end
    
    return recovery_time_sec

def build_all_charts_scenario2_3(requests, output_dir, db_type, scenario_num):
    """Строит все графики для сценариев 2 и 3."""
    # output_dir уже является специфической папкой

    ok_requests = [r for r in requests if r['status'] == 'OK']
    if not ok_requests:
        print("Нет успешных запросов!")
        return None

    response_times = sorted([r['response_time_ms'] for r in ok_requests])
    n = len(response_times)

    percentiles = {
        'p50_ms': response_times[int(n * 0.50)] if n > 0 else 0,
        'p75_ms': response_times[int(n * 0.75)] if n > 0 else 0,
        'p90_ms': response_times[int(n * 0.90)] if n > 0 else 0,
        'p95_ms': response_times[int(n * 0.95)] if n > 0 else 0,
        'p99_ms': response_times[int(n * 0.99)] if n > 0 else 0,
        'mean_ms': np.mean(response_times) if response_times else 0,
        'total_requests': len(ok_requests)
    }
    
    # Для сценария 3 вычисляем время восстановления
    recovery_time = None
    if scenario_num == 3:
        recovery_time = calculate_recovery_time_scenario3(ok_requests)
        if recovery_time is not None:
            percentiles['recovery_time_sec'] = recovery_time
            print(f"\n{'='*60}")
            print(f"ВРЕМЯ ВОССТАНОВЛЕНИЯ: {recovery_time:.2f} секунд")
            print(f"{'='*60}")
            print(f"Время от начала снижения RPS до момента, когда p95 < 0.5s")
        else:
            print("\n⚠ Не удалось вычислить время восстановления")
            print("Возможно, p95 не опустился ниже 0.5s в течение теста")

    # 1. График времени ответа во времени
    build_response_time_over_time_simple(ok_requests, str(output_dir / f"response_time_over_time.png"), scenario_num, recovery_time)

    # 2. Распределение по перцентилям
    build_percentiles_distribution_simple(percentiles, str(output_dir / f"percentiles_distribution.png"), db_type, scenario_num)

    # 3. Гистограмма
    build_response_time_histogram(ok_requests, str(output_dir / f"histogram.png"), db_type)

    # 4. JSON
    save_json_simple(percentiles, str(output_dir / f"data.json"))
    
    return recovery_time


def build_rps_vs_p95_chart(phases, output_path, db_type):
    """График RPS vs p95 (для сценария 1)."""
    if not phases:
        return

    rps_values = [p['rps'] for p in phases]
    p95_values = [p['p95_ms'] / 1000.0 for p in phases]

    plt.figure(figsize=(12, 7))
    plt.plot(rps_values, p95_values, marker='o', linewidth=2.5, markersize=10,
             label=f'{db_type.upper()}', color='#3498db')
    plt.axhline(y=0.5, color='#e74c3c', linestyle='--', linewidth=2, label='Порог деградации (0.5s)')
    plt.xlabel('RPS (запросов в секунду)', fontsize=14, fontweight='bold')
    plt.ylabel('95-й перцентиль времени ответа (секунды)', fontsize=14, fontweight='bold')
    plt.title(f'Сценарий 1: Зависимость 95-го перцентиля от RPS ({db_type.upper()})',
              fontsize=16, fontweight='bold')
    plt.grid(True, alpha=0.3, linestyle='--')
    plt.legend(fontsize=12)

    for rps, p95 in zip(rps_values, p95_values):
        plt.annotate(f'{p95:.3f}s', (rps, p95),
                     textcoords="offset points", xytext=(0, 12), ha='center',
                     fontsize=9, bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))

    for i, (rps, p95) in enumerate(zip(rps_values, p95_values)):
        if p95 > 0.5:
            plt.axvline(x=rps, color='#f39c12', linestyle=':', linewidth=2,
                        label=f'Точка деградации (~{rps} RPS)')
            break

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"График RPS vs p95 сохранен: {output_path}")


def build_response_time_over_time(requests, output_path, phases):
    """График времени ответа во времени с разметкой фаз (сценарий 1)."""
    if not requests:
        return

    start_time_ms = min(r['start_ms'] for r in requests)
    times = [(r['start_ms'] - start_time_ms) / 1000.0 for r in requests]
    response_times = [r['response_time_ms'] / 1000.0 for r in requests]

    sorted_times = sorted(response_times)
    n = len(sorted_times)
    global_percentiles = {
        'p50': sorted_times[int(n * 0.50)] if n > 0 else 0,
        'p75': sorted_times[int(n * 0.75)] if n > 0 else 0,
        'p90': sorted_times[int(n * 0.90)] if n > 0 else 0,
        'p95': sorted_times[int(n * 0.95)] if n > 0 else 0,
        'p99': sorted_times[int(n * 0.99)] if n > 0 else 0
    }

    plt.figure(figsize=(16, 8))

    if len(requests) > 10000:
        step = len(requests) // 10000
        plt.plot(times[::step], response_times[::step], alpha=0.6, linewidth=0.5, color='#3498db')
    else:
        plt.plot(times, response_times, alpha=0.6, linewidth=0.5, color='#3498db')

    for phase in phases:
        phase_start = (phase['start_time_ms'] - start_time_ms) / 1000.0
        phase_end = (phase['end_time_ms'] - start_time_ms) / 1000.0

        plt.axvline(x=phase_start, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        plt.axvline(x=phase_end, color='gray', linestyle='--', alpha=0.5, linewidth=1)

        mid_time = (phase_start + phase_end) / 2
        plt.text(mid_time, plt.ylim()[1] * 0.95, f"RPS {phase['rps']}",
                 ha='center', va='top', fontsize=9, rotation=90,
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))

    # Единая цветовая палитра для всех перцентилей
    colors_map = {'p50': '#2ecc71', 'p75': '#f39c12', 'p90': '#e67e22', 'p95': '#e74c3c', 'p99': '#c0392b'}
    for p_name, p_value in global_percentiles.items():
        plt.axhline(y=p_value, color=colors_map[p_name], linestyle=':', linewidth=1.5,
                    alpha=0.7, label=f'{p_name} = {p_value:.3f}s')

    plt.xlabel('Время от начала теста (секунды)', fontsize=14, fontweight='bold')
    plt.ylabel('Время ответа (секунды)', fontsize=14, fontweight='bold')
    plt.title('Сценарий 1: График времени ответа во времени', fontsize=16, fontweight='bold')
    plt.legend(fontsize=10, loc='upper left')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"График времени ответа во времени сохранен: {output_path}")


def build_response_time_over_time_simple(requests, output_path, scenario_num, recovery_time=None):
    """График времени ответа во времени (сценарии 2 и 3)."""
    if not requests:
        return

    start_time_ms = min(r['start_ms'] for r in requests)
    times = [(r['start_ms'] - start_time_ms) / 1000.0 for r in requests]
    response_times = [r['response_time_ms'] / 1000.0 for r in requests]

    sorted_times = sorted(response_times)
    n = len(sorted_times)
    global_percentiles = {
        'p50': sorted_times[int(n * 0.50)] if n > 0 else 0,
        'p75': sorted_times[int(n * 0.75)] if n > 0 else 0,
        'p90': sorted_times[int(n * 0.90)] if n > 0 else 0,
        'p95': sorted_times[int(n * 0.95)] if n > 0 else 0,
        'p99': sorted_times[int(n * 0.99)] if n > 0 else 0
    }

    plt.figure(figsize=(16, 8))

    if len(requests) > 10000:
        step = len(requests) // 10000
        plt.plot(times[::step], response_times[::step], alpha=0.6, linewidth=0.5, color='#3498db')
    else:
        plt.plot(times, response_times, alpha=0.6, linewidth=0.5, color='#3498db')

    # Единая цветовая палитра для всех перцентилей
    colors_map = {'p50': '#2ecc71', 'p75': '#f39c12', 'p90': '#e67e22', 'p95': '#e74c3c', 'p99': '#c0392b'}
    for p_name, p_value in global_percentiles.items():
        plt.axhline(y=p_value, color=colors_map[p_name], linestyle=':', linewidth=1.5,
                    alpha=0.7, label=f'{p_name} = {p_value:.3f}s')
    
    # Для сценария 3 добавляем разметку фаз и время восстановления
    if scenario_num == 3:
        overload_ramp_end = SCENARIO3_OVERLOAD_RAMP_DURATION_SEC
        overload_hold_end = overload_ramp_end + SCENARIO3_OVERLOAD_HOLD_DURATION_SEC
        recovery_ramp_end = overload_hold_end + SCENARIO3_RECOVERY_RAMP_DURATION_SEC
        
        # Вертикальные линии для границ фаз
        plt.axvline(x=overload_ramp_end, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        plt.axvline(x=overload_hold_end, color='orange', linestyle='--', alpha=0.7, linewidth=2, label='Начало снижения RPS')
        plt.axvline(x=recovery_ramp_end, color='green', linestyle='--', alpha=0.7, linewidth=2, label='Начало фазы восстановления')
        
        # Подписи фаз
        plt.text(overload_ramp_end / 2, plt.ylim()[1] * 0.95, 'Разгон', ha='center', fontsize=9,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
        plt.text((overload_ramp_end + overload_hold_end) / 2, plt.ylim()[1] * 0.95, 'Перегрузка', ha='center', fontsize=9,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='orange', alpha=0.7))
        plt.text((overload_hold_end + recovery_ramp_end) / 2, plt.ylim()[1] * 0.95, 'Снижение', ha='center', fontsize=9,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightblue', alpha=0.7))
        plt.text((recovery_ramp_end + plt.xlim()[1]) / 2, plt.ylim()[1] * 0.95, 'Восстановление', ha='center', fontsize=9,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.7))
        
        # Отмечаем время восстановления, если вычислено
        if recovery_time is not None:
            recovery_moment = overload_hold_end + recovery_time
            plt.axvline(x=recovery_moment, color='green', linestyle='-', linewidth=3, 
                       alpha=0.8, label=f'Восстановление (p95<0.5s) через {recovery_time:.1f}s')
            plt.plot(recovery_moment, 0.5, 'go', markersize=15, label='Момент восстановления')
    
    plt.axhline(y=0.5, color='r', linestyle='--', linewidth=2, alpha=0.7, label='Порог 0.5s')

    plt.xlabel('Время от начала теста (секунды)', fontsize=14, fontweight='bold')
    plt.ylabel('Время ответа (секунды)', fontsize=14, fontweight='bold')
    title = f'Сценарий {scenario_num}: График времени ответа во времени'
    if scenario_num == 3 and recovery_time is not None:
        title += f' (Время восстановления: {recovery_time:.2f}s)'
    plt.title(title, fontsize=16, fontweight='bold')
    plt.legend(fontsize=9, loc='upper left', ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"График времени ответа во времени сохранен: {output_path}")


def build_percentiles_distribution(phases, output_path, db_type):
    """Распределение по перцентилям (для сценария 1)."""
    if not phases:
        return

    rps_values = [p['rps'] for p in phases]
    x_pos = np.arange(len(rps_values))
    width = 0.15

    fig, ax = plt.subplots(figsize=(14, 8))

    p50_values = [p['p50_ms'] / 1000.0 for p in phases]
    p75_values = [p['p75_ms'] / 1000.0 for p in phases]
    p90_values = [p['p90_ms'] / 1000.0 for p in phases]
    p95_values = [p['p95_ms'] / 1000.0 for p in phases]
    p99_values = [p['p99_ms'] / 1000.0 for p in phases]

    # Единая цветовая палитра для всех перцентилей
    colors_percentiles = {'p50': '#2ecc71', 'p75': '#f39c12', 'p90': '#e67e22', 'p95': '#e74c3c', 'p99': '#c0392b'}

    ax.bar(x_pos - 2 * width, p50_values, width, label='p50', alpha=0.8, color=colors_percentiles['p50'])
    ax.bar(x_pos - width, p75_values, width, label='p75', alpha=0.8, color=colors_percentiles['p75'])
    ax.bar(x_pos, p90_values, width, label='p90', alpha=0.8, color=colors_percentiles['p90'])
    ax.bar(x_pos + width, p95_values, width, label='p95', alpha=0.8, color=colors_percentiles['p95'])
    ax.bar(x_pos + 2 * width, p99_values, width, label='p99', alpha=0.8, color=colors_percentiles['p99'])

    ax.set_xlabel('RPS (запросов в секунду)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Время ответа (секунды)', fontsize=14, fontweight='bold')
    ax.set_title(f'Сценарий 1: Распределение времени ответа по перцентилям ({db_type.upper()})',
                 fontsize=16, fontweight='bold')
    ax.set_xticks(x_pos)
    ax.set_xticklabels([str(int(rps)) for rps in rps_values])
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"График распределения по перцентилям сохранен: {output_path}")


def build_percentiles_distribution_simple(percentiles, output_path, db_type, scenario_num):
    """Распределение по перцентилям для сценариев 2 и 3 (единое значение)."""
    if not percentiles:
        return

    p_names = ['p50', 'p75', 'p90', 'p95', 'p99']
    p_values = [
        percentiles['p50_ms'] / 1000.0,
        percentiles['p75_ms'] / 1000.0,
        percentiles['p90_ms'] / 1000.0,
        percentiles['p95_ms'] / 1000.0,
        percentiles['p99_ms'] / 1000.0
    ]

    fig, ax = plt.subplots(figsize=(10, 7))

    # Единая цветовая палитра для всех перцентилей
    colors_list = ['#2ecc71', '#f39c12', '#e67e22', '#e74c3c', '#c0392b']
    bars = ax.bar(p_names, p_values, alpha=0.8, color=colors_list, edgecolor='black', linewidth=1.5)

    # Добавляем значения на столбцы
    for bar, value in zip(bars, p_values):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{value:.3f}s',
                ha='center', va='bottom', fontsize=11, fontweight='bold')

    ax.set_xlabel('Перцентиль', fontsize=14, fontweight='bold')
    ax.set_ylabel('Время ответа (секунды)', fontsize=14, fontweight='bold')
    ax.set_title(f'Сценарий {scenario_num}: Распределение времени ответа по перцентилям ({db_type.upper()})',
                 fontsize=16, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"График распределения по перцентилям сохранен: {output_path}")


def build_response_time_histogram(requests, output_path, db_type):
    """Гистограмма распределения времени ответа."""
    if not requests:
        return

    response_times = [r['response_time_ms'] / 1000.0 for r in requests]

    plt.figure(figsize=(14, 8))

    n_bins = min(50, len(set(response_times)))
    plt.hist(response_times, bins=n_bins, edgecolor='black', alpha=0.7, color='#3498db')

    sorted_times = sorted(response_times)
    n = len(sorted_times)

    percentiles = {
        0.5: sorted_times[int(n * 0.50)],
        0.75: sorted_times[int(n * 0.75)],
        0.9: sorted_times[int(n * 0.90)],
        0.95: sorted_times[int(n * 0.95)],
        0.99: sorted_times[int(n * 0.99)]
    }

    # Единая цветовая палитра для всех перцентилей
    colors_map = {
        0.5: '#2ecc71',
        0.75: '#f39c12',
        0.9: '#e67e22',
        0.95: '#e74c3c',
        0.99: '#c0392b'
    }
    
    for p, value in percentiles.items():
        plt.axvline(x=value, color=colors_map[p], linestyle='--', linewidth=2,
                    label=f'p{int(p * 100)} = {value:.3f}s')

    plt.xlabel('Время ответа (секунды)', fontsize=14, fontweight='bold')
    plt.ylabel('Количество запросов', fontsize=14, fontweight='bold')
    plt.title(f'Гистограмма распределения времени ответа ({db_type.upper()})',
              fontsize=16, fontweight='bold')
    plt.legend(fontsize=11)
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Гистограмма сохранена: {output_path}")


def save_json(phases, output_path):
    """Сохраняет данные в JSON (сценарий 1)."""
    phases_for_json = []
    for p in phases:
        phase_json = {k: v for k, v in p.items() if k != 'response_times'}
        phases_for_json.append(phase_json)
    with open(output_path, 'w') as f:
        json.dump(phases_for_json, f, indent=2, default=str)
    print(f"Данные сохранены в JSON: {output_path}")


def save_json_simple(percentiles, output_path):
    """Сохраняет данные в JSON (сценарии 2 и 3)."""
    with open(output_path, 'w') as f:
        json.dump(percentiles, f, indent=2, default=str)
    print(f"Данные сохранены в JSON: {output_path}")
    
    # Для сценария 3 выводим время восстановления в консоль, если оно есть
    if 'recovery_time_sec' in percentiles:
        recovery_time = percentiles['recovery_time_sec']
        print(f"\nВремя восстановления сохранено в JSON: {recovery_time:.2f} секунд")


def main():
    parser = argparse.ArgumentParser(description='Парсинг результатов Gatling и построение графиков')
    parser.add_argument('--scenario', type=int, required=True, choices=[1, 2, 3],
                        help='Номер сценария (1, 2 или 3)')
    parser.add_argument('--log-path', type=str, default=None,
                        help='Путь к simulation.log (по умолчанию последний)')
    parser.add_argument('--db-type', type=str, default=None,
                        help='Тип БД (postgres/mongo). По умолчанию определяется автоматически')
    parser.add_argument('--output-dir', type=str, default='results',
                        help='Корневая директория для сохранения результатов')

    args = parser.parse_args()

    # Определяем тип БД
    db_type = args.db_type or get_db_type()

    # Создаем специфическую директорию для результатов
    # Структура: results/<db_type>/scenario_<N>/
    base_output_dir = Path(args.output_dir)
    final_output_dir = base_output_dir / db_type / f"scenario_{args.scenario}"
    final_output_dir.mkdir(parents=True, exist_ok=True)

    # Находим simulation.log
    if args.log_path:
        log_path = args.log_path
    else:
        log_path = find_latest_simulation_log()
        if not log_path:
            print("Ошибка: не найден simulation.log.")
            print("Укажите путь к simulation.log вручную:")
            print("  python3 scripts/parse_gatling_results.py --scenario 1 --log-path <путь>")
            sys.exit(1)

    print(f"Парсинг: {log_path}")
    print(f"Сценарий: {args.scenario}")
    print(f"Тип БД: {db_type}")
    print(f"Результаты будут сохранены в: {final_output_dir}")

    # Парсим логи
    requests = parse_simulation_log(log_path)
    print(f"Найдено запросов: {len(requests)}")

    if not requests:
        print("Ошибка: не найдено запросов в логе!")
        sys.exit(1)

    # Обрабатываем в зависимости от сценария
    if args.scenario == 1:
        phases = split_scenario1_into_phases(requests, SCENARIO1_RPS_LEVELS,
                                             SCENARIO1_RAMP_DURATION_SEC, SCENARIO1_LEVEL_DURATION_SEC)
        print(f"Найдено фаз: {len(phases)}")

        if not phases:
            print("Ошибка: не удалось разбить на фазы!")
            sys.exit(1)

        # Выводим таблицу в консоль
        print("\n" + "=" * 100)
        print("РЕЗУЛЬТАТЫ ПО ФАЗАМ (все требуемые перцентили):")
        print("=" * 100)
        print(f"{'RPS':<10} {'Запросов':<12} {'p50 (s)':<12} {'p75 (s)':<12} "
              f"{'p90 (s)':<12} {'p95 (s)':<12} {'p99 (s)':<12} {'Среднее (s)':<12}")
        print("-" * 100)
        for p in phases:
            print(f"{p['rps']:<10} {p['total_requests']:<12} {p['p50_ms'] / 1000:<12.3f} "
                  f"{p['p75_ms'] / 1000:<12.3f} {p['p90_ms'] / 1000:<12.3f} "
                  f"{p['p95_ms'] / 1000:<12.3f} {p['p99_ms'] / 1000:<12.3f} {p['mean_ms'] / 1000:<12.3f}")

        # Строим графики (передаем специфическую папку)
        build_all_charts_scenario1(phases, requests, final_output_dir, db_type)

        # Находим максимальный RPS
        max_rps = None
        for p in phases:
            if p['p95_ms'] <= 500:
                max_rps = p['rps']
            else:
                break

        if max_rps:
            print(f"\nМаксимальный RPS (p95 <= 0.5s): {max_rps}")
        else:
            print("\nВНИМАНИЕ: даже при минимальном RPS p95 превышает 0.5s!")

    else:  # Сценарии 2 и 3
        ok_requests = [r for r in requests if r['status'] == 'OK']
        print(f"Успешных запросов: {len(ok_requests)}")

        if not ok_requests:
            print("Ошибка: нет успешных запросов!")
            sys.exit(1)

        # Вычисляем перцентили
        response_times = sorted([r['response_time_ms'] for r in ok_requests])
        n = len(response_times)

        percentiles = {
            'p50_ms': response_times[int(n * 0.50)] if n > 0 else 0,
            'p75_ms': response_times[int(n * 0.75)] if n > 0 else 0,
            'p90_ms': response_times[int(n * 0.90)] if n > 0 else 0,
            'p95_ms': response_times[int(n * 0.95)] if n > 0 else 0,
            'p99_ms': response_times[int(n * 0.99)] if n > 0 else 0,
            'mean_ms': np.mean(response_times) if response_times else 0,
            'total_requests': len(ok_requests)
        }

        # Выводим таблицу в консоль
        print("\n" + "=" * 100)
        print(f"РЕЗУЛЬТАТЫ - Сценарий {args.scenario} (все требуемые перцентили):")
        print("=" * 100)
        print(f"{'Метрика':<20} {'Значение':<20}")
        print("-" * 100)
        print(f"{'Всего запросов':<20} {percentiles['total_requests']:<20}")
        print(f"{'p50 (s)':<20} {percentiles['p50_ms'] / 1000:<20.3f}")
        print(f"{'p75 (s)':<20} {percentiles['p75_ms'] / 1000:<20.3f}")
        print(f"{'p90 (s)':<20} {percentiles['p90_ms'] / 1000:<20.3f}")
        print(f"{'p95 (s)':<20} {percentiles['p95_ms'] / 1000:<20.3f}")
        print(f"{'p99 (s)':<20} {percentiles['p99_ms'] / 1000:<20.3f}")
        print(f"{'Среднее (s)':<20} {percentiles['mean_ms'] / 1000:<20.3f}")

        # Строим графики (передаем специфическую папку)
        # Функция build_all_charts_scenario2_3 сама вычислит время восстановления для сценария 3
        recovery_time = build_all_charts_scenario2_3(ok_requests, final_output_dir, db_type, args.scenario)
        
        # Для сценария 3 выводим время восстановления
        if args.scenario == 3 and recovery_time is not None:
            print(f"\n{'='*60}")
            print(f"ИТОГ: Время восстановления = {recovery_time:.2f} секунд")
            print(f"{'='*60}")
            print(f"Время от начала снижения RPS до момента, когда p95 < 0.5s")
        elif args.scenario == 3:
            print(f"\n{'='*60}")
            print(f"ВНИМАНИЕ: Не удалось вычислить время восстановления")
            print(f"Возможно, p95 не опустился ниже 0.5s в течение теста")
            print(f"{'='*60}")

    print("\nВсе графики построены!")


if __name__ == "__main__":
    main()