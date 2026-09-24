from odoo import models, fields, api, _
import base64
from io import BytesIO
import xlsxwriter
from datetime import date, time, datetime, timedelta
from dateutil.relativedelta import relativedelta
import pytz
from itertools import groupby
from collections import defaultdict
import re
import json
import logging

_logger = logging.getLogger(__name__)

ALLOWED_PRODUCT_CATEGORIES = ['EXPORT', 'LOKAL', 'FUEL']

class PackingSummaryWizard(models.TransientModel):
    _name = 'packing.summary.wizard'
    _description = 'Laporan Rekap Packing'

    warehouse_id = fields.Many2many(comodel_name='stock.warehouse', string="Warehouse")
    start_date = fields.Date(string="Date", required=True, default=lambda self: date.today().replace(day=1))
    end_date = fields.Date(string="End Date", required=True, default=lambda self: (date.today().replace(day=1) + relativedelta(months=1, days=-1)))
    is_all_warehouse = fields.Boolean(string="Is All Warehouse", default=False)
    file = fields.Binary('File')

    def _get_data_report(self, start_date, end_date, warehouse_ids):
        warehouse_filter = ""

        params = {
            'start_date': start_date,
            'end_date': end_date,
            'allowed_categories': list(ALLOWED_PRODUCT_CATEGORIES),
        }

        if warehouse_ids:
            warehouse_filter = "AND sw.id IN %(warehouse_ids)s"
            params['warehouse_ids'] = tuple(warehouse_ids)

        query = f"""
            WITH base_move AS (
                SELECT
                    sw.name AS warehouse,
                    sml.oven_number AS oven,
                    sml.production_date AS production_date,
                    sml.product_id,
                    SUM(sml.quantity) AS qty,
                    MAX(COALESCE(sm.tonase_asli, 0)) AS tonase_asli,
                    sml.product_uom_id

                FROM stock_move_line sml
                    JOIN stock_move sm ON sml.move_id = sm.id
                    JOIN stock_picking sp ON sm.picking_id = sp.id
                    JOIN stock_location sl ON sl.id = sml.location_dest_id
                    JOIN stock_warehouse sw ON (sl.id = sw.view_location_id OR sl.parent_path LIKE '%%/' || sw.view_location_id || '/%%')

                WHERE
                    sp.scheduled_date::date BETWEEN %(start_date)s AND %(end_date)s
                    AND sp.state IN ('confirmed','assigned','done')
                    AND sm.repack_line_id IS NULL
                    AND sm.repack_output_id IS NULL
                    {warehouse_filter}

                GROUP BY
                    sw.name,
                    sml.oven_number,
                    sml.production_date,
                    sml.product_id,
                    sml.product_uom_id
            ),

            base_data AS (
                SELECT
                    bm.warehouse,
                    bm.oven,
                    bm.production_date,
                    bm.product_id,
                    pt.name->>'id_ID' AS product,
                    pt.is_cl AS is_cl,
                    pc.name AS product_category,
                    uu.name->>'id_ID' AS uom_category,
                    COALESCE(uu.weight_per_uom_category, 0) AS weight_per_uom_category,
                    MAX(COALESCE(pav.weight_per_product_attribute, 0)) AS weight_per_product_attribute,
                    MAX(CASE WHEN pa.name->>'id_ID' = 'Grade' THEN pav.name->>'id_ID' END) AS classification,
                    bm.qty,
                    bm.tonase_asli

                FROM base_move bm
                    JOIN product_product pp ON bm.product_id = pp.id
                    JOIN product_template pt ON pp.product_tmpl_id = pt.id
                    LEFT JOIN product_category pc ON pt.categ_id = pc.id
                    LEFT JOIN uom_uom uu ON uu.id = bm.product_uom_id
                    LEFT JOIN product_variant_combination pvc ON pvc.product_product_id = pp.id
                    LEFT JOIN product_template_attribute_value ptav ON ptav.id = pvc.product_template_attribute_value_id
                    LEFT JOIN product_attribute pa ON pa.id = ptav.attribute_id
                    LEFT JOIN product_attribute_value pav ON pav.id = ptav.product_attribute_value_id

                WHERE pc.name = ANY(%(allowed_categories)s)

                GROUP BY
                    bm.warehouse,
                    bm.oven,
                    bm.production_date,
                    bm.product_id,
                    pt.name->>'id_ID',
                    pt.is_cl,
                    pc.name,
                    uu.name->>'id_ID',
                    uu.weight_per_uom_category,
                    bm.qty,
                    bm.tonase_asli
            ),

            oven_unique AS (
                SELECT DISTINCT
                    warehouse,
                    oven,
                    production_date
                FROM base_data
                WHERE
                    oven IS NOT NULL AND production_date IS NOT NULL
            ),

            warehouse_oven_total AS (
                SELECT
                    warehouse,
                    COUNT(*) AS total_oven

                FROM oven_unique
                GROUP BY
                    warehouse
            ),

            report_data AS (
                SELECT
                    warehouse,
                    COALESCE(classification, 'FUEL') AS grade,
                    weight_per_product_attribute,
                    SUM(qty) AS qty,
                    MAX(COALESCE(tonase_asli, 0)) AS tonase_asli

                FROM base_data

                GROUP BY
                    warehouse,
                    COALESCE(classification,'FUEL'),
                    weight_per_product_attribute
            ),

            final_data AS (
                SELECT
                    rd.warehouse,
                    rd.grade,
                    rd.weight_per_product_attribute,
                    rd.qty,
                    rd.tonase_asli,
                    COALESCE(wot.total_oven, 0) AS total_oven

                FROM report_data rd
                    LEFT JOIN warehouse_oven_total wot ON wot.warehouse = rd.warehouse
            )

            SELECT
                warehouse,
                grade,
                weight_per_product_attribute,
                qty,
                tonase_asli,
                total_oven

            FROM final_data

            ORDER BY
                warehouse,
                grade,
                weight_per_product_attribute
        """
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        if not rows:
            _logger.info("Query mengembalikan hasil kosong.")
            return {}

        result = {}
        for row in rows:
            warehouse = row['warehouse']
            grade = row['grade']

            warehouse_data = result.setdefault(warehouse, {
                'total_oven': row['total_oven'],
                'grades': {},
            })

            grade_data = warehouse_data['grades'].setdefault(grade, {'items': []})
            grade_data['items'].append({
                'weight_per_product_attribute': row['weight_per_product_attribute'],
                'qty': row['qty'],
                'tonase_asli': row['tonase_asli'],
            })

        try:
            pretty_json = json.dumps(result, indent=2, ensure_ascii=False, default=str)
            _logger.debug("Isi Report Data:\n%s", pretty_json)
        except Exception as e:
            _logger.error("Gagal membuat JSON report: %s", e)

        return result
    
    def format_date_range(self, start_date, end_date):
        bulan = [
            "JANUARI", "FEBRUARI", "MARET", "APRIL",
            "MEI", "JUNI", "JULI", "AGUSTUS",
            "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"
        ]

        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)

        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)

        if start_date.year == end_date.year:
            if start_date.month == end_date.month:
                return (
                    f"{start_date.day:02d} - "
                    f"{end_date.day:02d} {bulan[end_date.month - 1]} "
                    f"{end_date.year}"
                )

            return (
                f"{start_date.day:02d} {bulan[start_date.month - 1]} - "
                f"{end_date.day:02d} {bulan[end_date.month - 1]} "
                f"{end_date.year}"
            )

        return (
            f"{start_date.day:02d} {bulan[start_date.month - 1]} "
            f"{start_date.year} - "
            f"{end_date.day:02d} {bulan[end_date.month - 1]} "
            f"{end_date.year}"
        )

    def button_print(self):
        self.ensure_one()

        warehouse_ids = None
        if self.warehouse_id:
            warehouse_ids = self.warehouse_id.ids
        else:
            warehouse_ids = self.env['stock.warehouse'].search([]).ids
        
        data_report = self._get_data_report(self.start_date, self.end_date, warehouse_ids if warehouse_ids else None)

        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        #################################################################################
        title_center = workbook.add_format({'bold': 1, 'valign':'vcenter', 'align':'center'})
        title_center.set_font_size('14')
        #################################################################################
        header_table = workbook.add_format({'bold': 1, 'valign':'vcenter', 'align':'center'})
        header_table.set_font_size('12')
        header_table.set_text_wrap()
        header_table.set_border()
        #################################################################################
        content_left = workbook.add_format({'valign':'vcenter', 'align':'left'})
        content_left.set_font_size('12')
        content_left.set_border()
        #################################################################################
        content_center = workbook.add_format({'valign':'vcenter', 'align':'center'})
        content_center.set_font_size('12')
        content_center.set_border()
        #################################################################################
        number_center = workbook.add_format({'valign':'vcenter', 'align':'center', 'num_format':'#,##0.0'})
        number_center.set_font_size('12')
        number_center.set_border()
        #################################################################################
        number_right = workbook.add_format({'valign':'vcenter', 'align':'right', 'num_format':'#,##0.0'})
        number_right.set_font_size('12')
        number_right.set_border()
        #################################################################################
        integer_right = workbook.add_format({'valign':'vcenter', 'align':'right', 'num_format':'#,##0'})
        integer_right.set_font_size('12')
        integer_right.set_border()
        #################################################################################
        footer_center = workbook.add_format({'bold': 1, 'valign':'vcenter', 'align':'center'})
        footer_center.set_font_size('12')
        footer_center.set_border()
        #################################################################################
        number_center_bold = workbook.add_format({'bold': 1, 'valign':'vcenter', 'align':'center', 'num_format':'#,##0.0'})
        number_center_bold.set_font_size('12')
        number_center_bold.set_border()
        #################################################################################
        number_right_bold = workbook.add_format({'bold': 1, 'valign':'vcenter', 'align':'right', 'num_format':'#,##0.0'})
        number_right_bold.set_font_size('12')
        number_right_bold.set_border()
        #################################################################################
        integer_right_bold = workbook.add_format({'bold': 1, 'valign':'vcenter', 'align':'right', 'num_format':'#,##0'})
        integer_right_bold.set_font_size('12')
        integer_right_bold.set_border()

        worksheet1 = workbook.add_worksheet('Data')
        worksheet1.set_column('A:A', 15)
        worksheet1.set_column('B:B', 15)
        worksheet1.set_column('C:C', 15)
        worksheet1.set_column('D:D', 15)
        worksheet1.set_column('E:E', 15)
        worksheet1.set_column('F:F', 15)
        worksheet1.set_column('G:G', 15)
        worksheet1.set_column('H:H', 15)
        worksheet1.set_column('I:I', 15)
        worksheet1.set_column('J:J', 15)
        worksheet1.set_column('K:K', 15)
        worksheet1.set_column('L:L', 15)
        worksheet1.set_column('M:M', 15)

        worksheet1.merge_range('A2:M2', 'REKAP HASIL PACKING BARANG JADI', title_center)
        worksheet1.merge_range('A3:M3', 'PERIODE '  + '(' + str(self.format_date_range(self.start_date, self.end_date)) + ')', title_center)

        i = 4
        worksheet1.merge_range(i, 0, i+3, 0, 'PABRIK', header_table)
        worksheet1.merge_range(i, 1, i+3, 1, 'GRADE', header_table)
        worksheet1.merge_range(i, 2, i+3, 2, 'HASIL PACKING', header_table)
        worksheet1.merge_range(i, 3, i+3, 3, 'RATA-RATA BOX/KRG PER OVEN', header_table)
        worksheet1.merge_range(i, 4, i, 7, 'BERAT MENURUT  PEB', header_table)
        worksheet1.merge_range(i+1, 4, i+3, 4, 'TONASE PEB (KG)', header_table)
        worksheet1.merge_range(i+1, 5, i+3, 5, 'TONASE PACKING (KG)', header_table)
        worksheet1.merge_range(i+1, 6, i+3, 6, 'PERSENTASE (%) TOTAL PACKING', header_table)
        worksheet1.merge_range(i+1, 7, i+3, 7, 'RATA-RATA PER OVEN (KG)', header_table)
        worksheet1.merge_range(i, 8, i, 11, 'BERAT TONASE ASLI', header_table)
        worksheet1.merge_range(i+1, 8, i+3, 8, 'TONASE ASLI (KG)', header_table)
        worksheet1.merge_range(i+1, 9, i+3, 9, 'TONASE PACKING (KG)', header_table)
        worksheet1.merge_range(i+1, 10, i+3, 10, 'PERSENTASE (%) TOTAL PACKING', header_table)
        worksheet1.merge_range(i+1, 11, i+3, 11, 'RATA-RATA PER OVEN (KG)', header_table)
        worksheet1.merge_range(i, 12, i+3, 12, 'JUMLAH OVEN YG DIBONGKAR', header_table)
        i += 4

        gt_quantity = 0
        gt_oven = 0
        gt_packing = 0
        gt_tonase_packing = 0

        for wh_name, wh_data in data_report.items():
            total_oven = wh_data.get('total_oven', 0)
            gt_oven += total_oven
            grades = wh_data.get("grades", {})

            wh_rows = sum(len(g.get("items", [])) for g in grades.values())
            if wh_rows == 0:
                continue
            
            wh_quantity = sum(
                it.get('qty', 0)
                for g in grades.values()
                for it in g.get("items", [])
            )
            gt_quantity += wh_quantity
            wh_packing = sum(
                it.get('qty', 0) * it.get('weight_per_product_attribute', 0)
                for g in grades.values()
                for it in g.get("items", [])
            )
            gt_packing += wh_packing
            wh_tonase_packing = sum(
                it.get('qty', 0) * it.get('tonase_asli', 0)
                for g in grades.values()
                for it in g.get("items", [])
            )
            gt_tonase_packing += wh_tonase_packing
            wh_avg_quantity = wh_quantity / total_oven if total_oven else 0
            wh_percent_packing = 0
            wh_avg_oven = 0
            wh_percent_tonase_packing = 0
            wh_avg_tonase_oven = 0
            
            if wh_rows > 1:
                worksheet1.merge_range(i, 0, i + wh_rows - 1, 0, wh_name, content_center)
            else:
                worksheet1.write(i, 0, wh_name, content_center)

            for grade_name, grade_data in grades.items():
                items = grade_data.get("items", [])
                if not items:
                    continue

                if len(items) > 1:
                    worksheet1.merge_range(i, 1, i + len(items) - 1, 1, grade_name, content_center)
                else:
                    worksheet1.write(i, 1, grade_name, content_center)

                for item in items:
                    quantity = item.get('qty', 0)
                    weight = item.get('weight_per_product_attribute', 0)
                    total_packing = quantity * weight

                    avg_quantity = quantity / total_oven if total_oven else 0
                    percent_packing = (total_packing / wh_packing * 100) if wh_packing else 0
                    wh_percent_packing += percent_packing
                    avg_oven = total_packing / total_oven if total_oven else 0
                    wh_avg_oven += avg_oven
                    tonase_asli = item.get('tonase_asli', 0)
                    tonase_packing = quantity * tonase_asli
                    percent_tonase_packing = (tonase_packing / wh_tonase_packing * 100) if wh_tonase_packing else 0
                    wh_percent_tonase_packing += percent_tonase_packing
                    avg_tonase_oven = tonase_packing / total_oven if total_oven else 0
                    wh_avg_tonase_oven += avg_tonase_oven

                    worksheet1.write(i, 2, quantity, number_right)
                    worksheet1.write(i, 3, avg_quantity, number_right)
                    worksheet1.write(i, 4, weight, number_center)
                    worksheet1.write(i, 5, total_packing, number_right)
                    worksheet1.write(i, 6, percent_packing, number_center)
                    worksheet1.write(i, 7, avg_oven, number_right)
                    worksheet1.write(i, 8, tonase_asli, number_center)
                    worksheet1.write(i, 9, tonase_packing, number_right)
                    worksheet1.write(i, 10, percent_tonase_packing, number_center)
                    worksheet1.write(i, 11, avg_tonase_oven, number_right)
                    worksheet1.write(i, 12, '', number_right)
                    i += 1
            
            worksheet1.merge_range(i, 0, i, 1, 'TOTAL', footer_center)
            worksheet1.write(i, 2, wh_quantity, number_right_bold)
            worksheet1.write(i, 3, wh_avg_quantity, number_right_bold)
            worksheet1.write(i, 5, wh_packing, number_right_bold)
            worksheet1.write(i, 6, wh_percent_packing, number_center_bold)
            worksheet1.write(i, 7, wh_avg_oven, number_right_bold)
            worksheet1.write(i, 9, wh_tonase_packing, number_right_bold)
            worksheet1.write(i, 10, wh_percent_tonase_packing, number_center_bold)
            worksheet1.write(i, 11, wh_avg_tonase_oven, number_right_bold)
            worksheet1.write(i, 12, total_oven, number_right_bold)
            i += 1
        
        wh_avg_quantity = gt_quantity / gt_oven if gt_oven else 0
        wh_avg_packing = gt_packing / gt_oven if gt_oven else 0
        wh_avg_tonase_packing = gt_tonase_packing / gt_oven if gt_oven else 0

        worksheet1.merge_range(i, 0, i, 1, 'TOTAL SELURUH', footer_center)
        worksheet1.write(i, 2, gt_quantity, number_right_bold)
        worksheet1.write(i, 3, wh_avg_quantity, number_right_bold)
        worksheet1.write(i, 5, gt_packing, number_right_bold)
        worksheet1.write(i, 7, wh_avg_packing, number_right_bold)
        worksheet1.write(i, 9, gt_tonase_packing, number_right_bold)
        worksheet1.write(i, 11, wh_avg_tonase_packing, number_right_bold)
        worksheet1.write(i, 12, gt_oven, number_right_bold)

        workbook.close()
        file=base64.encodebytes(fp.getvalue())
        self.write({'file':file})
        fp.close()
        
        return{
            'type' : 'ir.actions.act_url',
            'url': 'web/content/?model=packing.summary.wizard&field=file&download=true&id=%s&filename=Laporan Rekap Packing.xlsx'%(self.id),
            'target': 'new',
        }
