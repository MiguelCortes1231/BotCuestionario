#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import dotenv
import pandas as pd
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from encuesta_bot import EncuestaBot

dotenv.load_dotenv()

SPECIAL_COLUMNS = [
    "ID",
    "CORREO",
    "NOMBRE_COMPLETO",
    "CALLE",
    "NUM_EXTERIOR",
    "NUM_INTERIOR",
    "COLONIA",
    "CODIGO_POSTAL",
    "ENTIDAD",
    "MUNICIPIO",
]


def build_special_logger() -> logging.Logger:
    logger = logging.getLogger("encuestas_especiales")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    Path("logs").mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler("logs/encuestas_especiales.log", encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


logger = build_special_logger()


class EncuestasEspecialesBot(EncuestaBot):
    def __init__(self, csv_path: str, headless: bool = False):
        self.bd_dir = Path("bd_especiales")
        self.errors_dir = Path("errores")
        self.validated_dir = Path("validado_especiales")
        self.errors_csv = self.errors_dir / "bd_errores.csv"
        self.initial_csv_path = Path(csv_path)
        super().__init__(csv_path, headless=headless)
        self.processed_file = self.validated_dir / "validado_especiales.txt"
        self.processed_emails = set()
        self._load_processed()
        logger.info("🤖 BOT ESPECIAL INICIALIZADO")
        logger.info(f"📁 Bandeja especial: {self.bd_dir}")
        logger.info(f"🧾 Errores: {self.errors_csv}")
        logger.info(f"✅ Validados: {self.processed_file}")

    def _setup_directories(self):
        directories = [
            "downloads",
            "logs",
            "temp_captcha",
            str(self.bd_dir),
            str(self.errors_dir),
            str(self.validated_dir),
        ]

        for dir_name in directories:
            Path(dir_name).mkdir(parents=True, exist_ok=True)

    def _mark_as_processed(self, email: str, nombre: str, estado: str = "EXITOSO"):
        try:
            timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"{email},{nombre},{timestamp},{estado}\n"

            with open(self.processed_file, "a", encoding="utf-8") as f:
                f.write(line)

            self.processed_emails.add(email)
            logger.info(f"✅ Registro validado: {email}")
        except Exception as e:
            logger.error(f"❌ Error marcando como validado: {e}")

    def llenar_datos_personales(self, row: pd.Series) -> bool:
        try:
            logger.info(f"👤 Llenando datos para: {row['NOMBRE_COMPLETO']}")

            nombre_elem = self._safe_find_element(By.ID, "NombreRFC")
            if not nombre_elem or not self._safe_send_keys(nombre_elem, row["NOMBRE_COMPLETO"]):
                return False

            self._random_delay(0.5, 1)

            calle_elem = self._safe_find_element(By.ID, "Calle")
            if not calle_elem or not self._safe_send_keys(calle_elem, str(row["CALLE"])):
                return False

            self._random_delay(0.5, 1)

            num_ext_elem = self._safe_find_element(By.ID, "NumExt")
            if not num_ext_elem or not self._safe_send_keys(num_ext_elem, str(row["NUM_EXTERIOR"])):
                return False

            num_int_value = str(row.get("NUM_INTERIOR", "")).strip()
            if num_int_value and num_int_value.lower() != "nan":
                num_int_elem = self._safe_find_element(By.ID, "NumInt", timeout=3)
                if num_int_elem:
                    self._safe_send_keys(num_int_elem, num_int_value)
                    self._random_delay(0.3, 0.8)

            colonia_elem = self._safe_find_element(By.ID, "Asentamiento")
            if not colonia_elem or not self._safe_send_keys(colonia_elem, str(row["COLONIA"])):
                return False

            self._random_delay(0.5, 1)

            cp_elem = self._safe_find_element(By.ID, "CP")
            if not cp_elem or not self._safe_send_keys(cp_elem, str(row["CODIGO_POSTAL"])[:5]):
                return False

            logger.info("✅ Datos personales llenados")
            return True
        except Exception as e:
            logger.error(f"❌ Error llenando datos personales: {e}")
            return False

    def enviar_captcha_y_submit(self, captcha_text: str) -> bool:
        try:
            captcha_input = self._safe_find_element(By.ID, "captcha")
            if not captcha_input:
                return False

            if not self._safe_send_keys(captcha_input, captcha_text):
                return False

            logger.info("🔑 Captcha ingresado")
            self._random_delay(1, 2)

            submit_btn = self._safe_find_element(By.CSS_SELECTOR, "input[value='Enviar']")
            if not submit_btn:
                return False

            self._safe_click(submit_btn)
            logger.info("📤 Formulario enviado")

            try:
                WebDriverWait(self.driver, 12).until(lambda drv: drv.execute_script("return document.readyState") == "complete")
            except Exception:
                logger.warning("⚠️ La página no confirmó carga completa después del envío")

            self._random_delay(2, 4)
            return True
        except Exception as e:
            logger.error(f"❌ Error enviando formulario: {e}")
            return False

    def verificar_resultado_envio(self) -> Tuple[bool, str]:
        try:
            page_source = self.driver.page_source
            normalized = page_source.lower()

            success_text = "el cuestionario fue registrado exitosamente"
            captcha_invalid_markers = [
                "captcha es inválido",
                "captcha es invalido",
                "cã³digo de verificaciã³n captcha es invã¡lido",
                "codigo de verificacion captcha es invalido",
                "captcha inv",
            ]
            generic_error_markers = [
                "forbidden",
                "403",
                "error",
                "denied",
                "bad gateway",
                "service unavailable",
                "internal server error",
            ]

            if success_text in normalized:
                logger.info("✅ Confirmado por mensaje exacto de éxito")
                return True, "EXITOSO"

            if any(marker in normalized for marker in captcha_invalid_markers):
                logger.warning("⚠️ Captcha inválido detectado")
                return False, "CAPTCHA_INVALIDO"

            alert_text = self._extract_alert_text()
            if alert_text:
                logger.warning(f"⚠️ Respuesta con alerta: {alert_text}")
                return False, f"ALERTA: {alert_text[:120]}"

            if any(marker in normalized for marker in generic_error_markers):
                logger.warning("⚠️ La página devolvió un error genérico")
                return False, "ERROR_PAGINA"

            logger.warning("⚠️ No apareció el mensaje de éxito esperado")
            return False, "SIN_CONFIRMACION_EXITO"
        except Exception as e:
            logger.error(f"❌ Error verificando resultado del envío: {e}")
            return False, f"ERROR_VERIFICACION: {str(e)[:100]}"

    def _extract_alert_text(self) -> str:
        try:
            selectors = [
                "div.alert.alert-success",
                "div.alert.alert-danger",
                "div.alert",
            ]
            for selector in selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    text = element.text.strip()
                    if text:
                        return " ".join(text.split())
        except Exception as e:
            logger.debug(f"No se pudo extraer alerta: {e}")
        return ""

    def procesar_registro(self, row: pd.Series, idx: int) -> Tuple[bool, str]:
        email = str(row["CORREO"])
        nombre = str(row["NOMBRE_COMPLETO"])
        inicio_registro = time.perf_counter()

        logger.info(f"\n{'=' * 50}")
        logger.info(f"📋 Procesando registro especial {idx + 1}")
        logger.info(f"👤 {nombre}")
        logger.info(f"📧 {email}")
        logger.info("=" * 50)

        if email in self.processed_emails:
            logger.info(f"⏭️ Registro ya validado anteriormente: {email}")
            return True, "YA_VALIDADO"

        try:
            self.esperar_url_disponible()

            if not self.navegar_a_encuesta():
                return False, "NO_SE_PUDO_ABRIR_ENCUESTA"

            if not self.llenar_datos_personales(row):
                return False, "ERROR_DATOS_PERSONALES"

            if not self.seleccionar_entidad_municipio(row):
                return False, "ERROR_ENTIDAD_MUNICIPIO"

            if not self.llenar_correo(row):
                return False, "ERROR_CORREO"

            if not self.llenar_preguntas():
                return False, "ERROR_PREGUNTAS"

            captcha_text = self.resolver_captcha()
            if not captcha_text:
                return False, "NO_SE_PUDO_RESOLVER_CAPTCHA"

            if not self.enviar_captcha_y_submit(captcha_text):
                return False, "ERROR_ENVIO_FORMULARIO"

            exito, motivo = self.verificar_resultado_envio()
            if exito:
                self._mark_as_processed(email, nombre, motivo)
                logger.info(f"✅ Registro especial {idx + 1} validado correctamente")
            else:
                logger.warning(f"⚠️ Registro especial {idx + 1} falló: {motivo}")

            tiempo_total = time.perf_counter() - inicio_registro
            logger.info(f"⏱️ Registro especial {idx + 1} terminado en {tiempo_total:.2f} segundos")
            return exito, motivo
        except Exception as e:
            logger.error(f"❌ Error procesando registro especial {idx + 1}: {e}", exc_info=True)
            tiempo_total = time.perf_counter() - inicio_registro
            logger.info(f"⏱️ Registro especial {idx + 1} terminó con error en {tiempo_total:.2f} segundos")
            return False, f"ERROR_EXCEPCION: {str(e)[:120]}"

    def esperar_url_disponible(self):
        espera_segundos = int(os.getenv("SPECIAL_URL_RETRY_SECONDS", "10"))
        espera_bloqueo_html_segundos = int(os.getenv("SPECIAL_URL_FORBIDDEN_RETRY_SECONDS", "20"))
        intento = 1

        while True:
            try:
                logger.info(f"🔎 Verificando disponibilidad de URL_ENCUESTA, intento #{intento}")
                response = requests.get(
                    self.base_url,
                    timeout=int(os.getenv("SPECIAL_URL_STATUS_TIMEOUT", "20")),
                    allow_redirects=True,
                )

                if response.status_code == 200:
                    if self._response_looks_forbidden(response.text):
                        logger.warning(
                            "⏸️ URL_ENCUESTA respondió 200 pero renderizó una página de bloqueo/forbidden. "
                            f"Registro en pausa, reintentando en {espera_bloqueo_html_segundos} segundos..."
                        )
                        time.sleep(espera_bloqueo_html_segundos)
                        intento += 1
                        continue

                    logger.info("✅ URL_ENCUESTA disponible con estatus 200 y contenido válido")
                    return

                logger.warning(
                    f"⏸️ URL_ENCUESTA respondió {response.status_code}. "
                    f"Registro en pausa, reintentando en {espera_segundos} segundos..."
                )
            except requests.RequestException as e:
                logger.warning(
                    f"⏸️ No se pudo consultar URL_ENCUESTA ({e}). "
                    f"Registro en pausa, reintentando en {espera_segundos} segundos..."
                )

            time.sleep(espera_segundos)
            intento += 1

    def _response_looks_forbidden(self, html: str) -> bool:
        normalized = " ".join((html or "").lower().split())
        forbidden_markers = [
            "<title>403 forbidden</title>",
            "<h1>forbidden</h1>",
            "you don't have permission to access",
            "you do not have permission to access",
            "403 forbidden",
            "access denied",
        ]
        return any(marker in normalized for marker in forbidden_markers)

    def ejecutar(self) -> bool:
        try:
            ciclo = 1
            while True:
                logger.info("\n" + "=" * 70)
                logger.info(f"🔁 INICIANDO CICLO ESPECIAL #{ciclo}")
                logger.info("=" * 70)

                csv_path = self.initial_csv_path if ciclo == 1 else detectar_csv_en_bd_especiales()
                self.csv_path = csv_path

                df = self._leer_csv_actual(csv_path)
                if df.empty:
                    logger.info("🏁 El archivo especial solo contiene encabezados. Proceso finalizado.")
                    self._initialize_errors_csv()
                    return True

                self._initialize_errors_csv()

                if not self.iniciar_navegador():
                    logger.error("❌ No se pudo iniciar el navegador")
                    return False

                exitosos = 0
                fallidos = 0

                try:
                    for idx, row in df.iterrows():
                        ok, motivo = self.procesar_registro(row, idx)
                        if ok:
                            exitosos += 1
                        else:
                            fallidos += 1
                            self._append_error_row(self._serialize_row(row, motivo))

                        if idx < len(df) - 1:
                            delay = float(os.getenv("SPECIAL_DELAY_BETWEEN_RECORDS", "2"))
                            logger.info(f"⏳ Esperando {delay:.2f} segundos antes del siguiente registro...")
                            time.sleep(delay)
                finally:
                    self.cerrar_navegador()

                self._replace_bd_with_errors()

                logger.info("\n" + "=" * 60)
                logger.info("📊 RESUMEN DEL CICLO ESPECIAL")
                logger.info("=" * 60)
                logger.info(f"✅ Registros exitosos: {exitosos}")
                logger.info(f"❌ Registros con error: {fallidos}")
                logger.info(f"🧾 Reintentos pendientes: {fallidos}")
                logger.info("=" * 60)

                if fallidos == 0:
                    logger.info("🎉 No quedaron errores pendientes. Proceso terminado.")
                    return True

                ciclo += 1
        except Exception as e:
            logger.error(f"❌ Error en ejecución especial: {e}", exc_info=True)
            return False
        finally:
            self.cerrar_navegador()

    def _leer_csv_actual(self, csv_path: Path) -> pd.DataFrame:
        logger.info(f"📖 Leyendo archivo CSV especial: {csv_path}")
        df = pd.read_csv(csv_path, encoding="cp1252")
        df.columns = [str(col).strip().upper() for col in df.columns]

        for column in SPECIAL_COLUMNS:
            if column not in df.columns:
                df[column] = ""

        df = df[SPECIAL_COLUMNS].fillna("")
        logger.info(f"📊 Registros pendientes en este ciclo: {len(df)}")
        return df

    def _serialize_row(self, row: pd.Series, motivo: str) -> dict:
        serialized = {}
        for column in SPECIAL_COLUMNS:
            value = row[column] if column in row else ""
            if pd.isna(value):
                value = ""
            serialized[column] = str(value)

        logger.info(f"🧾 Registro enviado a errores: {serialized.get('CORREO', '')} | Motivo: {motivo}")
        return serialized

    def _initialize_errors_csv(self):
        self.errors_dir.mkdir(parents=True, exist_ok=True)
        with open(self.errors_csv, "w", newline="", encoding="cp1252") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=SPECIAL_COLUMNS)
            writer.writeheader()
        logger.info(f"🗂️ Archivo de errores preparado: {self.errors_csv}")

    def _append_error_row(self, row: dict):
        self.errors_dir.mkdir(parents=True, exist_ok=True)
        file_exists = self.errors_csv.exists()
        needs_header = (not file_exists) or self.errors_csv.stat().st_size == 0

        with open(self.errors_csv, "a", newline="", encoding="cp1252") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=SPECIAL_COLUMNS)
            if needs_header:
                writer.writeheader()
            writer.writerow(row)

        logger.info(f"💾 Registro agregado a errores: {row.get('CORREO', '')}")

    def _replace_bd_with_errors(self):
        self.bd_dir.mkdir(parents=True, exist_ok=True)

        for file_path in self.bd_dir.iterdir():
            if file_path.is_file():
                file_path.unlink()

        destino = self.bd_dir / self.errors_csv.name
        shutil.copy2(self.errors_csv, destino)
        logger.info(f"♻️ bd_especiales ahora contiene: {destino.name}")


