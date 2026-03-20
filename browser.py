import os
import platform
import shutil
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService


# ==========================================================
# 🧩 Helpers de ENV / Paths
# ==========================================================


def _cleanup_chrome_tmp_dirs(paths: dict) -> None:
    """
    Compatibilidad con codigo existente.

    Ya no se crean directorios temporales manuales para Chrome, por lo que
    el sistema operativo gestiona esos archivos por su cuenta.
    """
    return None




def _truthy(val: str | None, default: bool = False) -> bool:
    """
    /**
     * 🔍 Convierte un texto a booleano real (ideal para ENV).
     *
     * ✅ TRUE si val es: "1", "true", "yes", "y", "on" (sin importar mayúsculas)
     * ✅ Si val es None -> regresa default
     */
    """
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_download_dir(download_dir: str | None) -> str:
    """
    /**
     * 📁 Resuelve y asegura la existencia del directorio de descargas.
     *
     * 🧠 Lógica:
     * - Si no se pasa `download_dir`, usa ENV DOWNLOAD_DIR
     * - Si tampoco existe, usa "downloads" por defecto
     * - Expande (~), convierte a absoluto y crea el folder si no existe
     */
    """
    if not download_dir:
        download_dir = os.getenv("DOWNLOAD_DIR", "downloads")

    p = Path(download_dir).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


# ==========================================================
# 🐳 Detección de entorno headless (Railway/PaaS)
# ==========================================================
def _is_docker() -> bool:
    """
    /**
     * 🐳 Detecta si el proceso se está ejecutando dentro de Docker.
     *
     * ⚠️ Nota: En Railway/PAAS esto puede fallar (a veces no hay /.dockerenv).
     */
    """
    if os.path.exists("/.dockerenv"):
        return True

    # Cgroup heurístico (puede no contener "docker" en algunos PaaS)
    try:
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists():
            txt = cgroup.read_text(errors="ignore").lower()
            if any(x in txt for x in ("docker", "kubepods", "containerd")):
                return True
    except Exception:
        pass

    return False


def _is_headless_environment() -> bool:
    """
    /**
     * 🖥️ Detecta si NO hay entorno gráfico disponible.
     *
     * ✅ En contenedores/servidores normalmente NO existe DISPLAY.
     * ✅ Railway suele ejecutar Linux sin DISPLAY, aunque _is_docker() regrese False.
     */
    """
    display = os.getenv("DISPLAY")
    wayland = os.getenv("WAYLAND_DISPLAY")

    # Señales típicas de PaaS/CI
    railway = os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_STATIC_URL")
    heroku_like = os.getenv("DYNO")
    ci = os.getenv("CI")

    if railway or heroku_like:
        return True

    if ci and _truthy(ci, default=False):
        return True

    if not display and not wayland:
        return True

    return False


# ==========================================================
# 🌐 Detección binarios Chrome/Chromium y chromedriver
# ==========================================================
def _pick_chrome_binary() -> str | None:
    """
    /**
     * 🌐 Determina qué binario de Chrome/Chromium usar.
     *
     * 🧠 Prioridad:
     * 1️⃣ ENV CHROME_BINARY o CHROME_BIN
     * 2️⃣ Rutas típicas en Linux/Docker
     * 3️⃣ PATH del sistema (shutil.which)
     */
    """
    env_bin = os.getenv("CHROME_BINARY") or os.getenv("CHROME_BIN")
    if env_bin:
        return env_bin

    for candidate in (
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ):
        if Path(candidate).exists():
            return candidate

    return (
        shutil.which("chromium")
        or shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium-browser")
    )


def _pick_chromedriver() -> str | None:
    """
    /**
     * 🚗 Determina qué chromedriver usar.
     *
     * 🧠 Prioridad:
     * 1️⃣ ENV CHROMEDRIVER o CHROMEDRIVER_BIN
     * 2️⃣ Ruta fija /usr/bin/chromedriver
     * 3️⃣ PATH del sistema
     */
    """
    env_drv = os.getenv("CHROMEDRIVER") or os.getenv("CHROMEDRIVER_BIN")
    if env_drv:
        return env_drv

    for candidate in ("/usr/bin/chromedriver",):
        if Path(candidate).exists():
            return candidate

    return shutil.which("chromedriver")


