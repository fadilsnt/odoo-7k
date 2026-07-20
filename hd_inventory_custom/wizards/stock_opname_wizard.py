from odoo import models, fields, api, _
import base64
from io import BytesIO
import xlsxwriter
from datetime import date, time, datetime, timedelta
from dateutil.relativedelta import relativedelta
import pytz

DAYS = {
    0: "SENIN",
    1: "SELASA",
    2: "RABU",
    3: "KAMIS",
    4: "JUMAT",
    5: "SABTU",
    6: "MINGGU",
}

MONTHS = {
    1: "JANUARI",
    2: "FEBRUARI",
    3: "MARET",
    4: "APRIL",
    5: "MEI",
    6: "JUNI",
    7: "JULI",
    8: "AGUSTUS",
    9: "SEPTEMBER",
    10: "OKTOBER",
    11: "NOVEMBER",
    12: "DESEMBER",
}

class StockOpnameWizard(models.TransientModel):
    _name = 'stock.opname.wizard'
    _description = 'Laporan Opname'

    warehouse_id = fields.Many2one('stock.warehouse', string='Gudang', required=True)
    category_ids = fields.Many2many('product.category', string='Kategori Produk', required=True)
    as_of_date  = fields.Date('Tanggal', required=True, default=fields.Date.today())
    file = fields.Binary('File')

    def button_print(self):
        self.ensure_one()

        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        #################################################################################
        center_title = workbook.add_format({'bold': 1, 'valign':'vcenter', 'align':'center'})
        center_title.set_font_size('16')
        #################################################################################
        left_title_sub = workbook.add_format({'valign':'vleft', 'align':'left'})
        left_title_sub.set_font_size('13')
        #################################################################################
        header_title = workbook.add_format({'bold': 1, 'valign':'vcenter', 'align':'left'})
        header_title.set_font_size('13')
        #################################################################################
        header_table = workbook.add_format({'bold': 1, 'valign':'vcenter', 'align':'center'})
        header_table.set_font_size('13')
        header_table.set_bg_color('#dad9d5')
        header_table.set_border()
        #################################################################################
        content_left_format = workbook.add_format({'valign':'vcenter', 'align':'left'})
        content_left_format.set_font_size('12')
        content_left_format.set_border()
        #################################################################################
        content_center_format = workbook.add_format({'valign':'vcenter', 'align':'center'})
        content_center_format.set_font_size('12')
        content_center_format.set_border()
        #################################################################################
        content_numb_format = workbook.add_format({'valign':'vcenter', 'align':'right'})
        content_numb_format.set_font_size('12')
        content_numb_format.set_border()
        #################################################################################
        sign_center_format = workbook.add_format({'valign':'vcenter', 'align':'center'})
        sign_center_format.set_font_size('12')
        #################################################################################
        sign_bottom_format = workbook.add_format({'valign':'vbottom', 'align':'center'})
        sign_bottom_format.set_font_size('12')
        
        worksheet1 = workbook.add_worksheet('All')
        worksheet1.set_column('A:A', 10)
        worksheet1.set_column('B:B', 15)
        worksheet1.set_column('C:C', 15)
        worksheet1.set_column('D:D', 15)
        worksheet1.set_column('E:E', 15)
        worksheet1.set_column('F:F', 15)
        worksheet1.set_column('G:G', 15)
        worksheet1.set_column('H:H', 15)

        worksheet1.merge_range('A1:H1', 'STOK OPNAME ' + self.warehouse_id.name.upper(), center_title)
        date = fields.Date.to_date(self.as_of_date)
        formatted_date = (
            f"{DAYS[date.weekday()]}, {date.day:02d} {MONTHS[date.month]} {date.year}"
        )
        worksheet1.merge_range('A2:H2', 'TANGGAL : ' + formatted_date.upper(), left_title_sub)

        tz = pytz.timezone("Asia/Jakarta")
        before_local = tz.localize(datetime.combine(self.as_of_date - timedelta(days=1), time.max))
        current_local = tz.localize(datetime.combine(self.as_of_date, time.max))
        before_date = before_local.astimezone(pytz.UTC).replace(tzinfo=None)
        current_date = current_local.astimezone(pytz.UTC).replace(tzinfo=None)

        start_local = tz.localize(datetime.combine(self.as_of_date, time.min))
        end_local = tz.localize(datetime.combine(self.as_of_date, time.max))
        start_date = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        end_date = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

        i = 3
        for category in self.category_ids:
            self._cr.execute(
                """
                    SELECT pt.id FROM product_template pt
                    WHERE pt.type = 'consu' AND pt.categ_id = %s AND pt.active=true
                    ORDER BY pt.name asc
                """, (category.id,))
            product_ids = self.env['product.template'].browse([r[0] for r in self._cr.fetchall()])

            sum_before_qty = sum(sum(vr.with_context(warehouse_id=self.warehouse_id.id, to_date=before_date).qty_available for vr in product.product_variant_ids) or 0.0 for product in product_ids) or 0.0
            sum_current_qty = sum(sum(vr.with_context(warehouse_id=self.warehouse_id.id, to_date=before_date).qty_available for vr in product.product_variant_ids) or 0.0 for product in product_ids) or 0.0
            sum_diff_qty = sum_current_qty - sum_before_qty
            if sum_before_qty != 0 or sum_current_qty != 0:
                worksheet1.merge_range(i, 0, i, 7, '' + category.name.upper(), header_title)
                i += 1
                worksheet1.write(i, 0, 'NO', header_table)
                worksheet1.merge_range(i, 1, i, 2, 'NAMA BARANG', header_table)
                worksheet1.write(i, 3, 'STOK AWAL', header_table)
                worksheet1.write(i, 4, 'OPNAME', header_table)
                worksheet1.write(i, 5, 'SELISIH', header_table)
                worksheet1.merge_range(i, 6, i, 7, 'KETERANGAN', header_table)
                i += 1
                product_number = 1

                for product in product_ids:
                    
                    first_variant = 1
                    for variant in product.product_variant_ids:
                        before_qty = variant.with_context(warehouse_id=self.warehouse_id.id, to_date=before_date).qty_available
                        current_qty = variant.with_context(warehouse_id=self.warehouse_id.id, to_date=current_date).qty_available
                        diff_qty = current_qty - before_qty
                        diff_notes = ''
                        if diff_qty != 0:
                            self._cr.execute("""
                                SELECT sm.id
                                FROM stock_move sm
                                    JOIN stock_location src ON src.id = sm.location_id
                                    JOIN stock_location dst ON dst.id = sm.location_dest_id
                                WHERE
                                    (src.usage = 'inventory' OR dst.usage = 'inventory') AND (src.warehouse_id = %s OR dst.warehouse_id = %s)
                                    AND sm.product_id = %s AND sm.date BETWEEN %s AND %s AND sm.state = 'done'
                                ORDER BY sm.date desc
                            """, (self.warehouse_id.id, self.warehouse_id.id, variant.id, start_date, end_date, ))
                            move_ids = self.env['stock.move'].sudo().browse([r[0] for r in self._cr.fetchall()])
                            if move_ids:
                                diff_notes = move_ids[0].notes or move_ids[0].reference
                        
                        if before_qty != 0 or current_qty != 0:
                            worksheet1.write(i, 0, product_number if first_variant == 1 else '', content_center_format)
                            worksheet1.merge_range(i, 1, i, 2, variant.display_name, content_left_format)
                            worksheet1.write(i, 3, before_qty if before_qty else '-', content_numb_format)
                            worksheet1.write(i, 4, current_qty if current_qty else '-', content_numb_format)
                            worksheet1.write(i, 5, diff_qty if diff_qty else '-', content_numb_format)
                            worksheet1.merge_range(i, 6, i, 7, diff_notes, content_left_format)
                            i += 1
                            first_variant += 1
                    
                    if first_variant > 1:
                        product_number += 1

                i += 2
        
        i += 1
        worksheet1.merge_range(i, 0, i, 1, 'ADM. PRODUKSI', sign_center_format)
        worksheet1.merge_range(i, 2, i, 3, 'PA. PACKING', sign_center_format)
        worksheet1.merge_range(i, 4, i, 5, 'KA. PRODUKSI', sign_center_format)
        worksheet1.merge_range(i, 6, i, 7, 'KA. PABRIK', sign_center_format)
        i += 1
        worksheet1.merge_range(i, 0, i+5, 1, '(                                            )', sign_bottom_format)
        worksheet1.merge_range(i, 2, i+5, 3, '(                                            )', sign_bottom_format)
        worksheet1.merge_range(i, 4, i+5, 5, '(                                            )', sign_bottom_format)
        worksheet1.merge_range(i, 6, i+5, 7, '(                                            )', sign_bottom_format)
        
        workbook.close()
        file=base64.encodebytes(fp.getvalue())
        self.write({'file':file})
        fp.close()
        
        return{
            'type' : 'ir.actions.act_url',
            'url': 'web/content/?model=stock.opname.wizard&field=file&download=true&id=%s&filename=Laporan Opname.xlsx'%(self.id),
            'target': 'new',
        }




