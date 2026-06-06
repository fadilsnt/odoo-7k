{
    "name": "Export Stock Report",
    "version": "18.0.1.0.0",
    "author": "Yayan H",
    "website": "",
    "category": "Inventory",
    "summary": "Custom Export Stock Report with PDF",
    "depends": ["base", "stock", "product", "web"],
    "data": [
        "views/stock_picking.xml",
        "views/tree_form_view.xml",
        "views/product_template_view.xml",
        "wizard/cek_cl_wizard.xml", 
        "wizard/export_stock_wizard_views.xml",
        "wizard/stock_quant.xml",
        "wizard/wizard_laporan_persediaan_view.xml",
        "reports/export_stock_report.xml",
        "reports/report_export_stock_template.xml",
        "reports/stok_persediaan_report.xml",
        "reports/dalam_pengiriman.xml",
        "reports/cek_cl_report.xml",
        "security/ir.model.access.csv",
    ],
    'assets': {
        'web.assets_backend': [
            ('after', 'web/static/src/webclient/user_menu/user_menu.js', 'export_stock_report/static/src/js/user_menu.js'),
            'export_stock_report/static/src/js/user_menu.xml',
        ],
    },

    "installable": True,
    "application": False,
}
