# Home Assistant Rostelecom Key integration

[![hacs_badge][hacs-shield]][hacs]
[![GitHub Release][releases-shield]][releases]
[![GitHub all releases][downloads-shield]][downloads]
[![Donate](https://img.shields.io/badge/donate-Tinkoff-FFDD2D.svg)](https://www.tinkoff.ru/rm/r_XcxxSexrTl.GlEflRXPzn/NA5GF67360)

Интеграция для управления умными домофонами Ростелеком через сервис [key.rt.ru](https://key.rt.ru) из Home Assistant.

## Установка

### Через HACS (рекомендуется)

1. Нажмите кнопку ниже:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.][hacs-repository-shield]][hacs-repository]

2. **Или** в HACS перейдите в "Интеграции", нажмите ⋮ → "Пользовательские репозитории"
3. Добавте `https://github.com/quetureve/hartkey` как "Интеграция"
4. Найдите "Hartkey" в списке интеграций HACS и установите
5. Перезагрузите Home Assistant

### Вручную

1. Скопируйте папку `custom_components/hartkey` в директорию `config/custom_components/` вашего Home Assistant
2. Перезагрузите Home Assistant

## Настройка

1. В Home Assistant перейдите в **Настройки** → **Устройства и службы** → **Интеграции**
2. Нажмите **"Добавить интеграцию"**
3. Найдите **"hartkey"** в списке
4. Вставьте Bearer Token (см. инструкцию ниже)
5. Настройте интервал обновления (по умолчанию 5 минут)

## Получение Bearer Token

1. Перейдите на [key.rt.ru/main/devices](https://key.rt.ru/main/devices)
2. Авторизуйтесь в своем аккаунте
3. Откройте **Инструменты разработчика** (F12)
4. Перейдите на вкладку **"Сеть" (Network)**
5. Обновите страницу (F5)
6. Найдите в списке любой запрос к API (например, к `household.key.rt.ru`)
7. Откройте этот запрос и перейдите на вкладку **"Заголовки" (Headers)**
8. Найдите заголовок **"Authorization"**
9. Скопируйте значение токена (без слова `Bearer`)

## Возможности

### 🎛️ Кнопки управления
- Отдельная кнопка для каждого домофона/ворот
- Быстрое открытие двери/ворот одним нажатием
- Доступны в интерфейсе и автоматизациях

### 📊 Сенсоры событий
- **Время последнего открытия** каждого устройства
- **Тип открытия** (API, распознавание лица, пин-код, RFID и т.д.)

## Конфигурация

Частоту обновления сенсоров можно изменить через окно настройки интеграции:

- **По умолчанию**: каждые 5 минут
- **Минимальный интервал**: 1 минута
- **Максимальный интервал**: 24 часа

## Поддержка

Если у вас возникли проблемы с работой интеграции:

1. Проверьте правильность введенного Bearer Token
2. Убедитесь, что ваш аккаунт key.rt.ru активен
3. Проверьте логи Home Assistant для диагностики ошибок
4. Создайте issue на [GitHub][issues]

***

[commits-shield]: https://img.shields.io/github/commit-activity/y/quetureve/hartkey.svg
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs]: https://github.com/hacs/integration
[hacs-repository-shield]: https://my.home-assistant.io/badges/hacs_repository.svg
[hacs-repository]: https://my.home-assistant.io/redirect/hacs_repository/?owner=quetureve&repository=hartkey&category=integration
[home-assistant]: https://www.home-assistant.io/
[releases-shield]: https://img.shields.io/github/v/release/quetureve/hartkey.svg
[releases]: https://github.com/quetureve/hartkey/releases
[downloads-shield]: https://img.shields.io/github/downloads/quetureve/hartkey/total
[downloads]: https://github.com/quetureve/hartkey/releases
[issues]: https://github.com/quetureve/hartkey/issues