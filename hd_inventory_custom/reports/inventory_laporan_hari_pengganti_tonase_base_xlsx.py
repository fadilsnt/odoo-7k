from odoo import models
from datetime import datetime, date, timedelta
import re
import json
import logging

_logger = logging.getLogger(__name__)

def fmt_qty(val):
    s = f"{float(val):.1f}" 
    return s.rstrip("0").rstrip(".")

def format_tanggal_indonesia(dt=None):
    hari_map = {0: "SENIN", 1: "SELASA", 2: "RABU", 3: "KAMIS", 4: "JUMAT", 5: "SABTU", 6: "MINGGU"}
    bulan_map = {1: "JANUARI", 2: "FEBRUARI", 3: "MARET", 4: "APRIL", 5: "MEI", 6: "JUNI", 
                 7: "JULI", 8: "AGUSTUS", 9: "SEPTEMBER", 10: "OKTOBER", 11: "NOVEMBER", 12: "DESEMBER"}

    if not dt:
        dt = date.today()
    elif isinstance(dt, str):
        dt = datetime.strptime(dt, "%Y-%m-%d").date()

    return "{} / {} {} {}".format(hari_map[dt.weekday()], dt.day, bulan_map[dt.month], dt.year)

def _grade_sort_key(grade):
    if grade == "UNCLASSIFIED":
        return (99, "")

    m = re.match(r'^([A-Z]+)', grade)
    grade_key = m.group(1) if m else grade

    grade_order = {
        'A': 1,
        'B': 2,
        'BC': 3,
        'C': 4,
        'D': 5, 
    }

    return (grade_order.get(grade_key, 50), grade_key)

def _get_oven_key(oven, prod_date):
    if not oven:
        return "NONE"

    if prod_date:
        if isinstance(prod_date, str):
            prod_date = datetime.strptime(prod_date, "%Y-%m-%d").date()
        elif isinstance(prod_date, datetime):
            prod_date = prod_date.date()

        if isinstance(prod_date, date):
            return f"{oven} ({prod_date.strftime('%d/%m')})"

    return oven

