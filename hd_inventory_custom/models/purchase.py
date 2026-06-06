import logging
from odoo import models, fields, api, _
import io
from collections import defaultdict
import xlsxwriter
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    btb_number = fields.Char(string="No. BTB", readonly=True, copy=False)
    vendor_invoice_date = fields.Date(string="Tanggal Invoice Vendor")

    def _prepare_picking(self):
        _logger.info('_prepare_picking executed')
        if not self.group_id:
            self.group_id = self.group_id.create(self._prepare_group_vals())
        if not self.partner_id.property_stock_supplier.id:
            raise UserError(_("You must set a Vendor Location for this partner %s", self.partner_id.name))
        return {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'user_id': False,
            'date': self.date_order,
            'origin': self.name,
            'location_dest_id': self._get_destination_location(),
            'location_id': self.partner_id.property_stock_supplier.id,
            'company_id': self.company_id.id,
            'state': 'draft',
            'partner_ref': self.partner_ref
        }    

    def action_print_btb(self):
        self.ensure_one()
        return self.env.ref('hd_inventory_custom.action_report_bukti_terima_barang').report_action(self)    

    def print_xlsx_report(self, start_date=None, end_date=None):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)

        # ================= FORMAT =================
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        header_fmt = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 10})
        cell_fmt = workbook.add_format({'border': 1, 'valign': 'top'})
        right_fmt = workbook.add_format({'border': 1, 'align': 'right'})
        qty_fmt = workbook.add_format({'num_format': '#,##0','align': 'right','border': 1,})
        idr_fmt = workbook.add_format({'num_format': '[$Rp-421] #,##0.00;([$Rp-421] #,##0.00)', 'align': 'right', 'border': 1,})
        bold_fmt = workbook.add_format({'bold': True})
        border_right_fmt = workbook.add_format({'border': 0, 'right': 1})
        border_left_fmt = workbook.add_format({'border': 0, 'left': 1})
        border_top_fmt = workbook.add_format({'border': 0, 'top': 1})
        border_bottom_fmt = workbook.add_format({'border': 0, 'bottom': 1})
        border_right_top = workbook.add_format({'border': 0, 'top': 1, 'right': 1})
        border_left_top = workbook.add_format({'border': 0, 'top': 1, 'left': 1})
        border_right_bottom = workbook.add_format({'border': 0, 'bottom': 1, 'right': 1})
        border_left_bottom = workbook.add_format({'border': 0, 'bottom': 1, 'left': 1})         
        border_left_bottom_total = workbook.add_format({'border': 0, 'bottom': 1, 'left': 1, 'bold': True}) 

        # ===== SIGNATURE STYLES =====
        sign_title_fmt = workbook.add_format({'bold': True,'align': 'center','valign': 'vcenter',})
        sign_space_fmt = workbook.add_format({'align': 'center','valign': 'vcenter',})
        sign_name_fmt = workbook.add_format({'align': 'center','valign': 'top','font_size': 9,'bottom': 1,})

        # ================= AMBIL DATA =================
        data_lines = self._get_rekap_pembelian_data(start_date, end_date)
        _logger.info("Data Lines: %s", data_lines)
        tgl_awal = self.format_tanggal_id(start_date)
        tgl_akhir = self.format_tanggal_id(end_date)        

        # ================= GROUP PER SUPPLIER =================
        suppliers_data = defaultdict(list)
        for line in data_lines:
            supplier_name = line['supplier_name'] or 'UNKNOWN'
            suppliers_data[supplier_name].append(line)

        # ================= LOOP PER SUPPLIER =================
        for supplier_name, lines in suppliers_data.items():
            # Sheet name max 31 char, replace invalid chars
            sheet_name = supplier_name[:31].replace('/', '_').replace('\\', '_')
            sheet = workbook.add_worksheet(sheet_name)
            sheet.set_paper(9)  
            sheet.set_margins(top=0.5, bottom=0.5, left=0.25, right=0.25)
            sheet.fit_to_pages(1, 0)              
            sheet.hide_gridlines(2)

            # Column widths
            # ================== SET COLUMN WIDTH ==================
            sheet.set_column('A:A', 1)  
            sheet.set_column('B:B', 3)  
            sheet.set_column('C:C', 10)
            sheet.set_column('D:D', 9)
            sheet.set_column('E:E', 3)
            sheet.set_column('F:F', 25)
            sheet.set_column('G:G', 6)
            sheet.set_column('H:H', 14)
            sheet.set_column('I:I', 5)
            sheet.set_column('J:J', 11)
            sheet.set_column('K:K', 16)
            sheet.set_column('L:L', 16)
            sheet.set_column('M:M', 1)  

            # ================== GUDANG ==================
            gudang_list = sorted(set(line.get('gudang_name') for line in lines if line.get('gudang_name')))
            gudang_name = ", ".join(gudang_list) if gudang_list else "-"

            # ================== BORDER KIRI ==================
            # Kolom A = index 0 (0-based)
            for row in range(0, 6):  # baris 1–6 (header info)
                sheet.write(row, 0, '', border_left_fmt)
            sheet.write('A1', '', border_left_top)  # atas kiri

            # ================== HEADER & MERGE ==================
            sheet.merge_range('B1:L1', '', border_top_fmt)
            sheet.merge_range('B2:L2', f'REKAP PEMBELIAN', title_fmt)

            sheet.merge_range('B4:C4', 'SUPPLIER', bold_fmt)
            sheet.merge_range('D4:F4', supplier_name)

            sheet.merge_range('B5:C5', 'PERIODE', bold_fmt)


            sheet.merge_range('D5:F5', f"{tgl_awal} s/d {tgl_akhir}")
            sheet.merge_range('I4:J4', 'LOKASI PABRIK', bold_fmt)
            sheet.merge_range('K4:L4', gudang_name)

            # ================== BORDER KANAN ==================
            # Kolom L = index 11 (0-based)
            for row in range(0, 6):
                sheet.write(row, 12, '', border_right_fmt)
            sheet.write('M1', '', border_right_top)  # atas kanan

            # ================= TABLE HEADER =================
            row = 5  # row 5 (0-based)
            # Border kiri & kanan baris header
            sheet.write(row, 1, '', border_left_fmt)    # B5
            sheet.write(row, 12, '', border_right_fmt)  # K5

            # Header
            sheet.write(row, 1, 'NO', header_fmt)                     # B5
            sheet.merge_range(row, 2, row, 3, 'NO. BTB', header_fmt)  # C5:D5
            sheet.merge_range(row, 4, row, 5, 'KETERANGAN BARANG', header_fmt)  # E5:F5
            sheet.write(row, 6, 'QTY', header_fmt)                    # G5
            sheet.write(row, 7, 'HARGA', header_fmt)                  # H5
            sheet.merge_range(row, 8, row, 9, 'TOTAL', header_fmt)    # I5:J5
            sheet.write(row, 10, 'PAJAK', header_fmt)           # K5
            sheet.write(row, 11, 'GRAND TOTAL', header_fmt)           # K5
            sheet.set_row(row, 22)

            # ================= TABLE DATA =================
            row += 1
            start_row_data = row
            for no, line in enumerate(lines, start=1):
                keterangan = ' '.join(line.get('keterangan_barang', '').splitlines())

                sheet.write(row, 0, '', border_left_fmt)  # B
                sheet.write(row, 1, no, cell_fmt)  # B
                sheet.merge_range(row, 2, row, 3, line.get('btb_number', ''), cell_fmt)
                sheet.merge_range(row, 4, row, 5, keterangan, cell_fmt)
                sheet.write(row, 6, line.get('qty', 0), qty_fmt)
                sheet.write(row, 7, line.get('harga', 0), idr_fmt)
                sheet.merge_range(row, 8, row, 9, line.get('total', 0), idr_fmt)
                sheet.write(row, 10, line.get('tax_amount', 0), idr_fmt)
                sheet.write(row, 11, line.get('grand_total', 0), idr_fmt)
                sheet.write(row, 12, '', border_right_fmt)

                row += 1

            end_row_data = row - 1
            sheet.merge_range(row, 1, row, 7, 'TOTAL', border_left_bottom_total)

            sheet.merge_range( row, 8, row, 9, f'=SUM(I{start_row_data+1}:I{end_row_data+1})', idr_fmt)
            sheet.write_formula( row, 10, f'=SUM(K{start_row_data+1}:K{end_row_data+1})', idr_fmt)
            sheet.write_formula( row, 11, f'=SUM(L{start_row_data+1}:L{end_row_data+1})', idr_fmt)
            
            sheet.write(row, 0, '', border_left_fmt)    # B5
            sheet.write(row, 12, '', border_right_fmt)
            

            # ================= SIGNATURE =================
            row += 1
            sheet.write(row, 0, '', border_left_fmt)    # B5
            sheet.write(row, 12, '', border_right_fmt)

            # Judul tanda tangan
            sheet.merge_range(row, 1, row, 4, 'DIBAYAR', sign_title_fmt)      # A-E
            sheet.write(row, 5, 'DIPERIKSA', sign_title_fmt)                 # F
            sheet.merge_range(row, 6, row, 8, 'DIKETAHUI', sign_title_fmt)   # G-I
            sheet.merge_range(row, 9, row, 10, 'DIBUAT', sign_title_fmt)     # J-K

            # Tinggi baris judul
            sheet.set_row(row, 22)

            # Space tanda tangan (4 baris)
            space_rows = 4
            for i in range(1, space_rows + 1):
                r = row + i
                sheet.write(r, 0, '', border_left_fmt)
                sheet.merge_range(r, 1, r, 4, '', sign_space_fmt)      # A-E
                sheet.write(r, 5, '', sign_space_fmt)                  # F
                sheet.merge_range(r, 6, r, 8, '', sign_space_fmt)      # G-I
                sheet.merge_range(r, 9, r, 10, '', sign_space_fmt)     # J-K
                sheet.write(r, 12, '', border_right_fmt)
                sheet.set_row(r, 15) 

            row = row + space_rows + 1
            sheet.write(row, 0, '', border_left_fmt)
            sheet.merge_range(row, 1, row, 4, '(...........................................)', sign_space_fmt)
            sheet.write(row, 5, '(...........................................)', sign_space_fmt)
            sheet.merge_range(row, 6, row, 8, '(...........................................)', sign_space_fmt)
            sheet.merge_range(row, 9, row, 10, '(...........................................)', sign_space_fmt)
            sheet.write(row, 12, '', border_right_fmt)

            row = row + 1
            sheet.write(row, 0, '', border_left_bottom)
            sheet.merge_range(row, 1, row, 4, 'Nama & Tanda Tangan', sign_name_fmt)
            sheet.write(row, 5, 'Nama & Tanda Tangan', sign_name_fmt)
            sheet.merge_range(row, 6, row, 8, 'Nama & Tanda Tangan', sign_name_fmt)
            sheet.merge_range(row, 9, row, 10, 'Nama & Tanda Tangan', sign_name_fmt)
            sheet.write(row, 11, '', border_bottom_fmt)
            sheet.write(row, 12, '', border_right_bottom)
            sheet.set_row(row, 22)


        workbook.close()
        output.seek(0)
        return output.read()

    def _get_rekap_pembelian_data(self, start_date=None, end_date=None):
        from datetime import datetime

        # ================= NORMALIZE DATE =================
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%d/%m/%Y").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%d/%m/%Y").date()

        query = """
            SELECT
                po.partner_id       AS supplier_id,
                rp.name             AS supplier_name,
                po.name             AS no_po,
                po.btb_number       AS btb_number,
                pol.name            AS keterangan_barang,
                pol.product_qty     AS qty,
                pol.price_unit      AS harga,
                pol.price_subtotal  AS total,
                pol.price_total     AS grand_total,
                pol.price_tax       AS tax_amount,
                wh.name             AS gudang_name
            FROM purchase_order po
            JOIN purchase_order_line pol ON pol.order_id = po.id
            LEFT JOIN res_partner rp ON rp.id = po.partner_id
            LEFT JOIN stock_picking_type pt ON pt.id = po.picking_type_id
            LEFT JOIN stock_warehouse wh ON wh.id = pt.warehouse_id
        """

        params = []

        # ================= FILTER DATE =================
        where_clauses = []
        if start_date:
            where_clauses.append("DATE(po.date_order) >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("DATE(po.date_order) <= %s")
            params.append(end_date)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        # ================= ORDER BY SUPPLIER & PO =================
        query += " ORDER BY rp.name, po.name, pol.id"

        _logger.warning("🧪 FINAL SQL PARAMS (DATE CAST): %s", params)
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()
        _logger.warning("📊 QUERY RESULT: %s", rows)

        return rows

    def format_tanggal_id(self, tgl):
        if not tgl:
            return '-'

        if isinstance(tgl, str):
            for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                try:
                    tgl = datetime.strptime(tgl, fmt)
                    break
                except ValueError:
                    continue
            else:
                return '-'  # format tidak dikenali

        bulan_id = [
            'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
            'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
        ]

        return f"{tgl.day} {bulan_id[tgl.month - 1]} {tgl.year}"
