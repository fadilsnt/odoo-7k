# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Preset dasar untuk tiap provider yang sudah dikenal.
# 'model' sengaja dikosongkan untuk provider yang model-nya sering berubah/
# banyak pilihan (opencode zen, custom) -> user isi manual sesuai model yang
# ingin dipakai. Untuk Groq kita isi default lama supaya upgrade mulus.
PROVIDER_PRESETS = {
    'groq': {
        'base_url': 'https://api.groq.com/openai/v1',
        'model': 'qwen/qwen3-32b',
    },
    'opencode_zen': {
        'base_url': 'https://opencode.ai/zen/v1',
        'model': '',
    },
    'custom': {
        'base_url': '',
        'model': '',
    },
}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_pivot_provider = fields.Selection(
        selection=[
            ('groq', 'Groq'),
            ('opencode_zen', 'OpenCode Zen (opencode.ai/zen)'),
            ('custom', 'Custom / Provider Lain (OpenAI-compatible)'),
        ],
        string='AI Provider',
        config_parameter='ai_pivot_filter.provider',
        default='groq',
        help="Pilih penyedia AI. Semua provider di sini menggunakan format "
             "API yang kompatibel dengan OpenAI Chat Completions "
             "(endpoint /chat/completions), jadi Base URL + Model + API Key "
             "saja yang perlu disesuaikan.",
    )
    ai_pivot_api_key = fields.Char(
        string='API Key',
        config_parameter='ai_pivot_filter.api_key',
    )
    ai_pivot_model = fields.Char(
        string='Model',
        config_parameter='ai_pivot_filter.model',
        default='qwen/qwen3-32b',
        help="Nama model sesuai yang disediakan provider, misal "
             "'qwen/qwen3-32b' (Groq) atau nama model dari daftar model "
             "OpenCode Zen.",
    )
    ai_pivot_base_url = fields.Char(
        string='Base URL',
        config_parameter='ai_pivot_filter.base_url',
        default='https://api.groq.com/openai/v1',
        help="Base URL API, tanpa akhiran '/chat/completions' (contoh: "
             "https://api.groq.com/openai/v1 atau https://opencode.ai/zen/v1).",
    )

    @api.onchange('ai_pivot_provider')
    def _onchange_ai_pivot_provider(self):
        preset = PROVIDER_PRESETS.get(self.ai_pivot_provider)
        if not preset:
            return
        self.ai_pivot_base_url = preset['base_url']
        # Hanya timpa model jika ada default yang jelas untuk provider ini,
        # supaya tidak menghapus model custom yang mungkin sudah diisi user
        # untuk provider 'custom'/'opencode_zen'.
        if preset['model']:
            self.ai_pivot_model = preset['model']
