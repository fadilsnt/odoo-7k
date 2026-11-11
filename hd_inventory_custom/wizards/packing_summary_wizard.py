from odoo import models, fields, api, _
import base64
from io import BytesIO
import xlsxwriter
from datetime import date, time, datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError, ValidationError
import pytz
from itertools import groupby
from collections import defaultdict
import re
import json
import logging

_logger = logging.getLogger(__name__)

ALLOWED_PRODUCT_CATEGORIES = ['EXPORT', 'FUEL', 'LOKAL']
MONTH_NAMES = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
    5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
    9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember',
}

_W_REG = [226,326,401,498,507,715,682,221,303,303,498,498,250,306,252,386,507,507,507,507,507,507,507,507,507,507,268,268,498,498,498,463,894,579,544,533,615,488,459,631,623,252,319,520,420,855,646,662,517,673,543,459,487,642,567,890,519,487,468,307,386,307,498,498,291,479,525,423,525,498,305,471,525,229,239,455,229,799,525,527,525,525,349,391,335,525,452,715,433,453,395,314,460,314,498]
_W_BOLD = [226,326,438,498,507,729,705,233,312,312,498,498,258,306,267,430,507,507,507,507,507,507,507,507,507,507,276,276,498,498,498,463,898,606,561,529,630,488,459,637,631,267,331,547,423,874,659,676,532,686,563,473,495,653,591,906,551,520,478,325,430,325,498,498,300,494,537,418,537,503,316,474,537,246,255,480,246,813,537,538,537,537,355,399,347,537,473,745,459,474,397,344,475,344,498]


class AutofitSheet:
    PAD_PX = 6

    def __init__(self, worksheet, font_size=16, row_height=15.75):
        self._ws = worksheet
        self._em_px = font_size * 96.0 / 72.0
        self._row_height = row_height
        self.widths = {}
        self.merges = []
        self.max_row = -1
        worksheet.set_default_row(row_height)

    def _text_px(self, text, bold):
        table = _W_BOLD if bold else _W_REG
        em = sum(table[ord(ch) - 32] if 32 <= ord(ch) <= 126 else 560 for ch in text)
        return em / 1000.0 * self._em_px

    def _width(self, value, fmt):
        if value is None or value == '':
            return 0
        bold = bool(fmt is not None and getattr(fmt, 'bold', 0))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            num_fmt = getattr(fmt, 'num_format', None) or 'General'
            sections = str(num_fmt).split(';')
            if value == 0 and len(sections) >= 3 and sections[2] == '':
                return 0
            first = sections[0]
            decimals = len(first.split('.')[1].rstrip('_)')) if '.' in first else 0
            text = f"{value:,.{decimals}f}"
        else:
            text = str(value)
        px = max(self._text_px(line, bold) for line in text.split('\n'))
        return (px + self.PAD_PX) / 7.0

    def write(self, row, col, value, fmt=None):
        self.max_row = max(self.max_row, row)
        self.widths[col] = max(self.widths.get(col, 0), self._width(value, fmt))
        return self._ws.write(row, col, value, fmt)

    def write_row(self, row, col, data, fmt=None):
        for n, value in enumerate(data):
            self.write(row, col + n, value, fmt)

    def merge_range(self, first_row, first_col, last_row, last_col, data, fmt=None):
        self.max_row = max(self.max_row, last_row)
        width = self._width(data, fmt)
        if first_col == last_col:
            self.widths[first_col] = max(self.widths.get(first_col, 0), width)
        elif width:
            self.merges.append((first_col, last_col, width))
        return self._ws.merge_range(first_row, first_col, last_row, last_col, data, fmt)

    def apply(self, min_width=3):
        widths = dict(self.widths)
        for first, last, need in sorted(self.merges, key=lambda m: m[1] - m[0]):
            cols = range(first, last + 1)
            have = sum(max(min_width, widths.get(c, 0)) for c in cols)
            if need > have:
                extra = (need - have) / len(cols)
                for c in cols:
                    widths[c] = max(min_width, widths.get(c, 0)) + extra
        for col, width in widths.items():
            self._ws.set_column(col, col, round(max(min_width, min(width, 255)), 2))
        for r in range(self.max_row + 1):
            self._ws.set_row(r, self._row_height)

    def __getattr__(self, name):
        return getattr(self._ws, name)

