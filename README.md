# 🤖📝 BOT DE ENCUESTA SEMARNAT

Automatiza el llenado de encuestas usando **Python 3.12 + Selenium + 2Captcha** 🚀

Este proyecto toma registros desde un archivo `.csv`, abre el formulario en Chrome, llena los campos automáticamente, resuelve el captcha con **2Captcha** y lleva control de los correos ya procesados ✅

---

## 🌟 ¿Qué hace este bot?

Este bot fue pensado para:

- 📥 Leer registros desde un archivo CSV
- 🌐 Abrir la encuesta automáticamente en Chrome
- ✍️ Llenar datos personales y preguntas
- 🧩 Resolver el captcha con 2Captcha
- 📧 Evitar reprocesar correos ya usados
- 📝 Guardar logs detallados
- 📂 Detectar automáticamente el `.csv` dentro de `bd/`

---

## 🧠 ¿Cómo funciona?

El flujo general es este:

1. 📂 Busca un archivo `.csv` dentro de la carpeta `bd/`
2. 📖 Lee el archivo y valida columnas obligatorias
3. 🌍 Abre la página de la encuesta
4. 👤 Llena nombre, dirección, correo y demás campos
5. ❓ Marca respuestas predefinidas
6. 🧩 Descarga el captcha y lo envía a 2Captcha
7. 📤 Envía el formulario
8. ✅ Guarda el resultado en `txt_verificados/procesados.txt`
9. 📝 Escribe logs en la carpeta `logs/`

---

## 🗂️ Estructura del proyecto

```text
proyecto-encuesta/
├── bd/                     # Aquí va el archivo CSV
├── browser.py              # Configuración de Selenium y Chrome
├── captcha_solver.py       # Integración con 2Captcha
├── encuesta_bot.py         # Bot principal
├── requirements.txt        # Dependencias del proyecto
├── logs/                   # Logs de ejecución
├── downloads/              # Descargas del navegador
├── temp_captcha/           # Imágenes temporales de captcha
└── txt_verificados/        # Control de registros procesados
```

---

## ⚙️ Requisitos

Antes de usarlo, asegúrate de tener:

- 🐍 **Python 3.12**
- 🌐 **Google Chrome** o **Chromium**
- 🚗 **ChromeDriver** compatible
- 🔑 Una cuenta con saldo en **2Captcha**

---

## 📦 Instalación

### 1. Crear entorno virtual

```bash
python3.12 -m venv venv
```

### 2. Activar entorno virtual

#### En macOS / Linux

