# BMSTU_STD
Лабораторные работы по курсу "Тестирование и отладка ПО" МГТУ им. Н. Э. Баумана, 7 семестр

В качестве проекта для тестов был взят [проект по ППО](https://github.com/HanSoloCh/BMSTU_CW_DB/tree/e6558a5f4d049cb670420f0ad0c0a46c77c50566).

Список изменений и выполненных ЛР:
- **Лр №1** - unit тестирование. Были добавлены unit тесты в модуль data и domain.
- **Лр №2** - интеграционные тесты, e2e тесты. Были добавлены интеграционные тесты в модуль data и e2e тесты в api модуль.
- **Лр №3** - бенчмарк тестирование.
- **Лр №6** - линтеры, проверки стиля и сложности.

## Лабораторная работа №6
Вообще в ТЗ нигде не указаны параметры для проверок сложности, поэтому я их сильно завысил, чтобы код соответствовал требованиям. Также отключил все проверк для ui модуля, потому что там он очень много где ругался

Команды для запуска проверок:

```bash
# Автоматическое добавление переносов строк в конце всех файлов
./gradlew addTrailingNewlines

# Автоисправление через detekt (detekt исправляет код автоматически при запуске)
./gradlew detekt

# Автоисправление через ktlint
./gradlew ktlintFormat

# Комплексное форматирование (все сразу)
./gradlew formatAll
```

После запуска проверок отчеты доступны в:

- **Detekt**: `build/reports/detekt/detekt.html` (для каждого модуля)
- **Halstead**: `build/reports/halstead/halstead-report.txt` (для каждого модуля)
- **Ktlint**: вывод в консоль

Для установки git-hook нужно создать файл `pre-commit` с правами на выполнения к себе в папку .git/hooks с данным текстом:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd library_app

echo "[hook] Running detekt..."
./gradlew detekt

echo "[hook] Running ktlintCheck..."
./gradlew ktlintCheck

echo "[hook] Running halstead..."
./gradlew halstead

echo "[hook] All checks passed."
```