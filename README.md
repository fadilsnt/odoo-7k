# Dokumentasi Modul (Ringkas)

Dokumen ini menyajikan ringkasan modul yang terdapat pada workspace beserta model utama, relasi antar-model, dan catatan perubahan basis data kustom yang dihasilkan oleh implementasi logic dan fungsi pada setiap modul.

Informasi disusun berdasarkan telaah terhadap berkas-berkas `models/` setiap modul; untuk rincian implementasi silakan merujuk pada berkas sumber masing-masing modul.

---

## Ringkasan per modul

1. access_roles
   - Model utama:
     - `access.role` — menyimpan peran akses; atribut penting meliputi `name`, `user_ids` (Many2many → `res.users`), `role_management_id` (Many2one → `role.management`), dan `groups_ids` (Many2many → `res.groups`).
     - `role.management` — menyimpan konfigurasi role dan pembatasan sistem; atribut meliputi `domain_ids`, `role_ids` (Many2many → `access.role`), `menu_ids` (Many2many → `ir.ui.menu`), serta One2many ke `field.access` untuk pengaturan rinci.
     - `field.access` — menyimpan konfigurasi akses tingkat model/field/button/tab/report/action; terhubung ke `ir.model`, `button.registry`, `tab.registry`, `filter.registry`, `groupby.registry`, `ir.actions.report`, dan `ir.actions.server`.
   - Relasi dan logika utama:
     - Mekanisme reified group fields: field boolean/selection yang dipetakan ke `res.groups` dan pembaruan view XML secara dinamis melalui `res.groups._update_role_groups_view`.
     - Sinkronisasi otomatis antara `res.users` dan `access.role` melalui field `access_role_id` dan pengelolaan koleksi `user_ids`.
   - Dampak pada basis data: penambahan tabel entitas baru (`access.role`, `role.management`, `field.access`) beserta tabel relasi Many2many terkait.

2. fjr_custom_stock
   - Model dan ekstensi utama:
     - `product.grade` — entitas penanda grade produk (`name`).
     - Ekstensi `product.template` / `product.product` — penambahan atribut seperti `container_capacity`, `product_grade_id`, `sales_person_ids` (Many2many → `res.users`), serta penyesuaian perhitungan kuantitas sesuai konteks gudang.
     - Ekstensi `stock.move`, `stock.move.line`, `stock.quant`, `stock.picking`, `stock.warehouse` — penambahan atribut terkait kapasitas kontainer, kuantitas bernilai (`valued_quantity`), rata-rata (`average_quantity`), `actual_date`, serta pembatasan akses/gudang melalui `allowed_warehouse_ids`.
     - Ekstensi `res.users` — penambahan `allowed_warehouse_ids` (Many2many → `stock.warehouse`) dan flag `customer` dengan sinkronisasi grup.
   - Relasi dan logika utama:
     - Relasi `product_grade_id` menuju `product.grade` (Many2one).
     - Filterisasi pencarian stock berdasarkan `allowed_warehouse_ids` di override `_search` pada beberapa model.
     - Perhitungan `container_quantity` (quantity ÷ container_capacity) diterapkan pada beberapa model untuk konversi box/kontainer.
   - Dampak pada basis data: penambahan tabel `product_grade`, relasi M2M antara pengguna dan gudang (`res_users_allowed_stock_warehouse_rel`), serta kolom tambahan pada tabel produk dan stok.

3. hd_inventory_custom
   - Model dan ekstensi utama:
     - `product.template` — penambahan `owner_id` (Many2one → `res.partner`), `consume_product_ids` (Many2many → `product.product`), dan flag `is_cl`.
     - Ekstensi `stock.move` dan `stock.quant` — penambahan atribut tonase (`tonase_asli`, `reserved_tonase_asli`, `inventory_tonase_asli_*`), `owner_id`, dan `sales_person_ids`, serta logika propagasi tonase pada operasi inventory.
   - Relasi dan logika utama:
     - `consume_product_ids` merepresentasikan produk yang dikonsumsi otomatis ketika produk terkait diterima (relasi M2M `product_template_consume_rel`).
     - Tonase ditambahkan sebagai atribut kuantitas khusus dan dipertahankan/diupdate pada operasi create/write/inventory.
   - Dampak pada basis data: M2M `product_template_consume_rel` dan kolom tambahan untuk menyimpan nilai tonase dan owner pada tabel stok.

