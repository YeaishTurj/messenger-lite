#!/usr/bin/env python3
"""
Messenger Lite - A high-performance, lightweight Facebook Messenger Desktop client for Linux.
Built with PyQt6 and QtWebEngine.

Optimizations:
- ~180MB - 250MB RAM usage (compared to 800MB-1.2GB for Electron)
- Hardware-accelerated video decoding (VA-API on Intel/AMD GPUs)
- PipeWire screen sharing on Wayland (Hyprland / Sway)
- WebRTC Audio & Video Calling with auto-granted media permissions
- Incoming call auto-raise & critical priority desktop alerts
- Native System Tray with real-time unread badge counter
- Automatic attachment download handler with completion notifications
- External links open in default web browser (single tab, unwrapped redirects)
- Zero white-flash dark theme background on startup (#18191a)
- Slim Messenger Blue progress bar during page load (#0099ff)
- V8 memory garbage collector triggered on hide/minimize
- Single-instance enforcement (re-running focuses existing window)
"""

import sys
import os
import re
import shutil
import subprocess
import urllib.parse
import time
import json

# ---------------------------------------------------------
# Chromium & Qt Optimization Flags
# (Must be configured before QApplication initializes)
# ---------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "wayland;xcb")

existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
optimizations = (
    "--enable-features=VaapiVideoDecoder,VaapiIgnoreDriverChecks,WebRTCPipeWireCapturer "
    "--enable-gpu-rasterization "
    "--enable-zero-copy "
    "--ignore-gpu-blocklist "
    "--disable-features=Translate,AutofillServerCommunication,OptimizationHints "
    "--js-flags=--expose-gc "
)
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{existing_flags} {optimizations}".strip()