def detectar_csv_en_bd_especiales(csv_path: Optional[str] = None) -> Path:
    if csv_path:
        return Path(csv_path)

    bd_dir = Path("bd_especiales")
    if not bd_dir.exists():
        raise FileNotFoundError("No existe la carpeta 'bd_especiales'")

    csv_files = sorted(
        file_path for file_path in bd_dir.iterdir()
        if file_path.is_file() and file_path.suffix.lower() == ".csv"
    )

    if not csv_files:
        raise FileNotFoundError("No se encontró ningún archivo .csv dentro de 'bd_especiales'")

    if len(csv_files) > 1:
        csv_names = ", ".join(file_path.name for file_path in csv_files)
        raise FileExistsError(
            f"Se encontraron múltiples archivos CSV en 'bd_especiales': {csv_names}. "
            "Usa --csv para indicar cuál procesar."
        )

    return csv_files[0]


def main():
    import argparse

    parser = argparse.ArgumentParser(description="🤖 Bot especial de Encuesta SEMARNAT")
    parser.add_argument(
        "--csv",
        type=str,
        help="Ruta al archivo CSV. Si se omite, se detecta automáticamente en bd_especiales/",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecutar en modo headless (sin interfaz gráfica)",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Ejecutar con interfaz gráfica",
    )
    parser.set_defaults(headless=False)

    args = parser.parse_args()

    try:
        csv_path = detectar_csv_en_bd_especiales(args.csv)
    except (FileNotFoundError, FileExistsError) as e:
        print(f"❌ Error: {e}")
        return 1

    print("\n" + "=" * 70)
    print("🤖 BOT DE ENCUESTAS ESPECIALES - INICIO")
    print("=" * 70)
    print(f"📁 CSV: {csv_path}")
    print(f"🖥️  Modo headless: {args.headless}")
    print("=" * 70 + "\n")

    if not csv_path.exists():
        print(f"❌ Error: No se encuentra el archivo CSV: {csv_path}")
        return 1

    api_key = os.getenv("CAPTCHA_API_KEY")
    if not api_key or api_key == "TU_API_KEY_AQUI":
        print("❌ Error: No has configurado la API key de 2Captcha")
        print("💡 Edita el archivo .env y configura CAPTCHA_API_KEY")
        return 1

    bot = EncuestasEspecialesBot(str(csv_path), headless=args.headless)

    try:
        exito = bot.ejecutar()
        return 0 if exito else 1
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupción por usuario")
        return 130
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