4. report-stock-delivery (submodul)
   - `repack_stock`:
     - Menambahkan model `stock.repack.line` dan `stock.repack.output` untuk proses repacking pada `stock.picking`.
     - Menyediakan alur pembuatan `stock.move.line` dan pengisian `move_ids_without_package` saat repack.
   - `export_stock_report`:
     - Menyediakan report abstract (`export.stock.report.*`) dan wizard untuk parameter laporan.
     - Ekstensi `stock.move` menambah field `no_cont` dan `keterangan` serta mempengaruhi logika penggabungan move (prevent merge when `no_cont` differs).
     - Logika laporan melakukan agregasi per picking dan move_line, menghitung box/kontainer berdasarkan `container_capacity` dan konversi UoM.
   - `hide_menu_user`:
     - Menyediakan ekstensi pada `res.users` untuk pengaturan visibilitas menu.
   - Dampak pada basis data: penambahan tabel repack dan tabel bantu laporan, serta kolom tambahan pada `stock.move`.

5. query_deluxe
   - Model utama: `querydeluxe` — menyimpan query SQL mentah (`name`), hasil (`html`) dan informasi `rowcount`.
   - Logika: eksekusi SQL mentah melalui `self.env.cr.execute()` dan pembentukan output HTML; fitur ini memiliki risiko eksekusi SQL langsung sehingga harus digunakan dengan hati-hati.
   - Dampak pada basis data: penambahan tabel `querydeluxe`.

6. report_pdf_options
   - Menyediakan ekstensi pada aksi/report PDF (`ir_actions.py`) untuk menambah opsi terkait perilaku pembuatan PDF.
   - Dampak pada basis data: umumnya perubahan ringan pada `ir.actions` atau penambahan model konfigurasi.

7. report_xlsx
   - Menyediakan helper/report untuk ekspor XLSX melalui ekstensi model laporan.
   - Dampak pada basis data: perluasan fungsionalitas reporting, biasanya tanpa perubahan skema besar.

8. modul UI (muk*web*\*)
   - Modul-modul UI menambah ekstensi seperti `res_config_settings`, `res_company`, penyesuaian `res_users`, serta controller `ir_http` dan asset editor.
   - Tujuan utama adalah kustomisasi antarmuka, tema, dan aset front-end; perubahan basis data biasanya terbatas pada pengaturan dan metadata asset.

## Perubahan skema basis data (ringkas)

- Contoh tabel/entitas baru: `access_role`, `role_management`, `field_access`, `product_grade`, `stock_repack_line`, `stock_repack_output`, `querydeluxe`, serta M2M relasi seperti `res_users_allowed_stock_warehouse_rel` dan `product_template_consume_rel`.
- Penambahan kolom pada tabel eksisting: atribut pada `stock.move` (`container_quantity`, `valued_quantity`, `average_quantity`, `no_cont`, `keterangan`, `owner_id`, `tonase_asli`, dll.), `stock.move.line` (`container_quantity`, `product_grade_id`), `stock.quant` (kolom tonase), serta perluasan pada `product.template`.

## Catatan implementasi penting

- Beberapa model mengoverride `_search` untuk menerapkan pembatasan berdasarkan `env.user.allowed_warehouse_ids`, sehingga hasil pencarian dan laporan dapat berbeda tergantung hak akses pengguna.
- Modul `access_roles` menghasilkan field reified dari `res.groups` dan memodifikasi arsitektur view (`ir.ui.view.arch`) secara dinamis untuk menampilkan field-field tersebut.
- Modul `query_deluxe` mengeksekusi SQL mentah pada database; fitur ini berpotensi berisiko dan harus dikelola dengan kehati-hatian.
- Konversi unit dan perhitungan berdasarkan kapasitas kontainer (`container_capacity`) digunakan di beberapa lokasi, termasuk laporan ekspor.

## Rekomendasi tindak lanjut

- Verifikasi dan dokumentasikan skema model secara lengkap dengan memeriksa direktori `access_roles/models` dan `fjr_custom_stock/models` untuk referensi bidang yang lebih rinci.
- Pertimbangkan pembuatan diagram ER sederhana untuk memvisualisasikan relasi antar tabel kritis.

---

Dokumen ini disusun secara otomatis sebagai ringkasan. Apabila diinginkan, dokumentasi dapat dilengkapi dengan tautan ke berkas sumber atau diagram ER.

## Diagram ER per modul

Diagram ER (Mermaid) untuk modul-modul yang menambahkan relasi atau entitas basis data dibuat di `docs/diagrams/`:

- `docs/diagrams/access_roles.md`
- `docs/diagrams/fjr_custom_stock.md`
- `docs/diagrams/hd_inventory_custom.md`
- `docs/diagrams/report_stock_delivery_repack.md`
- `docs/diagrams/query_deluxe.md`

Silakan buka berkas-berkas tersebut untuk melihat diagram Mermaid yang merepresentasikan entitas dan relasi utama.
