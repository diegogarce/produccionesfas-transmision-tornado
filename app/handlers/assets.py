import imghdr
import os
import uuid

from app.handlers.base import BaseHandler

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGO_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "logos")
MAX_LOGO_SIZE = 5 * 1024 * 1024
ALLOWED_FORMATS = {"png", "jpeg", "gif", "webp"}


class LogoUploadHandler(BaseHandler):
    def post(self):
        if not self.is_admin():
            self.set_status(403)
            self.write({"status": "error", "message": "Solo administradores."})
            return

        files = self.request.files.get("logo")
        if not files:
            self.set_status(400)
            self.write({"status": "error", "message": "No se recibió ningún archivo."})
            return

        file_info = files[0]
        payload = file_info.get("body")
        if not payload:
            self.set_status(400)
            self.write({"status": "error", "message": "El archivo está vacío."})
            return

        if len(payload) > MAX_LOGO_SIZE:
            self.set_status(413)
            self.write({"status": "error", "message": "El logo supera los 5 MB permitidos."})
            return

        detected_type = imghdr.what(None, payload)
        if not detected_type or detected_type not in ALLOWED_FORMATS:
            self.set_status(400)
            self.write({"status": "error", "message": "Formato no soportado. Usa PNG, JPG o WebP."})
            return

        extension = "jpg" if detected_type == "jpeg" else detected_type
        safe_name = f"logo-{uuid.uuid4().hex}.{extension}"
        os.makedirs(LOGO_UPLOAD_DIR, exist_ok=True)
        destination = os.path.join(LOGO_UPLOAD_DIR, safe_name)

        try:
            with open(destination, "wb") as handle:
                handle.write(payload)
        except Exception as exc:
            self.set_status(500)
            self.write({"status": "error", "message": f"No se pudo guardar el logo: {exc}"})
            return

        logo_url = self.static_url(f"uploads/logos/{safe_name}")
        self.write({"status": "success", "logo_url": logo_url, "asset_id": safe_name})
