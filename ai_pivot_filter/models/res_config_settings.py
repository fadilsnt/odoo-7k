# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_pivot_groq_api_key = fields.Char(
        string='Groq API Key',
        config_parameter='ai_pivot_filter.groq_api_key',
    )
    ai_pivot_groq_model = fields.Char(
        string='Groq Model',
        config_parameter='ai_pivot_filter.groq_model',
        default='qwen/qwen3-32b',
    )
    ai_pivot_groq_base_url = fields.Char(
        string='Groq Base URL',
        config_parameter='ai_pivot_filter.groq_base_url',
        default='https://api.groq.com/openai/v1',
    )
