#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import dotenv
import pandas as pd
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from encuestas_especiales import EncuestasEspecialesBot, detectar_csv_en_bd_especiales, logger

dotenv.load_dotenv()


SUCCESS_MARKER = "el cuestionario fue registrado exitosamente"
CAPTCHA_INVALID_MARKERS = [
    "captcha es inválido",
    "captcha es invalido",
    "cã³digo de verificaciã³n captcha es invã¡lido",
    "codigo de verificacion captcha es invalido",
    "captcha inv",
]
GENERIC_ERROR_MARKERS = [
    "forbidden",
    "403",
    "denied",
    "bad gateway",
    "service unavailable",
    "internal server error",
]


@dataclass
class CaptchaSession:
    php_sessid: str
    captcha_id: str
    captcha_text: str
    token_antifraude: str
    flujo_token: str
    cve_proyecto: str
    referer: str
    created_at: float
    successful_posts: int = 0

    @property
    def age_seconds(self) -> float:
        return time.perf_counter() - self.created_at


class EncuestaPostBot(EncuestasEspecialesBot):
    def __init__(self, csv_path: str, headless: bool = False):
        self.initial_csv_path = Path(csv_path)
        self.csv_run_name = self.initial_csv_path.stem
        self.responses_root_dir = Path("respuesta_post")
        self.curls_root_dir = Path("curls")
        self.post_validated_root_dir = Path("post_validados")
        self.responses_dir = self.responses_root_dir / self.csv_run_name
        self.curls_dir = self.curls_root_dir / self.csv_run_name
        self.post_validated_dir = self.post_validated_root_dir / self.csv_run_name
        super().__init__(csv_path, headless=headless)
        self.post_url = self._build_post_url()
        self.current_captcha: Optional[CaptchaSession] = None
        self.processed_file = self.post_validated_dir / "post_validados.txt"
        self.processed_emails = set()
        self._load_processed()
        logger.info(f"📨 Respuestas POST: {self.responses_dir}")
        logger.info(f"🧾 CURLs POST: {self.curls_dir}")
        logger.info(f"✅ Validados POST: {self.processed_file}")

    def _build_post_url(self) -> str:
        base = self.base_url.split("/llenado/")[0].rstrip("/")
        return f"{base}/llenado/salvacuestionario"

    def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        delay = random.uniform(min_seconds, max_seconds)
        logger.info(f"⏳ Esperando {delay:.2f} segundos...")
        time.sleep(delay)

    def _setup_directories(self):
        directories = [
            "downloads",
            "logs",
            "temp_captcha",
            "bd_especiales",
            "errores",
            "validado_especiales",
            str(self.responses_root_dir),
            str(self.curls_root_dir),
            str(self.post_validated_root_dir),
            str(self.responses_dir),
            str(self.curls_dir),
            str(self.post_validated_dir),
        ]

        for dir_name in directories:
            Path(dir_name).mkdir(parents=True, exist_ok=True)

    def _random_email_from_row(self, row: pd.Series) -> str:
        correo = str(row["CORREO"]).strip().lower()
        if correo.endswith("@yopmail.com"):
            dominios = [
                "@gmail.com",
                "@outlook.com",
                "@yahoo.com",
                "@icloud.com",
                "@hotmail.com",
                "@mail.com",
                "@protonmail.com",
                "@aol.com",
                "@zoho.com",
                "@gmx.com",
                "@yandex.com",
                "@qq.com",
                "@163.com",
                "@mail.ru",
                "@web.de",
                "@t-online.de",
                "@libero.it",
                "@orange.fr",
                "@naver.com",
                "@rediffmail.com",
                "@tutanota.com",
                "@fastmail.com",
                "@hushmail.com",
                "@posteo.de",
                "@email.com",
                "@usa.com",
                "@consultant.com",
                "@engineer.com",
                "@me.com",
                "@live.com",
            ]
            correo = correo[:-len("@yopmail.com")] + random.choice(dominios)
        return correo.upper()

    def _random_area_respuesta_1(self) -> str:
        respuestas = [
            "Estoy de acuerdo en que asi sea.",
            "Estoy de acuerdo con que se haga.",
            "Acepto que se realice.",
            "Apruebo que ocurra.",
            "Doy mi consentimiento.",
            "Doy el visto bueno.",
            "Que asi sea.",
            "Me parece bien que se haga.",
            "Lo apoyo.",
            "Lo respaldo.",
            "Estoy a favor de que se haga.",
            "Estoy a favor de que ocurra.",
            "Estoy a favor.",
            "Me pronuncio a favor.",
            "Voto a favor.",
            "Cuenta con mi aprobacion.",
            "Cuenta con mi apoyo.",
            "Que se lleve a cabo.",
            "Que se realice.",
            "Procedamos.",
            "Aprobado.",
            "Sin problema, que suceda.",
            "Me parece perfecto que se haga.",
            "Me parece acertado.",
            "Por mi, adelante.",
            "Que se haga.",
            "Claro que debe hacerse.",
            "Es lo correcto que ocurra.",
        ]
        return random.choice(respuestas).upper()

    def _row_num_int(self, row: pd.Series) -> str:
        value = str(row.get("NUM_INTERIOR", "")).strip()
        if not value or value.lower() == "nan":
            return ""
        return value.upper()

    def _normalize_text(self, value: object, default: str = "") -> str:
        text = str(value if value is not None else default).strip()
        if not text or text.lower() == "nan":
            return default
        return text.upper()

    def _status_suffix(self, ok: bool) -> str:
        return "succes" if ok else "error"

    def _record_slug(self, row: pd.Series) -> str:
        correo = str(row["CORREO"]).strip().lower()
        local_part = correo.split("@", 1)[0]
        local_part = local_part.replace("yopmail", "")
        local_part = re.sub(r"[^a-z0-9._-]+", "_", local_part)
        return local_part.strip("._-") or "registro"

    def _artifact_path(self, directory: Path, row: pd.Series, ok: bool, extension: str) -> Path:
        filename = f"{self._record_slug(row)}-{self._status_suffix(ok)}.{extension}"
        return directory / filename

    def _save_response_artifact(self, row: pd.Series, ok: bool, html: str):
        path = self._artifact_path(self.responses_dir, row, ok, "htm")
        path.write_text(html or "", encoding="utf-8", errors="ignore")
        logger.info(f"💾 Respuesta guardada en {path}")

    def _build_curl_command(self, payload: Dict[str, str], captcha_session: CaptchaSession) -> str:
        curl_parts = [
            f"curl '{self.post_url}'",
            "  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'",
            "  -H 'Accept-Language: es-US,es-419;q=0.9,es;q=0.8'",
            "  -H 'Cache-Control: max-age=0'",
            "  -H 'Connection: keep-alive'",
            f"  -H 'Origin: {self.post_url.split('/llenado/')[0]}'",
            f"  -H 'Referer: {captcha_session.referer}'",
            "  -H 'Upgrade-Insecure-Requests: 1'",
            (
                "  -H 'User-Agent: "
                + os.getenv(
                    "USER_AGENT",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                )
                + "'"
            ),
            f"  -b 'PHPSESSID={captcha_session.php_sessid}'",
        ]

        for key, value in payload.items():
            curl_parts.append(f"  -F \"{key}={value}\"")

        curl_parts.append("  -F \"archivoAdj1=@;type=application/octet-stream\"")
        curl_parts.append("  -F \"archivoAdj2=@;type=application/octet-stream\"")
        return " \\\n".join(curl_parts)

    def _save_curl_artifact(self, row: pd.Series, ok: bool, curl_command: str):
        path = self._artifact_path(self.curls_dir, row, ok, "txt")
        path.write_text(curl_command + "\n", encoding="utf-8")
        logger.info(f"💾 CURL guardado en {path}")

    def _get_cookie_value(self, name: str) -> str:
        for cookie in self.driver.get_cookies():
            if cookie.get("name") == name:
                return str(cookie.get("value", ""))
        return ""

    def _hidden_value(self, field_name: str) -> str:
        element = (
            self._safe_find_element(By.NAME, field_name, timeout=2)
            or self._safe_find_element(By.CSS_SELECTOR, f"input[name='{field_name}']", timeout=2)
        )
        return element.get_attribute("value").strip() if element else ""

    def _invalidate_captcha(self, reason: str):
        if not self.current_captcha:
            return

        logger.warning(
            "♻️ Invalidando captcha actual. "
            f"Motivo: {reason}. "
            f"Posts exitosos con este captcha: {self.current_captcha.successful_posts}. "
            f"Duración: {self.current_captcha.age_seconds:.2f}s"
        )
        self.current_captcha = None

    def _wait_for_captcha_page(self) -> bool:
        captcha_selectors = [
            (By.ID, "captcha-image"),
            (By.CSS_SELECTOR, "img[alt='captcha']"),
            (By.CSS_SELECTOR, "img[src^='data:image/']"),
            (By.XPATH, "//input[@name='captcha[input]']/preceding::img[1]"),
        ]

        weird_wait = int(os.getenv("POST_CAPTCHA_MISSING_WAIT_SECONDS", "10"))
        attempt = 1

        while True:
            self.esperar_url_disponible()
            logger.info(f"🌍 Cargando encuesta para extraer sesión/captcha, intento #{attempt}")
            self.driver.get(self.base_url)

            try:
                WebDriverWait(self.driver, 20).until(
                    lambda drv: drv.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                logger.warning("⚠️ La página no confirmó document.readyState=complete")

            for by, value in captcha_selectors:
                captcha_img = self._safe_find_element(by, value, timeout=3)
                if captcha_img:
                    logger.info(f"✅ Captcha detectado con selector {by}={value}")
                    return True

            logger.warning(
                "⏸️ No apareció el captcha con los selectores esperados. "
                f"Esperando {weird_wait} segundos antes de reintentar..."
            )
            time.sleep(weird_wait)
            attempt += 1

    def _obtener_nuevo_captcha(self) -> Optional[CaptchaSession]:
        if not self._wait_for_captcha_page():
            return None

        captcha_text = self.resolver_captcha()
        if not captcha_text:
            return None

        php_sessid = self._get_cookie_value("PHPSESSID")
        captcha_id = self._hidden_value("captcha[id]")
        token_antifraude = self._hidden_value("token_antifraude")
        flujo_token = self._hidden_value("flujo_token")
        cve_proyecto = self._hidden_value("cveProyecto")

        if not cve_proyecto:
            cve_proyecto = self.base_url.rstrip("/").split("/")[-1]

        missing = [
            name
            for name, value in (
                ("PHPSESSID", php_sessid),
                ("captcha[id]", captcha_id),
                ("token_antifraude", token_antifraude),
                ("flujo_token", flujo_token),
                ("cveProyecto", cve_proyecto),
            )
            if not value
        ]
        if missing:
            logger.error(f"❌ No se pudieron extraer estos valores de sesión: {missing}")
            return None

        captcha_session = CaptchaSession(
            php_sessid=php_sessid,
            captcha_id=captcha_id,
            captcha_text=captcha_text.strip(),
            token_antifraude=token_antifraude,
            flujo_token=flujo_token,
            cve_proyecto=cve_proyecto,
            referer=self.base_url,
            created_at=time.perf_counter(),
        )
        logger.info(
            "🧩 Nueva sesión captcha lista. "
            f"PHPSESSID={captcha_session.php_sessid}, "
            f"captcha_id={captcha_session.captcha_id}, "
            f"captcha_text={captcha_session.captcha_text}"
        )
        return captcha_session

    def _ensure_active_captcha(self) -> Optional[CaptchaSession]:
        while not self.current_captcha:
            self.current_captcha = self._obtener_nuevo_captcha()
            if not self.current_captcha:
                logger.warning("⏸️ No se pudo preparar un captcha válido. Reintentando en 10 segundos...")
                time.sleep(10)
        return self.current_captcha

    def _build_payload(self, row: pd.Series, captcha_session: CaptchaSession) -> Dict[str, str]:
        return {
            "NombreRFC": self._normalize_text(row["NOMBRE_COMPLETO"]),
            "Calle": self._normalize_text(row["CALLE"]),
            "NumExt": self._normalize_text(row["NUM_EXTERIOR"]),
            "NumInt": self._row_num_int(row),
            "Asentamiento": self._normalize_text(row["COLONIA"]),
            "CP": self._normalize_text(str(row["CODIGO_POSTAL"])[:5]),
            "selectEntidad": self._normalize_text(row["ENTIDAD"]),
            "email": self._random_email_from_row(row),
            "areaRespuesta1": self._random_area_respuesta_1(),
            "radioMIA": "1",
            "radioRespuesta3": "0",
            "radioRespuesta4": "0",
            "captcha[id]": captcha_session.captcha_id,
            "captcha[input]": captcha_session.captcha_text,
            "cveProyecto": captcha_session.cve_proyecto,
            "token_antifraude": captcha_session.token_antifraude,
            "flujo_token": captcha_session.flujo_token,
            "website": "",
            "btnEnviar": "Enviar",
        }

    def _post_formulario(self, payload: Dict[str, str], captcha_session: CaptchaSession) -> Tuple[bool, str, str, str]:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "es-US,es-419;q=0.9,es;q=0.8",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Origin": self.post_url.split("/llenado/")[0],
            "Referer": captcha_session.referer,
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": os.getenv(
                "USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            ),
        }

        files = [
            ("archivoAdj1", ("", b"", "application/octet-stream")),
            ("archivoAdj2", ("", b"", "application/octet-stream")),
        ]
        curl_command = self._build_curl_command(payload, captcha_session)

        with requests.Session() as session:
            session.cookies.set("PHPSESSID", captcha_session.php_sessid)
            response = session.post(
                self.post_url,
                data=payload,
                files=files,
                headers=headers,
                timeout=int(os.getenv("POST_REQUEST_TIMEOUT", "60")),
                allow_redirects=True,
            )

        html = response.text or ""
        normalized = " ".join(html.lower().split())

        if SUCCESS_MARKER in normalized:
            return True, "EXITOSO", html, curl_command

        if any(marker in normalized for marker in CAPTCHA_INVALID_MARKERS):
            return False, "CAPTCHA_INVALIDO", html, curl_command

        if any(marker in normalized for marker in GENERIC_ERROR_MARKERS):
            return False, "ERROR_PAGINA", html, curl_command

        return False, "RESPUESTA_NO_EXITOSA", html, curl_command

    def procesar_registro(self, row: pd.Series, idx: int) -> Tuple[bool, str]:
        email_base = str(row["CORREO"]).strip()
        nombre = str(row["NOMBRE_COMPLETO"]).strip()
        inicio_registro = time.perf_counter()
        intento = 1
        max_retries = int(os.getenv("POST_MAX_RETRIES_PER_RECORD", "0"))

        logger.info(f"\n{'=' * 50}")
        logger.info(f"📋 Procesando registro POST {idx + 1}")
        logger.info(f"👤 {nombre}")
        logger.info(f"📧 {email_base}")
        logger.info("=" * 50)

        if email_base in self.processed_emails:
            logger.info(f"⏭️ Registro ya validado anteriormente: {email_base}")
            return True, "YA_VALIDADO"

        while True:
            if max_retries and intento > max_retries:
                logger.error(f"❌ Se alcanzó el máximo de reintentos para el registro {idx + 1}")
                return False, "MAX_REINTENTOS"

            try:
                captcha_session = self._ensure_active_captcha()
                if not captcha_session:
                    logger.warning("⏸️ Sin sesión captcha activa; reintentando...")
                    time.sleep(10)
                    continue

                payload = self._build_payload(row, captcha_session)
                logger.info(
                    f"📮 Enviando POST intento #{intento} del registro {idx + 1} "
                    f"con captcha activo hace {captcha_session.age_seconds:.2f}s "
                    f"y {captcha_session.successful_posts} éxitos acumulados"
                )

                ok, motivo, html, curl_command = self._post_formulario(payload, captcha_session)
                self._save_response_artifact(row, ok, html)
                self._save_curl_artifact(row, ok, curl_command)
                resumen_html = " ".join((html or "").split())[:500]
                logger.info(f"📥 Respuesta POST registro {idx + 1}: {resumen_html}")
                if ok:
                    captcha_session.successful_posts += 1
                    self._mark_as_processed(email_base, nombre, motivo)
                    logger.info(
                        "✅ Registro enviado correctamente por POST. "
                        f"Captcha actual lleva {captcha_session.successful_posts} éxitos "
                        f"en {captcha_session.age_seconds:.2f}s"
                    )
                    tiempo_total = time.perf_counter() - inicio_registro
                    logger.info(f"⏱️ Registro POST {idx + 1} terminado en {tiempo_total:.2f} segundos")
                    return True, motivo

                logger.warning(
                    f"⚠️ Registro {idx + 1} falló en POST. Motivo: {motivo}. "
                    f"Respuesta resumida: {resumen_html}"
                )
                self._invalidate_captcha(motivo)
                logger.info("🔄 Se refrescará la página para obtener nuevos valores antes de reintentar este mismo registro")
                intento += 1
                continue

            except requests.RequestException as e:
                logger.warning(f"⚠️ Error HTTP en registro {idx + 1}: {e}")
                self._invalidate_captcha("ERROR_REQUEST")
                time.sleep(10)
                intento += 1
            except Exception as e:
                logger.error(f"❌ Error procesando registro POST {idx + 1}: {e}", exc_info=True)
                self._invalidate_captcha("ERROR_EXCEPCION")
                time.sleep(10)
                intento += 1

    def ejecutar(self) -> bool:
        try:
            df = self._leer_csv_actual(self.initial_csv_path)
            if df.empty:
                logger.info("🏁 El archivo CSV no contiene registros pendientes.")
                return True

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
                        logger.error(f"❌ Registro {idx + 1} terminó sin éxito definitivo: {motivo}")

                    if idx < len(df) - 1:
                        self._random_delay(1, 2)
            finally:
                self.cerrar_navegador()

            logger.info("\n" + "=" * 60)
            logger.info("📊 RESUMEN FINAL POST")
            logger.info("=" * 60)
            logger.info(f"✅ Registros exitosos: {exitosos}")
            logger.info(f"❌ Registros fallidos: {fallidos}")
            if self.current_captcha:
                logger.info(
                    "🧩 Último captcha usado: "
                    f"{self.current_captcha.successful_posts} éxitos "
                    f"en {self.current_captcha.age_seconds:.2f}s"
                )
            logger.info("=" * 60)

            return fallidos == 0
        except Exception as e:
            logger.error(f"❌ Error en ejecución POST: {e}", exc_info=True)
            return False
        finally:
            self.cerrar_navegador()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="🤖 Bot POST de Encuesta SEMARNAT")
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
    print("🤖 BOT DE ENCUESTA POST - INICIO")
    print("=" * 70)
    print(f"📁 CSV: {csv_path}")
    print(f"🌐 POST URL: {os.getenv('URL_ENCUESTA', 'https://consultaspublicas.semarnat.gob.mx:8443/llenado/23QR2025T0061')}")
    print(f"🖥️  Modo headless: {args.headless}")
    print("=" * 70 + "\n")

    if not Path(csv_path).exists():
        print(f"❌ Error: No se encuentra el archivo CSV: {csv_path}")
        return 1

    api_key = os.getenv("CAPTCHA_API_KEY")
    if not api_key or api_key == "TU_API_KEY_AQUI":
        print("❌ Error: No has configurado la API key de 2Captcha")
        print("💡 Edita el archivo .env y configura CAPTCHA_API_KEY")
        return 1

    bot = EncuestaPostBot(str(csv_path), headless=args.headless)

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
