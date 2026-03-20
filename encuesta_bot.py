#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📋 BOT DE ENCUESTA SEMARNAT
--------------------------------------------------------------------------------
Bot automatizado para llenar encuestas en el portal de SEMARNAT
Lee datos de un archivo CSV y procesa cada registro

Características:
✅ Lectura de CSV con pandas
✅ Manejo de sesiones por registro
✅ Resolución de captchas con 2Captcha
✅ Logging detallado
✅ Archivo de control de procesados
✅ Timeouts configurables
"""

import os
import sys
import time
import random
import logging
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from datetime import datetime
import csv

import pandas as pd
import dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Importar módulos locales
from browser import build_driver
from captcha_solver import CaptchaSolver

# Cargar variables de entorno
dotenv.load_dotenv()

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/encuesta_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class EncuestaBot:
    """
    🤖 Bot principal para la encuesta de SEMARNAT
    """
    
    def __init__(self, csv_path: str, headless: bool = False):
        """
        Inicializa el bot
        
        Args:
            csv_path: Ruta al archivo CSV con los datos
            headless: Modo headless (sin interfaz gráfica)
        """
        self.csv_path = Path(csv_path)
        self.headless = headless
        self.driver = None
        self.captcha_solver = None
        self.processed_file = Path("txt_verificados/procesados.txt")
        self.processed_emails = set()
        
        # URL base
        self.base_url = os.getenv("URL_ENCUESTA", 
            "https://consultaspublicas.semarnat.gob.mx:8443/llenado/23QR2025T0061")
        
        # Crear directorios necesarios
        self._setup_directories()
        
        # Cargar emails ya procesados
        self._load_processed()
        
        logger.info("=" * 60)
        logger.info("🤖 BOT DE ENCUESTA SEMARNAT INICIALIZADO")
        logger.info(f"📁 CSV: {self.csv_path}")
        logger.info(f"📋 Procesados: {len(self.processed_emails)} registros")
        logger.info("=" * 60)
    
    def _setup_directories(self):
        """Crea los directorios necesarios"""
        directories = [
            "downloads",
            "txt_verificados",
            "logs",
            "temp_captcha"
        ]
        
        for dir_name in directories:
            Path(dir_name).mkdir(parents=True, exist_ok=True)
            logger.debug(f"📁 Directorio asegurado: {dir_name}")
    
    def _load_processed(self):
        """Carga los emails ya procesados desde el archivo de control"""
        if self.processed_file.exists():
            try:
                with open(self.processed_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if ',' in line:
                            email = line.strip().split(',')[0]
                            self.processed_emails.add(email)
                logger.info(f"✅ Cargados {len(self.processed_emails)} emails procesados")
            except Exception as e:
                logger.error(f"❌ Error cargando procesados: {e}")
    
    def _mark_as_processed(self, email: str, nombre: str, estado: str = "EXITOSO"):
        """
        Marca un registro como procesado
        
        Args:
            email: Correo del registro
            nombre: Nombre completo
            estado: Estado del procesamiento
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"{email},{nombre},{timestamp},{estado}\n"
            
            with open(self.processed_file, 'a', encoding='utf-8') as f:
                f.write(line)
            
            self.processed_emails.add(email)
            logger.info(f"✅ Registro marcado como procesado: {email}")
            
        except Exception as e:
            logger.error(f"❌ Error marcando como procesado: {e}")
    
    def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Pausa aleatoria entre acciones"""
        delay = random.uniform(min_seconds, max_seconds)
        logger.debug(f"⏳ Esperando {delay:.2f} segundos...")
        time.sleep(delay)
    
    def _safe_find_element(self, by: By, value: str, timeout: int = 10):
        """Busca un elemento de manera segura"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            logger.warning(f"⚠️ Elemento no encontrado: {value}")
            return None
    
    def _safe_send_keys(self, element, text: str, clear_first: bool = True):
        """Envía texto a un elemento de manera segura"""
        try:
            if clear_first:
                element.clear()
                self._random_delay(0.2, 0.5)
            
            element.send_keys(str(text).upper())
            logger.debug(f"✏️ Texto ingresado: {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"❌ Error enviando texto: {e}")
            return False
    
    def _safe_select_by_value(self, select_element, value: str):
        """Selecciona una opción de un select de manera segura"""
        try:
            select = Select(select_element)
            select.select_by_value(value)
            logger.debug(f"🔽 Seleccionado: {value}")
            return True
        except Exception as e:
            logger.error(f"❌ Error seleccionando opción: {e}")
            return False
    
    def _safe_click(self, element):
        """Hace click en un elemento de manera segura"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            self._random_delay(0.5, 1.0)
            element.click()
            logger.debug("🖱️ Click realizado")
            return True
        except Exception as e:
            logger.error(f"❌ Error haciendo click: {e}")
            return False
    
    def iniciar_navegador(self):
        """Inicia el navegador con la configuración adecuada"""
        try:
            logger.info("🌐 Iniciando navegador...")
            
            self.driver = build_driver(
                headless=self.headless,
                download_dir="downloads",
                page_load_timeout=int(os.getenv("SELENIUM_PAGELOAD_TIMEOUT", 90)),
                script_timeout=int(os.getenv("SELENIUM_SCRIPT_TIMEOUT", 90)),
                implicit_wait=int(os.getenv("SELENIUM_IMPLICIT_WAIT", 10))
            )
            
            # Inicializar solucionador de captchas
            self.captcha_solver = CaptchaSolver()
            
            logger.info("✅ Navegador iniciado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error iniciando navegador: {e}", exc_info=True)
            return False
    
    def cerrar_navegador(self):
        """Cierra el navegador y limpia recursos"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ Navegador cerrado correctamente")
            except Exception as e:
                logger.error(f"❌ Error cerrando navegador: {e}")
            finally:
                self.driver = None
    
    def navegar_a_encuesta(self):
        """Navega a la página de la encuesta"""
        try:
            logger.info(f"🌍 Navegando a: {self.base_url}")
            self.driver.get(self.base_url)
            
            # Esperar a que cargue la página
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "NombreRFC"))
            )
            
            logger.info("✅ Página cargada correctamente")
            self._random_delay(2, 4)
            return True
            
        except Exception as e:
            logger.error(f"❌ Error navegando a la encuesta: {e}")
            return False
    
    def llenar_datos_personales(self, row: pd.Series) -> bool:
        """
        Llena los datos personales del formulario
        
        Args:
            row: Fila del DataFrame con los datos
        """
        try:
            logger.info(f"👤 Llenando datos para: {row['NOMBRE_COMPLETO']}")
            
            # Nombre completo
            nombre_elem = self._safe_find_element(By.ID, "NombreRFC")
            if not nombre_elem or not self._safe_send_keys(nombre_elem, row['NOMBRE_COMPLETO']):
                return False
            
            self._random_delay(0.5, 1)
            
            # Calle
            calle_elem = self._safe_find_element(By.ID, "Calle")
            if not calle_elem or not self._safe_send_keys(calle_elem, str(row['CALLE'])):
                return False
            
            self._random_delay(0.5, 1)
            
            # Número exterior
            num_ext_elem = self._safe_find_element(By.ID, "NumExt")
            if not num_ext_elem or not self._safe_send_keys(num_ext_elem, str(row['NUM_EXTERIOR'])):
                return False
            
            self._random_delay(0.5, 1)
            
            # Colonia
            colonia_elem = self._safe_find_element(By.ID, "Asentamiento")
            if not colonia_elem or not self._safe_send_keys(colonia_elem, str(row['COLONIA'])):
                return False
            
            self._random_delay(0.5, 1)
            
            # Código Postal
            cp_elem = self._safe_find_element(By.ID, "CP")
            if not cp_elem or not self._safe_send_keys(cp_elem, str(row['CODIGO_POSTAL'])[:5]):
                return False
            
            logger.info("✅ Datos personales llenados")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error llenando datos personales: {e}")
            return False
    
    def seleccionar_entidad_municipio(self, row: pd.Series) -> bool:
        """
        Selecciona entidad y municipio
        
        Args:
            row: Fila del DataFrame con los datos
        """
        try:
            # Seleccionar entidad
            entidad_select = self._safe_find_element(By.ID, "selectEntidad")
            if not entidad_select:
                return False
            
            # Esperar a que carguen las opciones
            self._random_delay(1, 2)
            
            if not self._safe_select_by_value(entidad_select, str(row['ENTIDAD'])):
                logger.error("❌ No se pudo seleccionar entidad")
                return False
            
            logger.info(f"🏛️ Entidad seleccionada: {row['ENTIDAD']}")
            self._random_delay(1, 2)
            
            # Seleccionar municipio
            municipio_select = self._safe_find_element(By.ID, "selMunicipio")
            if not municipio_select:
                return False
            
            if not self._safe_select_by_value(municipio_select, str(row['MUNICIPIO'])):
                logger.error("❌ No se pudo seleccionar municipio")
                return False
            
            logger.info(f"🏘️ Municipio seleccionado: {row['MUNICIPIO']}")
            self._random_delay(1, 2)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error seleccionando entidad/municipio: {e}")
            return False
    
    def llenar_correo(self, row: pd.Series) -> bool:
        """
        Llena el campo de correo electrónico
        
        Args:
            row: Fila del DataFrame con los datos
        """
        try:
            correo_elem = self._safe_find_element(By.ID, "email")
            if not correo_elem:
                return False

            correo = str(row['CORREO']).lower()
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
            
            if not self._safe_send_keys(correo_elem, correo):
                return False
            
            logger.info(f"📧 Correo: {correo}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error llenando correo: {e}")
            return False
    
    def llenar_preguntas(self) -> bool:
        """
        Llena las preguntas de la encuesta
        """
        try:
            # Pregunta 1 - Textarea
            area1_elem = self._safe_find_element(By.ID, "areaRespuesta1")
            if area1_elem:
                respuestas_area1 = [
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
                respuesta_area1 = random.choice(respuestas_area1)
                self._safe_send_keys(area1_elem, respuesta_area1)
                logger.info(f"✅ Pregunta 1: {respuesta_area1}")
            
            self._random_delay(0.5, 1)
            
            # Pregunta 2 - Radio Sí
            try:
                radio_si = self.driver.find_element(By.CSS_SELECTOR, "input[name='radioMIA'][value='1']")
                self._safe_click(radio_si)
                logger.info("✅ Pregunta 2: Sí")
            except Exception as e:
                logger.warning(f"⚠️ Error en pregunta 2: {e}")
            
            self._random_delay(0.5, 1)
            
            # Pregunta 3 - Radio No
            try:
                radio_no_3 = self.driver.find_element(By.CSS_SELECTOR, "input[name='radioRespuesta3'][value='0']")
                self._safe_click(radio_no_3)
                logger.info("✅ Pregunta 3: No")
            except Exception as e:
                logger.warning(f"⚠️ Error en pregunta 3: {e}")
            
            self._random_delay(0.5, 1)
            
            # Pregunta 4 - Radio No
            try:
                radio_no_4 = self.driver.find_element(By.CSS_SELECTOR, "input[name='radioRespuesta4'][value='0']")
                self._safe_click(radio_no_4)
                logger.info("✅ Pregunta 4: No")
            except Exception as e:
                logger.warning(f"⚠️ Error en pregunta 4: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error llenando preguntas: {e}")
            return False
    
    def resolver_captcha(self) -> Optional[str]:
        """
        Resuelve el captcha de la página
        
        Returns:
            Texto del captcha o None si falla
        """
        try:
            logger.info("🔍 Buscando captcha...")
            
            # Encontrar elemento de imagen del captcha
            captcha_img = self._safe_find_element(By.ID, "captcha-image", timeout=10)
            if not captcha_img:
                logger.error("❌ No se encontró la imagen del captcha")
                return None
            
            # Obtener el ID oculto del captcha
            captcha_hidden = self._safe_find_element(By.ID, "captcha-hidden", timeout=5)
            captcha_id = captcha_hidden.get_attribute('value') if captcha_hidden else "desconocido"
            logger.info(f"🆔 Captcha ID: {captcha_id}")
            
            # Resolver captcha
            logger.info("🤔 Resolviendo captcha con 2Captcha...")
            captcha_text = self.captcha_solver.solve_captcha_from_driver(self.driver, captcha_img)
            
            if captcha_text:
                logger.info(f"✅ Captcha resuelto: {captcha_text}")
                return captcha_text
            else:
                logger.error("❌ No se pudo resolver el captcha")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error en captcha: {e}")
            return None
    
    def enviar_captcha_y_submit(self, captcha_text: str) -> bool:
        """
        Ingresa el captcha y envía el formulario
        
        Args:
            captcha_text: Texto del captcha resuelto
        """
        try:
            # Ingresar captcha
            captcha_input = self._safe_find_element(By.ID, "captcha")
            if not captcha_input:
                return False
            
            if not self._safe_send_keys(captcha_input, captcha_text):
                return False
            
            logger.info("🔑 Captcha ingresado")
            self._random_delay(1, 2)
            
            # Hacer clic en Enviar
            submit_btn = self._safe_find_element(By.CSS_SELECTOR, "input[value='Enviar']")
            if not submit_btn:
                return False
            
            self._safe_click(submit_btn)
            logger.info("📤 Formulario enviado")
            
            # Esperar respuesta
            self._random_delay(3, 5)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error enviando formulario: {e}")
            return False
    
    def verificar_envio_exitoso(self) -> bool:
        """
        Verifica si el envío fue exitoso
        """
        try:
            # Buscar indicadores de éxito
            page_source = self.driver.page_source.lower()
            
            success_indicators = [
                "gracias por su participación",
                "encuesta enviada exitosamente",
                "registro completo",
                "éxito"
            ]
            
            for indicator in success_indicators:
                if indicator in page_source:
                    logger.info(f"✅ Envío exitoso - {indicator}")
                    return True
            
            logger.warning("⚠️ No se pudo confirmar envío exitoso")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error verificando envío: {e}")
            return False
    
    def procesar_registro(self, row: pd.Series, idx: int) -> bool:
        """
        Procesa un registro individual
        
        Args:
            row: Fila del DataFrame
            idx: Índice del registro
            
        Returns:
            True si se procesó correctamente
        """
        email = str(row['CORREO'])
        nombre = str(row['NOMBRE_COMPLETO'])
        inicio_registro = time.perf_counter()
        
        logger.info(f"\n{'='*50}")
        logger.info(f"📋 Procesando registro {idx + 1}")
        logger.info(f"👤 {nombre}")
        logger.info(f"📧 {email}")
        logger.info('='*50)
        
        # Verificar si ya fue procesado
        if email in self.processed_emails:
            logger.info(f"⏭️ Registro ya procesado anteriormente: {email}")
            tiempo_total = time.perf_counter() - inicio_registro
            logger.info(f"⏱️ Registro {idx + 1} omitido en {tiempo_total:.2f} segundos")
            return True
        
        try:
            # Navegar a la encuesta
            if not self.navegar_a_encuesta():
                return False
            
            # Llenar datos
            if not self.llenar_datos_personales(row):
                return False
            
            if not self.seleccionar_entidad_municipio(row):
                return False
            
            if not self.llenar_correo(row):
                return False
            
            if not self.llenar_preguntas():
                return False
            
            # Resolver captcha
            captcha_text = self.resolver_captcha()
            if not captcha_text:
                logger.error("❌ No se pudo resolver el captcha")
                return False
            
            # Enviar formulario
            if not self.enviar_captcha_y_submit(captcha_text):
                return False
            
            # Verificar éxito
            exito = self.verificar_envio_exitoso()
            
            if exito:
                self._mark_as_processed(email, nombre, "EXITOSO")
                logger.info(f"✅ Registro {idx + 1} procesado EXITOSAMENTE")
            else:
                self._mark_as_processed(email, nombre, "FALLIDO")
                logger.warning(f"⚠️ Registro {idx + 1} procesado con advertencias")
            
            tiempo_total = time.perf_counter() - inicio_registro
            logger.info(f"⏱️ Registro {idx + 1} terminado en {tiempo_total:.2f} segundos")
            
            return exito
            
        except Exception as e:
            logger.error(f"❌ Error procesando registro {idx + 1}: {e}", exc_info=True)
            self._mark_as_processed(email, nombre, f"ERROR: {str(e)[:50]}")
            tiempo_total = time.perf_counter() - inicio_registro
            logger.info(f"⏱️ Registro {idx + 1} terminó con error en {tiempo_total:.2f} segundos")
            return False
    
    def ejecutar(self):
        """
        Ejecuta el bot principal
        """
        try:
            # Leer CSV
            logger.info(f"📖 Leyendo archivo CSV: {self.csv_path}")
            df = pd.read_csv(self.csv_path, encoding='cp1252')
            logger.info(f"📊 Total de registros: {len(df)}")
            
            # Validar columnas necesarias
            required_columns = ['CORREO', 'NOMBRE_COMPLETO', 'CALLE', 'NUM_EXTERIOR', 
                              'COLONIA', 'CODIGO_POSTAL', 'ENTIDAD', 'MUNICIPIO']
            
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.error(f"❌ Columnas faltantes en CSV: {missing_columns}")
                return False
            
            # Iniciar navegador
            if not self.iniciar_navegador():
                logger.error("❌ No se pudo iniciar el navegador")
                return False
            
            exitosos = 0
            fallidos = 0
            
            # Procesar cada registro
            for idx, row in df.iterrows():
                try:
                    # Procesar registro
                    if self.procesar_registro(row, idx):
                        exitosos += 1
                    else:
                        fallidos += 1
                    
                    # Delay entre registros
                    if idx < len(df) - 1:
                        delay = random.uniform(1, 3)
                        logger.info(f"⏳ Esperando {delay:.2f} segundos antes del siguiente registro...")
                        time.sleep(delay)
                        
                        # Refrescar para siguiente registro
                        logger.info("🔄 Refrescando página...")
                        self.driver.get(self.base_url)
                        self._random_delay(2, 4)
                    
                except Exception as e:
                    logger.error(f"❌ Error crítico en registro {idx}: {e}")
                    fallidos += 1
                    
                    # Intentar recuperar
                    try:
                        self.driver.get(self.base_url)
                        self._random_delay(3, 5)
                    except:
                        pass
            
            # Resumen final
            logger.info("\n" + "="*60)
            logger.info("📊 RESUMEN FINAL")
            logger.info("="*60)
            logger.info(f"✅ Registros exitosos: {exitosos}")
            logger.info(f"❌ Registros fallidos: {fallidos}")
            logger.info(f"📋 Total procesados: {exitosos + fallidos}")
            logger.info("="*60)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en ejecución principal: {e}", exc_info=True)
            return False
            
        finally:
            # Cerrar navegador
            self.cerrar_navegador()


def detectar_csv_en_bd(csv_path: Optional[str] = None) -> Path:
    """
    Obtiene la ruta del CSV a usar.

    Si se proporciona `csv_path`, la respeta. Si no, busca archivos `.csv`
    dentro de `bd/` y usa el unico disponible.
    """
    if csv_path:
        return Path(csv_path)

    bd_dir = Path("bd")
    if not bd_dir.exists():
        raise FileNotFoundError("No existe la carpeta 'bd'")

    csv_files = sorted(
        file_path for file_path in bd_dir.iterdir()
        if file_path.is_file() and file_path.suffix.lower() == ".csv"
    )

    if not csv_files:
        raise FileNotFoundError("No se encontro ningun archivo .csv dentro de 'bd'")

    if len(csv_files) > 1:
        csv_names = ", ".join(file_path.name for file_path in csv_files)
        raise FileExistsError(
            f"Se encontraron multiples archivos CSV en 'bd': {csv_names}. "
            "Usa --csv para indicar cual procesar."
        )

    return csv_files[0]


def main():
    """
    Función principal
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='🤖 Bot de Encuesta SEMARNAT')
    parser.add_argument('--csv', type=str,
                       help='Ruta al archivo CSV. Si se omite, se detecta automaticamente en bd/')
    parser.add_argument('--headless', action='store_true',
                       help='Ejecutar en modo headless (sin interfaz gráfica)')
    parser.add_argument('--no-headless', dest='headless', action='store_false',
                       help='Ejecutar con interfaz gráfica')
    parser.set_defaults(headless=False)
    
    args = parser.parse_args()
    
    try:
        csv_path = detectar_csv_en_bd(args.csv)
    except (FileNotFoundError, FileExistsError) as e:
        print(f"❌ Error: {e}")
        return 1
    
    print("\n" + "="*70)
    print("🤖 BOT DE ENCUESTA SEMARNAT - INICIO")
    print("="*70)
    print(f"📁 CSV: {csv_path}")
    print(f"🖥️  Modo headless: {args.headless}")
    print("="*70 + "\n")
    
    # Verificar archivo CSV
    if not csv_path.exists():
        print(f"❌ Error: No se encuentra el archivo CSV: {csv_path}")
        print("💡 Asegúrate de que el archivo existe en la ruta especificada")
        return 1
    
    # Verificar API key
    api_key = os.getenv("CAPTCHA_API_KEY")
    if not api_key or api_key == "TU_API_KEY_AQUI":
        print("❌ Error: No has configurado la API key de 2Captcha")
        print("💡 Edita el archivo .env y configura CAPTCHA_API_KEY")
        return 1
    
    # Ejecutar bot
    bot = EncuestaBot(str(csv_path), headless=args.headless)
    
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
