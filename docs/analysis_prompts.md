# Варианты промптов анализа

Промпты лежат в `config/deepseek_prompts.yaml`. Верхний блок
`prompt_variants` задаёт подписи кнопок:

```yaml
prompt_variants:
  game_analysis: "Обычный разбор"
  game_analysis_sarcastic: "Саркастичный разбор"
  game_analysis_shahmaty_eto_kruto: "Шахматы — это Круто"
```

Каждый вариант — секция с `system` и `user_template`.

## Повторный анализ

В модалке анализа:

1. Выберите вариант промпта.
2. Нажмите «🔄 Повторить анализ».

Запрос:

```http
POST /player/<username>/game/<game_id>/analyze
Content-Type: application/json

{"prompt_key": "game_analysis_sarcastic", "force": true}
```

- `force: true` перезапускает анализ, даже если результат уже есть.
- Новый результат перезаписывает `game_analysis` у партии.
- Без `force` уже готовый анализ просто возвращается.

Выбранный вариант сохраняется в `localStorage` браузера.
