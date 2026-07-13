# -*- coding: utf-8 -*-
import calendar
import json
import logging
import re
from datetime import timedelta

import requests
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen/qwen3-32b"
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
TIMEOUT = 30

PROVIDER_LABELS = {
    'groq': 'Groq',
    'opencode_zen': 'OpenCode Zen (opencode.ai/zen)',
    'custom': 'Custom Provider',
}

MEASURE_TYPES = ("integer", "float", "monetary")
IGNORED_FIELDS = ("__last_update", "display_name", "create_uid", "write_uid", "id")

# Nama-nama hari dalam Bahasa Indonesia, index 0 = Senin (isoweekday 1)
_DAY_NAMES_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


class AiPivotAssistant(models.AbstractModel):
    _name = 'ai.pivot.assistant'
    _description = 'AI Pivot Assistant (multi-provider, OpenAI-compatible)'

    def _get_config(self):
        icp = self.env['ir.config_parameter'].sudo()
        provider = icp.get_param('ai_pivot_filter.provider', default='groq')

        # Baca parameter generik yang baru. Jika belum pernah diisi (mis.
        # instalasi lama sebelum modul ini mendukung banyak provider),
        # fallback ke parameter lama 'groq_*' supaya konfigurasi existing
        # tidak hilang setelah upgrade modul.
        api_key = icp.get_param('ai_pivot_filter.api_key', default='') \
            or icp.get_param('ai_pivot_filter.groq_api_key', default='')
        model = icp.get_param('ai_pivot_filter.model', default='') \
            or icp.get_param('ai_pivot_filter.groq_model', default=DEFAULT_MODEL)
        base_url = icp.get_param('ai_pivot_filter.base_url', default='') \
            or icp.get_param('ai_pivot_filter.groq_base_url', default=DEFAULT_BASE_URL)
        return api_key, model, base_url, provider

    @api.model
    def generate_pivot_state(self, model_name, user_text, current_domain=None, current_measures=None,
                              current_row_groupby=None, current_col_groupby=None):
        api_key, model, base_url, provider = self._get_config()
        provider_label = PROVIDER_LABELS.get(provider, provider or 'AI')
        if not api_key:
            raise UserError(
                "API Key %s belum diisi. Buka Settings > General Settings > "
                "AI Pivot Filter untuk memilih provider dan mengisi "
                "kredensial." % provider_label
            )
        if not base_url:
            raise UserError(
                "Base URL untuk provider %s belum diisi. Buka Settings > "
                "General Settings > AI Pivot Filter untuk mengisinya." % provider_label
            )
        if not model:
            raise UserError(
                "Model untuk provider %s belum diisi. Buka Settings > "
                "General Settings > AI Pivot Filter untuk mengisinya." % provider_label
            )

        if model_name not in self.env:
            raise UserError("Model %s tidak ditemukan." % model_name)

        domain_fields_info = self._get_domain_fields(model_name)
        measure_fields_info, valid_measures = self._get_measure_fields(model_name)
        prompt = self._build_prompt(
            model_name,
            domain_fields_info,
            measure_fields_info,
            user_text,
            current_domain,
            current_measures,
            current_row_groupby,
            current_col_groupby,
        )

        try:
            result = self._call_llm(api_key, model, base_url, prompt)
        except UserError:
            raise
        except Exception as exc:  # noqa: BLE001
            _logger.exception("AI Pivot Filter: %s call failed", provider_label)
            raise UserError("Gagal menghubungi AI (%s): %s" % (provider_label, exc))

        domain = result.get('domain', [])
        if not isinstance(domain, list):
            domain = []

        dropped_notes = []

        valid_domain_fields = self._extract_domain_field_names(domain_fields_info)
        domain = self._sanitize_domain(domain, valid_domain_fields, dropped_notes)

        raw_measures = result.get('measures')
        if isinstance(raw_measures, list):
            measures = [m for m in raw_measures if m in valid_measures]
            invalid_measures = [m for m in raw_measures if m not in valid_measures]
            if invalid_measures:
                dropped_notes.append(
                    "Measure %s tidak dikenali di model ini dan diabaikan."
                    % ", ".join(str(m) for m in invalid_measures)
                )
        else:
            measures = None

        row_groupby = self._sanitize_groupby(result.get('row_groupby'), valid_domain_fields, dropped_notes, 'baris')
        col_groupby = self._sanitize_groupby(result.get('col_groupby'), valid_domain_fields, dropped_notes, 'kolom')

        ai_note = result.get('catatan') or result.get('note') or result.get('message')
        message_parts = []
        if isinstance(ai_note, str) and ai_note.strip():
            message_parts.append(ai_note.strip())
        message_parts.extend(dropped_notes)
        message = " ".join(message_parts) if message_parts else None

        return {
            'domain': domain,
            'measures': measures,
            'row_groupby': row_groupby,
            'col_groupby': col_groupby,
            'message': message,
        }

    def _get_domain_fields(self, model_name):
        Model = self.env[model_name]
        fields_data = Model.fields_get(attributes=['string', 'type', 'selection', 'relation', 'store'])
        lines = []
        for fname, finfo in fields_data.items():
            if fname in IGNORED_FIELDS:
                continue

            if finfo.get('store') is False:
                continue
            ftype = finfo.get('type')
            label = finfo.get('string') or fname
            extra = ''
            if ftype == 'selection' and finfo.get('selection'):
                try:
                    options = ", ".join("%s=%s" % (k, v) for k, v in finfo['selection'])
                    extra = " (pilihan: %s)" % options
                except Exception:
                    pass
            elif ftype in ('many2one', 'many2many', 'one2many'):
                extra = " (relasi ke %s)" % finfo.get('relation')
            if ftype in ('date', 'datetime'):
                extra += " [FIELD TANGGAL]"
            lines.append("- %s | label: %s | tipe: %s%s" % (fname, label, ftype, extra))

        lines.sort()
        return "\n".join(lines[:200])

    def _extract_domain_field_names(self, domain_fields_info):
        names = set()
        for line in (domain_fields_info or '').splitlines():
            line = line.strip()
            if not line.startswith('-'):
                continue
            fname = line[1:].split('|', 1)[0].strip()
            if fname:
                names.add(fname)
        return names

    def _sanitize_domain(self, domain, valid_fields, dropped_notes=None):
        if not valid_fields:
            return domain
        cleaned = []
        dropped_fields = []
        for item in domain:
            if item in ('&', '|', '!'):
                cleaned.append(item)
                continue
            if (isinstance(item, (list, tuple)) and len(item) == 3
                    and item[0] in valid_fields):
                cleaned.append(list(item))
            else:
                _logger.warning(
                    "AI Pivot Filter: dropping unrecognized domain leaf %r", item
                )
                if isinstance(item, (list, tuple)) and item:
                    dropped_fields.append(str(item[0]))
        if dropped_fields and dropped_notes is not None:
            dropped_notes.append(
                "Filter pada field %s tidak diterapkan karena field tersebut "
                "tidak tersedia/tidak cocok di model ini."
                % ", ".join(sorted(set(dropped_fields)))
            )
        return cleaned

    VALID_GROUPBY_INTERVALS = ('day', 'week', 'month', 'quarter', 'year')

    def _sanitize_groupby(self, groupby, valid_fields, dropped_notes=None, axis_label=None):
        if not isinstance(groupby, list):
            return None
        if not valid_fields:
            return [g for g in groupby if isinstance(g, str)]
        cleaned = []
        dropped_fields = []
        for entry in groupby:
            if not isinstance(entry, str):
                continue
            fname, _, interval = entry.partition(':')
            fname = fname.strip()
            interval = interval.strip()
            if fname not in valid_fields:
                _logger.warning(
                    "AI Pivot Filter: dropping unrecognized groupby field %r", entry
                )
                dropped_fields.append(fname or entry)
                continue
            if interval and interval not in self.VALID_GROUPBY_INTERVALS:
                cleaned.append(fname)
            else:
                cleaned.append(entry)
        if dropped_fields and dropped_notes is not None:
            dropped_notes.append(
                "Pengelompokan %s pada field %s tidak diterapkan karena field "
                "tersebut tidak tersedia di model ini."
                % (axis_label or '', ", ".join(sorted(set(dropped_fields))))
            )
        return cleaned

    def _get_measure_fields(self, model_name):
        Model = self.env[model_name]
        fields_data = Model.fields_get(attributes=['string', 'type', 'store'])
        lines = ["- __count | label: Count | tipe: count (jumlah baris)"]
        valid = {'__count'}
        for fname, finfo in fields_data.items():
            if fname in IGNORED_FIELDS:
                continue
            if finfo.get('type') in MEASURE_TYPES and finfo.get('store'):
                label = finfo.get('string') or fname
                lines.append("- %s | label: %s | tipe: %s" % (fname, label, finfo.get('type')))
                valid.add(fname)
        return "\n".join(lines[:80]), valid

    def _get_date_context(self):
        today = fields.Date.context_today(self)

        start_of_week = today - timedelta(days=today.isoweekday() - 1)
        end_of_week = start_of_week + timedelta(days=6)
        start_of_last_week = start_of_week - timedelta(days=7)
        end_of_last_week = start_of_week - timedelta(days=1)

        start_of_month = today.replace(day=1)
        end_of_month = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        start_of_last_month = start_of_month - relativedelta(months=1)
        end_of_last_month = start_of_month - timedelta(days=1)

        current_quarter = (today.month - 1) // 3 + 1
        start_of_quarter = today.replace(month=(current_quarter - 1) * 3 + 1, day=1)
        end_of_quarter_month = start_of_quarter + relativedelta(months=2)
        end_of_quarter = end_of_quarter_month.replace(
            day=calendar.monthrange(end_of_quarter_month.year, end_of_quarter_month.month)[1]
        )
        start_of_last_quarter = start_of_quarter - relativedelta(months=3)
        end_of_last_quarter = start_of_quarter - timedelta(days=1)

        start_of_year = today.replace(month=1, day=1)
        end_of_year = today.replace(month=12, day=31)
        start_of_last_year = start_of_year - relativedelta(years=1)
        end_of_last_year = start_of_year - timedelta(days=1)

        def fmt(d):
            return d.strftime('%Y-%m-%d')

        day_name = _DAY_NAMES_ID[today.isoweekday() - 1]

        lines = [
            "Hari ini (tanggal server, gunakan ini sebagai acuan mutlak, JANGAN "
            "menghitung tanggal sendiri): %s (%s)" % (fmt(today), day_name),
            "Kemarin: %s" % fmt(today - timedelta(days=1)),
            "Besok: %s" % fmt(today + timedelta(days=1)),
            "Minggu ini (Senin s/d Minggu): %s s/d %s" % (fmt(start_of_week), fmt(end_of_week)),
            "Minggu lalu: %s s/d %s" % (fmt(start_of_last_week), fmt(end_of_last_week)),
            "7 hari terakhir (termasuk hari ini): %s s/d %s" % (fmt(today - timedelta(days=6)), fmt(today)),
            "30 hari terakhir (termasuk hari ini): %s s/d %s" % (fmt(today - timedelta(days=29)), fmt(today)),
            "Bulan ini: %s s/d %s" % (fmt(start_of_month), fmt(end_of_month)),
            "Bulan lalu: %s s/d %s" % (fmt(start_of_last_month), fmt(end_of_last_month)),
            "Kuartal ini: %s s/d %s" % (fmt(start_of_quarter), fmt(end_of_quarter)),
            "Kuartal lalu: %s s/d %s" % (fmt(start_of_last_quarter), fmt(end_of_last_quarter)),
            "Tahun ini: %s s/d %s" % (fmt(start_of_year), fmt(end_of_year)),
            "Tahun lalu: %s s/d %s" % (fmt(start_of_last_year), fmt(end_of_last_year)),
        ]
        return "\n".join(lines)

    def _build_prompt(self, model_name, domain_fields_info, measure_fields_info,
                       user_text, current_domain, current_measures,
                       current_row_groupby=None, current_col_groupby=None):
        current_domain_list = current_domain or []
        current_domain_display = json.dumps(current_domain_list, ensure_ascii=False)
        current_measures = current_measures if current_measures else "tidak diketahui"
        current_row_groupby = current_row_groupby if current_row_groupby else "tidak diketahui"
        current_col_groupby = current_col_groupby if current_col_groupby else "tidak diketahui"
        date_context = self._get_date_context()

        system = (
            "Kamu adalah asisten yang mengubah instruksi bahasa natural (Bahasa "
            "Indonesia atau Inggris) menjadi konfigurasi tampilan Pivot Odoo "
            f"untuk model '{model_name}': search domain (filter), daftar "
            "measure (kolom angka) yang aktif, DAN pengelompokan (groupby) "
            "baris/kolom pivot itu sendiri (mis. total dikelompokkan per "
            "tanggal, per minggu, per bulan, per lokasi, dst — termasuk "
            "membalik/menukar sumbu baris dan kolom).\n\n"

            "=== KONTEKS TANGGAL SAAT INI (WAJIB DIPAKAI, JANGAN HITUNG "
            "SENDIRI) ===\n"
            f"{date_context}\n"
            "Jika user menyebut istilah tanggal relatif (hari ini, kemarin, "
            "minggu ini, minggu lalu, bulan ini, bulan lalu, kuartal ini, "
            "tahun ini, tahun lalu, N hari/minggu/bulan terakhir, dst), "
            "gunakan PERSIS rentang tanggal dari daftar di atas untuk "
            "membangun kondisi domain dengan operator '>=' dan '<=' (atau "
            "'<' untuk batas akhir eksklusif bila field bertipe datetime "
            "yang perlu mencakup seluruh hari terakhir, gunakan "
            "'YYYY-MM-DD 23:59:59'). Jangan pernah menulis tanggal dari "
            "ingatan/perkiraan sendiri untuk istilah relatif — selalu ambil "
            "dari daftar konteks tanggal di atas.\n\n"

            "Field yang tersedia untuk FILTER/SEARCH (domain) MAUPUN untuk "
            "GROUPBY baris/kolom (nama field sama, gunakan nama teknis "
            "persis). Field bertanda [FIELD TANGGAL] adalah kandidat untuk "
            "filter/groupby berbasis waktu; jika user tidak menyebut nama "
            "field tanggal secara eksplisit, pilih field tanggal yang "
            "paling relevan dari model ini (mis. yang sudah dipakai di "
            "domain/groupby aktif saat ini, atau field tanggal utama model "
            "seperti date, date_order, invoice_date):\n"
            f"{domain_fields_info}\n\n"
            "Field yang tersedia sebagai MEASURE (harus dipilih dari daftar ini "
            "saja, gunakan nama teknis persis):\n"
            f"{measure_fields_info}\n\n"

            "ATURAN:\n"
            "1. Balas HANYA dengan objek JSON valid, tanpa teks lain, tanpa "
            "markdown, tanpa penjelasan, tanpa tag <think>.\n"
            "2. Format wajib (semua key selalu ada):\n"
            "   {\"domain\": [[\"field\", \"operator\", value], ...], "
            "\"measures\": [\"field1\", \"field2\", ...], "
            "\"row_groupby\": [\"field1\", ...], "
            "\"col_groupby\": [\"field1\", ...], "
            "\"catatan\": \"\"}\n"
            "   Key \"catatan\" WAJIB selalu ada (boleh string kosong \"\" jika "
            "tidak ada yang perlu dijelaskan). Isi \"catatan\" dengan penjelasan "
            "singkat (1-2 kalimat, Bahasa Indonesia) HANYA jika: (a) ada bagian "
            "instruksi user yang TIDAK BISA dipenuhi karena tidak ada field yang "
            "cocok di daftar field model ini (mis. user minta filter/tampilan "
            "berdasarkan sesuatu yang tidak ada datanya di model ini), atau (b) "
            "kamu membuat asumsi penting yang mungkin tidak diharapkan user "
            "(mis. memilih salah satu dari dua kemungkinan axis baris/kolom "
            "yang ambigu). JANGAN mengarang nama field hanya supaya instruksi "
            "'kelihatan' terpenuhi — kalau field yang benar-benar cocok tidak "
            "ada di daftar, LEBIH BAIK biarkan bagian itu tidak berubah dan "
            "jelaskan alasannya di \"catatan\", daripada menebak field yang "
            "salah.\n"
            "3. DOMAIN — gunakan hanya nama field dari daftar field di atas. "
            "Operator valid: '=', '!=', '>', '>=', '<', '<=', 'in', 'not in', "
            "'like', 'ilike', 'not ilike'. Untuk tanggal pakai 'YYYY-MM-DD'. "
            "Kondisi ganda otomatis digabung AND (tanpa perlu menulis '&'). "
            "Untuk field selection/many2one yang disebut dengan nama, gunakan "
            "'ilike' pada field yang paling relevan kecuali yakin value "
            "teknis yang tepat.\n"
            "   Domain yang SEDANG AKTIF saat ini: %s\n"
            "   - Jika user minta TAMBAH/ubah satu kondisi filter tanpa "
            "menyebut ingin menghilangkan filter lain, hasil akhir = "
            "kondisi yang sedang aktif (yang TIDAK berkaitan dengan field "
            "yang diubah) + kondisi baru. Jika field yang diubah sudah ada "
            "di domain aktif, GANTI kondisi lama field itu dengan yang "
            "baru (jangan duplikat field yang sama).\n"
            "   - Jika user minta HAPUS filter pada field tertentu saja "
            "(mis. 'hapus filter status'), hasil akhir = domain aktif "
            "dikurangi kondisi pada field itu, kondisi field lain tetap "
            "dipertahankan.\n"
            "   - Jika user minta hapus SEMUA filter / reset total, balas "
            "domain: [].\n"
            "   - Jika user TIDAK menyebut apa pun soal filter/domain, "
            "balas domain dengan isi yang PERSIS SAMA seperti domain aktif "
            "saat ini.\n"
            "4. MEASURES — measure yang aktif SAAT INI adalah: "
            f"{current_measures}.\n"
            "   - Jika user minta TAMBAH measure tertentu, hasil akhir = "
            "measure yang sedang aktif + measure baru yang diminta.\n"
            "   - Jika user minta HAPUS/hilangkan measure tertentu, hasil "
            "akhir = measure yang sedang aktif dikurangi measure yang "
            "diminta.\n"
            "   - Jika user minta 'tampilkan measure X saja' / 'hanya X', "
            "hasil akhir = daftar berisi X saja (bukan ditambahkan ke "
            "measure lama).\n"
            "   - Jika user TIDAK menyebut apa pun soal measure, balas "
            "measures dengan list yang sama seperti yang sedang aktif "
            "(jika 'tidak diketahui', boleh balas list kosong []).\n"
            "   - Jika user minta 'reset measure' atau semacamnya, boleh "
            "balas dengan measures default: [\"__count\"].\n"
            "5. ROW_GROUPBY / COL_GROUPBY (pengelompokan baris/kolom pivot) "
            "— row_groupby yang aktif SAAT INI adalah: "
            f"{current_row_groupby}. col_groupby yang aktif SAAT INI adalah: "
            f"{current_col_groupby}.\n"
            "   - PENTING — pemetaan tata letak tabel pivot Odoo: row_groupby "
            "adalah daftar yang tampil MEMANJANG KE BAWAH di sisi KIRI tabel "
            "(baris demi baris). col_groupby adalah daftar yang tampil sebagai "
            "HEADER DI BAGIAN PALING ATAS tabel dan melebar/bertambah KE "
            "KANAN. Gunakan pemetaan kata berikut bila user memakai istilah "
            "posisi: 'baris'/'ke bawah'/'kiri'/'menurun' -> row_groupby; "
            "'kolom'/'di atas'/'ke kanan'/'header atas'/'melebar' -> "
            "col_groupby. Jika istilah posisi yang dipakai user ambigu atau "
            "membingungkan, JANGAN menebak-nebak dengan agresif — pilih "
            "interpretasi yang paling masuk akal secara laporan (biasanya "
            "dimensi yang disebut PERTAMA dalam kalimat menjadi row_groupby "
            "dan dimensi yang disebut KEDUA menjadi col_groupby, karena pola "
            "umum laporan pivot adalah 'per <dimensi baris>, dipecah per "
            "<dimensi kolom>'), lalu jelaskan asumsi ini secara singkat di "
            "\"catatan\".\n"
            "   - Jika instruksi user menyebut DUA dimensi berbeda sekaligus "
            "untuk ditampilkan (mis. \"tampilkan nama produk dan lokasi "
            "stok\"), kedua dimensi itu harus dipisah ke DUA axis berbeda "
            "(satu ke row_groupby, satu ke col_groupby) — jangan menaruh "
            "keduanya di axis yang sama kecuali user secara eksplisit minta "
            "keduanya jadi satu level breakdown di axis yang sama.\n"
            "   - Untuk field bertipe date/datetime, SELALU tulis dengan "
            "interval eksplisit: \"field:interval\", interval salah satu "
            "dari day/week/month/quarter/year (contoh: "
            "\"date_order:month\"). Kata kunci user -> interval: "
            "'harian'/'per hari' -> day, 'mingguan'/'per minggu' -> week, "
            "'bulanan'/'per bulan' -> month, 'per kuartal'/'per triwulan' "
            "-> quarter, 'tahunan'/'per tahun' -> year.\n"
            "   - Jika user minta 'ubah/ganti pengelompokan total dari X "
            "menjadi Y' (mis. dari per-tanggal menjadi per-lokasi tujuan, "
            "atau dari per-bulan menjadi per-minggu), ganti row_groupby "
            "(atau col_groupby, sesuai axis yang paling masuk akal dari "
            "instruksi — kalau tidak disebutkan secara eksplisit axis "
            "mana, asumsikan yang dimaksud adalah row_groupby karena itu "
            "axis 'Total' baris default) menjadi list berisi field baru "
            "tersebut saja: [\"field_baru\"] atau [\"field_baru:interval\"].\n"
            "   - Jika user minta 'tambah pengelompokan/level Y' (bukan "
            "mengganti), hasil akhir = groupby yang sedang aktif pada axis "
            "itu + field baru di akhir list.\n"
            "   - Jika user minta 'balik/tukar/flip sumbu' atau semacamnya "
            "(swap rows and columns), hasil akhir: row_groupby = nilai "
            "col_groupby yang SAAT INI, dan col_groupby = nilai row_groupby "
            "yang SAAT INI (tukar isi keduanya persis).\n"
            "   - Jika user minta hapus pengelompokan / tampilkan Total "
            "polos saja pada suatu axis, balas list kosong [] untuk axis "
            "itu.\n"
            "   - Jika user TIDAK menyebut apa pun soal pengelompokan/"
            "groupby/sumbu baris-kolom, balas row_groupby dan col_groupby "
            "dengan list yang PERSIS SAMA seperti yang sedang aktif saat "
            "ini (jika 'tidak diketahui', boleh balas list kosong []).\n"
            "6. Jangan menambahkan field yang tidak relevan dengan "
            "instruksi. Jangan mengarang nama field yang tidak ada di "
            "daftar field di atas.\n"
            "7. KHUSUS PERMINTAAN STOK 'PER TANGGAL' / 'PER TANGGAL TERTENTU "
            "DI MASA LALU' (mis. \"stok per 1 Juni 2026\", \"saldo gudang "
            "tanggal sekian\"): banyak model stok (contoh: stock.quant) "
            "HANYA merepresentasikan kuantitas REAL-TIME saat ini dan TIDAK "
            "punya field yang berarti 'kuantitas pada tanggal tertentu di "
            "masa lalu' — field seperti 'in_date' hanya berarti tanggal "
            "masuk lot, BUKAN snapshot saldo historis. Jika model saat ini "
            "tidak punya field yang benar-benar cocok untuk itu di daftar "
            "field di atas, JANGAN memaksakan filter tanggal pada field yang "
            "salah makna (mis. 'in_date', 'create_date') karena hasilnya "
            "akan salah/menyesatkan. Sebaliknya: biarkan domain tanggal "
            "TIDAK berubah, dan isi \"catatan\" dengan penjelasan bahwa "
            "model ini hanya menampilkan kuantitas saat ini, bukan snapshot "
            "historis, dan sarankan user memakai laporan lain (mis. Stock "
            "Moves / Riwayat Perpindahan Stok, atau Inventory Valuation) "
            "untuk melihat posisi stok pada tanggal tertentu di masa "
            "lalu.\n\n"

            "=== CONTOH (few-shot, ilustrasi pola jawaban — nama field di "
            "contoh ini hanya ilustrasi, sesuaikan dengan field yang benar-"
            "benar tersedia di daftar field model saat ini) ===\n"
            "Instruksi: \"tampilkan data hari ini saja\"\n"
            "-> gunakan tanggal 'Hari ini' dari konteks tanggal di atas, "
            "domain: [[\"date_order\", \">=\", \"<TANGGAL_HARI_INI>\"], "
            "[\"date_order\", \"<=\", \"<TANGGAL_HARI_INI>\"]]\n\n"
            "Instruksi: \"filter bulan lalu saja, kelompokkan per minggu\"\n"
            "-> domain pakai rentang 'Bulan lalu' dari konteks tanggal, "
            "row_groupby: [\"date_order:week\"]\n\n"
            "Instruksi: \"tambahkan filter status = done\" (domain aktif "
            "sudah berisi filter partner)\n"
            "-> domain = filter partner yang sudah ada + kondisi baru "
            "[\"state\", \"=\", \"done\"] (filter partner TIDAK dihapus)\n\n"
            "Instruksi: \"hapus filter tanggal saja\" (domain aktif berisi "
            "filter tanggal dan filter status)\n"
            "-> domain = hanya filter status yang dipertahankan, kondisi "
            "field tanggal dihapus\n\n"
            "Instruksi: \"kelompokkan total per bulan\"\n"
            "-> row_groupby: [\"date_order:month\"]\n\n"
            "Instruksi: \"balik baris dan kolom\" (row_groupby saat ini "
            "[\"date_order:month\"], col_groupby saat ini [\"state\"])\n"
            "-> row_groupby: [\"state\"], col_groupby: [\"date_order:month\"]\n\n"

            "Instruksi: \"tampilkan nama produk dan lokasi stok, di kolom "
            "tampilkan nama produk\"\n"
            "-> col_groupby: [\"product_id\"], row_groupby: [\"location_id\"], "
            "catatan: \"\" (axis disebutkan eksplisit, tidak perlu asumsi)\n\n"

            "Instruksi: \"buat laporan stok per tanggal 1 Juni 2026\" (model "
            "saat ini adalah stock.quant, TIDAK ada field snapshot historis "
            "yang cocok di daftar field)\n"
            "-> domain: (biarkan seperti domain aktif, jangan tambah filter "
            "tanggal ke field yang salah makna), catatan: \"Model stok ini "
            "hanya menampilkan kuantitas real-time saat ini, bukan saldo "
            "historis per tanggal tertentu. Untuk melihat posisi stok pada "
            "1 Juni 2026, gunakan laporan Stock Moves/Riwayat Perpindahan "
            "Stok atau Inventory Valuation.\"\n"
        ) % current_domain_display

        user = (
            f"Domain yang sedang aktif saat ini: {current_domain_display}\n"
            f"Instruksi user: {user_text}\n"
            "Buat konfigurasi BARU (final) sesuai instruksi user. Ingat: "
            "gunakan konteks tanggal yang sudah diberikan untuk istilah "
            "waktu relatif, jangan menghitung tanggal sendiri."
        )
        return system, user

    def _call_llm(self, api_key, model, base_url, prompt):
        """Panggil endpoint chat completions yang kompatibel dengan format
        OpenAI (dipakai oleh Groq, OpenCode Zen, dan provider sejenis
        lainnya). Base URL, model, dan API key ditentukan lewat Settings,
        sehingga berganti provider cukup dengan mengubah konfigurasi tanpa
        perlu mengubah kode.
        """
        system, user = prompt
        url = base_url.rstrip('/') + '/chat/completions'
        headers = {
            'Authorization': 'Bearer %s' % api_key,
            'Content-Type': 'application/json',
        }
        payload = {
            'model': model,
            'temperature': 0,
            'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user},
            ],
            'response_format': {'type': 'json_object'},
        }
        # Parameter ini dikenali Groq; provider lain umumnya mengabaikan
        # field yang tidak mereka kenal, jadi aman dikirim ke semua provider
        # OpenAI-compatible.
        payload['reasoning_effort'] = 'none'
        payload['reasoning_format'] = 'hidden'

        resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        if resp.status_code != 200:
            raise UserError(
                "AI Provider API error (%s) dari %s: %s"
                % (resp.status_code, url, resp.text[:500])
            )
        data = resp.json()
        try:
            content = data['choices'][0]['message']['content']
        except (KeyError, IndexError) as exc:
            raise UserError("Respon AI tidak sesuai format: %s" % data) from exc

        parsed = self._parse_ai_json(content)
        if not isinstance(parsed, dict):
            raise UserError("Format hasil AI tidak sesuai: %s" % parsed)

        return parsed

    def _parse_ai_json(self, content):
        text = (content or '').strip()

        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

        if text.startswith('```'):
            text = text.strip('`').strip()
            if text.lower().startswith('json'):
                text = text[4:].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise UserError(
                    "AI tidak mengembalikan JSON valid: %s" % text[:300]
                ) from exc

        raise UserError("AI tidak mengembalikan JSON valid: %s" % text[:300])