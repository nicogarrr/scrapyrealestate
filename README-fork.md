# Fork de Nico: pisos en Asturias <100.000€ con ascensor → Telegram

Adaptación de [mcrespov/scrapyrealestate](https://github.com/mcrespov/scrapyrealestate)
para avisar en un canal de Telegram de pisos **en venta en Asturias, hasta
100.000 € y con ascensor**, en cuanto se publican.

## Cambios respecto al original

- **Sin token por defecto**: el original traía hardcodeado un token de bot del
  autor. Eliminado; solo se usa el bot propio (web de config o
  `TELEGRAM_BOT_TOKEN`).
- **Datos persistentes**: `./data` se monta como volumen (config + histórico de
  avisos sobreviven a recrear el contenedor; en el original eran efímeros).
- **Build local**: la imagen de Docker Hub es solo x86; el servidor es ARM, así
  que el compose construye desde el código.
- **Límites de recursos** en compose (1 CPU / 1,5 GB) para convivir con otras
  apps del mismo servidor, y sin puertos publicados.
- **Overrides por entorno**: `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` por
  variables de entorno, sin escribir secretos en `config.json`.
- **Fix €/m²**: el parseo de m² se comía un dígito (85 m² → 8).
- **Config de Asturias** en `config.asturias.json`: Idealista, Pisos.com,
  Fotocasa y Yaencontre con filtros de venta + ascensor en la URL y precio
  máximo local (100.000 €). Habitaclia fuera: apenas tiene oferta en Asturias.
  Ciclo cada ~15 min. El primer ciclo solo registra lo existente
  (`send_first: False`): avisa a partir de las novedades, sin flood inicial.

## Despliegue (servidor Oracle, docker)

```bash
git clone https://github.com/nicogarrr/scrapyrealestate flats-bot
cd flats-bot
mkdir -p data && cp config.asturias.json data/config.json
# .env con el token del bot (NO se commitea):
printf 'TELEGRAM_BOT_TOKEN=xxxx\nTELEGRAM_CHAT_ID=-100xxxx\n' > .env && chmod 600 .env
docker compose up -d --build
docker logs -f flats-bot-asturias
```

El bot de Telegram debe ser **administrador del canal**. Para sacar el
`TELEGRAM_CHAT_ID` del canal: añadir el bot, escribir cualquier mensaje en el
canal y mirar `https://api.telegram.org/bot<TOKEN>/getUpdates`
(`chat.id`, empieza por `-100`).
