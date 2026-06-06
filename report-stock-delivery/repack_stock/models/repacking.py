from odoo import models, fields


class StockRepackLine(models.Model):
    _name = "stock.repack.line"
    _description = "Stock Repack Line"

    picking_id = fields.Many2one(
        "stock.picking",
        string="Picking",
        ondelete="cascade"
    )

    product_a_id = fields.Many2one(
        "product.product",
        string="Product Awal",
        required=True
    )

    qty_a = fields.Float(
        string="Qty",
        required=True
    )

    product_b_id = fields.Many2one(
        "product.product",
        string="Product Repack",
    )

    qty_b = fields.Float(
        string="Qty",
    )

    repack_output_ids = fields.One2many(
        "stock.repack.output",
        "repack_line_id",
        string="Hasil Repack"
    )

class StockRepackOutput(models.Model):
    _name = "stock.repack.output"
    _description = "Stock Repack Output"

    repack_line_id = fields.Many2one(
        "stock.repack.line",
        ondelete="cascade"
    )

    product_b_id = fields.Many2one(
        "product.product",
        string="Product Hasil",
        required=True
    )

    qty_b = fields.Float(
        string="Qty Hasil",
        required=True
    )
