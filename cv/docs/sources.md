# Источники и проверка payload

Честная разбивка: что **подтверждено реальным захватом**, а что было
**реконструкцией**, и как проверить всё на нашей конкретной камере.

## Откуда взялась информация

| Что | Источник | Статус |
|-----|----------|--------|
| Транспорт (multipart XML + JPEG), структура `EventNotificationAlert`, поля `licensePlate`, `direction=forward/reverse`, `confidenceLevel`, `pictureInfoList` | **Реальный дословный захват** с камеры iDS-2CD7A26G0/P-IZHS (та же DeepinView ANPR-серия, прошивка V5.8.60), пост #13 на IPCamTalk | ✅ подтверждено |
| Имена частей `licensePlatePicture.jpg` / `vehiclePicture.jpg` / `detectionPicture.jpg` | тот же захват | ✅ подтверждено |
| Настройка приёмника через `PUT /ISAPI/Event/notification/httpHosts/1` | тот же тред, пост #16 (рабочий пример с Postman) | ✅ подтверждено |
| Поля-маппинг в нашем коде (`licensePlate`, `direction`, `confidenceLevel`, `channelName`) | `backend/src/hikvision.py` в этом репозитории | ✅ есть в коде |
| Мои первые `anpr_entry.xml` / `anpr_exit.xml` | **реконструкция** по ISAPI + именам полей из нашего парсера | ⚠️ синтетика, не дословно с вендора |
| Официальная страница `XML_EventNotificationAlert_ANPRMsg` | tpp.hikvision.com (ISAPI wiki) | ⛔ за логином партнёра — прочитать не удалось |

**Вывод:** дословный эталон — `samples/real_capture_ipcamtalk.xml`. Мои
синтетические `anpr_entry.xml`/`anpr_exit.xml` оставлены как упрощённые
демо для тестов ENTRY/EXIT (в реальном захвате `forward`=ENTRY совпало).

## Есть ли «тестовый API вендора»?

Публичной песочницы Hikvision, отдающей фейковое ANPR-событие, **нет**.
Авторитетная спецификация — ISAPI Developer Guide, он за партнёрским логином
на tpp.hikvision.com. НО проверять не нужно по спеке — **сама камера и есть
тестовый API**: у неё REST-интерфейс ISAPI, к которому можно обращаться напрямую
(digest-аутентификация, `admin` + пароль).

### Как снять реальный ответ прямо с камеры

Замените `<CAM_IP>` и пароль. Это и есть «проверяемый ответ от камеры».

```bash
# 1. Базовая инфо об устройстве — проверка, что ISAPI доступен
curl --digest -u admin:'PASSWORD' http://<CAM_IP>/ISAPI/System/deviceInfo

# 2. Возможности ANPR-канала
curl --digest -u admin:'PASSWORD' http://<CAM_IP>/ISAPI/Traffic/channels/1/capabilities

# 3. Куда камера шлёт события (настроенные listening-серверы)
curl --digest -u admin:'PASSWORD' http://<CAM_IP>/ISAPI/Event/notification/httpHosts

# 4. ЖИВОЙ поток событий — открывается и висит; проезжает машина → прилетает
#    тот самый multipart EventNotificationAlert. Это эталонный реальный payload.
curl --digest -u admin:'PASSWORD' http://<CAM_IP>/ISAPI/Event/notification/alertStream
```

Эндпоинт `alertStream` (#4) отдаёт ровно то, что мы парсим, прямо с вашей
камеры — без посредников. Можно сравнить байт-в-байт с
`samples/real_capture_ipcamtalk.xml`.

### Настроить отправку на наш capture-сервер (из треда, рабочий вариант)

```
PUT http://<CAM_IP>/ISAPI/Event/notification/httpHosts/1
Auth: Digest (admin / PASSWORD)
Content-Type: application/xml

<HttpHostNotification version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <id>1</id>
  <protocolType>HTTP</protocolType>
  <parameterFormatType>XML</parameterFormatType>
  <addressingFormatType>ipaddress</addressingFormatType>
  <ipAddress>НАШ_СЕРВЕР_IP</ipAddress>
  <portNo>8088</portNo>
  <httpAuthenticationMethod>none</httpAuthenticationMethod>
  <ANPR>
    <detectionUploadPicturesType opt="all,licensePlatePicture,detectionPicture">all</detectionUploadPicturesType>
  </ANPR>
</HttpHostNotification>
```

## Важные практические заметки (из того же реального треда)

- **Detection mode** должен быть `License Plate & Vehicle`, а не только `Vehicle`,
  иначе номер не приходит (придёт `unknown`).
- **ANR (дозапись)**: если включён, камера зацикливает первое событие, пока не
  получит `HTTP/1.1 200 OK`. Наш capture-сервер обязан отвечать `200`, иначе —
  повторы. На время отладки ANR лучше выключить.
- Можно случайно получать событие `TPSRealTime` (счётчик трафика, JSON, без
  номера) вместо `ANPR` — проверять `eventType`.
- Открытие шлагбаума с пульта **не** генерит ANPR-событие — нужен отдельный
  alarm-input.

## Ссылки

- IPCamTalk, реальный захват и настройка: https://ipcamtalk.com/threads/get-passed-license-plate-numbers-using-isapi.79032/
- Конкретный пост с дословным payload (#13): https://ipcamtalk.com/threads/get-passed-license-plate-numbers-using-isapi.79032/post-888807
- Официальная ISAPI-страница (нужен партнёрский логин): https://tpp.hikvision.com/wiki/isapi/anpr/GUID-328FC5AD-38EA-4409-9E75-996279BF2A46.html
- Карточка нашей модели: https://www.hikvision.com/en/products/IP-Products/Network-Cameras/DeepinView-Series/ids-2cd7a46g0-p-izhs-y-/