# ---------------------------------------------------------
# Dependency Check
# ---------------------------------------------------------
try:
    from PyQt6.QtCore import (
        Qt, QUrl, QSize, QPoint, QDir, QStandardPaths,
        pyqtSlot, QByteArray
    )
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QSystemTrayIcon,
        QMenu, QMessageBox, QProgressBar, QVBoxLayout, QWidget
    )
    from PyQt6.QtGui import (
        QIcon, QPixmap, QPainter, QColor, QFont,
        QAction, QKeySequence, QShortcut, QDesktopServices
    )
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    from PyQt6.QtWebEngineCore import (
        QWebEngineProfile, QWebEnginePage, QWebEngineSettings,
        QWebEngineDownloadRequest, QWebEngineScript
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError as e:
    missing_mod = str(e)
    print("\n" + "=" * 60)
    print(" [!] Missing Required Dependencies for Messenger Lite")
    print("=" * 60)
    print(f"Details: {missing_mod}")
    print("\nPlease install the required packages using pacman:")
    print("  sudo pacman -S python-pyqt6 python-pyqt6-webengine\n")
    print("=" * 60 + "\n")
    
    if shutil.which("notify-send"):
        subprocess.run([
            "notify-send",
            "-u", "critical",
            "-a", "Messenger Lite",
            "Missing Dependencies",
            "Please run: sudo pacman -S python-pyqt6 python-pyqt6-webengine"
        ], check=False)
    sys.exit(1)

# ---------------------------------------------------------
# Paths & Settings
# ---------------------------------------------------------
APP_NAME = "messenger-lite"
APP_DISPLAY_NAME = "Messenger"
USER_DATA_DIR = os.path.expanduser("~/.local/share/messenger-lite")
CACHE_DIR = os.path.expanduser("~/.cache/messenger-lite")
SINGLE_INSTANCE_KEY = "messenger_lite_single_instance_sock"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

MESSENGER_URL = "https://www.messenger.com/"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_ICON = os.path.join(SCRIPT_DIR, "..", "assets", "icon.svg")
OFFICIAL_ICON_PATH = os.path.expanduser("~/.local/share/messenger-lite/icon.svg")

# Built-in Official Facebook Messenger Vector SVG
OFFICIAL_SVG_DATA = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800">
  <radialGradient id="a" cx="101.9" cy="809" r="1.1" gradientTransform="matrix(800 0 0 -800 -81386 648000)" gradientUnits="userSpaceOnUse">
    <stop offset="0" style="stop-color:#0099ff"/>
    <stop offset=".6" style="stop-color:#a033ff"/>
    <stop offset=".9" style="stop-color:#ff5280"/>
    <stop offset="1" style="stop-color:#ff7061"/>
  </radialGradient>
  <path fill="url(#a)" d="M400 0C174.7 0 0 165.1 0 388c0 116.6 47.8 217.4 125.6 287 6.5 5.8 10.5 14 10.7 22.8l2.2 71.2a32 32 0 0 0 44.9 28.3l79.4-35c6.7-3 14.3-3.5 21.4-1.6 36.5 10 75.3 15.4 115.8 15.4 225.3 0 400-165.1 400-388S625.3 0 400 0z"/>
  <path fill="#FFF" d="m159.8 501.5 117.5-186.4a60 60 0 0 1 86.8-16l93.5 70.1a24 24 0 0 0 28.9-.1l126.2-95.8c16.8-12.8 38.8 7.4 27.6 25.3L522.7 484.9a60 60 0 0 1-86.8 16l-93.5-70.1a24 24 0 0 0-28.9.1l-126.2 95.8c-16.8 12.8-38.8-7.3-27.5-25.2z"/>
</svg>"""

ICON_CANDIDATES = [
    OFFICIAL_ICON_PATH,
    ASSETS_ICON,
    os.path.join(SCRIPT_DIR, "assets", "icon.svg"),
    os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps/messenger-lite.svg"),
    os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps/messenger.svg"),
    os.path.expanduser("~/.local/share/pixmaps/messenger-lite.svg"),
    os.path.expanduser("~/.local/share/pixmaps/messenger.svg")
]

def ensure_official_icon_on_disk():
    if not os.path.exists(OFFICIAL_ICON_PATH):
        try:
            os.makedirs(os.path.dirname(OFFICIAL_ICON_PATH), exist_ok=True)
            with open(OFFICIAL_ICON_PATH, "wb") as f:
                f.write(OFFICIAL_SVG_DATA)
        except Exception:
            pass

def get_base_icon() -> QIcon:
    ensure_official_icon_on_disk()
    for path in ICON_CANDIDATES:
        if os.path.exists(path):
            return QIcon(path)
    pix = QPixmap()
    pix.loadFromData(OFFICIAL_SVG_DATA, "SVG")
    return QIcon(pix)

# ---------------------------------------------------------
# Meta / Facebook Allowed Authentication & Checkpoint Domains
# ---------------------------------------------------------
ALLOWED_AUTH_DOMAINS = (
    "messenger.com",
    "facebook.com",
    "fb.com",
    "fbcdn.net",
    "fbsbx.com",       # Meta static/sandbox (CAPTCHA & security checkpoints)
    "facebook.net",
    "meta.com",
    "m.me",
    "instagram.com",
    "accountkit.com",
    "recaptcha.net",   # Google reCAPTCHA
    "gstatic.com",     # Google static assets
    "google.com",      # Google reCAPTCHA endpoints
)

# ---------------------------------------------------------
# External URL Dispatcher (Wayland & Linux Native)
# ---------------------------------------------------------
_last_opened_url = None
_last_opened_time = 0.0

def clean_external_url(url_str: str) -> str:
    """Unwrap Meta / Facebook / Messenger redirect tracker parameters if present"""
    if not url_str:
        return ""
    try:
        parsed = urllib.parse.urlparse(url_str)
        # Never unwrap internal authentication checkpoints like fbsbx.com/captcha
        if "fbsbx.com" in parsed.netloc or "/captcha/" in parsed.path or "/checkpoint/" in parsed.path:
            return url_str
        if any(d in parsed.netloc for d in ("facebook.com", "messenger.com", "wl.co")):
            qs = urllib.parse.parse_qs(parsed.query)
            if "u" in qs and qs["u"]:
                return urllib.parse.unquote(qs["u"][0])
    except Exception:
        pass
    return url_str

def open_external_url(target):
    """Reliably launch external URL in user's default browser (e.g. Chrome / Brave) with de-duplication"""
    global _last_opened_url, _last_opened_time

    if isinstance(target, QUrl):
        url_str = target.toString()
    else:
        url_str = str(target)

    url_str = clean_external_url(url_str).strip()
    if not url_str or url_str in ("about:blank", "about:", ""):
        return

    # Debounce identical URL within 1.5 seconds to prevent duplicate tabs
    now = time.time()
    if url_str == _last_opened_url and (now - _last_opened_time) < 1.5:
        return
    _last_opened_url = url_str
    _last_opened_time = now

    # 1. Primary: xdg-open in detached session
    try:
        subprocess.Popen(
            ["xdg-open", url_str],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return
    except Exception:
        pass

    # 2. Secondary: gio open
    if shutil.which("gio"):
        try:
            subprocess.Popen(
                ["gio", "open", url_str],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return
        except Exception:
            pass

    # 3. Fallback: QDesktopServices
    QDesktopServices.openUrl(QUrl(url_str))

# ---------------------------------------------------------
# Custom WebEnginePage for External Links & Calling
# ---------------------------------------------------------
class ExternalLinkPage(QWebEnginePage):
    """Temporary page to intercept window.open and target='_blank' links"""
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.has_dispatched = False
        self.urlChanged.connect(self.on_url_changed)

    def _dispatch_once(self, url: QUrl):
        if self.has_dispatched:
            return
        url_str = url.toString()
        host = url.host().lower()

        # Do not dispatch internal authentication checkpoints or CAPTCHAs to external browser
        if any(d in host for d in ALLOWED_AUTH_DOMAINS) or not url_str or url_str in ("about:blank", "about:"):
            return

        self.has_dispatched = True
        open_external_url(url_str)
        self.deleteLater()

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame):
        host = url.host().lower()
        if any(d in host for d in ALLOWED_AUTH_DOMAINS) or not is_main_frame:
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
        url_str = url.toString()
        if url_str and url_str not in ("about:blank", "about:"):
            self._dispatch_once(url)
            return False
        return True

    def on_url_changed(self, url: QUrl):
        self._dispatch_once(url)

class MessengerWebPage(QWebEnginePage):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.featurePermissionRequested.connect(self.on_feature_permission_requested)
        self.setBackgroundColor(QColor("#18191a"))

    def on_feature_permission_requested(self, security_origin: QUrl, feature):
        host = security_origin.host()
        # Automatically allow media devices and notifications for Messenger, Facebook & checkpoints
        if any(d in host for d in ALLOWED_AUTH_DOMAINS):
            try:
                policy = getattr(QWebEnginePage.PermissionPolicy, 'PermissionGrantedByUser', None)
                if policy is None:
                    policy = getattr(QWebEnginePage, 'PermissionGrantedByUser', 1)
                self.setFeaturePermission(security_origin, feature, policy)
            except Exception as err:
                print(f"[!] Error granting feature permission: {err}")
        else:
            try:
                policy = getattr(QWebEnginePage.PermissionPolicy, 'PermissionDeniedByUser', None)
                if policy is None:
                    policy = getattr(QWebEnginePage, 'PermissionDeniedByUser', 0)
                self.setFeaturePermission(security_origin, feature, policy)
            except Exception:
                pass

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame):
        # 1. Subframes (iframes for CAPTCHA, authentication, embeds) MUST always load internally
        if not is_main_frame:
            return True

        host = url.host().lower()
        url_str = url.toString()

        # 2. Allow empty or internal browser schemes
        if (
            not host
            or url.scheme() in ("blob", "data", "about", "wss", "ws")
        ):
            return True

        # 3. Allow all Meta login, OAuth, checkpoint, and CAPTCHA domains
        if any(d in host for d in ALLOWED_AUTH_DOMAINS):
            return True

        # 4. Any external URL (e.g. YouTube, GitHub, news): open in default browser!
        open_external_url(url_str)
        return False
        return False

    def createWindow(self, window_type):
        return ExternalLinkPage(self.profile(), self)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        pass

# ---------------------------------------------------------
# Main Application Window
# ---------------------------------------------------------
class MessengerWindow(QMainWindow):
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.is_quitting = False
        self.base_icon = get_base_icon()
        self.current_unread_count = 0

        self.setWindowTitle("Messenger")
        self.setWindowIcon(self.base_icon)
        self.resize(1120, 780)
        self.setMinimumSize(600, 500)

        # Eliminate white flash during window creation
        self.setStyleSheet("QMainWindow { background-color: #18191a; }")

        # Setup persistent web profile
        self.profile = QWebEngineProfile("messenger_storage", self)
        os.makedirs(USER_DATA_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.profile.setPersistentStoragePath(USER_DATA_DIR)
        self.profile.setCachePath(CACHE_DIR)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        self.profile.setHttpUserAgent(USER_AGENT)

        # Limit cache growth (120MB max disk cache)
        if hasattr(self.profile, 'setHttpCacheMaximumSize'):
            self.profile.setHttpCacheMaximumSize(120 * 1024 * 1024)

        # WebEngine settings
        settings = self.profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.DnsPrefetchEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste, True)

        # Connect download handler
        self.profile.downloadRequested.connect(self.on_download_requested)

        # Subframe helper script for iframe focus & captcha response injection
        subframe_helper = QWebEngineScript()
        subframe_helper.setName("subframe_focus_captcha_helper")
        subframe_helper.setSourceCode("""
        (function() {
            function ensureFocus(target) {
                if (!target) return;
                var tag = target.tagName ? target.tagName.toUpperCase() : '';
                if (tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable) {
                    target.focus();
                }
            }

            document.addEventListener('pointerdown', function(e) { ensureFocus(e.target); }, true);
            document.addEventListener('mousedown', function(e) { ensureFocus(e.target); }, true);
            document.addEventListener('click', function(e) { ensureFocus(e.target); }, true);

            window.addEventListener('message', function(ev) {
                if (ev.data && ev.data.type === 'FILL_CAPTCHA') {
                    var inputs = document.querySelectorAll('input#audio-response, input[name="audio-response"], input.rc-response-input-field, input[type="text"]');
                    for (var i = 0; i < inputs.length; i++) {
                        inputs[i].focus();
                        inputs[i].value = ev.data.text;
                        inputs[i].dispatchEvent(new Event('input', { bubbles: true }));
                        inputs[i].dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            });
        })();
        """)
        subframe_helper.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        subframe_helper.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        subframe_helper.setRunsOnSubFrames(True)
        self.profile.scripts().insert(subframe_helper)

        # Inject click interceptor for external links
        link_script = QWebEngineScript()
        link_script.setName("messenger_external_link_interceptor")
        link_script.setSourceCode("""
        (function() {
            const allowed = [
                'messenger.com', 'facebook.com', 'fb.com', 'fbcdn.net',
                'fbsbx.com', 'facebook.net', 'meta.com', 'm.me',
                'instagram.com', 'recaptcha.net', 'gstatic.com', 'google.com'
            ];
            document.addEventListener('click', function(e) {
                let el = e.target;
                while (el && el.tagName !== 'A') {
                    el = el.parentElement;
                }
                if (el && el.tagName === 'A' && el.href) {
                    const href = el.href;
                    if (href.startsWith('http://') || href.startsWith('https://')) {
                        try {
                            const url = new URL(href);
                            const host = url.hostname.toLowerCase();
                            const isInternal = allowed.some(d => host === d || host.endsWith('.' + d));
                            if (!isInternal) {
                                e.preventDefault();
                                e.stopPropagation();
                                window.open(href, '_blank');
                            }
                        } catch (err) {}
                    }
                }
            }, true);
        })();
        """)
        link_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        link_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        link_script.setRunsOnSubFrames(False)
        self.profile.scripts().insert(link_script)

        # Desktop notification presenter
        if hasattr(self.profile, 'setNotificationPresenter'):
            self.profile.setNotificationPresenter(self.handle_web_notification)

        # Container & Layout with Slim Messenger Blue Progress Bar
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFixedHeight(2)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #18191a;
            }
            QProgressBar::chunk {
                background-color: #0099ff;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Web view setup
        self.web_page = MessengerWebPage(self.profile, self)
        self.web_page.fullScreenRequested.connect(self.on_fullscreen_requested)

        self.web_view = QWebEngineView(self)
        self.web_view.setPage(self.web_page)
        self.web_view.setStyleSheet("background-color: #18191a;")
        self.web_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.web_view)

        self.setCentralWidget(container)
        container.setFocusProxy(self.web_view)
        self.setFocusProxy(self.web_view)

        # Connect loading & title signals
        self.web_view.loadStarted.connect(self.on_load_started)
        self.web_view.loadProgress.connect(self.on_load_progress)
        self.web_view.loadFinished.connect(self.on_load_finished)
        self.web_view.titleChanged.connect(self.on_title_changed)

        # Setup System Tray Icon & Shortcuts
        self.setup_tray_icon()
        self.setup_shortcuts()

        # Load Messenger Web
        self.web_view.load(QUrl(MESSENGER_URL))

    def on_load_started(self):
        self.progress_bar.show()
        self.progress_bar.setValue(10)

    def on_load_progress(self, progress):
        self.progress_bar.setValue(progress)

    def on_load_finished(self, success):
        self.progress_bar.hide()

    def on_fullscreen_requested(self, request):
        if request.toggleOn():
            self.showFullScreen()
            request.accept()
        else:
            self.showNormal()
            request.accept()

    def on_download_requested(self, download: QWebEngineDownloadRequest):
        download_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        filename = download.suggestedFileName() or download.downloadFileName() or "messenger-attachment"
        download.setDownloadDirectory(download_dir)
        download.setDownloadFileName(filename)
        download.accept()

        def on_finished():
            if download.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                self.send_system_notification(
                    "Messenger Download Finished",
                    f"Saved {filename} to Downloads",
                    urgency="normal"
                )
        download.isFinishedChanged.connect(on_finished)

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self.base_icon, self)
        self.tray_icon.setToolTip("Messenger Lite")

        self.tray_menu = QMenu()
        
        show_action = QAction("Show / Hide", self)
        show_action.triggered.connect(self.toggle_visibility)
        self.tray_menu.addAction(show_action)

        reload_action = QAction("Reload Page (Ctrl+R)", self)
        reload_action.triggered.connect(self.reload_page)
        self.tray_menu.addAction(reload_action)

        mute_action = QAction("Mute Audio", self)
        mute_action.setCheckable(True)
        mute_action.toggled.connect(self.toggle_mute)
        self.tray_menu.addAction(mute_action)

        captcha_action = QAction("Enter CAPTCHA Response (Ctrl+I)", self)
        captcha_action.triggered.connect(self.prompt_captcha_input)
        self.tray_menu.addAction(captcha_action)

        self.tray_menu.addSeparator()

        quit_action = QAction("Quit Messenger", self)
        quit_action.triggered.connect(self.really_quit)
        self.tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Q"), self, self.really_quit)
        QShortcut(QKeySequence("Ctrl+W"), self, self.hide_to_tray)
        QShortcut(QKeySequence("Ctrl+R"), self, self.reload_page)
        QShortcut(QKeySequence("F5"), self, self.reload_page)
        QShortcut(QKeySequence("Ctrl+I"), self, self.prompt_captcha_input)
        QShortcut(QKeySequence("Ctrl+="), self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl++"), self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self, self.zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self, self.zoom_reset)

    def prompt_captcha_input(self):
        """Native dialog helper to inject audio CAPTCHA response across all frames"""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self,
            "CAPTCHA Input Helper",
            "Enter the audio verification response (what you heard):",
            text=""
        )
        if ok and text.strip():
            val = json.dumps(text.strip())
            js = f"""
            (function() {{
                var msg = {{ type: 'FILL_CAPTCHA', text: {val} }};
                window.postMessage(msg, '*');
                var iframes = document.querySelectorAll('iframe');
                for (var i = 0; i < iframes.length; i++) {{
                    try {{
                        iframes[i].contentWindow.postMessage(msg, '*');
                    }} catch (e) {{}}
                }}
            }})();
            """
            self.web_page.runJavaScript(js)

    def zoom_in(self):
        factor = self.web_view.zoomFactor()
        self.web_view.setZoomFactor(min(factor + 0.1, 2.5))

    def zoom_out(self):
        factor = self.web_view.zoomFactor()
        self.web_view.setZoomFactor(max(factor - 0.1, 0.5))

    def zoom_reset(self):
        self.web_view.setZoomFactor(1.0)

    def reload_page(self):
        self.web_view.reload()

    def toggle_mute(self, muted: bool):
        self.web_page.setAudioMuted(muted)

    def show_and_activate(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self):
        self.hide()
        # Memory optimization: trigger V8 GC when hidden to reclaim RAM
        if hasattr(self, 'web_page') and self.web_page:
            self.web_page.runJavaScript("if (window.gc) { window.gc(); }")

    def toggle_visibility(self):
        if self.isVisible() and not self.isMinimized():
            self.hide_to_tray()
        else:
            self.show_and_activate()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visibility()

    def handle_web_notification(self, notification):
        title = (notification.title() or "").strip()
        msg = (notification.message() or "").strip()

        # Check for incoming calls
        is_call = "call" in title.lower() or "call" in msg.lower()
        if is_call:
            self.show_and_activate()
            self.send_system_notification(
                f"📞 {title or 'Messenger Call'}",
                msg or "Incoming call...",
                urgency="critical"
            )
        else:
            if not self.isActiveWindow() or not self.isVisible():
                self.send_system_notification(title, msg, urgency="normal")

    def send_system_notification(self, title, message, urgency="normal"):
        if not title and not message:
            return
        if shutil.which("notify-send"):
            try:
                icon_path = OFFICIAL_ICON_PATH if os.path.exists(OFFICIAL_ICON_PATH) else "messenger-lite"
                subprocess.Popen([
                    "notify-send",
                    "-a", "Messenger",
                    "-u", urgency,
                    "-i", icon_path,
                    title,
                    message
                ])
                return
            except Exception:
                pass

        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def on_title_changed(self, title: str):
        match = re.search(r'\((\d+)\)', title)
        if match:
            count = int(match.group(1))
            self.update_tray_badge(count)
        elif '(*)' in title or '*' in title:
            self.update_tray_badge('•')
        else:
            self.update_tray_badge(0)

    def update_tray_badge(self, unread):
        if unread == self.current_unread_count:
            return
        self.current_unread_count = unread

        if unread == 0 or unread is None:
            self.tray_icon.setIcon(self.base_icon)
            self.setWindowIcon(self.base_icon)
            self.tray_icon.setToolTip("Messenger Lite")
            return

        size = 64
        pixmap = self.base_icon.pixmap(size, size)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        badge_radius = 16
        center_x = size - badge_radius - 2
        center_y = size - badge_radius - 2
        painter.setBrush(QColor(235, 64, 52))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(center_x, center_y), badge_radius, badge_radius)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Sans", 14, QFont.Weight.Bold)
        painter.setFont(font)
        text = str(unread) if str(unread) != '•' else "•"
        painter.drawText(
            center_x - badge_radius, center_y - badge_radius,
            badge_radius * 2, badge_radius * 2,
            Qt.AlignmentFlag.AlignCenter, text
        )
        painter.end()

        badged_icon = QIcon(pixmap)
        self.tray_icon.setIcon(badged_icon)
        self.setWindowIcon(badged_icon)
        self.tray_icon.setToolTip(f"Messenger Lite - {unread} unread messages")

    def closeEvent(self, event):
        if self.is_quitting:
            event.accept()
        else:
            event.ignore()
            self.hide_to_tray()

    def really_quit(self):
        self.is_quitting = True
        if hasattr(self, 'web_view') and self.web_view:
            self.web_view.stop()
            self.web_view.setPage(None)
        if hasattr(self, 'web_page') and self.web_page:
            self.web_page.deleteLater()
        self.app.quit()

# ---------------------------------------------------------
# Single Instance Management & Entry Point
# ---------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setWindowIcon(get_base_icon())

    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_KEY)
    if socket.waitForConnected(400):
        socket.write(b"SHOW\n")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        sys.exit(0)

    server = QLocalServer()
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    server.listen(SINGLE_INSTANCE_KEY)

    window = MessengerWindow(app)

    def handle_incoming_connection():
        client = server.nextPendingConnection()
        if client:
            client.readyRead.connect(lambda: on_client_read(client))

    def on_client_read(client):
        data = client.readAll().data().decode("utf-8")
        if "SHOW" in data:
            window.show_and_activate()

    server.newConnection.connect(handle_incoming_connection)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
