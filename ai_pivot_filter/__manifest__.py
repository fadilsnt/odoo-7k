# -*- coding: utf-8 -*-
{
    'name': 'AI Pivot Generator',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Update filter/domain pada Pivot View menggunakan chatbox AI',
    'description': """
        AI Pivot Generator
    """,
    'author': 'Herul Ramdani',
    'depends': ['web', 'base'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_pivot_filter/static/src/js/ai_pivot_registry.js',
            'ai_pivot_filter/static/src/js/ai_pivot_bridge.js',
            'ai_pivot_filter/static/src/js/pivot_patch.js',
            'ai_pivot_filter/static/src/js/ai_pivot_dialog.js',
            'ai_pivot_filter/static/src/js/ai_pivot_systray.js',
            'ai_pivot_filter/static/src/xml/ai_pivot_dialog.xml',
            'ai_pivot_filter/static/src/xml/ai_pivot_systray.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
