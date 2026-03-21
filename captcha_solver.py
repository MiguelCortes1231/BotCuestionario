#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🧩 CAPTCHA SOLVER PARA 2CAPTCHA
--------------------------------------------------------------------------------
Módulo especializado para resolver captchas usando el servicio 2Captcha
Con manejo robusto de errores y logging detallado
"""

import os
import time
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from twocaptcha import TwoCaptcha
from twocaptcha.api import ApiException, NetworkException
import dotenv

# Cargar variables de entorno
dotenv.load_dotenv()

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/captcha.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class CaptchaSolver:
    """
    🎯 Solucionador de captchas usando 2Captcha
    
    Características:
    - Soporte para captchas de imagen normales
    - Manejo de errores detallado
    - Timeouts configurables
    - Logging completo
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el solucionador de captchas
        
        Args:
            api_key: API key de 2Captcha (opcional, por defecto usa variable de entorno)
        """
        self.api_key = api_key or os.getenv("CAPTCHA_API_KEY")
        if not self.api_key:
            raise ValueError("❌ No se encontró API_KEY para 2Captcha")
        
        # Inicializar solver
        self.solver = TwoCaptcha(self.api_key)
        
        # Configuración por defecto
        self.default_timeout = 120
        self.polling_interval = 5
        
        logger.info("✅ CaptchaSolver inicializado correctamente")
    
    def download_captcha_image(self, driver, captcha_img_element) -> Optional[str]:
        """
        📥 Descarga la imagen del captcha desde la página
        
        Args:
            driver: Instancia de Selenium WebDriver
            captcha_img_element: Elemento img del captcha
            
        Returns:
            Ruta del archivo temporal o None si falla
        """
        try:
            # Obtener src de la imagen
            img_src = captcha_img_element.get_attribute('src')
            if not img_src:
                logger.error("❌ No se pudo obtener src de la imagen")
                return None
            
            # Crear directorio temporal si no existe
            temp_dir = Path("temp_captcha")
            temp_dir.mkdir(exist_ok=True)
            
            # Generar nombre único
            timestamp = int(time.time())
            img_path = temp_dir / f"captcha_{timestamp}.png"

            if img_src.startswith("data:image/"):
                logger.info("📸 Captcha embebido detectado en formato base64")
                try:
                    _, encoded_image = img_src.split(",", 1)
                    image_bytes = base64.b64decode(encoded_image)
                except Exception as e:
                    logger.error(f"❌ No se pudo decodificar el captcha en base64: {e}")
                    return None
            else:
                logger.info(f"📸 URL del captcha: {img_src}")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                response = requests.get(img_src, headers=headers, timeout=30)
                response.raise_for_status()
                image_bytes = response.content
            
            # Guardar imagen
            with open(img_path, 'wb') as f:
                f.write(image_bytes)
            
            logger.info(f"✅ Captcha descargado: {img_path}")
            return str(img_path)
            
        except Exception as e:
            logger.error(f"❌ Error descargando captcha: {e}")
            return None
    
    def solve_captcha(self, image_path: str, timeout: int = 120) -> Optional[Dict[str, Any]]:
        """
        🧩 Resuelve el captcha usando 2Captcha
        
        Args:
            image_path: Ruta a la imagen del captcha
            timeout: Timeout máximo en segundos
            
        Returns:
            Diccionario con resultado o None si falla
        """
        try:
            # Verificar que el archivo existe
            if not os.path.exists(image_path):
                logger.error(f"❌ Archivo no encontrado: {image_path}")
                return None
            
            file_size = os.path.getsize(image_path)
            logger.info(f"📁 Imagen captcha: {image_path} ({file_size} bytes)")
            
            # Resolver captcha
            logger.info("🔄 Enviando captcha a 2Captcha...")
            result = self.solver.normal(
                image_path,
                timeout=timeout,
                pollingInterval=self.polling_interval
            )
            
            if result and 'code' in result:
                logger.info(f"✅ Captcha resuelto: {result['code']}")
                logger.info(f"📋 ID de tarea: {result.get('captchaId', 'N/A')}")
                return result
            else:
                logger.error("❌ Respuesta inválida de 2Captcha")
                return None
                
        except ApiException as e:
            logger.error(f"❌ Error de API 2Captcha: {e}")
            if "ERROR_WRONG_USER_KEY" in str(e):
                logger.error("💡 API key inválida")
            elif "ERROR_ZERO_BALANCE" in str(e):
                logger.error("💡 Saldo insuficiente en 2Captcha")
            return None
            
        except NetworkException as e:
            logger.error(f"❌ Error de red: {e}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}", exc_info=True)
            return None
    
    def solve_captcha_from_driver(self, driver, captcha_img_element) -> Optional[str]:
        """
        🔄 Método completo: descarga y resuelve el captcha
        
        Args:
            driver: Instancia de Selenium WebDriver
            captcha_img_element: Elemento img del captcha
            
        Returns:
            Texto del captcha o None si falla
        """
        # Descargar imagen
        img_path = self.download_captcha_image(driver, captcha_img_element)
        if not img_path:
            return None
        
        try:
            # Resolver captcha
            result = self.solve_captcha(img_path)
            if result and 'code' in result:
                return result['code']
            return None
            
        finally:
            # Limpiar archivo temporal (opcional)
            try:
                if os.path.exists(img_path):
                    os.remove(img_path)
                    logger.debug(f"🧹 Archivo temporal eliminado: {img_path}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar archivo temporal: {e}")


def main():
    """
    Función de prueba para verificar el funcionamiento
    """
    print("=" * 60)
    print("🧪 PRUEBA DE CAPTCHA SOLVER")
    print("=" * 60)
    
    # Verificar API key
    api_key = os.getenv("CAPTCHA_API_KEY")
    if not api_key or api_key == "TU_API_KEY_AQUI":
        print("❌ Configura tu API_KEY en el archivo .env")
        return 1
    
    print(f"✅ API Key configurada: {api_key[:5]}...{api_key[-5:]}")
    
    # Inicializar solver
    try:
        solver = CaptchaSolver(api_key)
        print("✅ Solver inicializado")
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    # Probar con un archivo de ejemplo
    test_path = "test_captcha.png"
    if os.path.exists(test_path):
        print(f"\n📁 Probando con archivo: {test_path}")
        result = solver.solve_captcha(test_path)
        if result:
            print(f"\n✅ Resultado: {result}")
        else:
            print("❌ Falló la resolución")
    else:
        print(f"\n⚠️ Archivo de prueba no encontrado: {test_path}")
        print("💡 Para probar, coloca una imagen de captcha como 'test_captcha.png'")
    
    return 0


if __name__ == "__main__":
    exit(main())
