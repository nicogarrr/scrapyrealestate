# Auditoría de portales Strategy Miner 2.4

- Fecha: 24-09-2026
- Método: Playwright con Chromium instalado localmente, contexto público, sin login y sin proxies.
- Alcance: comprobar qué contratos de scraping siguen siendo útiles para `scrapyrealestate`.

## Resumen ejecutivo

| Portal | HTTP observado | Contenido usable observado | Decisión |
|---|---:|---|---|
| Idealista | 403 en la respuesta HTTP, pero el documento renderizado contiene 30 `article.item` y 30 enlaces `/inmueble/` | Sí | Mantener como fuente experimental con browser/Scrapy-Playwright; no activar evasión de controles |
| Habitaclia | 200 en la portada; la ruta probada no resolvió a un listado y el documento no tuvo tarjetas | No en esa prueba | No cambiar el spider con la URL de portada; mantener pendiente una ruta de búsqueda válida y verificarla por separado |
| Yaencontre | 404 en la ruta de Asturias probada | No | No usar esa URL ni Inferir selectores; mantener el spider deshabilitado hasta validar la ruta de resultados |

## Idealista: hechos verificados en vivo

La captura de `https://www.idealista.com/venta-viviendas/asturias/` devolvió una página con 30 tarjetas `article.item`, 30 contenedores `.item-info-container` y 30 enlaces de anuncios. La respuesta fue `403`, pero el DOM renderizado sí contenía los resultados. Esto confirma que el estado HTTP no basta para declarar bloqueado; hay que distinguir entre bloqueo total y respuesta renderizada con contenido.

La página también mostró:

- Filtro `Ascensor`: `https://www.idealista.com/venta-viviendas/asturias/con-ascensor/`.
- Paginación: `pagina-2.htm`, `pagina-3.htm`, etc. `?pagina=2` no es el contrato observado.
- Precio actual: `450.000€`, con separación de millares con punto.
- Características en `span.item-detail`.
- Enlace estable: `a.item-link[href*='/inmueble/']`.
- ID: el número de `/inmueble/<id>/`.
- La tarjeta puede incluir texto deЕНИам locales; el parser actual todavía reutiliza estado entre tarjetas y produce IDs repetidos en la prueba local.

### Acción técnica prioritaria

1. Reescribir `IdealistaSpider` con una instancia de `ScrapyrealestateItem` por tarjeta.
2. Usar `a.item-link` y `/inmueble/<id>/` para identidad.
3. Inicializar `rooms`, `m2`, `floor` y `elevator` por tarjeta.
4. Detectar ascensor por URL de búsqueda y por texto explícito de la tarjeta, sin asumir que toda tarjeta lo tiene.
5. Añadir una prueba de contrato con la captura real anonimizada y comprobar que 30 entradas producen 30 IDs únicos.

## Habitaclia: hechos observados

La portada respondió `200`, pero el documento fue una pantalla de consentimiento y no una lista. La ruta de búsqueda probada en la auditoría automatizada no resolvió a resultados. Por tanto, no hay base para cambiar el spider a selectores nuevos: primero hay que encontrar una URL de búsqueda válida y capturar su HTML real.

## Yaencontre: hechos observados

`https://www.yaencontre.com/venta/pisos/asturias` respondió `404`. La URL actual del repositorio tampoco debe considerarse válida sin una nueva verificación. El spider existente permanece sin soporte operativo.

## Fuentes de ideas externas revisadas

- `agusyornet/idealista-monitor`: https://github.com/agusyornet/idealista-monitor — patrón de monitorización y estado visto; usa un proveedor de acceso de pago, no se incorpora el proveedor.
- `OxyHQ/Homiio`: https://github.com/OxyHQ/Homiio — patrón de proveedor con fallback JSON/AJAX/HTML y pruebas de parsers; útil como referencia de arquitectura, no como dependencia directa.
- `abracadabra50/open-properties`: https://github.com/abracadabra50/open-properties — contrato de configuración de búsqueda y normalización multiportales; requiere revisar licencias y adaptarlo al Item actual.
- `Alexramsal/home-ops`: https://github.com/Alexramsal/home-ops — referencia de normalización, deduplicación, persistencia y dashboard; no assume que sus selectores siguen vigentes.
- `sergi039/idealista-tracker-ai`: https://github.com/sergi039/idealista-tracker-ai — referencia de seguimiento e histórico; validar cada scraper antes de copiar.

No se recommendan proxies gratuitos, rotación de User-Agent para evadir bloqueos ni extracción de tokens, cookies o datos internos de terceros. La integración debe usar rutas públicas permitidas, APIs autorizadas o una fuente de datos contratada, respetando los términos de cada portal.

## Actualización posterior: Yaencontre sí tiene ruta pública válida

La primera auditoría comprobó `https://www.yaencontre.com/venta/pisos/asturias`, pero una segunda prueba con Chromium encontró la ruta correcta:

- Base: `https://www.yaencontre.com/venta/pisos/gijon` → `200`, 42 tarjetas.
- Ascensor: `https://www.yaencontre.com/venta/pisos/gijon/f-ascensor` → `200`, título con `864` resultados y 42 tarjetas.
- Paginación: `pag-2`, `pag-3`, etc. No usar `/pagina-2`.
- La tarjeta actual es `article.real-estate-map-list-card`.
- El enlace de detalle sigue `/venta/piso/inmueble-<id>-<listingId>`; el segundo número es el ID del anuncio.
- Precio, m², habitaciones y baños están en `.price-wrapper` y `.media-info`.

Se actualizó el spider y se añadieron dos pruebas con la captura real. La ruta de configuración de Asturias debe cambiarse a una URL municipal válida cuando se configure el mercado concreto; no convertir la ruta `asturias` en un hecho válido por analogía.
