# samples — эталонные payload'ы

Синтетические, но структурно достоверные ANPR-события Hikvision
(`EventNotificationAlert`, namespace `ver20/XMLSchema`).

| Файл | Сценарий | direction | Номер |
|------|----------|-----------|-------|
| `anpr_entry.xml` | въезд | `forward` → ENTRY | 123ABC02 |
| `anpr_exit.xml`  | выезд  | `reverse` → EXIT  | 123ABC02 |

⚠️ Это **черновик до съёма реального трафика**. Как только `capture_server.py`
запишет настоящие события с камеры, эти файлы заменяются/дополняются реальными
(многие прошивки добавляют свои поля — `picName`, `XID`, абсолютные/UTC времена,
вложенные блоки `vehicleInfo`). После этого правим `backend/src/hikvision.py`
под фактический формат.
