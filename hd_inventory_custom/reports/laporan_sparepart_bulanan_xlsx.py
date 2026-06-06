from odoo import models, _
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)

class ReportLaporanSparepartXlsx(models.AbstractModel):
    _name = 'report.hd_inventory_custom.report_laporan_sparepart_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    # =========================================================
    # PERIOD LABEL
    # =========================================================
    def _get_period_label(self, start_date, end_date):
        # Jika bulan & tahun sama
        if (start_date.month == end_date.month and start_date.year == end_date.year):
            return (
                f"{start_date.day} - "
                f"{end_date.day} "
                f"{start_date.strftime('%B %Y')}"
            )

        # Jika tahun sama tapi bulan beda
        elif start_date.year == end_date.year:
            return (
                f"{start_date.day} {start_date.strftime('%B')} - "
                f"{end_date.day} {end_date.strftime('%B %Y')}"
            )

        # Jika tahun beda
        return (
            f"{start_date.day} {start_date.strftime('%B %Y')} - "
            f"{end_date.day} {end_date.strftime('%B %Y')}"
        )

    # =========================================================
    # HELPERS
    # =========================================================
    def _fetch_qty_map(self):
        return {
            row['product_id']: float(row['qty'] or 0.0)
            for row in self.env.cr.dictfetchall()
        }
    
    # =========================================================
    # QTY INVENTORY ADJUSTMENT
    # =========================================================
    def _get_qty_adjustment_map(self, product_ids, warehouse, start_date, end_date,):
        if not product_ids:
            return {}

        self.env.cr.execute("""
            SELECT
                sml.product_id,
                COALESCE(SUM(
                    CASE
                        -- tambah stock
                        WHEN src.usage = 'inventory'
                            AND dest.usage = 'internal'
                        THEN sml.quantity

                        -- kurang stock
                        WHEN src.usage = 'internal'
                            AND dest.usage = 'inventory'
                        THEN -sml.quantity
                        ELSE 0
                    END
                ), 0) AS qty
            FROM stock_move_line sml
            JOIN stock_location src ON src.id = sml.location_id
            JOIN stock_location dest ON dest.id = sml.location_dest_id
            WHERE sml.product_id = ANY(%s)
                AND sml.state = 'done'
                AND sml.date >= %s
                AND sml.date <= %s
                AND (
                        -- inventory -> warehouse ini
                        (
                            src.usage = 'inventory'
                            AND dest.warehouse_id = %s
                        )
                        OR
                        -- warehouse ini -> inventory
                        (
                            dest.usage = 'inventory'
                            AND src.warehouse_id = %s
                        )
                )
            GROUP BY sml.product_id
        """, [
            product_ids,
            start_date,
            end_date,
            warehouse.id,
            warehouse.id,
        ])

        return self._fetch_qty_map()
    # =========================================================
    # PRODUCTS
    # =========================================================
    def _get_products_data(self, sparepart_category_id):
        self.env.cr.execute("""
            WITH RECURSIVE categ_tree AS (
                SELECT id
                FROM product_category
                WHERE id = %s

                UNION ALL

                SELECT pc.id
                FROM product_category pc
                JOIN categ_tree ct ON pc.parent_id = ct.id
            )

            SELECT
                pp.id,
                COALESCE(
                    pt.name->>'id_ID',
                    pt.name->>'en_US',
                    ''
                ) AS name,
                pc.id AS categ_id,
                pc.name AS categ_name
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            JOIN product_category pc ON pc.id = pt.categ_id
            WHERE pt.categ_id IN (
                SELECT id
                FROM categ_tree
                WHERE id != %s
            )
            ORDER BY
                pc.name,
                name
        """, [
            sparepart_category_id,
            sparepart_category_id,
        ])

        return self.env.cr.dictfetchall()

    # =========================================================
    # STOCK AWAL
    # =========================================================
    def _get_stock_awal_map(self, product_ids, warehouse, start_date,):
        if not product_ids:
            return {}

        location_ids = self.env['stock.location'].search([
            ('id', 'child_of', warehouse.view_location_id.id)
        ]).ids

        self.env.cr.execute("""
            SELECT
                sm.product_id,
                COALESCE(SUM(
                    CASE
                        WHEN sm.location_dest_id = ANY(%s)
                        THEN sm.product_uom_qty
                        ELSE 0
                    END
                ), 0)

                -

                COALESCE(SUM(
                    CASE
                        WHEN sm.location_id = ANY(%s)
                        THEN sm.product_uom_qty
                        ELSE 0
                    END
                ), 0)

                AS qty

            FROM stock_move sm
            WHERE sm.product_id = ANY(%s)
                AND sm.state = 'done'
                AND sm.date < %s
                AND (
                    sm.location_id = ANY(%s)
                    OR
                    sm.location_dest_id = ANY(%s)
                )
            GROUP BY sm.product_id
        """, [
            location_ids,
            location_ids,
            product_ids,
            start_date,
            location_ids,
            location_ids,
        ])

        return self._fetch_qty_map()

    # =========================================================
    # QTY BELI
    # =========================================================
    def _get_qty_beli_map(self, product_ids, warehouse, start_date, end_date,):
        if not product_ids:
            return {}

        self.env.cr.execute("""
            SELECT
                sm.product_id,
                COALESCE(SUM(sm.product_uom_qty), 0) AS qty
            FROM stock_move sm
            JOIN stock_picking sp ON sp.id = sm.picking_id
            JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
            WHERE sm.product_id = ANY(%s)
              AND sm.state IN ('assigned', 'done')
              AND sm.date >= %s
              AND sm.date <= %s
              AND spt.code = 'incoming'
              AND spt.warehouse_id = %s
            GROUP BY sm.product_id
        """, [
            product_ids,
            start_date,
            end_date,
            warehouse.id,
        ])

        return self._fetch_qty_map()

    # =========================================================
    # QTY MUTASI KELUAR
    # =========================================================
    def _get_qty_mutasi_keluar_map(self, product_ids, warehouse, start_date, end_date,):
        if not product_ids:
            return {}

        self.env.cr.execute("""
            SELECT
                sm.product_id,
                COALESCE(SUM(sm.product_uom_qty), 0) AS qty
            FROM stock_move sm
            JOIN stock_location src ON src.id = sm.location_id
            JOIN stock_location dest ON dest.id = sm.location_dest_id
            WHERE sm.product_id = ANY(%s)
                AND sm.state = 'done'
                AND sm.date >= %s
                AND sm.date <= %s

                -- source dari warehouse ini
                AND src.warehouse_id = %s

                -- destination ke warehouse lain
                AND dest.warehouse_id IS NOT NULL
                AND dest.warehouse_id != %s

                -- hanya internal transfer
                AND src.usage = 'internal'
                AND dest.usage = 'internal'

            GROUP BY sm.product_id
        """, [
            product_ids,
            start_date,
            end_date,
            warehouse.id,
            warehouse.id,
        ])

        return self._fetch_qty_map()

    # =========================================================
    # QTY MUTASI MASUK
    # =========================================================
    def _get_qty_mutasi_masuk_map(self, product_ids, warehouse, start_date, end_date,):
        if not product_ids:
            return {}

        self.env.cr.execute("""
            SELECT
                sm.product_id,
                COALESCE(SUM(sm.product_uom_qty), 0) AS qty
            FROM stock_move sm
            JOIN stock_location src ON src.id = sm.location_id
            JOIN stock_location dest ON dest.id = sm.location_dest_id
            WHERE sm.product_id = ANY(%s)
                AND sm.state = 'done'
                AND sm.date >= %s
                AND sm.date <= %s

                -- destination ke warehouse ini
                AND dest.warehouse_id = %s

                -- source dari warehouse lain
                AND src.warehouse_id IS NOT NULL
                AND src.warehouse_id != %s

                -- hanya internal transfer
                AND src.usage = 'internal'
                AND dest.usage = 'internal'

                GROUP BY sm.product_id
        """, [
            product_ids,
            start_date,
            end_date,
            warehouse.id,
            warehouse.id,
        ])

        return self._fetch_qty_map()

    # =========================================================
    # QTY PAKAI
    # =========================================================
    def _get_qty_pakai_map(self, product_ids, warehouse, start_date, end_date, usage_location,):
        if not product_ids or not usage_location:
            return {}

        self.env.cr.execute("""
            SELECT
                sm.product_id,
                COALESCE(SUM(sm.product_uom_qty), 0) AS qty
            FROM stock_move sm
            JOIN stock_location src ON src.id = sm.location_id
            WHERE sm.product_id = ANY(%s)
            AND sm.state = 'done'
            AND sm.date >= %s
            AND sm.date <= %s
            AND sm.location_dest_id = %s
            AND src.id = ANY(%s)

            GROUP BY sm.product_id
        """, [
            product_ids,
            start_date,
            end_date,
            usage_location.id,
            self.env['stock.location'].search([
                ('id', 'child_of', warehouse.view_location_id.id)
            ]).ids,
        ])

        return self._fetch_qty_map()

    # =========================================================
    # MAIN REPORT
    # =========================================================
    def generate_xlsx_report(self, workbook, data, wizard):
        # =========================================================
        # FORMAT
        # =========================================================
        title_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 14,
        })

        subtitle_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 11,
        })

        header_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })

        subheader_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })

        text_format = workbook.add_format({
            'border': 1,
            'valign': 'vcenter',
        })

        number_format = workbook.add_format({
            'border': 1,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0',
        })

        category_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'bg_color': '#D9EAD3',
        })

        # =========================================================
        # WAREHOUSE
        # =========================================================
        if wizard.warehouse_id:
            warehouses = wizard.warehouse_id
        else:
            warehouses = self.env['stock.warehouse'].search([])

        # =========================================================
        # MASTER DATA
        # =========================================================
        sparepart_category = self.env.ref('hd_inventory_custom.product_category_sparepart', raise_if_not_found=False)
        usage_location = self.env.ref('hd_inventory_custom.stock_location_sparepart_usage', raise_if_not_found=False)

        if not sparepart_category:
            return

        # =========================================================
        # PRODUCTS
        # =========================================================
        products_data = self._get_products_data(sparepart_category.id)
        grouped_products = defaultdict(list)

        product_ids = []
        for product in products_data:
            grouped_products[
                (
                    product['categ_id'],
                    product['categ_name']
                )
            ].append(product)

            product_ids.append(product['id'])

        # =========================================================
        # LOOP WAREHOUSE
        # =========================================================
        for warehouse in warehouses:
            # =====================================================
            # QUERY DATA
            # =====================================================
            stock_awal_map = self._get_stock_awal_map(product_ids, warehouse, wizard.start_date,)
            qty_beli_map = self._get_qty_beli_map(product_ids, warehouse, wizard.start_date, wizard.end_date,)
            qty_mutasi_keluar_map = self._get_qty_mutasi_keluar_map(product_ids, warehouse, wizard.start_date, wizard.end_date,)
            qty_mutasi_masuk_map = self._get_qty_mutasi_masuk_map(product_ids, warehouse, wizard.start_date, wizard.end_date,)
            qty_pakai_map = self._get_qty_pakai_map(product_ids, warehouse, wizard.start_date, wizard.end_date, usage_location,)
            qty_adjustment_map = self._get_qty_adjustment_map(product_ids, warehouse, wizard.start_date, wizard.end_date,)

            _logger.info("qty_adjustment_map: %s", qty_adjustment_map)

            # =====================================================
            # SHEET
            # =====================================================
            sheet_name = warehouse.name[:31]
            sheet = workbook.add_worksheet(sheet_name)

            sheet.set_column('A:A', 20)
            sheet.set_column('B:B', 40)
            sheet.set_column('C:I', 18)

            # =====================================================
            # TITLE
            # =====================================================
            title = f'LAPORAN SPARE PART {warehouse.name.upper()}'
            sheet.merge_range('A1:I1', title, title_format)

            period = self._get_period_label(wizard.start_date, wizard.end_date,).upper()
            sheet.merge_range('A2:I2', f"PERIODE {period}", subtitle_format)

            company_name = self.env.company.name or ''
            sheet.merge_range('A3:I3', company_name.upper(), subtitle_format)

            # =====================================================
            # HEADER
            # =====================================================
            sheet.merge_range('A5:A6', 'KATEGORI', header_format)
            sheet.merge_range('B5:B6', 'ITEM', header_format)
            sheet.merge_range('C5:C6', 'STOCK AWAL', header_format)

            sheet.merge_range('D5:D6', 'BELI', header_format)

            sheet.merge_range('E5:E6', 'MUTASI KELUAR', header_format)
            sheet.merge_range('F5:F6', 'MUTASI MASUK', header_format)

            sheet.merge_range('G5:G6', 'LAIN - LAIN', header_format)

            sheet.merge_range('H5:H6', 'PAKAI', header_format)
            sheet.merge_range('I5:I6', 'STOCK AKHIR', header_format)

            # =====================================================
            # DATA
            # =====================================================
            row = 6

            for (category_id, category_name), category_products in grouped_products.items():
                sheet.merge_range(row, 0, row, 8, str(category_name or '').upper(), category_format)
                row += 1

                for product in category_products:
                    stock_awal = stock_awal_map.get(product['id'], 0.0)
                    qty_beli = qty_beli_map.get(product['id'], 0.0)
                    qty_mutasi_keluar = qty_mutasi_keluar_map.get(product['id'], 0.0)
                    qty_mutasi_masuk = qty_mutasi_masuk_map.get(product['id'], 0.0)
                    qty_pakai = qty_pakai_map.get(product['id'], 0.0)
                    qty_adjustment = qty_adjustment_map.get(product['id'], 0.0)
                    
                    stock_akhir = (
                        stock_awal
                        + qty_beli
                        + qty_mutasi_masuk
                        + qty_adjustment
                        - qty_mutasi_keluar
                        - qty_pakai
                    )

                    if qty_adjustment < 0:
                        adjustment_display = f"({abs(int(qty_adjustment)):,})"
                    else:
                        adjustment_display = f"{int(qty_adjustment):,}"                         

                    sheet.write(row, 0, "", text_format)
                    sheet.write_string(row, 1, str(product.get('name') or ''), text_format)
                    sheet.write_number(row, 2, float(stock_awal), number_format)
                    sheet.write_number(row, 3, float(qty_beli), number_format)
                    sheet.write_number(row, 4, float(qty_mutasi_keluar), number_format)
                    sheet.write_number(row, 5, float(qty_mutasi_masuk), number_format)
                    sheet.write(row, 6, adjustment_display, text_format)
                    sheet.write_number(row, 7, float(qty_pakai), number_format)
                    sheet.write_number(row, 8, float(stock_akhir), number_format)                 

                    row += 1