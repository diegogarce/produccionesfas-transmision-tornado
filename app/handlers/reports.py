import tornado.web

from app.handlers.base import BaseHandler
from app.services import analytics_service


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_active_sessions_export_rows(active_sessions):
    rows = []
    for row in active_sessions or []:
        rows.append(
            {
                "user_id": row.get("user_id"),
                "user_name": row.get("user_name"),
                "start_time": row.get("start_time"),
                "last_ping": row.get("last_ping"),
                "session_minutes": row.get("session_minutes"),
                "session_seconds": row.get("session_seconds"),
            }
        )
    return rows


class ReportsHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, slug=None):
        if not self.is_admin():
            self.redirect("/watch")
            return
            
        from app.services import events_service
        event = None
        if slug:
            event = events_service.get_event_by_slug(slug)
            
        if not event and self.current_event_id():
            event = events_service.get_event_by_id(self.current_event_id())
            
        if not event:
            self.redirect("/admin/events")
            return

        event_id = event["id"]
        # Ensure exports (which rely on current_event_id) are scoped to this event.
        self.set_secure_cookie("current_event_id", str(event_id))
        # Show all participants (historical list)
        active_sessions = analytics_service.list_all_participants_for_report(event_id=event_id)
        self.render(
            "reports.html",
            event=event,
            active_sessions=active_sessions,
            ws_url=f"{self.get_ws_scheme()}://{self.request.host}/ws?role=reports&event_id={event_id}",
        )


class ReportsExportHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        export_format = self.get_query_argument("format", default="csv").strip().lower()
        kind = self.get_query_argument("kind", default="active_sessions").strip().lower()
        active_within_seconds = _safe_int(self.get_query_argument("window", default=None), default=None)
        
        event_id = self.current_event_id()
        if not event_id:
            try:
                event_id = int(self.get_query_argument("event_id"))
            except (TypeError, ValueError, tornado.web.MissingArgumentError):
                event_id = None

        if kind != "active_sessions":
            self.set_status(400)
            self.finish({"error": "kind inválido"})
            return

        active_sessions = analytics_service.list_all_participants_for_report(event_id=event_id)

        rows = _build_active_sessions_export_rows(active_sessions)
        filename_base = "reporte_sesiones_activas"

        if export_format == "csv":
            self._send_csv(filename_base, rows)
            return

        if export_format == "xlsx":
            self._send_xlsx(filename_base, rows)
            return

        if export_format == "pdf":
            self._send_pdf(filename_base, rows)
            return

        self.set_status(400)
        self.finish({"error": "format inválido (use csv, xlsx o pdf)"})

    def _send_csv(self, filename_base, rows):
        import csv
        import io
        from datetime import datetime

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["user_id", "user_name", "start_time", "last_ping", "session_minutes", "session_seconds"])
        for row in rows:
            writer.writerow(
                [
                    row.get("user_id"),
                    row.get("user_name"),
                    row.get("start_time"),
                    row.get("last_ping"),
                    row.get("session_minutes"),
                    row.get("session_seconds"),
                ]
            )

        # Excel on Windows often expects BOM for UTF-8 CSV.
        csv_text = "\ufeff" + output.getvalue()
        data = csv_text.encode("utf-8")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_base}_{ts}.csv"
        self.set_header("Content-Type", "text/csv; charset=utf-8")
        self.set_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.write(data)

    def _send_xlsx(self, filename_base, rows):
        try:
            from openpyxl import Workbook
        except Exception:
            self.set_status(500)
            self.finish({"error": "Falta dependencia openpyxl para generar XLSX"})
            return

        import io
        from datetime import datetime

        wb = Workbook()
        ws = wb.active
        ws.title = "Sesiones activas"

        headers = ["user_id", "user_name", "start_time", "last_ping", "session_minutes", "session_seconds"]
        ws.append(headers)
        for row in rows:
            ws.append(
                [
                    row.get("user_id"),
                    row.get("user_name"),
                    row.get("start_time"),
                    row.get("last_ping"),
                    row.get("session_minutes"),
                    row.get("session_seconds"),
                ]
            )

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_base}_{ts}.xlsx"
        self.set_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.set_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.write(stream.getvalue())

    def _send_pdf(self, filename_base, rows):
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except Exception:
            self.set_status(500)
            self.finish({"error": "Falta dependencia reportlab para generar PDF"})
            return

        import io
        from datetime import datetime

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()

        ts_human = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elements = [
            Paragraph("Reporte: Sesiones activas", styles["Title"]),
            Paragraph(f"Generado: {ts_human}", styles["Normal"]),
            Spacer(1, 12),
        ]

        table_data = [["User ID", "Nombre", "Inicio", "Último ping", "Min", "Seg"]]
        for row in rows:
            table_data.append(
                [
                    str(row.get("user_id") or ""),
                    str(row.get("user_name") or ""),
                    str(row.get("start_time") or ""),
                    str(row.get("last_ping") or ""),
                    str(row.get("session_minutes") or ""),
                    str(row.get("session_seconds") or ""),
                ]
            )

        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ]
            )
        )
        elements.append(table)

        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_base}_{ts}.pdf"
        self.set_header("Content-Type", "application/pdf")
        self.set_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.write(pdf_bytes)
