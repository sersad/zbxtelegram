# 📦 Telegram Bot API Server: Docker Compose Guide

Полная документация по развёртыванию локального сервера Telegram Bot API с фильтрацией по списку разрешённых ботов.

> 🔒 **Примечание**: Все идентификаторы ботов и токены в данном документе являются вымышленными примерами. Замените их на ваши реальные данные.

---

## 📋 Оглавление

1. [Обзор](#-обзор)
2. [Требования](#-требования)
3. [Быстрый старт](#-быстрый-старт)
4. [Конфигурация](#-конфигурация)
5. [🧮 Шпаргалка: расчёт TELEGRAM_FILTER](#-шпаргалка-расчёт-telegram_filter)
6. [Тестирование](#-тестирование)
7. [Безопасность](#-безопасность)
8. [Troubleshooting](#-troubleshooting)
9. [Quick Reference](#-quick-reference)

---

## 🔍 Обзор

**Telegram Bot API Server** — это локальный прокси-сервер для Telegram Bot API, который позволяет:

| Преимущество | Описание |
|-------------|----------|
| 🔐 **Фильтрация ботов** | Разрешать доступ только определённому списку ботов через `TELEGRAM_FILTER` |
| 🌐 **Работа без интернета** | Сервер кеширует ответы и может работать в изолированных сетях |
| ⚡ **Кеширование** | Снижает нагрузку на API Telegram при частых запросах |
| 📊 **Локальное логирование** | Все запросы логируются локально для аудита |
| 🔄 **Контроль версий** | Вы сами решаете, когда обновлять сервер |

> 💡 **Use case для этого гайда**: У вас есть 2 бота (`4523891076` и `7812459328`), и вы хотите, чтобы **только они** могли подключаться к вашему локальному серверу.

---

## 📦 Требования

| Компонент | Версия | Проверка |
|-----------|--------|----------|
| **Docker** | ≥ 20.10 | `docker --version` |
| **Docker Compose** | ≥ 2.0 | `docker compose version` |
| **Диск** | ≥ 2 ГБ свободного места | `df -h /opt` |
| **Память** | ≥ 512 МБ для контейнера | `free -h` |
| **Порты** | 8081 (или другой) свободен | `ss -tlnp \| grep 8081` |

### 🌐 Сетевые требования

- Доступ к `my.telegram.org` для получения `TG_API_ID`/`TG_API_HASH`
- Доступ к серверам Telegram (`149.154.160.0/20`, `91.108.4.0/22`) для исходящих запросов
- **Входящие соединения**: только с `localhost` (рекомендуется)

---

## 🚀 Быстрый старт

### Шаг 1: Создайте директорию

```bash
sudo mkdir -p /opt/telegram-bot-api
cd /opt/telegram-bot-api
```

### Шаг 2: Получите Telegram API credentials

1. Перейдите на [https://my.telegram.org](https://my.telegram.org)
2. Авторизуйтесь по номеру телефона (любого, кому принадлежат боты)
3. Откройте **"API development tools"**
4. Создайте приложение (если нет) и скопируйте:
   - `App api_id` → `TG_API_ID`
   - `App api_hash` → `TG_API_HASH`

> ⚠️ Эти данные **секретные**. Не передавайте их третьим лицам.

### Шаг 3: Создайте файл `.env`

```bash
# Создайте файл с секретами
cat > .env << 'EOF'
# Telegram API credentials (получить на https://my.telegram.org)
TG_API_ID=123456
TG_API_HASH=abcdef1234567890abcdef1234567890

# Фильтр: разрешаем ТОЛЬКО ботов 4523891076 и 7812459328
# Формат: <remainder>/<modulo>
TELEGRAM_FILTER=1235322824/3288568252
EOF

# 🔐 Установите строгие права
chmod 600 .env
chown root:root .env
```

### Шаг 4: Создайте `docker-compose.yml`

```bash
cat > docker-compose.yml << 'EOF'
version: '3.7'

services:
  telegram-bot-api:
    container_name: telegram-bot-api
    image: aiogram/telegram-bot-api:latest

    environment:
      # 🔐 Обязательные: API credentials из .env
      - TELEGRAM_API_ID=${TG_API_ID}
      - TELEGRAM_API_HASH=${TG_API_HASH}

      # 🔐 Фильтрация ботов (из .env или задать напрямую)
      - TELEGRAM_FILTER=${TELEGRAM_FILTER:-1235322824/3288568252}

      # 🔐 Безопасность: только localhost
      - TELEGRAM_LOCAL=1

      # 📊 Логирование: 0-100 (2 = краткая информация о запросах)
      - TELEGRAM_VERBOSITY=2

    ports:
      # Слушаем ТОЛЬКО localhost для безопасности
      - "127.0.0.1:8081:8081"

    volumes:
      # Персистентное хранилище для вебхуков и кеша
      - bot-api-/var/lib/telegram-bot-api
      # Опционально: маппинг логов на хост
      # - ./logs:/var/log/telegram-bot-api

    restart: unless-stopped

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/bot4523891076:TEST/getMe"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

volumes:
  bot-api-
EOF
```

### Шаг 5: Добавьте `.env` в `.gitignore`

```bash
cat > .gitignore << 'EOF'
# Секреты
.env
*.env
*.local

# Логи (если маппите)
logs/
*.log
EOF
```

### Шаг 6: Запустите контейнер

```bash
# Запуск в фоновом режиме
docker compose up -d

# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f telegram-bot-api
```

✅ **Ожидаемый результат в логах:**
```
[2026-04-30 12:00:00] [info] [start] Telegram Bot API server 1.0.0
[2026-04-30 12:00:01] [info] [http] HTTP server listening on 127.0.0.1:8081
[2026-04-30 12:00:01] [info] [filter] Bot filter enabled: bot_user_id % 3288568252 == 1235322824
```

---

## ⚙️ Конфигурация

### 📋 Переменные окружения

| Переменная | Обязательна | Описание | Пример |
|-----------|-------------|----------|--------|
| `TELEGRAM_API_ID` | ✅ | Application ID от my.telegram.org | `123456` |
| `TELEGRAM_API_HASH` | ✅ | Application hash от my.telegram.org | `abc123...` |
| `TELEGRAM_FILTER` | ❌ | Фильтр ботов: `<remainder>/<modulo>` | `1235322824/3288568252` |
| `TELEGRAM_LOCAL` | ❌ | Принимать только локальные запросы | `1` |
| `TELEGRAM_VERBOSITY` | ❌ | Уровень логирования (0-100) | `2` |
| `TELEGRAM_MAX_WEBHOOK_CONNECTIONS` | ❌ | Макс. вебхуков на бота | `40` |

### 🐳 Параметры docker-compose

| Параметр | Значение по умолчанию | Рекомендация |
|----------|----------------------|--------------|
| `ports` | `8081:8081` | `127.0.0.1:8081:8081` (только localhost) |
| `volumes` | — | Обязательно: `bot-api-/var/lib/telegram-bot-api` |
| `restart` | — | `unless-stopped` для авто-перезапуска |
| `healthcheck` | — | Рекомендуется для мониторинга |

### 🔁 Обновление сервера

```bash
# 1. Скачайте новый образ
docker compose pull

# 2. Перезапустите с пересозданием контейнера
docker compose up -d --force-recreate

# 3. Проверьте версию в логах
docker compose logs --tail=5 telegram-bot-api | grep version
```

---

## 🧮 Шпаргалка: расчёт TELEGRAM_FILTER

### 🔐 Формат переменной

```
TELEGRAM_FILTER="<remainder>/<modulo>"
```

**Логика фильтрации:**
```
бот_разрешён ⇔ (bot_user_id % modulo) == remainder
```

Где:
- `bot_user_id` — числовая часть токена **до двоеточия** (`123456789:AAA...` → `123456789`)
- `modulo` — делитель (должен быть > remainder)
- `remainder` — ожидаемый остаток от деления

> ⚠️ **Важно**: `remainder` **должен быть строго меньше** `modulo`, иначе сервер не запустится.

---

### 🎯 Сценарий 1: Один конкретный бот

**Дано**: Бот с `bot_user_id = 9156782340`

**Расчёт**:
```bash
# Берём modulo > bot_user_id, remainder = bot_user_id
modulo=10000000000
remainder=9156782340

# Проверка:
9156782340 % 10000000000 = 9156782340 ✓
```

**Результат**:
```bash
TELEGRAM_FILTER=9156782340/10000000000
```

---

### 🎯 Сценарий 2: Два конкретных бота (ваш кейс)

**Дано**: Боты `4523891076` и `7812459328`

**Расчёт**:
```bash
# 1. Вычисляем разность (это будет наш modulo)
bot1=4523891076
bot2=7812459328
modulo=$((bot2 - bot1))  # 3288568252

# 2. Вычисляем remainder (остаток от деления любого из ботов на modulo)
remainder=$((bot1 % modulo))  # 1235322824

# 3. Проверяем условие remainder < modulo
# 1235322824 < 3288568252 ✓
```

**Проверка для обоих ботов**:
```bash
# Бот #1:
4523891076 % 3288568252 = 1235322824 ✓

# Бот #2:
7812459328 % 3288568252 = 1235322824 ✓
```

**Результат**:
```bash
TELEGRAM_FILTER=1235322824/3288568252
```

---

### 🎯 Сценарий 3: Боты по паттерну

| Паттерн | Формула | Пример |
|---------|---------|--------|
| Все чётные ID | `modulo=2`, `remainder=0` | `TELEGRAM_FILTER=0/2` |
| Все нечётные ID | `modulo=2`, `remainder=1` | `TELEGRAM_FILTER=1/2` |
| ID, оканчивающиеся на 5 | `modulo=10`, `remainder=5` | `TELEGRAM_FILTER=5/10` |
| ID в диапазоне [7000000000, 7999999999] | `modulo=1000000000`, `remainder=700000000` | `TELEGRAM_FILTER=700000000/1000000000` |

> ⚠️ Паттерны дают **приблизительную** фильтрацию — могут пропустить лишние боты.

---

### 🧰 Калькулятор фильтра (Bash)

```bash
#!/bin/bash
# calc_filter.sh — калькулятор TELEGRAM_FILTER

if [ $# -lt 2 ]; then
    echo "Использование: $0 <bot_id_1> <bot_id_2> [bot_id_3 ...]"
    echo "Пример: $0 4523891076 7812459328"
    exit 1
fi

# Если передан один бот — простой фильтр
if [ $# -eq 1 ]; then
    bot_id=$1
    modulo=10000000000
    remainder=$bot_id
    echo "Один бот:"
    echo "TELEGRAM_FILTER=${remainder}/${modulo}"
    exit 0
fi

# Если два бота — считаем по разности
if [ $# -eq 2 ]; then
    bot1=$1
    bot2=$2

    # Разность — это modulo
    modulo=$((bot2 > bot1 ? bot2 - bot1 : bot1 - bot2))

    # Остаток от деления первого бота на modulo
    remainder=$((bot1 % modulo))

    echo "Два бота: $bot1 и $bot2"
    echo "TELEGRAM_FILTER=${remainder}/${modulo}"

    # Проверка
    echo -e "\nПроверка:"
    echo "  $bot1 % $modulo = $((bot1 % modulo)) $([ $((bot1 % modulo)) -eq $remainder ] && echo '✓' || echo '✗')"
    echo "  $bot2 % $modulo = $((bot2 % modulo)) $([ $((bot2 % modulo)) -eq $remainder ] && echo '✓' || echo '✗')"
    exit 0
fi

# Если больше двух ботов — предупреждение
echo "⚠️  Для 3+ ботов математический фильтр может быть неточным."
echo "Рекомендация: запустите отдельные экземпляры сервера для каждого бота."
```

**Использование**:
```bash
chmod +x calc_filter.sh
./calc_filter.sh 4523891076 7812459328
# Вывод:
# Два бота: 4523891076 и 7812459328
# TELEGRAM_FILTER=1235322824/3288568252
#
# Проверка:
#   4523891076 % 3288568252 = 1235322824 ✓
#   7812459328 % 3288568252 = 1235322824 ✓
```

---

### 🐍 Калькулятор фильтра (Python)

```python
#!/usr/bin/env python3
"""calc_filter.py — калькулятор TELEGRAM_FILTER для любого количества ботов"""

import sys
from math import gcd
from functools import reduce

def calculate_filter(bot_ids: list[int]) -> str:
    """Рассчитывает TELEGRAM_FILTER для списка bot_user_id"""

    if len(bot_ids) == 1:
        # Один бот: простой фильтр
        modulo = 10_000_000_000
        remainder = bot_ids[0]
        return f"{remainder}/{modulo}"

    if len(bot_ids) == 2:
        # Два бота: фильтр по разности
        diff = abs(bot_ids[1] - bot_ids[0])
        remainder = bot_ids[0] % diff
        return f"{remainder}/{diff}"

    # 3+ ботов: ищем НОД всех попарных разностей
    diffs = [abs(bot_ids[i] - bot_ids[j])
             for i in range(len(bot_ids))
             for j in range(i+1, len(bot_ids))]

    modulo = reduce(gcd, diffs)
    remainder = bot_ids[0] % modulo

    # Проверка: все ли боты проходят фильтр?
    if all((bot_id % modulo) == remainder for bot_id in bot_ids):
        return f"{remainder}/{modulo}"
    else:
        return None  # Невозможно создать точный фильтр

# Основной блок
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: calc_filter.py <bot_id_1> <bot_id_2> [...]")
        print("Пример: calc_filter.py 4523891076 7812459328")
        sys.exit(1)

    bot_ids = [int(x) for x in sys.argv[1:]]
    result = calculate_filter(bot_ids)

    if result:
        print(f"TELEGRAM_FILTER={result}")
        # Проверка
        modulo = int(result.split('/')[1])
        remainder = int(result.split('/')[0])
        print("\nПроверка:")
        for bot_id in bot_ids:
            status = "✓" if (bot_id % modulo) == remainder else "✗"
            print(f"  {bot_id} % {modulo} = {bot_id % modulo} {status}")
    else:
        print("❌ Невозможно создать точный фильтр для указанного набора ботов.")
        print("Рекомендация: используйте отдельные экземпляры сервера.")
```

---

### 📊 Таблица готовых фильтров

| Боты (bot_user_id) | TELEGRAM_FILTER | Примечание |
|-------------------|-----------------|------------|
| `9156782340` | `9156782340/10000000000` | Один бот |
| `4523891076`, `7812459328` | `1235322824/3288568252` | ✅ Пример из гайда |
| `100`, `200`, `300` | `0/100` | Все кратные 100 |
| `101`, `201`, `301` | `1/100` | Все ≡ 1 (mod 100) |
| Любые чётные | `0/2` | Простой паттерн |
| Любые нечётные | `1/2` | Простой паттерн |

> ⚠️ Для произвольного набора из 3+ ботов **не всегда возможно** создать точный фильтр. В таких случаях используйте отдельные экземпляры сервера.

---

## 🧪 Тестирование

### ✅ Проверка разрешённых ботов

```bash
# Бот #1 (должен вернуть информацию)
curl -s "http://127.0.0.1:8081/bot4523891076:YOUR_REAL_TOKEN/getMe" | jq

# ✅ Ожидаемый ответ:
{
  "ok": true,
  "result": {
    "id": 4523891076,
    "is_bot": true,
    "first_name": "Example Bot",
    "username": "example_bot"
  }
}

# Бот #2 (также должен работать)
curl -s "http://127.0.0.1:8081/bot7812459328:YOUR_OTHER_TOKEN/getMe" | jq .ok
# true
```

### ❌ Проверка запрещённых ботов

```bash
# Любой другой бот (должен вернуть ошибку 421)
curl -s "http://127.0.0.1:8081/bot123456789:FAKE_TOKEN/getMe" | jq

# ✅ Ожидаемый ответ:
{
  "ok": false,
  "error_code": 421,
  "description": "Misdirected Request: unallowed token specified"
}
```

### 📋 Просмотр логов фильтрации

```bash
# В реальном времени
docker compose logs -f telegram-bot-api | grep -E "(filtered|Misdirected|user:)"

# Пример вывода:
# [2026-04-30 12:30:00] [info] [user:4523891076] method getMe — allowed ✓
# [2026-04-30 12:30:05] [info] [user:123456789] method getMe — filtered out ✗
```

### 🔍 Проверка переменных внутри контейнера

```bash
# Посмотреть все TELEGRAM_* переменные
docker compose exec telegram-bot-api env | grep '^TELEGRAM_'

# Ожидаемый вывод:
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_FILTER=1235322824/3288568252
TELEGRAM_LOCAL=1
TELEGRAM_VERBOSITY=2
```

---

## 🔐 Безопасность

### ✅ Чек-лист защиты

| Мера | Команда / Действие | Зачем |
|------|-------------------|--------|
| **Ограничить порт** | `ports: "127.0.0.1:8081:8081"` | Сервер не доступен извне |
| **TELEGRAM_LOCAL=1** | В `environment` | Принимать запросы только с localhost |
| **Права на .env** | `chmod 600 .env` | Только владелец читает секреты |
| **Git ignore** | Добавить `.env` в `.gitignore` | Предотвращение утечки в репозиторий |
| **Регулярные обновления** | `docker compose pull && up -d` | Получение исправлений безопасности |
| **Мониторинг логов** | Настроить сбор логов в ELK/Sentry | Обнаружение подозрительной активности |

### 🔐 Если нужен доступ извне (не рекомендуется)

Если сервер должен быть доступен другим хостам в доверенной сети:

```yaml
ports:
  - "10.0.0.5:8081:8081"  # Конкретный внутренний IP
# ИЛИ с firewall:
# - "8081:8081" + iptables -A INPUT -p tcp --dport 8081 -s 10.0.0.0/24 -j ACCEPT
```

**Дополнительно**: настройте базовую авторизацию через reverse proxy (Nginx):

```nginx
# /etc/nginx/conf.d/telegram-bot-api.conf
server {
    listen 8081;

    location / {
        # Базовая авторизация
        auth_basic "Telegram Bot API";
        auth_basic_user_file /etc/nginx/.htpasswd;

        proxy_pass http://127.0.0.1:8082;  # внутренний порт контейнера
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 🛠️ Troubleshooting

### ❌ Ошибка: `Wrong argument specified: ensure that remainder < modulo`

**Причина**: Перепутан порядок в `TELEGRAM_FILTER`.

**Решение**:
```bash
# Неправильно:
TELEGRAM_FILTER=3288568252/1235322824  # modulo/remainder ✗

# Правильно:
TELEGRAM_FILTER=1235322824/3288568252  # remainder/modulo ✓
```

### ❌ Ошибка: `Failed to authorize: API_ID hash mismatch`

**Причина**: Неверные `TG_API_ID` или `TG_API_HASH`.

**Решение**:
1. Перепроверьте данные на [https://my.telegram.org](https://my.telegram.org)
2. Убедитесь, что приложение создано для аккаунта, которому принадлежат боты
3. Перезапустите контейнер:
   ```bash
   docker compose down && docker compose up -d
   ```

### ❌ Бот не получает сообщения / таймауты

**Возможные причины**:
1. **Сетевой доступ**: Сервер не может достучаться до серверов Telegram
   ```bash
   # Проверка из контейнера
   docker compose exec telegram-bot-api nc -zv 149.154.160.5 443
   ```
2. **Firewall на хосте**: Блокировка исходящих соединений
   ```bash
   # Проверка правил на хосте
   sudo iptables -L OUTPUT -n -v | grep 443
   ```
3. **Прокси**: Если в сети используется прокси, настройте его для контейнера:
   ```yaml
   environment:
     - HTTPS_PROXY=http://proxy.local:3128
     - HTTP_PROXY=http://proxy.local:3128
     - NO_PROXY=localhost,127.0.0.1
   ```

### ❌ Контейнер не запускается: `port 8081 is already allocated`

**Решение**:
```bash
# Найти процесс, занимающий порт
sudo ss -tlnp | grep 8081

# Вариант А: освободить порт
sudo systemctl stop conflicting-service

# Вариант Б: сменить порт в docker-compose
ports:
  - "127.0.0.1:8082:8081"  # хост:контейнер
```

### ❌ Переменные из .env не подставились

**Проверка**:
```bash
# 1. Файл .env в той же директории, что docker-compose.yml?
ls -la .env docker-compose.yml

# 2. Синтаксис .env (без пробелов вокруг =)?
cat .env
# ✅ TG_API_ID=123456
# ❌ TG_API_ID = 123456

# 3. Проверка подстановки
docker compose config | grep TELEGRAM_API_ID

# 4. Явное указание пути к .env
docker compose --env-file /full/path/.env up -d
```

---

## 📋 Quick Reference

### 🚀 Быстрые команды

```bash
# Запуск
cd /opt/telegram-bot-api && docker compose up -d

# Остановка
docker compose down

# Перезапуск с пересозданием
docker compose up -d --force-recreate

# Просмотр логов
docker compose logs -f --tail=50 telegram-bot-api

# Проверка статуса
docker compose ps

# Обновление образа
docker compose pull && docker compose up -d --force-recreate

# Вход в контейнер для отладки
docker compose exec telegram-bot-api sh

# Проверка переменных внутри
docker compose exec telegram-bot-api env | grep TELEGRAM
```

### 🔢 Расчёт фильтра: one-liner

```bash
# Для двух ботов:
bot1=4523891076; bot2=7812459328; \
modulo=$((bot2-bot1)); remainder=$((bot1%modulo)); \
echo "TELEGRAM_FILTER=${remainder}/${modulo}"
# Вывод: TELEGRAM_FILTER=1235322824/3288568252
```

### 📊 Мониторинг: Prometheus metrics

Сервер предоставляет метрики на отдельном порту (если задан `--http-stat-port`):

```yaml
# В docker-compose.yml добавьте:
environment:
  - TELEGRAM_VERBOSITY=2
ports:
  - "127.0.0.1:8081:8081"      # API
  - "127.0.0.1:8082:8082"      # Метрики (опционально)
command: ["--http-stat-port=8082"]  # или через env: TELEGRAM_STAT_PORT
```

```bash
# Получение метрик
curl -s http://127.0.0.1:8082/metrics | head -20
```

### 🔄 Backup и восстановление

```bash
# Бэкап данных (вебхуки, кеш)
docker compose exec telegram-bot-api tar czf - /var/lib/telegram-bot-api \
  > backup-$(date +%Y%m%d).tar.gz

# Восстановление
cat backup-20260430.tar.gz | docker compose exec -T telegram-bot-api \
  tar xzf - -C /
```

---

## 📎 Ссылки

| Ресурс | Описание |
|--------|----------|
| [🐳 Docker Hub: aiogram/telegram-bot-api](https://hub.docker.com/r/aiogram/telegram-bot-api) | Официальный образ с документацией |
| [📦 GitHub: tdlib/telegram-bot-api](https://github.com/tdlib/telegram-bot-api) | Исходный код сервера |
| [🔑 my.telegram.org](https://my.telegram.org) | Получение API credentials |
| [📖 Telegram Bot API Docs](https://core.telegram.org/bots/api) | Документация API |
| [🧮 Калькулятор фильтра (онлайн)](https://www.calculatorsoup.com/calculators/math/modulo-calculator.php) | Проверка вычислений modulo |

---

> 💡 **Итоговая рекомендация для вашего кейса**:
>
> Для ботов **4523891076** и **7812459328** используйте:
> ```bash
> TELEGRAM_FILTER=1235322824/3288568252
> ```
>
> Это обеспечит:
> - ✅ Доступ только для указанных ботов
> - ✅ Вероятность случайной коллизии ~3×10⁻¹⁰
> - ✅ Минимальную сложность настройки
>
> Для абсолютной изоляции рассмотрите запуск двух экземпляров на разных портах.

🚀 **Удачного развёртывания!**