```bash
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

---

## 🔐 Configuración del archivo `.env`

Crea un archivo `.env` en la raíz del proyecto con algo como esto:

```env
CAPTCHA_API_KEY=TU_API_KEY_DE_2CAPTCHA
URL_ENCUESTA=https://consultaspublicas.semarnat.gob.mx:8443/llenado/23QR2025T0061
HEADLESS=0
SELENIUM_PAGELOAD_TIMEOUT=90
SELENIUM_SCRIPT_TIMEOUT=90
SELENIUM_IMPLICIT_WAIT=10
DOWNLOAD_DIR=downloads
```

### 📝 Variables importantes

- `CAPTCHA_API_KEY` 🔑: tu API key de 2Captcha
- `URL_ENCUESTA` 🌍: URL del formulario a llenar
- `HEADLESS` 👻: `1` para ocultar navegador, `0` para verlo
- `DOWNLOAD_DIR` 📥: carpeta de descargas

---

## 📄 Formato del CSV

El archivo `.csv` debe incluir estas columnas obligatorias:

```text
CORREO
NOMBRE_COMPLETO
CALLE
NUM_EXTERIOR
COLONIA
CODIGO_POSTAL
ENTIDAD
MUNICIPIO
```

### ✨ Ejemplo

```csv
CORREO,NOMBRE_COMPLETO,CALLE,NUM_EXTERIOR,COLONIA,CODIGO_POSTAL,ENTIDAD,MUNICIPIO
correo1@ejemplo.com,JUAN PEREZ,AV PRINCIPAL,123,CENTRO,77500,23,5
correo2@ejemplo.com,MARIA LOPEZ,CALLE SOL,45,MODERNA,77510,23,7
```

---

## ▶️ Cómo ejecutar el bot

### ✅ Forma recomendada

Coloca **un solo archivo `.csv`** dentro de `bd/` y ejecuta:

```bash
python encuesta_bot.py
```

El bot detectará automáticamente el archivo.

### ✅ También puedes indicar un archivo manualmente

```bash
python encuesta_bot.py --csv bd/mi_archivo.csv
```

### ✅ Ejecutar en modo headless

```bash
python encuesta_bot.py --headless
```

### ✅ Ejecutar con interfaz visible

```bash
python encuesta_bot.py --no-headless
```

---

## 📌 Regla importante del CSV automático

Si ejecutas:

```bash
python encuesta_bot.py
```

el comportamiento es este:

- ✅ Si hay **1 solo `.csv`** dentro de `bd/`, lo usa automáticamente
- ❌ Si no hay ningún `.csv`, muestra error
- ❌ Si hay varios `.csv`, muestra error y te pide usar `--csv`

Esto se hizo para evitar procesar el archivo incorrecto por accidente ⚠️

---

## 🧩 Integración con 2Captcha

El proyecto usa la librería:

```bash
2captcha-python
```

Flujo del captcha:

1. 📸 Selenium localiza la imagen del captcha
2. 📥 Se descarga la imagen temporalmente
3. ☁️ Se envía a 2Captcha
4. 🔓 Se recibe el texto resuelto
5. ⌨️ El bot lo escribe y envía el formulario

Si tu API key es incorrecta o no tienes saldo, el sistema lo reportará en logs ❌

---

## 📝 Archivos generados durante la ejecución

### `logs/encuesta_bot.log`

Guarda el detalle general del bot:

- inicio
- errores
- registros procesados
- resumen final

### `logs/captcha.log`

Guarda todo lo relacionado con la resolución del captcha:

- descarga de imagen
- respuesta de 2Captcha
- errores de API
- errores de red

### `txt_verificados/procesados.txt`

Aquí se guardan los registros ya procesados para evitar repetir correos.

Ejemplo:

```text
correo1@ejemplo.com,JUAN PEREZ,2026-03-20 00:30:10,EXITOSO
correo2@ejemplo.com,MARIA LOPEZ,2026-03-20 00:31:55,FALLIDO
```

---

## 🛡️ Comportamientos importantes

- ✅ Ya no se crean carpetas temporales manuales de Chrome en `/var/folders/...`
- ✅ El sistema operativo se encarga de manejar archivos temporales del navegador
- ✅ El bot crea automáticamente carpetas necesarias como `logs/`, `downloads/` y `txt_verificados/`
- ✅ Si un correo ya fue procesado, se salta automáticamente

---

## 🚨 Errores comunes

### ❌ "No se encontró ningún archivo .csv dentro de 'bd'"

Solución:

- coloca un archivo `.csv` dentro de `bd/`

### ❌ "Se encontraron múltiples archivos CSV en 'bd'"

Solución:

- deja solamente uno en `bd/`
- o ejecuta con `--csv`

### ❌ "No has configurado la API key de 2Captcha"

Solución:

- revisa tu archivo `.env`
- asegúrate de que `CAPTCHA_API_KEY` tenga valor real

### ❌ "Saldo insuficiente en 2Captcha"

Solución:

- agrega fondos a tu cuenta de 2Captcha

### ❌ Chrome no abre o Selenium falla

Solución:

- verifica que Chrome/Chromium esté instalado
- verifica que ChromeDriver sea compatible
- prueba con `--headless`

---

## 🧪 Comando rápido de uso

```bash
source venv/bin/activate
python encuesta_bot.py
```

---

## 💡 Recomendaciones

- 📂 Deja un solo CSV dentro de `bd/`
- 🔑 Verifica saldo y API key de 2Captcha antes de empezar
- 🖥️ Usa modo visible primero para validar que todo llena bien
- 📝 Revisa los logs si algo falla

---

## ❤️ Resumen

Este proyecto automatiza encuestas de forma bastante directa:

- toma datos desde CSV 📄
- abre el formulario 🌐
- llena respuestas ✍️
- resuelve captcha 🧩
- envía resultados 📤
- evita duplicados ✅

Si lo ejecutas correctamente, el comando principal ahora es simplemente:

```bash
python encuesta_bot.py
```

---

## 🙌 Nota final

Si después quieres, también se puede mejorar para:

- 📅 procesar automáticamente el CSV más reciente
- 📊 exportar un resumen final bonito
- 🔁 reintentar captchas fallidos
- 🧠 personalizar respuestas por fila

