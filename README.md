# AUTORA

Портфельный Django-проект современного автосервиса: публичный сайт, онлайн-заявка, приватный статус ремонта, кабинет сотрудников и системная админка.

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DJANGO_ENV=development
export CLIENT_TOKEN_ENCRYPTION_KEYS=local-development-encryption-key-change-me
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

`seed_demo` создаёт только контент сайта: настройки, услуги, клиентов, автомобили, заказы, события и позиции сметы. Пользователи, группы и пароли команда не создаёт.

Администратор создаётся стандартной командой Django:

```bash
python manage.py createsuperuser
```

После этого вход: `http://127.0.0.1:8000/admin/`.

## Проверки

```bash
python manage.py check
python manage.py test
python manage.py collectstatic --noinput
```

Реальные `.env`, база, загрузки и собранная статика не должны попадать в Git.

## Локальная админка и CSRF

Некоторые встроенные браузеры IDE отправляют `Origin: null`. В development-режиме проект безопасно нормализует такой заголовок только для loopback-хостов (`localhost`, `127.0.0.1`, `0.0.0.0`), после чего стандартная CSRF-проверка токена продолжает работать. В production это исключение отключено.

Для локального входа используйте `DJANGO_ENV=development`, `DJANGO_DEBUG=1`, откройте сначала `/admin/login/`, затем войдите суперпользователем, созданным через `python manage.py createsuperuser`.