# ==========================================================
# 🚀 build_driver: el punto crítico (aquí blindamos cuelgues)
# ==========================================================
def build_driver(
    headless: bool | None = None,
    download_dir: str | None = None,
    page_load_timeout: int | None = None,
    script_timeout: int | None = None,
    implicit_wait: int | None = None,
):
    """
    /**
     * 🧠 Construye y devuelve Selenium WebDriver (Chrome/Chromium).
     *
     * ✅ Funciona en:
     * 🍎 macOS (local con UI)
     * 🐧 Linux server (sin UI)
     * 🐳 Docker / Railway / PaaS (headless)
     *
     * 🎯 Objetivo principal:
     * - Evitar cuelgues infinitos (timeouts)
     * - Errores útiles para diagnóstico
     * - Compatibilidad en PaaS (flags + /tmp)
     *
     * 🔧 ENV importantes:
     * - HEADLESS=1/0
     * - DOWNLOAD_DIR=/app/downloads
     * - SELENIUM_PAGELOAD_TIMEOUT=90
     * - SELENIUM_SCRIPT_TIMEOUT=90
     * - SELENIUM_IMPLICIT_WAIT=0
     * - SELENIUM_VERBOSE_CHROMEDRIVER=1 (logs extra del driver)
     * - SELENIUM_HEADLESS_MODE=new|old (fallback por compat)
     */
    """
    system = platform.system().lower()
    is_linux = system == "linux"
    in_docker = _is_docker()
    no_display = _is_headless_environment()

    # ✅ Headless automático:
    # - Si HEADLESS viene seteado: respétalo.
    # - Si headless=None: decidir por heurística robusta.
    if headless is None:
        env_headless = os.getenv("HEADLESS")
        if env_headless is not None:
            headless = _truthy(env_headless, default=True)
        else:
            headless = bool(is_linux and (in_docker or no_display))

    # ✅ Timeouts configurables por ENV si no vienen como parámetro
    if page_load_timeout is None:
        page_load_timeout = int(os.getenv("SELENIUM_PAGELOAD_TIMEOUT", "90"))
    if script_timeout is None:
        script_timeout = int(os.getenv("SELENIUM_SCRIPT_TIMEOUT", "90"))
    if implicit_wait is None:
        implicit_wait = int(os.getenv("SELENIUM_IMPLICIT_WAIT", "0"))

    download_dir_abs = _resolve_download_dir(download_dir)

    opts = Options()

    # ✅ Selección explícita del binario de Chrome
    chrome_binary = _pick_chrome_binary()
    if chrome_binary:
        opts.binary_location = chrome_binary

    # 🌎 Idioma del navegador (SAT a veces es sensible)
    lang = os.getenv("LANG", "es-MX")
    opts.add_argument(f"--lang={lang}")

    # 🧬 User-Agent personalizado si existe
    user_agent = os.getenv("USER_AGENT")
    if user_agent:
        opts.add_argument(f"--user-agent={user_agent}")

    # 🖥️ Tamaño fijo (evita glitches en headless)
    opts.add_argument("--window-size=1920,1080")

    # 🧱 Flags típicos para contenedores / PaaS (evitan crash al iniciar)
    # ⚠️ En Railway suelen ser OBLIGATORIOS
    opts.add_argument("--disable-dev-shm-usage")   # /dev/shm pequeño => crash sin esto
    opts.add_argument("--no-sandbox")              # requerido en PaaS
    opts.add_argument("--disable-gpu")             # safe en headless Linux
    opts.add_argument("--disable-setuid-sandbox")

    # 🧠 Flags extra para entornos con pocos recursos (reduce procesos/hilos)
    opts.add_argument("--no-zygote")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-background-timer-throttling")
    opts.add_argument("--disable-renderer-backgrounding")
    opts.add_argument("--disable-features=Translate,BackForwardCache")
    opts.add_argument("--metrics-recording-only")
    opts.add_argument("--mute-audio")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")

    import random

    # 🛠️ Evita DevToolsActivePort crash en algunos entornos
    # Si NO defines SELENIUM_REMOTE_DEBUG_PORT -> usa random (evita puerto ocupado)
    rd_port_env = os.getenv("SELENIUM_REMOTE_DEBUG_PORT", "").strip()

    if rd_port_env:
        rd_port = int(rd_port_env)
    else:
        rd_port = random.randint(20000, 40000)

    print(f"🧩🌐 remote-debugging-port={rd_port}")
    opts.add_argument(f"--remote-debugging-port={rd_port}")

    # 👻 Headless: soporta fallback si “new” falla
    headless_mode = (os.getenv("SELENIUM_HEADLESS_MODE", "new") or "new").strip().lower()
    if headless:
        if headless_mode == "old":
            opts.add_argument("--headless")
        else:
            # Chromium moderno
            opts.add_argument("--headless=new")

    # 📥 Configuración de descargas automáticas
    prefs = {
        "download.default_directory": download_dir_abs,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    opts.add_experimental_option("prefs", prefs)

    # 🤖 Minimiza banners de "Chrome está siendo controlado..."
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    # 🚗 En Linux/Docker se usa chromedriver del sistema (apt)
    driver_path = _pick_chromedriver() if is_linux else None

    # 🧰 Verbose chromedriver (útil si se cuelga al iniciar)
    verbose_driver = _truthy(os.getenv("SELENIUM_VERBOSE_CHROMEDRIVER"), default=False)
    service_args = []
    if verbose_driver:
        service_args = ["--verbose"]
        # log file opcional
        log_path = os.getenv("CHROMEDRIVER_LOG", "/tmp/chromedriver.log")
        service_args += [f"--log-path={log_path}"]

    try:
        if driver_path:
            service = ChromeService(executable_path=driver_path, service_args=service_args)
        else:
            service = ChromeService(service_args=service_args)

        driver = webdriver.Chrome(service=service, options=opts)

    except Exception as e:
        # 🧨 Error detallado para diagnóstico
        info = (
            f"❌ No se pudo iniciar ChromeDriver.\n"
            f"   system={system} in_docker={in_docker} no_display={no_display} headless={headless}\n"
            f"   headless_mode={headless_mode}\n"
            f"   chrome_binary={chrome_binary}\n"
            f"   chromedriver={driver_path}\n"
            f"   downloads={download_dir_abs}\n"
            f"   remote_debug_port={rd_port}\n"
            f"   verbose_driver={verbose_driver}\n"
            f"   error={e}\n"
            f"   tips:\n"
            f"     - En Railway normalmente necesitas headless ✅\n"
            f"     - Asegúrate de tener chromium + chromium-driver instalados ✅\n"
            f"     - Si se cuelga al iniciar, activa SELENIUM_VERBOSE_CHROMEDRIVER=1 ✅\n"
            f"     - Si falla con --headless=new, prueba SELENIUM_HEADLESS_MODE=old ✅\n"
        )
        raise RuntimeError(info) from e

    # ⏱️ Timeouts IMPORTANTES (evitan cuelgues infinitos)
    # ✅ page load: protege driver.get()
    driver.set_page_load_timeout(int(page_load_timeout))
    # ✅ script timeout: protege JS/async
    driver.set_script_timeout(int(script_timeout))
    # ✅ implicit wait (mejor mantenerlo 0 si usas WebDriverWait)
    if implicit_wait and int(implicit_wait) > 0:
        driver.implicitly_wait(int(implicit_wait))

    # 🕵️ Oculta navigator.webdriver (evasión básica)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"},
        )
    except Exception:
        pass

    return driver