class PackingSummaryWizard(models.TransientModel):
    _name = 'packing.summary.wizard'
    _description = 'Laporan Rekap Packing'

    warehouse_id = fields.Many2many(comodel_name='stock.warehouse', string="Warehouse")
    start_date = fields.Date(string="Date", required=True, default=lambda self: date.today().replace(day=1))
    end_date = fields.Date(string="End Date", required=True, default=lambda self: (date.today().replace(day=1) + relativedelta(months=1, days=-1)))
    is_all_warehouse = fields.Boolean(string="Is All Warehouse", default=False)
    report_type = fields.Selection([
        ('main', 'Pusat'),
        ('branch', 'Cabang'),
        ('transit', 'Transit'),
    ], string="Jenis Laporan", default='main', required=True)
    grade_value_ids = fields.Many2many('product.attribute.value', 'rel_packing_summary_grade_value_ids', 'wizard_id', 'grade_value_id', string="Attribute Values", domain="[('attribute_id.name', 'in', ['grade','Grade','GRADE'])]")
    ungroup_tonase_asli = fields.Boolean(string="Ungroup Tonase Asli", default=False)
    file = fields.Binary('File')

    @staticmethod
    def _clean_box_label(label):
        label = re.sub(r'\([^)]*\)', '', label or '')
        label = re.sub(r'\s+', ' ', label).strip()
        return label or '-'

    def _get_period(self, start_date, end_date):

        if start_date.year != end_date.year:
            return "%s %s %s - %s %s %s" % (
                start_date.day, MONTH_NAMES[start_date.month], start_date.year,
                end_date.day, MONTH_NAMES[end_date.month], end_date.year,
            )
        if start_date.month != end_date.month:
            return "%s %s - %s %s %s" % (
                start_date.day, MONTH_NAMES[start_date.month],
                end_date.day, MONTH_NAMES[end_date.month], end_date.year,
            )
            
        return "%s - %s %s %s" % (
            start_date.day, end_date.day, MONTH_NAMES[end_date.month], end_date.year,
        )

    def _get_main_data_report(self, start_date, end_date, warehouse_ids):
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
                    sw.sequence AS warehouse_sequence,
                    sw.id AS warehouse_id,
                    sml.oven_number AS oven,
                    sml.production_date AS production_date,
                    sml.product_id,
                    SUM(sml.quantity) AS qty,
                    COALESCE(sm.tonase_asli, 0) AS tonase_asli,
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
                    sw.sequence,
                    sw.id,
                    sml.oven_number,
                    sml.production_date,
                    sml.product_id,
                    sml.product_uom_id,
                    COALESCE(sm.tonase_asli, 0)
            ),

            base_data AS (
                SELECT
                    bm.warehouse,
                    bm.warehouse_sequence,
                    bm.warehouse_id,
                    bm.oven,
                    bm.production_date,
                    bm.product_id,
                    pt.name->>'id_ID' AS product,
                    pt.is_cl AS is_cl,
                    pc.name AS product_category,
                    uu.name->>'id_ID' AS uom_category,
                    COALESCE(uu.weight_per_uom_category, 0) AS weight_per_uom_category,
                    CASE
                        WHEN pc.name = 'EXPORT' THEN
                            COALESCE(
                                NULLIF(NULLIF(MAX(COALESCE(pav.weight_per_product_attribute, 0)), 0), 1),
                                NULLIF(uu.weight_per_uom_category, 0),
                                0
                            )
                        ELSE
                            COALESCE(uu.weight_per_uom_category, 0)
                    END AS weight_per_product_attribute,
                    CASE
                        WHEN pc.name = 'EXPORT' THEN
                            COALESCE(
                                (ARRAY_AGG(
                                    pav.name->>'id_ID'
                                    ORDER BY pav.weight_per_product_attribute DESC
                                ) FILTER (WHERE COALESCE(pav.weight_per_product_attribute, 0) NOT IN (0, 1)))[1],
                                uu.name->>'id_ID'
                            )
                        ELSE
                            uu.name->>'id_ID'
                    END AS box_label,
                    MAX(CASE WHEN pa.name->>'id_ID' = 'Grade' THEN pav.name->>'id_ID' END) AS classification,
                    MAX(CASE WHEN pa.name->>'id_ID' = 'Grade' THEN pav.sequence END) AS grade_sequence,
                    MAX(CASE WHEN pa.name->>'id_ID' = 'Grade' THEN pav.id END) AS grade_value_id,
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
                    bm.warehouse_sequence,
                    bm.warehouse_id,
                    bm.oven,
                    bm.production_date,
                    bm.product_id,
                    bm.product_uom_id,
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
                    warehouse_sequence,
                    warehouse_id,
                    product_category,
                    CASE
                        WHEN UPPER(TRIM(product)) LIKE 'FUEL JUMBO BAG%%' THEN 'FUEL JUMBO BAG'
                        WHEN UPPER(TRIM(product)) LIKE 'SCRAP%%' THEN 'SCRAP'
                        ELSE COALESCE(classification, 'FUEL')
                    END AS grade,
                    weight_per_product_attribute,
                    box_label,
                    COALESCE(tonase_asli, 0) AS tonase_asli,
                    SUM(qty) AS qty,
                    MIN(
                        CASE
                            WHEN UPPER(TRIM(product)) LIKE 'FUEL JUMBO BAG%%' THEN NULL
                            WHEN UPPER(TRIM(product)) LIKE 'SCRAP%%' THEN NULL
                            ELSE grade_sequence
                        END
                    ) AS grade_sequence,
                    MIN(
                        CASE
                            WHEN UPPER(TRIM(product)) LIKE 'FUEL JUMBO BAG%%' THEN NULL
                            WHEN UPPER(TRIM(product)) LIKE 'SCRAP%%' THEN NULL
                            ELSE grade_value_id
                        END
                    ) AS grade_value_id

                FROM base_data

                GROUP BY
                    warehouse,
                    warehouse_sequence,
                    warehouse_id,
                    product_category,
                    CASE
                        WHEN UPPER(TRIM(product)) LIKE 'FUEL JUMBO BAG%%' THEN 'FUEL JUMBO BAG'
                        WHEN UPPER(TRIM(product)) LIKE 'SCRAP%%' THEN 'SCRAP'
                        ELSE COALESCE(classification, 'FUEL')
                    END,
                    weight_per_product_attribute,
                    box_label,
                    COALESCE(tonase_asli, 0)
            ),

            final_data AS (
                SELECT
                    rd.warehouse,
                    rd.warehouse_sequence,
                    rd.warehouse_id,
                    rd.product_category,
                    rd.grade,
                    rd.grade_sequence,
                    rd.grade_value_id,
                    rd.weight_per_product_attribute,
                    rd.box_label,
                    rd.tonase_asli,
                    rd.qty,
                    COALESCE(wot.total_oven, 0) AS total_oven

                FROM report_data rd
                    LEFT JOIN warehouse_oven_total wot ON wot.warehouse = rd.warehouse
            )

            SELECT
                warehouse,
                product_category,
                grade,
                weight_per_product_attribute,
                box_label,
                tonase_asli,
                qty,
                total_oven

            FROM final_data

            ORDER BY
                warehouse_sequence,
                warehouse_id,
                CASE WHEN grade = 'SCRAP' THEN 1 ELSE 0 END,
                array_position(%(allowed_categories)s::text[], product_category::text),
                grade_sequence ASC NULLS LAST,
                grade_value_id ASC NULLS LAST,
                CASE grade
                    WHEN 'FUEL' THEN 1
                    WHEN 'FUEL JUMBO BAG' THEN 2
                    ELSE 0
                END,
                grade,
                weight_per_product_attribute,
                tonase_asli,
                box_label
        """
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        if not rows:
            _logger.info("Query mengembalikan hasil kosong.")
            return {}

        result = {}
        item_index = {}
        ungroup = bool(self.ungroup_tonase_asli)
 
        for row in rows:
            warehouse = row['warehouse']
            grade = row['grade']
 
            warehouse_data = result.setdefault(warehouse, {
                'total_oven': row['total_oven'],
                'grades': {},
            })
            grade_data = warehouse_data['grades'].setdefault(grade, {'items': []})
 
            if not ungroup:
                key = (warehouse, grade, row['weight_per_product_attribute'])
            else:
                key = (warehouse, grade, row['weight_per_product_attribute'], row['tonase_asli'])
 
            item = item_index.get(key)
            if item is None:
                item = {
                    'weight_per_product_attribute': row['weight_per_product_attribute'],
                    'tonase_asli': 0.0 if not ungroup else row['tonase_asli'],
                    'qty': 0,
                    'boxes': {},
                }
                if not ungroup:
                    item['_tonase_values'] = set()
                item_index[key] = item
                grade_data['items'].append(item)
 
            qty = float(row['qty'] or 0)
            item['qty'] += qty
            if not ungroup:
                item['_tonase_values'].add(float(row['tonase_asli'] or 0))
 
            box_label = self._clean_box_label(row['box_label'])
            box = item['boxes'].setdefault(box_label.upper(), {'label': box_label, 'qty': 0})
            box['qty'] += qty
 
        if not ungroup:
            for warehouse_data in result.values():
                for grade_data in warehouse_data['grades'].values():
                    for item in grade_data['items']:
                        values = item.pop('_tonase_values')
                        filled = [v for v in values if v]
                        item['tonase_asli'] = sum(filled) / len(filled) if filled else 0.0

                    # grade_data['items'].sort(
                    #     key=lambda it: float(it['weight_per_product_attribute'] or 0)
                    # )
 
        try:
            pretty_json = json.dumps(result, indent=2, ensure_ascii=False, default=str)
            _logger.debug("Isi Report Data:\n%s", pretty_json)
        except Exception as e:
            _logger.error("Gagal membuat JSON report: %s", e)
 
        return result

    def _get_branch_data_report(self, start_date, end_date, warehouse_id):
        query = """
            WITH wh_loc AS (
                SELECT sl.id
                FROM stock_location sl
                    JOIN stock_warehouse sw ON (sl.id = sw.view_location_id OR sl.parent_path LIKE '%%/' || sw.view_location_id || '/%%')
                WHERE sw.id = %(warehouse_id)s
            ),

            prod AS (
                SELECT
                    pp.id AS product_id,
                    COALESCE(pt.name->>'id_ID', pt.name->>'en_US') AS name,
                    pc.name AS category,
                    MAX(COALESCE(pav.weight_per_product_attribute, 0)) AS attr_weight,
                    MAX(CASE WHEN UPPER(pa.name->>'id_ID') = 'BOX' THEN COALESCE(pav.name->>'id_ID', pav.name->>'en_US') END) AS box_attr_name,
                    MAX(CASE WHEN UPPER(pa.name->>'id_ID') = 'BOX' THEN pav.weight_per_product_attribute END) AS box_attr_weight,
                    MAX(CASE WHEN UPPER(pa.name->>'id_ID') = 'GRADE' THEN COALESCE(pav.name->>'id_ID', pav.name->>'en_US') END) AS grade,
                    MAX(CASE WHEN UPPER(pa.name->>'id_ID') = 'GRADE' THEN pav.sequence END) AS grade_sequence
                FROM product_product pp
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    JOIN product_category pc ON pc.id = pt.categ_id
                    LEFT JOIN product_variant_combination pvc ON pvc.product_product_id = pp.id
                    LEFT JOIN product_template_attribute_value ptav ON ptav.id = pvc.product_template_attribute_value_id
                    LEFT JOIN product_attribute pa ON pa.id = ptav.attribute_id
                    LEFT JOIN product_attribute_value pav ON pav.id = ptav.product_attribute_value_id
                WHERE pc.name = ANY(%(categories)s)
                GROUP BY pp.id, pt.id, pc.id
            ),

            pm AS (
                SELECT
                    sm.id AS move_id,
                    sm.product_id,
                    sm.product_uom AS uom_id,
                    sm.location_id AS src,
                    sm.location_dest_id AS dest,
                    COALESCE(NULLIF(sm.quantity, 0), sm.product_uom_qty) AS qty,
                    COALESCE(sm.tonase_asli, 0) AS tonase,
                    spt.code,
                    sp.scheduled_date::date AS day
                FROM stock_move sm
                    JOIN stock_picking sp ON sp.id = sm.picking_id
                    JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                WHERE sp.scheduled_date::date BETWEEN %(start_date)s AND %(end_date)s
                    AND sp.state IN ('confirmed', 'assigned', 'done')
                    AND sm.state <> 'cancel'
                    AND sm.repack_line_id IS NULL
                    AND sm.repack_output_id IS NULL
            ),

            mv AS (
                -- M : penerimaan, hanya data yang memiliki oven + tanggal produksi (HASIL PACKING)
                SELECT
                    'PACK' AS kind,
                    pm.product_id, sml.product_uom_id AS uom_id, pm.day, SUM(sml.quantity) AS qty, pm.tonase, sml.oven_number AS oven, sml.production_date AS prod_date
                FROM pm
                    JOIN stock_move_line sml ON sml.move_id = pm.move_id
                WHERE pm.code = 'incoming' AND sml.location_dest_id IN (SELECT id FROM wh_loc)
                    AND COALESCE(sml.oven_number, '') <> '' AND sml.production_date IS NOT NULL
                GROUP BY 1, pm.product_id, sml.product_uom_id, pm.day, pm.tonase, sml.oven_number, sml.production_date

                UNION ALL
                -- K : pengiriman
                SELECT 'K', product_id, uom_id, day, SUM(qty), 0, NULL, NULL
                FROM pm
                WHERE code = 'outgoing' AND src IN (SELECT id FROM wh_loc)
                GROUP BY product_id, uom_id, day

                UNION ALL
                -- MUTASI : transfer internal yang menembus batas warehouse
                SELECT CASE WHEN dest IN (SELECT id FROM wh_loc) THEN 'MUT_M' ELSE 'MUT_K' END, product_id, uom_id, NULL, SUM(qty), 0, NULL, NULL
                FROM pm
                WHERE code = 'internal' AND (src IN (SELECT id FROM wh_loc)) <> (dest IN (SELECT id FROM wh_loc))
                GROUP BY 1, product_id, uom_id

                UNION ALL
                -- REPACK : K = barang jadi yang direpack, M = hasil repack
                SELECT 'REP_K', srl.product_a_id, pt.uom_id, NULL, SUM(srl.qty_a), 0, NULL, NULL
                FROM stock_repack_line srl
                    JOIN stock_picking sp ON sp.id = srl.picking_id
                    JOIN product_product pp ON pp.id = srl.product_a_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE sp.location_dest_id IN (SELECT id FROM wh_loc)
                    AND sp.scheduled_date::date BETWEEN %(start_date)s AND %(end_date)s
                    AND sp.state NOT IN ('draft', 'cancel')
                GROUP BY srl.product_a_id, pt.uom_id

                UNION ALL
                SELECT 'REP_M', sro.product_b_id, pt.uom_id, NULL, SUM(sro.qty_b), 0, NULL, NULL
                FROM stock_repack_output sro
                    JOIN stock_repack_line srl ON srl.id = sro.repack_line_id
                    JOIN stock_picking sp ON sp.id = srl.picking_id
                    JOIN product_product pp ON pp.id = sro.product_b_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE sp.location_dest_id IN (SELECT id FROM wh_loc)
                    AND sp.scheduled_date::date BETWEEN %(start_date)s AND %(end_date)s
                    AND sp.state NOT IN ('draft', 'cancel')
                GROUP BY sro.product_b_id, pt.uom_id

                UNION ALL
                -- SALDO AWAL : forecasted qty sebelum tanggal awal filter
                SELECT 'OPEN', sm.product_id, sm.product_uom, NULL,
                    SUM(CASE WHEN sm.location_dest_id IN (SELECT id FROM wh_loc)
                        THEN COALESCE(NULLIF(sm.quantity, 0), sm.product_uom_qty)
                        ELSE -COALESCE(NULLIF(sm.quantity, 0), sm.product_uom_qty) END), 0, NULL, NULL
                FROM stock_move sm
                WHERE sm.state IN ('waiting', 'confirmed', 'partially_available', 'assigned', 'done')
                    AND sm.date::date < %(start_date)s
                    AND (sm.location_id IN (SELECT id FROM wh_loc)) <> (sm.location_dest_id IN (SELECT id FROM wh_loc))
                GROUP BY sm.product_id, sm.product_uom
            )

            SELECT
                prod.product_id, prod.name, prod.category, prod.grade, prod.grade_sequence,
                CASE
                    WHEN prod.category = 'EXPORT' THEN
                        COALESCE(NULLIF(NULLIF(prod.attr_weight, 0), 1), NULLIF(uu.weight_per_uom_category, 0), 0)
                    ELSE COALESCE(uu.weight_per_uom_category, 0)
                END AS weight,
                COALESCE(prod.box_attr_name, uu.name->>'id_ID', uu.name->>'en_US') AS box_name,
                COALESCE(prod.box_attr_weight, uu.weight_per_uom_category, 0) AS box_weight,
                mv.uom_id, mv.kind, mv.day, mv.qty, mv.tonase, mv.oven, mv.prod_date
            FROM mv
                JOIN prod ON prod.product_id = mv.product_id
                LEFT JOIN uom_uom uu ON uu.id = mv.uom_id
        """
        self.env.cr.execute(query, {
            'warehouse_id': warehouse_id,
            'start_date': start_date,
            'end_date': end_date,
            'categories': list(ALLOWED_PRODUCT_CATEGORIES),
        })
        days = [start_date + timedelta(days=d) for d in range((end_date - start_date).days + 1)]
        ungroup = bool(self.ungroup_tonase_asli)
        items, ovens, blocks = {}, set(), {}

        for row in self.env.cr.dictfetchall():
            kind, qty = row['kind'], float(row['qty'] or 0)
            tonase = float(row['tonase'] or 0)
            if kind == 'PACK':
                ovens.add((row['oven'], row['prod_date']))
            item = items.setdefault((row['product_id'], row['uom_id'], tonase if ungroup and kind == 'PACK' else 0), {
                'product': row, 'm': defaultdict(float), 'k': defaultdict(float), 'tonase': set(),
                'open': 0.0, 'rep_m': 0.0, 'rep_k': 0.0, 'mut_m': 0.0, 'mut_k': 0.0,
            })
            if kind == 'PACK':
                item['m'][row['day']] += qty
                if tonase:
                    item['tonase'].add(tonase)
            elif kind == 'K':
                item['k'][row['day']] += qty
            else:
                item[kind.lower()] += qty

        for item in items.values():
            p = item['product']
            title = self._clean_box_label(p['box_name']).upper()
            name = (p['name'] or '').upper()
            if name.startswith('FUEL JUMBO BAG'):
                grade = 'FUEL JUMBO BAG'
            elif name.startswith('SCRAP'):
                grade = 'SCRAP'
            elif p['grade']:
                grade = p['grade']
            elif p['category'] == 'LOKAL':
                grade = 'LOKAL KARUNG' if re.search(r'KARUNG|KRG', title) else 'LOKAL BOX'
            else:
                grade = 'FUEL'

            weight = float(p['weight'] or 0)
            tonase = sum(item['tonase']) / len(item['tonase']) if item['tonase'] else 0.0
            # TOTAL PACKING = jumlah seluruh tanggal pada baris (M); TOTAL KELUAR = jumlah seluruh (K)
            packing, total_k = sum(item['m'].values()), sum(item['k'].values())
            # SALDO AKHIR = (MUTASI M + REPACK M + PACKING) - (MUTASI K + REPACK K + KELUAR), ditambah saldo awal
            saldo = item['open'] + item['mut_m'] + item['rep_m'] + packing - item['mut_k'] - item['rep_k'] - total_k

            block = blocks.setdefault(title, {'weight': 1e9, 'grades': {}})
            block['weight'] = min(block['weight'], float(p['box_weight'] or 0) or 1e9)
            block['grades'].setdefault(grade, {
                'sequence': p['grade_sequence'] if p['grade_sequence'] is not None else 9999, 'rows': [],
            })['rows'].append({
                'name': p['name'],
                'weight': weight,
                'tonase': tonase,
                'tonase_packing': packing * tonase,
                'nums': [item['open']]
                        + [item[x].get(d, 0) for d in days for x in ('m', 'k')]
                        + [item['mut_m'], item['mut_k'], item['rep_m'], item['rep_k'], packing, total_k, saldo, packing * weight],
            })

        return {
            'days': days,
            'total_oven': len(ovens),
            'blocks': [
                {
                    'title': title,
                    'footer': 'TOTAL KARUNG' if re.search(r'KARUNG|KRG', title) else 'TOTAL BOX',
                    'grades': [
                        {'grade': grade, 'rows': sorted(g['rows'], key=lambda r: r['name'])}
                        for grade, g in sorted(b['grades'].items(), key=lambda x: (x[1]['sequence'], x[0]))
                    ],
                }
                for title, b in sorted(blocks.items(), key=lambda x: (x[1]['weight'], x[0]))
            ],
        }

    def _get_branch_packing_data_report(self, start_date, end_date, warehouse_id):
        days = [start_date + timedelta(days=d) for d in range((end_date - start_date).days + 1)]
        categories = self.env['product.category'].search([('name', '=', 'BAHAN PENOLONG')])
        paths = [categ.parent_path + '%' for categ in categories if categ.parent_path]
        if not paths:
            return {'days': days, 'rows': []}

        query = """
            WITH wh_loc AS (
                SELECT sl.id
                FROM stock_location sl
                    JOIN stock_warehouse sw ON (sl.id = sw.view_location_id OR sl.parent_path LIKE '%%/' || sw.view_location_id || '/%%')
                WHERE sw.id = %(warehouse_id)s
            ),

            prod AS (
                SELECT pp.id AS product_id, COALESCE(pt.name->>'id_ID', pt.name->>'en_US') AS name
                FROM product_product pp
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    JOIN product_category pc ON pc.id = pt.categ_id
                WHERE pc.parent_path LIKE ANY(%(paths)s)
            ),

            pm AS (
                SELECT
                    sm.product_id,
                    sm.location_id AS src,
                    sm.location_dest_id AS dest,
                    COALESCE(NULLIF(sm.quantity, 0), sm.product_uom_qty) AS qty,
                    spt.code,
                    sp.scheduled_date::date AS day
                FROM stock_move sm
                    JOIN stock_picking sp ON sp.id = sm.picking_id
                    JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                WHERE sp.scheduled_date::date BETWEEN %(start_date)s AND %(end_date)s
                    AND sp.state IN ('confirmed', 'assigned', 'done')
                    AND sm.state <> 'cancel'
                    AND sm.repack_line_id IS NULL
                    AND sm.repack_output_id IS NULL
                    AND sm.product_id IN (SELECT product_id FROM prod)
            ),

            mv AS (
                -- M : penerimaan
                SELECT 'M' AS kind, product_id, day, SUM(qty) AS qty
                FROM pm
                WHERE code = 'incoming' AND dest IN (SELECT id FROM wh_loc)
                GROUP BY product_id, day

                UNION ALL
                -- K : pengiriman
                SELECT 'K', product_id, day, SUM(qty)
                FROM pm
                WHERE code = 'outgoing' AND src IN (SELECT id FROM wh_loc)
                GROUP BY product_id, day

                UNION ALL
                -- MUTASI : transfer internal antar gudang (menembus batas warehouse wizard)
                SELECT CASE WHEN dest IN (SELECT id FROM wh_loc) THEN 'MUT_M' ELSE 'MUT_K' END, product_id, day, SUM(qty)
                FROM pm
                WHERE code = 'internal' AND (src IN (SELECT id FROM wh_loc)) <> (dest IN (SELECT id FROM wh_loc))
                GROUP BY 1, product_id, day

                UNION ALL
                -- SALDO AWAL : forecasted qty sebelum tanggal awal filter
                SELECT 'OPEN', sm.product_id, NULL,
                    SUM(CASE WHEN sm.location_dest_id IN (SELECT id FROM wh_loc)
                        THEN COALESCE(NULLIF(sm.quantity, 0), sm.product_uom_qty)
                        ELSE -COALESCE(NULLIF(sm.quantity, 0), sm.product_uom_qty) END)
                FROM stock_move sm
                WHERE sm.state IN ('waiting', 'confirmed', 'partially_available', 'assigned', 'done')
                    AND sm.date::date < %(start_date)s
                    AND sm.product_id IN (SELECT product_id FROM prod)
                    AND (sm.location_id IN (SELECT id FROM wh_loc)) <> (sm.location_dest_id IN (SELECT id FROM wh_loc))
                GROUP BY sm.product_id
            )

            SELECT prod.product_id, prod.name, mv.kind, mv.day, mv.qty
            FROM mv
                JOIN prod ON prod.product_id = mv.product_id
        """
        self.env.cr.execute(query, {
            'warehouse_id': warehouse_id,
            'start_date': start_date,
            'end_date': end_date,
            'paths': paths,
        })

        items = {}
        for row in self.env.cr.dictfetchall():
            item = items.setdefault(row['product_id'], {
                'name': row['name'], 'm': defaultdict(float), 'k': defaultdict(float),
                'open': 0.0, 'mut_m': 0.0, 'mut_k': 0.0,
            })
            qty = float(row['qty'] or 0)
            kind = row['kind']
            if kind in ('M', 'MUT_M'):
                item['m'][row['day']] += qty
            elif kind in ('K', 'MUT_K'):
                item['k'][row['day']] += qty
            if kind in ('MUT_M', 'MUT_K', 'OPEN'):
                item[kind.lower()] += qty

        rows = []
        for item in items.values():
            total_m, total_k = sum(item['m'].values()), sum(item['k'].values())
            saldo = item['open'] + total_m - total_k
            nums = [item['open']] \
                + [item[x].get(d, 0) for d in days for x in ('m', 'k')] \
                + [item['mut_m'], item['mut_k'], total_m, total_k, saldo]
            if not any(nums):
                continue
            rows.append({'name': item['name'] or '', 'nums': nums})
        rows.sort(key=lambda r: r['name'])
        return {'days': days, 'rows': rows}
    
    def _get_transit_data_report(self, start_date, end_date, warehouse_id, date_field):
        if date_field not in ('actual_date', 'scheduled_date'):
            raise ValidationError(_("Field tanggal tidak valid: %s") % date_field)
 
        tz = self.env.user.tz or 'Asia/Jakarta'
        date_expr = f"(sp.{date_field}::timestamp AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date"
 
        query = f"""
            WITH wh_loc AS (
                SELECT sl.id
                FROM stock_location sl
                    JOIN stock_warehouse sw ON (sl.id = sw.view_location_id OR sl.parent_path LIKE '%%/' || sw.view_location_id || '/%%')
                WHERE sw.id = %(warehouse_id)s
            ),
 
            prod AS (
                SELECT
                    pp.id AS product_id,
                    COALESCE(pt.name->>'id_ID', pt.name->>'en_US') AS name,
                    pc.name AS category,
                    MAX(COALESCE(pav.weight_per_product_attribute, 0)) AS attr_weight,
                    MAX(CASE WHEN UPPER(pa.name->>'id_ID') = 'BOX' THEN COALESCE(pav.name->>'id_ID', pav.name->>'en_US') END) AS box_attr_name,
                    MAX(CASE WHEN UPPER(pa.name->>'id_ID') = 'BOX' THEN pav.weight_per_product_attribute END) AS box_attr_weight,
                    MAX(CASE WHEN UPPER(pa.name->>'id_ID') = 'GRADE' THEN COALESCE(pav.name->>'id_ID', pav.name->>'en_US') END) AS grade,
                    MAX(CASE WHEN UPPER(pa.name->>'id_ID') = 'GRADE' THEN pav.sequence END) AS grade_sequence
                FROM product_product pp
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    JOIN product_category pc ON pc.id = pt.categ_id
                    LEFT JOIN product_variant_combination pvc ON pvc.product_product_id = pp.id
                    LEFT JOIN product_template_attribute_value ptav ON ptav.id = pvc.product_template_attribute_value_id
                    LEFT JOIN product_attribute pa ON pa.id = ptav.attribute_id
                    LEFT JOIN product_attribute_value pav ON pav.id = ptav.product_attribute_value_id
                WHERE pc.name = ANY(%(categories)s)
                GROUP BY pp.id, pt.id, pc.id
            ),
 
            pm AS (
                -- Transfer internal yang menembus batas warehouse transit (berbasis stock_move)
                SELECT
                    sm.product_id,
                    sm.product_uom AS uom_id,
                    sm.location_dest_id AS dest,
                    COALESCE(NULLIF(sm.quantity, 0), sm.product_uom_qty) AS qty,
                    {date_expr} AS day
                FROM stock_move sm
                    JOIN stock_picking sp ON sp.id = sm.picking_id
                    JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                WHERE spt.code = 'internal'
                    AND sp.{date_field} IS NOT NULL
                    AND sp.state NOT IN ('draft', 'cancel')
                    AND sm.state NOT IN ('draft', 'cancel')
                    AND sm.repack_line_id IS NULL
                    AND sm.repack_output_id IS NULL
                    AND sm.product_id IN (SELECT product_id FROM prod)
                    AND (sm.location_id IN (SELECT id FROM wh_loc)) <> (sm.location_dest_id IN (SELECT id FROM wh_loc))
                    AND {date_expr} BETWEEN %(start_date)s AND %(end_date)s
            ),
 
            fc AS (
                -- Forecast saldo awal: HANYA Transfer Internal (sama dengan M/K), tanggal sesuai date_field
                SELECT
                    sm.product_id,
                    sm.product_uom AS uom_id,
                    sm.location_dest_id AS dest,
                    COALESCE(NULLIF(sm.quantity, 0), sm.product_uom_qty) AS qty,
                    {date_expr} AS day
                FROM stock_move sm
                    JOIN stock_picking sp ON sp.id = sm.picking_id
                    JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                WHERE spt.code = 'internal'
                    AND sp.{date_field} IS NOT NULL
                    AND sp.state NOT IN ('draft', 'cancel')
                    AND sm.state IN ('waiting', 'confirmed', 'partially_available', 'assigned', 'done')
                    AND sm.repack_line_id IS NULL
                    AND sm.repack_output_id IS NULL
                    AND sm.product_id IN (SELECT product_id FROM prod)
                    AND (sm.location_id IN (SELECT id FROM wh_loc)) <> (sm.location_dest_id IN (SELECT id FROM wh_loc))
                    AND {date_expr} < %(start_date)s
            ),
 
            mv AS (
                SELECT
                    CASE WHEN dest IN (SELECT id FROM wh_loc) THEN 'M' ELSE 'K' END AS kind,
                    product_id, uom_id, day, SUM(qty) AS qty
                FROM pm
                GROUP BY 1, product_id, uom_id, day
 
                UNION ALL
                -- SALDO AWAL : forecast transfer internal sebelum tanggal awal filter
                SELECT 'OPEN', product_id, uom_id, NULL,
                    SUM(CASE WHEN dest IN (SELECT id FROM wh_loc) THEN qty ELSE -qty END)
                FROM fc
                GROUP BY product_id, uom_id
            )
 
            SELECT
                prod.product_id, prod.name, prod.category, prod.grade, prod.grade_sequence,
                CASE
                    WHEN prod.category = 'EXPORT' THEN
                        COALESCE(NULLIF(NULLIF(prod.attr_weight, 0), 1), NULLIF(uu.weight_per_uom_category, 0), 0)
                    ELSE COALESCE(uu.weight_per_uom_category, 0)
                END AS weight,
                COALESCE(prod.box_attr_name, uu.name->>'id_ID', uu.name->>'en_US') AS box_name,
                COALESCE(prod.box_attr_weight, uu.weight_per_uom_category, 0) AS box_weight,
                mv.uom_id, mv.kind, mv.day, mv.qty
            FROM mv
                JOIN prod ON prod.product_id = mv.product_id
                LEFT JOIN uom_uom uu ON uu.id = mv.uom_id
        """
        self.env.cr.execute(query, {
            'warehouse_id': warehouse_id,
            'start_date': start_date,
            'end_date': end_date,
            'categories': list(ALLOWED_PRODUCT_CATEGORIES),
            'tz': tz,
        })
 
        days = [start_date + timedelta(days=d) for d in range((end_date - start_date).days + 1)]
        items = {}
        for row in self.env.cr.dictfetchall():
            item = items.setdefault((row['product_id'], row['uom_id']), {
                'product': row, 'm': defaultdict(float), 'k': defaultdict(float), 'open': 0.0,
            })
            qty = float(row['qty'] or 0)
            if row['kind'] == 'M':
                item['m'][row['day']] += qty
            elif row['kind'] == 'K':
                item['k'][row['day']] += qty
            else:
                item['open'] += qty
 
        blocks = {}
        for item in items.values():
            p = item['product']
            title = self._clean_box_label(p['box_name']).upper()
            name = (p['name'] or '').upper()
            if name.startswith('FUEL JUMBO BAG'):
                grade = 'FUEL JUMBO BAG'
            elif name.startswith('SCRAP'):
                grade = 'SCRAP'
            elif p['grade']:
                grade = p['grade']
            elif p['category'] == 'LOKAL':
                grade = 'LOKAL KARUNG' if re.search(r'KARUNG|KRG', title) else 'LOKAL BOX'
            else:
                grade = 'FUEL'
 
            total_m, total_k = sum(item['m'].values()), sum(item['k'].values())
            saldo = item['open'] + total_m - total_k
            nums = [item['open']] \
                + [item[x].get(d, 0) for d in days for x in ('m', 'k')] \
                + [total_m, total_k, saldo]
            if not any(nums):
                continue
 
            block = blocks.setdefault(title, {'weight': 1e9, 'grades': {}})
            block['weight'] = min(block['weight'], float(p['box_weight'] or 0) or 1e9)
            block['grades'].setdefault(grade, {
                'sequence': p['grade_sequence'] if p['grade_sequence'] is not None else 9999, 'rows': [],
            })['rows'].append({'name': p['name'], 'weight': float(p['weight'] or 0), 'nums': nums})
 
        return {
            'days': days,
            'blocks': [
                {
                    'title': title,
                    'footer': 'TOTAL KARUNG' if re.search(r'KARUNG|KRG', title) else 'TOTAL BOX',
                    'grades': [
                        {'grade': grade, 'rows': sorted(g['rows'], key=lambda r: r['name'])}
                        for grade, g in sorted(b['grades'].items(), key=lambda x: (x[1]['sequence'], x[0]))
                    ],
                }
                for title, b in sorted(blocks.items(), key=lambda x: (x[1]['weight'], x[0]))
            ],
        }

    def button_print(self):
        self.ensure_one()

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
        decimal_center = workbook.add_format({'valign':'vcenter', 'align':'center', 'num_format':'#,##0.00'})
        decimal_center.set_font_size('12')
        decimal_center.set_border()
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

        warehouse_ids = None
        if self.is_all_warehouse:
            warehouse_ids = self.env['stock.warehouse'].search([])
        else:
            warehouse_ids = self.warehouse_id
        
        worksheet1 = workbook.add_worksheet('Data')

        if self.report_type == 'main':
            data_report = self._get_main_data_report(self.start_date, self.end_date, warehouse_ids.ids)

            selected_grades = [
                g.strip()
                for g in self.grade_value_ids.with_context(lang='id_ID').mapped('name')
                if g
            ]
            selected_grades_upper = {g.upper() for g in selected_grades}
            grade_total_label = 'TOTAL ' + ','.join(selected_grades) if selected_grades else ''

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
            worksheet1.merge_range('A3:M3', 'PERIODE '  + '(' + str(self._get_period(self.start_date, self.end_date)) + ')', title_center)

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
            branch_refs = {}

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

                    is_selected_grade = (grade_name or '').strip().upper() in selected_grades_upper

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

                        worksheet1.write(i, 2, quantity, integer_right)
                        worksheet1.write(i, 3, avg_quantity, number_right)
                        worksheet1.write(i, 4, weight, decimal_center)
                        worksheet1.write(i, 5, total_packing, integer_right)
                        worksheet1.write(i, 6, percent_packing, number_center)
                        worksheet1.write(i, 7, avg_oven, number_right)
                        worksheet1.write(i, 8, tonase_asli, decimal_center)
                        worksheet1.write(i, 9, tonase_packing, integer_right)
                        worksheet1.write(i, 10, percent_tonase_packing, number_center)
                        worksheet1.write(i, 11, avg_tonase_oven, number_right)
                        worksheet1.write(i, 12, '', number_right)

                        if is_selected_grade:
                            for box_key, b in item.get('boxes', {}).items():
                                box_ref = branch_refs.setdefault(wh_name, {}).setdefault(box_key, {
                                    'label': b['label'],
                                    'weight': 0.0,
                                    'box': 0.0,
                                    'tonase': 0.0,
                                })
                                box_ref['weight'] = max(box_ref['weight'], float(weight or 0))
                                box_ref['box'] += (b['qty'] / total_oven) if total_oven else 0
                                box_ref['tonase'] += (b['qty'] * float(tonase_asli or 0) / total_oven) if total_oven else 0

                        i += 1

                if selected_grades_upper:
                    gs_items = [
                        it
                        for g_name, g_data in grades.items()
                        if (g_name or '').strip().upper() in selected_grades_upper
                        for it in g_data.get('items', [])
                    ]
                    if gs_items:
                        gs_quantity = sum(it.get('qty', 0) for it in gs_items)
                        gs_packing = sum(
                            it.get('qty', 0) * it.get('weight_per_product_attribute', 0)
                            for it in gs_items
                        )
                        gs_tonase_packing = sum(
                            it.get('qty', 0) * it.get('tonase_asli', 0)
                            for it in gs_items
                        )

                        gs_avg_quantity = gs_quantity / total_oven if total_oven else 0
                        gs_percent_packing = (gs_packing / wh_packing * 100) if wh_packing else 0
                        gs_avg_oven = gs_packing / total_oven if total_oven else 0
                        gs_percent_tonase = (gs_tonase_packing / wh_tonase_packing * 100) if wh_tonase_packing else 0
                        gs_avg_tonase_oven = gs_tonase_packing / total_oven if total_oven else 0

                        worksheet1.merge_range(i, 0, i, 1, grade_total_label, footer_center)
                        worksheet1.write(i, 2, gs_quantity, integer_right_bold)
                        worksheet1.write(i, 3, gs_avg_quantity, number_right_bold)
                        worksheet1.write(i, 5, gs_packing, integer_right_bold)
                        worksheet1.write(i, 6, gs_percent_packing, number_center_bold)
                        worksheet1.write(i, 7, gs_avg_oven, number_right_bold)
                        worksheet1.write(i, 9, gs_tonase_packing, integer_right_bold)
                        worksheet1.write(i, 10, gs_percent_tonase, number_center_bold)
                        worksheet1.write(i, 11, gs_avg_tonase_oven, number_right_bold)
                        worksheet1.write(i, 12, '', number_right_bold)
                        i += 1
                
                worksheet1.merge_range(i, 0, i, 1, 'TOTAL', footer_center)
                worksheet1.write(i, 2, wh_quantity, integer_right_bold)
                worksheet1.write(i, 3, wh_avg_quantity, number_right_bold)
                worksheet1.write(i, 5, wh_packing, integer_right_bold)
                worksheet1.write(i, 6, wh_percent_packing, number_center_bold)
                worksheet1.write(i, 7, wh_avg_oven, number_right_bold)
                worksheet1.write(i, 9, wh_tonase_packing, integer_right_bold)
                worksheet1.write(i, 10, wh_percent_tonase_packing, number_center_bold)
                worksheet1.write(i, 11, wh_avg_tonase_oven, number_right_bold)
                worksheet1.write(i, 12, total_oven, number_right_bold)
                i += 1
            
            wh_avg_quantity = gt_quantity / gt_oven if gt_oven else 0
            wh_avg_packing = gt_packing / gt_oven if gt_oven else 0
            wh_avg_tonase_packing = gt_tonase_packing / gt_oven if gt_oven else 0

            worksheet1.merge_range(i, 0, i, 1, 'TOTAL SELURUH', footer_center)
            worksheet1.write(i, 2, gt_quantity, integer_right_bold)
            worksheet1.write(i, 3, wh_avg_quantity, number_right_bold)
            worksheet1.write(i, 5, gt_packing, integer_right_bold)
            worksheet1.write(i, 7, wh_avg_packing, number_right_bold)
            worksheet1.write(i, 9, gt_tonase_packing, integer_right_bold)
            worksheet1.write(i, 11, wh_avg_tonase_packing, number_right_bold)
            worksheet1.write(i, 12, gt_oven, number_right_bold)

            if branch_refs:
                branch_rows = []
                for wh_name, boxes in branch_refs.items():
                    box_list = sorted(boxes.values(), key=lambda b: (-b['weight'], b['label']))
                    total_box = sum(b['box'] for b in box_list)
                    total_tonase = sum(b['tonase'] for b in box_list)
                    branch_rows.append({
                        'warehouse': wh_name,
                        'boxes': box_list,
                        'total_box': total_box,
                        'total_tonase': total_tonase,
                        'total_avg': (total_tonase / total_box) if total_box else 0,
                    })
                
                branch_rows.sort(
                    key=lambda r: (r['total_box'], round(r['total_avg'], 1)),
                    reverse=True,
                )

                title_row = i + 2
                worksheet1.merge_range(title_row, 0, title_row, 12, 'URUTAN CABANG BERDASARKAN RATA-RATA PER OVEN', title_center)

                h = title_row + 2
                worksheet1.set_row(h, 20)
                worksheet1.set_row(h + 1, 20)
                worksheet1.merge_range(h, 2, h + 1, 2, 'NO.', header_table)
                worksheet1.merge_range(h, 3, h + 1, 3, 'PABRIK', header_table)
                worksheet1.merge_range(h, 4, h + 1, 4, 'UKURAN\nBOX', header_table)
                worksheet1.merge_range(h, 5, h + 1, 5, 'BOX\n' + ','.join(selected_grades), header_table)
                worksheet1.merge_range(h, 6, h + 1, 6, 'TONASE ASLI\n(KG)', header_table)
                worksheet1.merge_range(h, 7, h + 1, 7, 'RATA-RATA\nPER BOX (KG)', header_table)
                worksheet1.merge_range(h, 8, h + 1, 10, 'KETERANGAN', header_table)

                r = h + 2
                for no, br in enumerate(branch_rows, 1):
                    first_row = r
                    for b in br['boxes']:
                        avg_value = (b['tonase'] / b['box']) if b['box'] else 0
                        worksheet1.write(r, 4, b['label'], content_left)
                        worksheet1.write(r, 5, b['box'], number_right)
                        worksheet1.write(r, 6, b['tonase'], number_right)
                        worksheet1.write(r, 7, avg_value, number_right)
                        worksheet1.merge_range(r, 8, r, 10, '', content_left)
                        r += 1
                    last_detail_row = r - 1

                    if last_detail_row > first_row:
                        worksheet1.merge_range(first_row, 3, last_detail_row, 3, br['warehouse'], header_table)
                    else:
                        worksheet1.write(first_row, 3, br['warehouse'], header_table)

                    worksheet1.merge_range(r, 3, r, 4, 'TOTAL', footer_center)
                    worksheet1.write(r, 5, br['total_box'], number_right_bold)
                    worksheet1.write(r, 6, br['total_tonase'], number_right_bold)
                    worksheet1.write(r, 7, br['total_avg'], number_right_bold)
                    worksheet1.merge_range(r, 8, r, 10, '', content_left)

                    worksheet1.merge_range(first_row, 2, r, 2, no, content_center)
                    r += 1
            
        elif self.report_type == 'branch':
            FONT_SIZE = 16
            ROW_HEIGHT = 15.75

            def fmt(**kw):
                props = {'valign': 'vcenter', 'font_size': FONT_SIZE}
                props.update(kw)
                return workbook.add_format(props)

            title_center = fmt(bold=1, align='center')
            title_left = fmt(bold=1, align='left')
            header_table = fmt(bold=1, align='center', border=1)
            content_left = fmt(align='left', border=1)
            content_center = fmt(align='center', border=1)
            decimal_center = fmt(align='center', num_format='#,##0.00', border=1)
            number_right = fmt(align='right', num_format='#,##0.0', border=1)
            footer_center = fmt(bold=1, align='center', border=1)
            number_center_bold = fmt(bold=1, align='center', num_format='#,##0.0', border=1)
            number_right_bold = fmt(bold=1, align='right', num_format='#,##0.0', border=1)
            integer_right_bold = fmt(bold=1, align='right', num_format='#,##0', border=1)
            qty_right = fmt(align='right', num_format='#,##0;-#,##0;', border=1)
            qty_right_bold = fmt(bold=1, align='right', num_format='#,##0;-#,##0;', border=1)
            sum_rows = lambda rows: [sum(col) for col in zip(*[row['nums'] for row in rows])]

            for index, warehouse in enumerate(warehouse_ids.sorted(lambda w: (w.sequence, w.id))):
                data_report = self._get_branch_data_report(self.start_date, self.end_date, warehouse.id)
                days, total_oven, blocks = data_report['days'], data_report['total_oven'], data_report['blocks']

                all_rows = [row for b in blocks for g in b['grades'] for row in g['rows']]
                if not all_rows:
                    continue

                sheet_name = warehouse.name[:31]
                raw_sheet = worksheet1 if index == 0 else workbook.add_worksheet(sheet_name)
                raw_sheet.name = sheet_name
                raw_sheet.set_default_row(ROW_HEIGHT)
                raw_sheet.freeze_panes(0, 3)
                worksheet = AutofitSheet(raw_sheet, FONT_SIZE)
                
                titles = [warehouse.company_id.name.upper(), self._get_period(self.start_date, self.end_date).upper(), warehouse.name.upper(), 'BARANG JADI']
                for n, text in enumerate(titles):
                    worksheet.merge_range(n, 0, n, 5, text, title_left)

                gt_packing = sum(row['nums'][-1] for row in all_rows)
                gt_tonase = sum(row['tonase_packing'] for row in all_rows)
                n_nums = 9 + 2 * len(days)
                col_pct = 3 + n_nums
                col_tonase = col_pct + 2
                i = 4

                for block in blocks:
                    worksheet.merge_range(i, 0, i, col_pct, block['title'], title_center)
                    worksheet.merge_range(i, col_tonase, i, col_tonase + 2, 'TONASE REAL ' + block['title'], title_center)
                    i += 1

                    for col, label in enumerate(['GRADE', 'NAMA', 'KG/BOX']):
                        worksheet.merge_range(i, col, i + 1, col, label, header_table)
                    worksheet.write(i, 3, 'TANGGAL', header_table)
                    worksheet.write(i + 1, 3, 'SALDO AWAL', header_table)

                    col = 4
                    headers = [(str(d.day), ['M', 'K']) for d in days] + [
                        ('TOTAL MUTASI', ['M', 'K']), ('TOTAL REPACK', ['M', 'K']),
                        ('TOTAL PACKING', None), ('TOTAL KELUAR', None), ('SALDO AKHIR', None), ('TOTAL TONASE (KG)', None),
                    ]
                    for label, subs in headers:
                        if subs:
                            worksheet.merge_range(i, col, i, col + 1, label, header_table)
                            worksheet.write_row(i + 1, col, subs, header_table)
                            col += 2
                        else:
                            worksheet.merge_range(i, col, i + 1, col, label, header_table)
                            col += 1
                    for col, label in ((col_pct, '(%) TOTAL PACKING'), (col_tonase, 'KG/BOX'), (col_tonase + 1, 'TOTAL PACKING (KG)'), (col_tonase + 2, 'TOTAL PACKING (%)')):
                        worksheet.merge_range(i, col, i + 1, col, label, header_table)
                    i += 2

                    for g in block['grades']:
                        first_row = i
                        for row in g['rows']:
                            worksheet.write(i, 1, row['name'], content_left)
                            worksheet.write(i, 2, row['weight'], decimal_center)
                            for n, value in enumerate(row['nums']):
                                worksheet.write(i, 3 + n, value, number_right if n == n_nums - 1 else qty_right)
                            worksheet.write(i, col_tonase, row['tonase'], decimal_center)
                            worksheet.write(i, col_tonase + 1, row['tonase_packing'], number_right)
                            i += 1

                        if len(g['rows']) > 1:
                            worksheet.merge_range(first_row, 0, i - 1, 0, g['grade'], content_center)
                        else:
                            worksheet.write(first_row, 0, g['grade'], content_center)

                        worksheet.merge_range(i, 0, i, 2, 'TOTAL', footer_center)
                        for n, value in enumerate(sum_rows(g['rows'])):
                            worksheet.write(i, 3 + n, value, number_right_bold if n == n_nums - 1 else qty_right_bold)
                        g_tonase = sum(row['tonase_packing'] for row in g['rows'])
                        worksheet.write(i, col_tonase, 'TOTAL', footer_center)
                        worksheet.write(i, col_tonase + 1, g_tonase, number_right_bold)
                        worksheet.merge_range(first_row, col_pct, i, col_pct, (sum_rows(g['rows'])[-1] / gt_packing * 100) if gt_packing else 0, number_center_bold)
                        worksheet.merge_range(first_row, col_tonase + 2, i, col_tonase + 2, (g_tonase / gt_tonase * 100) if gt_tonase else 0, number_center_bold)
                        i += 1

                    rows = [row for g in block['grades'] for row in g['rows']]
                    b_tonase = sum(row['tonase_packing'] for row in rows)
                    worksheet.merge_range(i, 0, i, 2, block['footer'], footer_center)
                    for n, value in enumerate(sum_rows(rows)):
                        worksheet.write(i, 3 + n, value, number_right_bold if n == n_nums - 1 else qty_right_bold)
                    worksheet.write(i, col_pct, (sum_rows(rows)[-1] / gt_packing * 100) if gt_packing else 0, number_center_bold)
                    worksheet.write(i, col_tonase, 'TOTAL', footer_center)
                    worksheet.write(i, col_tonase + 1, b_tonase, number_right_bold)
                    worksheet.write(i, col_tonase + 2, (b_tonase / gt_tonase * 100) if gt_tonase else 0, number_center_bold)
                    i += 2

                worksheet.merge_range(i, 0, i, 2, 'TOTAL KESELURUHAN', footer_center)
                for n, value in enumerate(sum_rows(all_rows)):
                    worksheet.write(i, 3 + n, value, number_right_bold if n == n_nums - 1 else qty_right_bold)
                worksheet.write(i, col_pct, 100, number_center_bold)
                worksheet.write(i, col_tonase, 'TOTAL', footer_center)
                worksheet.write(i, col_tonase + 1, gt_tonase, number_right_bold)
                worksheet.write(i, col_tonase + 2, 100, number_center_bold)
                i += 2

                worksheet.merge_range(i, 0, i, 2, 'TOTAL BONGKAR', footer_center)
                worksheet.write(i, 3, total_oven, integer_right_bold)
                worksheet.write(i, 4, 'OVEN', footer_center)
                worksheet.merge_range(i, col_pct - 3, i, col_pct - 2, 'RATA2 TONASE PEB', footer_center)
                worksheet.write(i, col_pct - 1, (gt_packing / total_oven) if total_oven else 0, number_right_bold)
                worksheet.write(i, col_pct, 'KG', footer_center)
                worksheet.write(i, col_tonase, 'RATA2 TONASE ASLI', footer_center)
                worksheet.write(i, col_tonase + 1, (gt_tonase / total_oven) if total_oven else 0, number_right_bold)
                worksheet.write(i, col_tonase + 2, 'KG', footer_center)

                packing_data = self._get_branch_packing_data_report(self.start_date, self.end_date, warehouse.id)
                packing_rows = packing_data['rows']
                if packing_rows:
                    n_days = len(days)
                    col_last = 3 + 2 * n_days + 5
                    i += 2
                    worksheet.merge_range(i, 0, i, col_last, 'BARANG PENOLONG', title_left)
                    i += 1

                    worksheet.merge_range(i, 0, i + 1, 2, 'NAMA', header_table)
                    worksheet.write(i, 3, 'TANGGAL', header_table)
                    worksheet.write(i + 1, 3, 'SALDO AWAL', header_table)
                    col = 4
                    for label in [str(d.day) for d in days] + ['MUTASI']:
                        worksheet.merge_range(i, col, i, col + 1, label, header_table)
                        worksheet.write_row(i + 1, col, ['M', 'K'], header_table)
                        col += 2
                    for label in ('TOTAL MASUK', 'TOTAL KELUAR', 'SALDO AKHIR'):
                        worksheet.merge_range(i, col, i + 1, col, label, header_table)
                        col += 1
                    i += 2

                    for row in packing_rows:
                        worksheet.merge_range(i, 0, i, 2, row['name'], content_left)
                        for n, value in enumerate(row['nums']):
                            worksheet.write(i, 3 + n, value, qty_right)
                        i += 1

                worksheet.apply()
        
        elif self.report_type == 'transit':
            FONT_SIZE = 16
            ROW_HEIGHT = 15.75

            def fmt(**kw):
                props = {'valign': 'vcenter', 'font_size': FONT_SIZE}
                props.update(kw)
                return workbook.add_format(props)

            left_center = fmt(bold=1, align='left')
            title_center = fmt(bold=1, align='center')
            header_table = fmt(bold=1, align='center', border=1)
            content_left = fmt(align='left', border=1)
            content_center = fmt(align='center', border=1)
            decimal_center = fmt(align='center', num_format='#,##0.00', border=1)
            footer_center = fmt(bold=1, align='center', border=1)
            qty_right = fmt(align='right', num_format='#,##0;-#,##0;', border=1)
            qty_right_bold = fmt(bold=1, align='right', num_format='#,##0;-#,##0;', border=1)
            sum_rows = lambda rows: [sum(col) for col in zip(*[row['nums'] for row in rows])]

            transit_warehouses = warehouse_ids
            single = len(transit_warehouses) == 1
            used_names = set()
            sheet_count = 0

            for warehouse in transit_warehouses.sorted(lambda w: (w.sequence, w.id)):
                for suffix, date_field, in_transit in (
                    ('Stock', 'actual_date', False),
                    ('Dalam Perjalanan', 'scheduled_date', True),
                ):
                    base = re.sub(r'[\[\]:*?/\\]', '', 'Transit' if single else warehouse.name)
                    sheet_name = ('%s %s' % (base[:31 - len(suffix) - 1], suffix)).strip()
                    n = 1
                    while sheet_name.lower() in used_names:
                        n += 1
                        sheet_name = '%s %s' % (sheet_name[:28], n)
                    used_names.add(sheet_name.lower())

                    raw_sheet = worksheet1 if sheet_count == 0 else workbook.add_worksheet(sheet_name)
                    raw_sheet.name = sheet_name
                    sheet_count += 1
                    raw_sheet.set_default_row(ROW_HEIGHT)
                    raw_sheet.freeze_panes(0, 3)
                    worksheet = AutofitSheet(raw_sheet, FONT_SIZE)

                    data_report = self._get_transit_data_report(
                        self.start_date, self.end_date, warehouse.id, date_field)
                    days, blocks = data_report['days'], data_report['blocks']
                    head = 1 + 2 * len(days)
                    col_tot = 3 + head
                    col_end = col_tot + 2

                    def put(r, nums, f, worksheet=worksheet, head=head, col_tot=col_tot):
                        for n, value in enumerate(nums[:head]):
                            worksheet.write(r, 3 + n, value, f)
                        for n, value in enumerate(nums[head:]):
                            worksheet.write(r, col_tot + n, value, f)

                    titles = [
                        warehouse.company_id.name.upper(),
                        self._get_period(self.start_date, self.end_date).upper(),
                        ('DALAM PERJALANAN ' if in_transit else '') + warehouse.name.upper(),
                        'BARANG JADI',
                    ]
                    for n, text in enumerate(titles):
                        worksheet.merge_range(n, 0, n, 5, text, left_center)

                    all_rows = [row for b in blocks for g in b['grades'] for row in g['rows']]
                    i = 5
                    for block in blocks:
                        worksheet.merge_range(i, 0, i, col_end, block['title'], title_center)
                        i += 1

                        for col, label in ((0, 'GRADE'), (1, 'NAMA'), (2, 'KG/BOX')):
                            worksheet.merge_range(i, col, i + 1, col, label, header_table)
                        worksheet.write(i, 3, 'TANGGAL', header_table)
                        worksheet.write(i + 1, 3, 'SALDO AWAL', header_table)
                        col = 4
                        for d in days:
                            worksheet.merge_range(i, col, i, col + 1, str(d.day), header_table)
                            worksheet.write_row(i + 1, col, ['M', 'K'], header_table)
                            col += 2
                        for label in ('TOTAL MASUK', 'TOTAL KELUAR', 'SALDO AKHIR'):
                            worksheet.merge_range(i, col, i + 1, col, label, header_table)
                            col += 1
                        i += 2

                        for g in block['grades']:
                            first_row = i
                            for row in g['rows']:
                                worksheet.write(i, 1, row['name'], content_left)
                                worksheet.write(i, 2, row['weight'], decimal_center)
                                put(i, row['nums'], qty_right)
                                i += 1
                            if len(g['rows']) > 1:
                                worksheet.merge_range(first_row, 0, i - 1, 0, g['grade'], content_center)
                            else:
                                worksheet.write(first_row, 0, g['grade'], content_center)

                            worksheet.merge_range(i, 0, i, 2, 'TOTAL', footer_center)
                            put(i, sum_rows(g['rows']), qty_right_bold)
                            i += 1

                        rows = [row for g in block['grades'] for row in g['rows']]
                        worksheet.merge_range(i, 0, i, 2, block['footer'], footer_center)
                        put(i, sum_rows(rows), qty_right_bold)
                        i += 2

                    if all_rows:
                        worksheet.merge_range(i, 0, i, 2, 'TOTAL KESELURUHAN', footer_center)
                        put(i, sum_rows(all_rows), qty_right_bold)

                    worksheet.apply()

        workbook.close()
        file=base64.encodebytes(fp.getvalue())
        self.write({'file':file})
        fp.close()
        
        return{
            'type' : 'ir.actions.act_url',
            'url': 'web/content/?model=packing.summary.wizard&field=file&download=true&id=%s&filename=Laporan Rekap Packing (%s %s).xlsx'%(self.id, dict(self._fields["report_type"].selection).get(self.report_type), self._get_period(self.start_date, self.end_date)),
            'target': 'new',
        }