class InventoryLaporanHariPenggantiTonase(models.AbstractModel):
    _name = 'report.hd_inventory_custom.inventory_laporan_hari_pengganti_ton'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Laporan Inventory Hari Pengganti Tonase'
    _auto = False 

    def _get_data_xlsx_report(self, report_date, warehouse_id=None):
        warehouse_filter = ""
        params = {'report_date': report_date}
        
        if warehouse_id:
            warehouse_filter = "AND sw.id = %(warehouse_id)s"
            params['warehouse_id'] = warehouse_id

        query = f"""
            WITH base_move AS (
                SELECT
                    sw.name AS warehouse,
                    sml.oven_number AS oven,
                    sml.production_date AS production_date,
                    sml.line_packing AS line_packing,
                    sml.camp_tgl_briket AS camp_tgl_briket,
                    sml.briket_tgu AS briket_tgu,
                    sml.shift_briket AS shift_briket,
                    sml.bkr AS bkr,
                    sml.pembakar_penutup AS pembakar_penutup,
                    sml.lubang_setom AS lubang_setom,
                    sml.bongkaran AS bongkaran,
                    sml.asumsi_berat_ikat AS asumsi_berat_ikat,
                    sml.product_id,
                    SUM(sml.quantity) AS qty,
                    SUM(sml.tonase_asli) AS tonase,
                    sml.product_uom_id
                FROM stock_move_line sml
                JOIN stock_move sm ON sml.move_id = sm.id
                JOIN stock_picking sp ON sm.picking_id = sp.id
                JOIN stock_location sl ON sl.id = sml.location_dest_id
                JOIN stock_warehouse sw
                    ON (sl.id = sw.view_location_id
                    OR sl.parent_path LIKE '%%/' || sw.view_location_id || '/%%')
                WHERE sp.scheduled_date::date = %(report_date)s
                AND sp.state IN ('confirmed', 'assigned', 'done')
                {warehouse_filter}
                GROUP BY 
                    sw.name,
                    sml.oven_number,
                    sml.production_date,
                    sml.line_packing,
                    sml.camp_tgl_briket,
                    sml.briket_tgu,
                    sml.shift_briket,
                    sml.bkr,
                    sml.pembakar_penutup,
                    sml.lubang_setom,
                    sml.bongkaran,
                    sml.asumsi_berat_ikat,
                    sml.product_id,
                    sml.product_uom_id
            ),

            base_data AS (
                SELECT
                    bm.warehouse,
                    bm.oven,
                    bm.production_date,
                    bm.line_packing,
                    bm.camp_tgl_briket,
                    bm.briket_tgu,
                    bm.shift_briket,
                    bm.bkr,
                    bm.pembakar_penutup,
                    bm.lubang_setom,
                    bm.bongkaran,
                    bm.asumsi_berat_ikat,                    
                    pt.name->>'id_ID' AS product,
                    pt.is_cl AS is_cl,
                    pc.name AS product_category,
                    uu.name->>'id_ID' AS uom_category,
                    COALESCE(uu.weight_per_uom_category, 0) AS weight_per_uom_category,

                    -- tambahan
                    MAX(COALESCE(pav.weight_per_product_attribute, 0)) AS weight_per_product_attribute,
                    -- tambahan

                    MAX(CASE WHEN pa.name->>'id_ID' = 'Grade' THEN pav.name->>'id_ID' END)
                        || ' (' ||
                    MAX(CASE WHEN pa.name->>'id_ID' = 'BOX' THEN pav.name->>'id_ID' END)
                        || ')' AS classification,
                    bm.qty,
                    bm.tonase
                FROM base_move bm
                JOIN product_product pp ON bm.product_id = pp.id
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                LEFT JOIN product_category pc ON pt.categ_id = pc.id
                LEFT JOIN uom_uom uu ON uu.id = bm.product_uom_id
                LEFT JOIN product_variant_combination pvc ON pvc.product_product_id = pp.id
                LEFT JOIN product_template_attribute_value ptav ON ptav.id = pvc.product_template_attribute_value_id
                LEFT JOIN product_attribute pa ON pa.id = ptav.attribute_id
                LEFT JOIN product_attribute_value pav ON pav.id = ptav.product_attribute_value_id
                GROUP BY
                    bm.warehouse,
                    bm.oven,
                    bm.production_date,
                    bm.line_packing,
                    bm.camp_tgl_briket,
                    bm.briket_tgu,
                    bm.shift_briket,
                    bm.bkr,
                    bm.pembakar_penutup,
                    bm.lubang_setom,
                    bm.bongkaran,
                    bm.asumsi_berat_ikat,                    
                    pt.name->>'id_ID',
                    pt.is_cl,
                    pc.name,
                    uu.name,
                    uu.weight_per_uom_category,
                    bm.qty,
                    bm.tonase
            ),

            oven_group AS (
                SELECT
                    warehouse,
                    oven,
                    production_date,
                    line_packing,
                    camp_tgl_briket,
                    briket_tgu,
                    shift_briket,
                    bkr,
                    pembakar_penutup,
                    lubang_setom,
                    bongkaran,
                    asumsi_berat_ikat,                    
                    classification,
                    product_category,
                    uom_category,
                    weight_per_uom_category,

                    -- Tambahkan ini
                    MAX(weight_per_product_attribute) AS weight_per_product_attribute,
                    is_cl AS is_cl,
                    -- Tambahkan ini

                    json_agg(
                        json_build_object(
                            'product', product,
                            'qty', qty,
                            'tonase', tonase,
                            'weight_per_product_attribute', weight_per_product_attribute,
                            'is_cl', is_cl
                        ) ORDER BY product
                    ) AS products,

                    SUM(qty * COALESCE(tonase, 1)) AS total_per_oven

                FROM base_data
                GROUP BY
                    warehouse,
                    oven,
                    production_date,
                    line_packing,
                    camp_tgl_briket,
                    briket_tgu,
                    shift_briket,
                    bkr,
                    pembakar_penutup,
                    lubang_setom,
                    bongkaran,
                    asumsi_berat_ikat,                    
                    classification,
                    product_category,
                    is_cl,
                    uom_category,
                    weight_per_uom_category
            ),


            total_per_grade_cte AS (
                SELECT
                    warehouse,
                    COALESCE(classification,'UNCLASSIFIED') AS classification,
                    SUM(total_per_oven) AS total_per_grade
                FROM oven_group
                GROUP BY warehouse, COALESCE(classification,'UNCLASSIFIED')
            ),

            warehouse_group AS (
                SELECT
                    og.warehouse,
                    json_agg(
                        json_build_object(
                            'oven', og.oven,
                            'production_date', og.production_date,
                            'line_packing', og.line_packing,
                            'camp_tgl_briket', og.camp_tgl_briket,
                            'briket_tgu', og.briket_tgu,
                            'shift_briket', og.shift_briket,
                            'bkr', og.bkr,
                            'pembakar_penutup', og.pembakar_penutup,
                            'lubang_setom', og.lubang_setom,
                            'bongkaran', og.bongkaran,
                            'asumsi_berat_ikat', og.asumsi_berat_ikat,                            
                            'classification', og.classification,
                            'product_category', og.product_category,
                            'uom_category', og.uom_category,
                            'weight_per_uom_category', og.weight_per_uom_category,

                            -- tambahan
                            'weight_per_product_attribute', og.weight_per_product_attribute,
                            -- tambahan

                            'products', og.products,
                            'total_per_oven', og.total_per_oven
                        )
                        ORDER BY og.oven
                    ) AS ovens,
                    json_object_agg(COALESCE(tpg.classification,'UNCLASSIFIED'), tpg.total_per_grade) AS total_per_grade
                FROM oven_group og
                LEFT JOIN total_per_grade_cte tpg ON og.warehouse = tpg.warehouse AND og.classification = tpg.classification
                GROUP BY og.warehouse
            )
            
            SELECT json_object_agg(
                warehouse,
                json_build_object(
                    'ovens', ovens,
                    'total_per_grade', total_per_grade
                )
            )
            FROM warehouse_group;
        """
        self.env.cr.execute(query, params)
        row = self.env.cr.fetchone()

        if row and row[0]:
            try:
                pretty_json = json.dumps(row[0], indent=2, ensure_ascii=False)
                _logger.info("Isi Querynya:\n%s", pretty_json)
            except Exception as e:
                _logger.error("Gagal mem-parse JSON dari query: %s", e)
                _logger.info("Raw query result: %s", row[0])
        else:
            _logger.info("Query mengembalikan hasil kosong.")

        return row[0] if row and row[0] else {}
    
    def _get_repack_data(self, report_date, warehouse_id=None):
        if isinstance(report_date, str):
            report_date = datetime.strptime(report_date, "%Y-%m-%d")

        date_from = report_date
        date_to = report_date + timedelta(days=1)

        params = {
            'date_from': date_from,
            'date_to': date_to,
        }

        _logger.warning("PARAMS: %s", params)

        warehouse_filter = ""
        if warehouse_id:
            warehouse_filter = "AND sw.id = %(warehouse_id)s"
            params['warehouse_id'] = warehouse_id

        query = f"""
            WITH bongkar AS (
                SELECT 
                    pt_a.name->>'id_ID' AS product,
                    uu.name->>'id_ID' AS uom,
                    SUM(srl.qty_a) AS qty
                FROM stock_repack_line srl
                LEFT JOIN product_product pp_a ON srl.product_a_id = pp_a.id
                LEFT JOIN product_template pt_a ON pp_a.product_tmpl_id = pt_a.id
                LEFT JOIN uom_uom uu ON pt_a.uom_id = uu.id

                LEFT JOIN stock_picking sp ON srl.picking_id = sp.id
                LEFT JOIN stock_location sl ON sp.location_dest_id = sl.id
                LEFT JOIN stock_warehouse sw
                    ON (
                        sl.id = sw.view_location_id
                        OR sl.parent_path LIKE '%%/' || sw.view_location_id || '/%%'
                    )

                WHERE 
                    sp.scheduled_date >= %(date_from)s
                    AND sp.scheduled_date < %(date_to)s
                    {warehouse_filter}

                GROUP BY pt_a.name->>'id_ID', uu.name->>'id_ID'
            ),

            menjadi AS (
                SELECT 
                    pt_b.name->>'id_ID' AS product,
                    uu.name->>'id_ID' AS uom,
                    SUM(sro.qty_b) AS qty
                FROM stock_repack_output sro
                JOIN stock_repack_line srl ON sro.repack_line_id = srl.id
                LEFT JOIN product_product pp_b ON sro.product_b_id = pp_b.id
                LEFT JOIN product_template pt_b ON pp_b.product_tmpl_id = pt_b.id
                LEFT JOIN uom_uom uu ON pt_b.uom_id = uu.id

                LEFT JOIN stock_picking sp ON srl.picking_id = sp.id
                LEFT JOIN stock_location sl ON sp.location_dest_id = sl.id
                LEFT JOIN stock_warehouse sw
                    ON (
                        sl.id = sw.view_location_id
                        OR sl.parent_path LIKE '%%/' || sw.view_location_id || '/%%'
                    )

                WHERE 
                    sp.scheduled_date >= %(date_from)s
                    AND sp.scheduled_date < %(date_to)s
                    {warehouse_filter}

                GROUP BY pt_b.name->>'id_ID', uu.name->>'id_ID'
            )

            SELECT
                'BONGKAR: ' || COALESCE(
                    (
                        SELECT string_agg(
                            b.product || ': ' || TRIM(TRAILING '.0' FROM b.qty::text) || ' ' || COALESCE(b.uom, ''),
                            ' + '
                        )
                        FROM bongkar b
                    ),
                    '-'
                ) AS bongkar,

                'MENJADI: ' || COALESCE(
                    (
                        SELECT string_agg(
                            m.product || ': ' || TRIM(TRAILING '.0' FROM m.qty::text) || ' ' || COALESCE(m.uom, ''),
                            ' + '
                        )
                        FROM menjadi m
                    ),
                    '-'
                ) AS menjadi;
        """

        self.env.cr.execute(query, params)
        return self.env.cr.fetchall()

    def generate_xlsx_report(self, workbook, data, wizard):
        report_date = data.get('date')
        warehouse_id = data.get('warehouse_id')

        # === NORMALISASI WAREHOUSE ===
        warehouse = None
        if warehouse_id:
            if isinstance(warehouse_id, int):
                warehouse = self.env['stock.warehouse'].browse(warehouse_id)
            elif hasattr(warehouse_id, 'id'):  
                warehouse = warehouse_id
            elif isinstance(warehouse_id, str) and 'stock.warehouse' in warehouse_id:
                match = re.search(r'\((\d+),?\)', warehouse_id)
                if match:
                    warehouse = self.env['stock.warehouse'].browse(int(match.group(1)))

        date_today = format_tanggal_indonesia(report_date)
        data_report = self._get_data_xlsx_report(report_date, warehouse.id if warehouse else None)
        repack_data = self._get_repack_data(report_date, warehouse.id if warehouse else None)

        _logger.info("Repack Data %s", repack_data)

        # =========================================================
        # RENDER SHEET
        # =========================================================
        def _render_sheet(sheet, warehouse_name, ovens, total_per_grade=None):
            # ================= FORMATS =================
            fmt_header = workbook.add_format({'border': 1, 'bold': True, 'align': 'center', 'valign': 'vcenter'})
            fmt_label = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter'})
            fmt_header_packing = workbook.add_format({'border': 1, 'bold': True, 'align': 'left', 'valign': 'vcenter'})
            fmt_number = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
            fmt_text_center = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
            fmt_total = workbook.add_format({'border': 1, 'bold': True, 'align': 'right', 'valign': 'vcenter'})
            fmt_grade_total = workbook.add_format({'border': 1, 'align': 'right', 'valign': 'vcenter'})
            fmt_grade = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter', 'bold': True})

            # ================= OVEN LIST =================
            oven_list = []

            for o in ovens:
                oven_key = _get_oven_key(o.get("oven"), o.get("production_date"))

                if oven_key not in oven_list:
                    oven_list.append(oven_key)

            # ================= TITLE =================
            total_oven = len(oven_list)
            total_cols = 1 + (total_oven * 2)
            last_col = total_cols - 1
            warehouse_end_col = int((total_cols - 1) * 0.7)
            date_start_col = min(warehouse_end_col + 1, last_col)

            sheet.merge_range(0, 0, 0, warehouse_end_col, f"Gudang {warehouse_name}", fmt_label)
            if date_start_col == last_col:
                sheet.write(0, last_col, f"TANGGAL : {date_today}", fmt_label)
            else:
                sheet.merge_range(0, date_start_col, 0, last_col, f"TANGGAL : {date_today}", fmt_label)

            # ================= HEADER ROW 1 =================
            header_row = 1
            col = 0
            sheet.write(header_row, col, "PACKING", fmt_header_packing)
            col += 1
            for oven in oven_list:
                sheet.merge_range(header_row, col, header_row, col + 1, oven, fmt_header)
                col += 2

            # ================= MAP DATA =================
            data_map = {}
            total_per_oven = {}

            # ================= AGGREGATE LOKAL & FUEL =================
            aggregated_special = {}  # key: product name, value: {"qty": x, "uom": y}

            other_ovens = []

            for o in ovens:
                category = o.get("product_category")
                if category in ["LOKAL", "FUEL"]:
                    for p in o.get("products", []):
                        product_name = p.get("product")
                        qty = p.get("qty", 0)
                        uom = o.get("uom_category")
                        category = o.get("product_category")
                        if product_name in aggregated_special:
                            aggregated_special[product_name]["qty"] += qty
                        else:
                            aggregated_special[product_name] = {"qty": qty, "uom": uom, "category": category}
                else:
                    other_ovens.append(o)  # keep other products for normal mapping

            # ================= MAP OTHER OVENS =================
            for o in other_ovens:
                grade = o.get("classification") or "UNCLASSIFIED"

                oven = o.get("oven")
                prod_date = o.get("production_date")

                prod_date_obj = None
                if prod_date:
                    if isinstance(prod_date, str):
                        prod_date_obj = datetime.strptime(prod_date, "%Y-%m-%d").date()
                    elif isinstance(prod_date, (datetime, date)):
                        prod_date_obj = prod_date

                if oven and prod_date_obj:
                    oven_key = f"{oven} ({prod_date_obj.strftime('%d/%m')})"
                elif oven:
                    oven_key = oven
                else:
                    oven_key = "NONE"

                data_map.setdefault(grade, {})
                data_map[grade].setdefault(oven_key, {"products": {}})
                total_per_oven.setdefault(oven_key, 0)

                for p in o.get("products", []):
                    product = p.get("product")
                    qty = p.get("qty", 0)
                    weight = p.get("weight_per_product_attribute", 0)             
                    tonase = p.get("tonase")       

                    data_map[grade][oven_key]["products"].setdefault(product, {"qty": 0, "weight": 0})
                    data_map[grade][oven_key]["products"][product]["qty"] += qty
                    data_map[grade][oven_key]["products"][product]["tonase"] = p.get("tonase", 0)

                    tonase = p.get("tonase") or 1
                    if o.get("product_category") == "EXPORT":
                        total_per_oven[oven_key] += qty * tonase 
                    else:
                        total_per_oven[oven_key] += qty

            # ================= COMPUTE TOTAL PER GRADE =================
            if total_per_grade is None:
                total_per_grade = {}
                for grade in sorted(data_map.keys(), key=_grade_sort_key):
                    oven_data = data_map[grade]

            unclassified_total = sum(
                p.get("qty", 0)
                for o in ovens
                if not o.get("classification")
                for p in o.get("products", [])
            )
            if unclassified_total > 0:
                total_per_grade["UNCLASSIFIED"] = unclassified_total

            # ================= STATIC PICKING ROWS =================
            static_map = [
                ("CAMP.", "camp_tgl_briket"),
                ("UKURAN LUBANG KE STOM", "lubang_setom"),                
                ("BRKT TUNGGU JAM", "briket_tgu"),
                ("SHIFT BRIKET/PA", "shift_briket"),
                ("BKR(HR/JM)/KROAK", "bkr"),
                ("PEMBAKAR/PENUTUP", "pembakar_penutup"),
                ("ASUMSI/BERAT PER IKAT", "asumsi_berat_ikat")
            ]

            row = header_row + 1

            for label, field in static_map:
                sheet.write(row, 0, label, fmt_grade)
                col = 1

                for oven in oven_list:
                    value = ""

                    for o in ovens:
                        oven_key = _get_oven_key(o.get("oven"), o.get("production_date")) or "NONE"

                        if oven_key == oven:
                            value = o.get(field) or ""
                            break

                    sheet.merge_range(row, col, row, col + 1, value, fmt_number)
                    col += 2

                row += 1

            # ================= WRITE DATA (GRADE) =================
            grade_start_row = row

            for grade in sorted(data_map.keys(), key=_grade_sort_key):
                oven_data = data_map[grade]

                if grade == "UNCLASSIFIED":
                    all_products = set()
                    for o in ovens:
                        if not o.get("classification"):
                            for p in o.get("products", []):
                                all_products.add(o.get("product_category"))
                    if all(x in ["LOKAL", "FUEL"] for x in all_products):
                        continue  # skip baris UNCLASSIFIED

                col = 0
                sheet.write(row, col, grade, fmt_grade)
                col += 1

                for oven in oven_list:
                    data = oven_data.get(oven)
                    if data:
                        products = sorted(data["products"].items())

                        qty_str = " | ".join(
                            f"{fmt_qty(float(q['qty']))}"
                            for _, q in products
                        )

                        prod_str = " | ".join(name for name, _ in products)

                        sheet.write(row, col, qty_str, fmt_number)
                        sheet.write(row, col + 1, prod_str, fmt_text_center)

                    else:
                        sheet.write(row, col, "-", fmt_number)
                        sheet.write(row, col + 1, "-", fmt_text_center)

                    col += 2

                row += 1

            # ================= WRITE LOKAL/FUEL PER OVEN (TANPA HEADER) =================
            if aggregated_special:
                # produk -> oven -> list[{qty, uom}]
                product_per_oven = {}

                for o in ovens:
                    if o.get("product_category") in ["LOKAL", "FUEL"]:
                        oven_key = _get_oven_key(o.get("oven"), o.get("production_date")) or "NONE"

                        for p in o.get("products", []):
                            product_name = p.get("product")
                            qty = p.get("qty", 0)
                            uom = o.get("uom_category")

                            product_per_oven.setdefault(product_name, {})
                            product_per_oven[product_name].setdefault(oven_key, [])
                            product_per_oven[product_name][oven_key].append({
                                "qty": qty,
                                "uom": uom,
                            })

                products = sorted(product_per_oven.keys())

                for product_name in products:
                    oven_grouped_data = {}

                    # Ambil seluruh UOM dari semua oven untuk produk ini
                    all_uoms = sorted(
                        {
                            item["uom"]
                            for oven_items in product_per_oven[product_name].values()
                            for item in oven_items
                        },
                        key=lambda x: x.lower()
                    )

                    max_lines = len(all_uoms)

                    for oven in oven_list:
                        items = product_per_oven[product_name].get(oven, [])
                        grouped = {}

                        for item in items:
                            grouped.setdefault(item["uom"], [])
                            grouped[item["uom"]].append(item["qty"])

                        grouped_list = []

                        for uom in all_uoms:
                            qtys = grouped.get(uom, [])

                            grouped_list.append({
                                "uom": uom,
                                "qty_str": " | ".join(str(fmt_qty(q)) for q in qtys) if qtys else "-"
                            })

                        oven_grouped_data[oven] = grouped_list

                    for line_index in range(max_lines):
                        uom_str = all_uoms[line_index]

                        display_name = f"{product_name} ({uom_str})"

                        sheet.write(row + line_index, 0, display_name, fmt_grade)

                        col = 1

                        for oven in oven_list:
                            data = oven_grouped_data[oven][line_index]

                            if data["qty_str"] != "-":
                                sheet.write(row + line_index, col, data["qty_str"], fmt_number)
                                sheet.write(row + line_index, col + 1, data["uom"], fmt_text_center)
                            else:
                                sheet.write(row + line_index, col, "-", fmt_number)
                                sheet.write(row + line_index, col + 1, "-", fmt_text_center)

                            col += 2

                    row += max_lines

            # ================= TOTAL ROW =================
            sheet.write(row, 0, "TOTAL QTY (KG)", fmt_header)
            col = 1

            for oven in oven_list:
                total = 0.0

                for o in ovens:
                    oven_key = _get_oven_key(o.get("oven"), o.get("production_date")) or "NONE"
                    if oven_key == oven:
                        total += o.get("total_per_oven", 0)

                sheet.merge_range(row, col, row, col + 1, total if total else "-", fmt_total)
                col += 2

                # ================= TOTAL PER GRADE DI KANAN =================
                grade_col_start = last_col + 1
                grade_row_header = grade_start_row - 1
                sheet.write(grade_row_header, grade_col_start, "PRODUK", fmt_header)
                sheet.write(grade_row_header, grade_col_start + 1, "QTY", fmt_header)
                sheet.write(grade_row_header, grade_col_start + 2, "TOTAL", fmt_header)
                sheet.write(grade_row_header, grade_col_start + 3, "GRADE", fmt_header)

                grade_row = grade_start_row
                for grade in sorted(data_map.keys(), key=_grade_sort_key):
                    product_qty = {}
                    product_qty_raw = {}  # <-- tambahan

                    # ================= EXPORT =================
                    if grade not in ["LOKAL", "FUEL"]:
                        for o in ovens:
                            if (o.get("classification") or "UNCLASSIFIED") != grade:
                                continue

                            for p in o.get("products", []):
                                product = p.get("product")
                                qty = p.get("qty", 0)
                                uom = o.get("uom_category")
                                tonase = p.get("tonase") or 1
                                is_cl = p.get("is_cl", False)

                                # ================= QTY ASLI =================
                                product_qty_raw[product] = product_qty_raw.get(product, 0) + qty

                                # ================= TOTAL =================
                                value = qty * tonase
                                product_qty[product] = product_qty.get(product, 0) + value

                    if not product_qty:
                        continue

                    products = sorted(product_qty.keys())

                    # QTY tanpa perkalian
                    qtys = [fmt_qty(product_qty_raw[p]) for p in products]

                    # TOTAL pakai weight
                    total_grade = fmt_qty(sum(product_qty.values()))

                    sheet.write(grade_row, grade_col_start, " | ".join(products), fmt_text_center)
                    sheet.write(grade_row, grade_col_start + 1, " | ".join(qtys), fmt_text_center)
                    sheet.write(grade_row, grade_col_start + 2, total_grade, fmt_grade_total)
                    sheet.write(grade_row, grade_col_start + 3, grade, fmt_grade)

                    grade_row += 1
                    
            # ================= LOOP PRODUK LOKAL / FUEL =================
            if aggregated_special:
                for p_name, p_data in sorted(aggregated_special.items()):
                    category = p_data.get("category", "-")

                    # ============================================
                    # uom -> data
                    # ============================================
                    uom_data = {}

                    for o in ovens:
                        if o.get("product_category") != category:
                            continue

                        for p in o.get("products", []):
                            if p.get("product") != p_name:
                                continue

                            qty = p.get("qty", 0)
                            uom = o.get("uom_category")
                            is_cl = p.get("is_cl", False)
                            tonase = o.get("tonase", 1)
                            value = qty if is_cl else qty * tonase

                            if uom not in uom_data:
                                uom_data[uom] = {
                                    "qty": 0,
                                    "total": 0,
                                }

                            uom_data[uom]["qty"] += qty
                            uom_data[uom]["total"] += value

                    # ============================================
                    # WRITE ROW PER UOM
                    # ============================================
                    for uom, vals in sorted(uom_data.items()):
                        qty = vals["qty"]
                        total = vals["total"]

                        sheet.write(grade_row, grade_col_start, p_name, fmt_text_center)
                        sheet.write(grade_row, grade_col_start + 1, fmt_qty(qty), fmt_number)
                        sheet.write(grade_row, grade_col_start + 2, fmt_qty(total), fmt_grade_total)
                        sheet.write(grade_row, grade_col_start + 3, uom, fmt_grade)

                        grade_row += 1

            # ================= TOTAL SELURUH GRADE & RATA-RATA =================
            total_all_grades = 0

            for o in ovens:
                category = o.get("product_category")

                for p in o.get("products", []):
                    qty = p.get("qty", 0)
                    tonase = p.get("tonase") or 1
                    is_cl = p.get("is_cl", False)

                    total_all_grades += (qty * tonase)

            sheet.write(grade_row, grade_col_start + 2, fmt_qty(total_all_grades), fmt_total)
            sheet.write(grade_row, grade_col_start + 3, "TTL TONASE", fmt_header)

            # rata-rata per oven
            average_per_oven = round(total_all_grades / len(oven_list), 2) if oven_list else 0.00

            sheet.write(grade_row + 1, grade_col_start + 2, fmt_qty(average_per_oven), fmt_total)
            sheet.write(grade_row + 1, grade_col_start + 3, "RATA-RATA", fmt_header)


            # ================= COLUMN WIDTH =================
            sheet.set_column(0, 0, 25)  # PICKING / GRADE

            col_idx = 1
            for _ in range(total_oven):
                sheet.set_column(col_idx, col_idx, 7)      # QTY oven
                sheet.set_column(col_idx + 1, col_idx + 1, 18)  # PRODUK oven
                col_idx += 2

            # ===== KOLOM KANAN (SUMMARY GRADE) =====
            sheet.set_column(grade_col_start, grade_col_start, 40)       # PRODUK (A | B | D)
            sheet.set_column(grade_col_start + 1, grade_col_start + 1, 25)  # QTY (2 | 4 | 6)
            sheet.set_column(grade_col_start + 2, grade_col_start + 2, 10)  # TOTAL
            sheet.set_column(grade_col_start + 3, grade_col_start + 3, 15)  # GRADE

            # ================= JENIS ROW =================
            jenis_row = grade_row + 1

            sheet.write(jenis_row, 0, "JENIS", fmt_header)

            col = 1

            for oven in oven_list:
                value = ""

                for o in ovens:
                    oven_key = _get_oven_key(o.get("oven"), o.get("production_date")) or "NONE"

                    if oven_key == oven:
                        value = o.get("bongkaran") or ""
                        break

                sheet.merge_range(jenis_row, col, jenis_row, col + 1, value, fmt_number)
                col += 2            

            # ================= FOOTER =================
            footer_row = grade_row + 3
            
            if repack_data:
                bongkar, menjadi = repack_data[0]

                sheet.merge_range(footer_row, 0, footer_row, last_col, bongkar)
                footer_row += 1

                sheet.merge_range(footer_row, 0, footer_row, last_col, menjadi)
                footer_row += 1    

        # =========================================================
        # CASE 1 : SINGLE WAREHOUSE
        # =========================================================
        if warehouse:
            wh_name = warehouse.name
            ovens = data_report.get(wh_name, {}).get("ovens", [])
            total_per_grade = data_report.get(wh_name, {}).get("total_per_grade")
            sheet = workbook.add_worksheet(wh_name[:31])
            _render_sheet(sheet, wh_name, ovens, total_per_grade=total_per_grade)

        # =========================================================
        # CASE 2 : ALL WAREHOUSE
        # =========================================================
        else:
            for wh_name, wh_data in data_report.items():
                ovens = wh_data.get("ovens", [])
                total_per_grade = wh_data.get("total_per_grade")
                sheet = workbook.add_worksheet(wh_name[:31])
                _render_sheet(sheet, wh_name, ovens, total_per_grade=total_per_grade)
