from odoo import http
from odoo.http import request, content_disposition
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class PurchaseOrderXlsx(http.Controller):

    # ================= Build Filename =================
    def _build_filename(self, start_date=None, end_date=None):
        filename = "REKAP_PEMBELIAN"
        if start_date and end_date:
            filename += f"_{start_date}_s_d_{end_date}"
        elif start_date:
            filename += f"_from_{start_date}"
        elif end_date:
            filename += f"_until_{end_date}"
        filename += ".xlsx"
        return filename

    # ================= Helper Format Tanggal Indonesia =================
    def _format_tanggal_id(self, tgl):
        if not tgl:
            return '-'
        if isinstance(tgl, str):
            tgl = datetime.strptime(tgl, '%d/%m/%Y')
        bulan_id = [
            'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
            'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
        ]
        return f"{tgl.day} {bulan_id[tgl.month - 1]} {tgl.year}"

    # ================= ROUTE =================
    @http.route('/purchase/xlsx_report', type='http', auth='user')
    def generate_report_po_xlsx(self, start_date=None, end_date=None, **kw):
        """
        Generate XLSX report Purchase Order per supplier, with signature section
        """

        _logger.info("📥 CONTROLLER RAW start_date=%s end_date=%s", start_date, end_date)

        # ================= Parse Tanggal =================
        fmt = "%Y-%m-%d"
        try:
            start_dt = datetime.strptime(start_date, fmt) if start_date else None
            end_dt = datetime.strptime(end_date, fmt) if end_date else None
        except ValueError:
            return "❌ Format tanggal salah (yyyy-mm-dd)"

        _logger.info("📥 PARSED start_dt=%s end_dt=%s", start_dt, end_dt)

        if start_dt and end_dt and end_dt < start_dt:
            return "❌ End Date tidak boleh lebih kecil dari Start Date"

        domain = []
        if start_dt:
            domain.append(('date_order', '>=', start_dt))
        if end_dt:
            domain.append(('date_order', '<=', end_dt))

        _logger.info("🔎 DOMAIN: %s", domain)

        # ================= Ambil Data =================
        orders = request.env['purchase.order'].search(domain)
        _logger.info("📊 PO FOUND: %s", len(orders))

        # ================= Format tanggal untuk Excel dan filename =================
        tgl_awal_str = start_dt.strftime("%d/%m/%Y") if start_dt else None
        tgl_akhir_str = end_dt.strftime("%d/%m/%Y") if end_dt else None

        file_name = self._build_filename(
            start_date=start_dt.strftime("%d-%m-%Y") if start_dt else None,
            end_date=end_dt.strftime("%d-%m-%Y") if end_dt else None
        )

        # ================= Generate XLSX =================
        xlsx_data = orders.print_xlsx_report(
            start_date=tgl_awal_str,
            end_date=tgl_akhir_str
        )

        # ================= Return File =================
        return request.make_response(
            xlsx_data,
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(file_name)),
            ]
        )
