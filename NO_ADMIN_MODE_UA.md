# Режим без веб-адмінки

У v15 веб-адмінку вимкнено за замовчуванням:

```text
DISABLE_ADMIN_UI=True
```

Автоматичний scheduler і офіційний bot API продовжують працювати. `/health`,
публічні affiliate-посилання та `/advertise` залишаються доступними.

Генерація через API потребує `Authorization: Bearer <AUTOMATION_API_TOKEN>`.
Веб-панель, login, password reset і `/admin/security` повертають 404.

Щоб тимчасово повернути панель для діагностики, встановіть
`DISABLE_ADMIN_UI=False` і зробіть redeploy.
