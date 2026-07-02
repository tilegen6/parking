# Smart Parking — Frontend (админ-панель)

Админ-панель системы умной парковки. Показывает события распознавания
номеров, статистику и список камер.

## Стек

- **React 18 + TypeScript + Vite**
- **Tailwind CSS** — вёрстка
- **React Router** — страницы (Дашборд / События / Камеры)
- **TanStack Query** — запросы к backend, кэш, автообновление

## Запуск

```bash
cd frontend
cp .env.example .env        # при необходимости поправить VITE_API_URL
npm install
npm run dev
```

Откроется на http://localhost:5173. Backend должен быть запущен на
`http://localhost:8000` (или укажите свой адрес в `.env`).

## Сборка

```bash
npm run build      # сборка в dist/
npm run preview    # локальный предпросмотр сборки
npm run lint       # проверка типов (tsc --noEmit)
```

## Страницы

| Путь        | Что показывает                                              |
|-------------|------------------------------------------------------------|
| `/`         | Дашборд: событий сегодня, последнее распознавание, камеры |
| `/events`   | Таблица событий: фильтры, фото, автообновление каждые 5 с  |
| `/cameras`  | Список камер + форма добавления                            |

## Структура

```
src/
  api/
    client.ts    # fetch-обёртка
    types.ts     # типы ответов backend
    hooks.ts     # TanStack Query хуки
  components/     # Layout, Sidebar, Header, PhotoModal, ...
  pages/          # Dashboard, Events, Cameras
  lib/format.ts   # форматирование даты/направления/confidence
```
