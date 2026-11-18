import os
import json
import base64
import datetime
import requests
import pandas as pd
from pypdf import PdfReader
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from google.genai.errors import APIError

st.set_page_config(page_title="Multi-Agent Virtual Office - PLN Icon Plus", page_icon="🏢", layout="wide")

# --- KONFIGURASI PENYIMPANAN CLOUD (GITHUB) ---
GITHUB_REPO = "farhanismail996/Kantor-Aktivasi"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "") if "GITHUB_TOKEN" in st.secrets else ""
MEMORY_DIR = "user_memories"
os.makedirs(MEMORY_DIR, exist_ok=True)

def get_safe_username(username: str) -> str:
    return "".join(c for c in username.lower().strip() if c.isalnum() or c in ("_", "-"))

# --- FUNGSI BACA / TULIS FILE JSON KE GITHUB & LOKAL ---
def read_json_cloud(file_path: str, default_value: dict) -> dict:
    if GITHUB_TOKEN:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                decoded = base64.b64decode(res.json()["content"]).decode("utf-8")
                data = json.loads(decoded)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return data
        except Exception:
            pass

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return default_value

def write_json_cloud(file_path: str, data: dict, commit_msg: str):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if GITHUB_TOKEN:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        try:
            sha = None
            get_res = requests.get(url, headers=headers, timeout=5)
            if get_res.status_code == 200:
                sha = get_res.json().get("sha")

            encoded_content = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
            payload = {"message": commit_msg, "content": encoded_content}
            if sha:
                payload["sha"] = sha

            requests.put(url, headers=headers, json=payload, timeout=8)
        except Exception as e:
            st.toast(f"⚠️ Gagal sinkron ke Cloud: {e}")

def load_user_data(username: str) -> dict:
    safe_name = get_safe_username(username)
    return read_json_cloud(
        f"{MEMORY_DIR}/{safe_name}.json",
        {"pin": "", "index_pertanyaan": 0, "profil_selesai": False, "ringkasan_profil": "", "messages": []}
    )

def save_user_data(username: str, data: dict):
    safe_name = get_safe_username(username)
    write_json_cloud(f"{MEMORY_DIR}/{safe_name}.json", data, f"Update memori user: {safe_name}")

def load_team_workspace() -> dict:
    return read_json_cloud(
        f"{MEMORY_DIR}/team_workspace.json",
        {"shared_docs": [], "team_messages": []}
    )

def save_team_workspace(data: dict):
    write_json_cloud(f"{MEMORY_DIR}/team_workspace.json", data, "Update diskusi & dokumen tim")

def get_all_team_profiles() -> str:
    profil_tim = []
    if GITHUB_TOKEN:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{MEMORY_DIR}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                for item in res.json():
                    fname = item["name"]
                    if fname.endswith(".json") and fname != "team_workspace.json":
                        uname = fname.replace(".json", "")
                        udata = read_json_cloud(f"{MEMORY_DIR}/{fname}", {})
                        if udata.get("ringkasan_profil"):
                            profil_tim.append(f"### Anggota Tim: {uname.upper()}\n{udata['ringkasan_profil']}")
                if profil_tim:
                    return "\n\n".join(profil_tim)
        except Exception:
            pass

    for fname in os.listdir(MEMORY_DIR):
        if fname.endswith(".json") and fname != "team_workspace.json":
            uname = fname.replace(".json", "")
            udata = read_json_cloud(f"{MEMORY_DIR}/{fname}", {})
            if udata.get("ringkasan_profil"):
                profil_tim.append(f"### Anggota Tim: {uname.upper()}\n{udata['ringkasan_profil']}")
    return "\n\n".join(profil_tim) if profil_tim else "Belum ada profil anggota tim lain yang tersimpan."

# --- PELACAK TELEMETRI & STATUS AGENT ---
if "agent_telemetry" not in st.session_state:
    st.session_state.agent_telemetry = {
        "active_agents": [], # List agen yang sedang bekerja: ["sekretaris", "analis", "penulis", "fasilitator"]
        "task_desc": "Semua agen sedang bersantai di ruang istirahat menunggu instruksi.",
        "counts": {"sekretaris": 0, "analis": 0, "penulis": 0, "fasilitator": 0},
        "logs": []
    }

def catat_aktivitas_agent(agen_aktif: list, keterangan: str):
    st.session_state.agent_telemetry["active_agents"] = agen_aktif
    st.session_state.agent_telemetry["task_desc"] = keterangan
    for a in agen_aktif:
        if a in st.session_state.agent_telemetry["counts"]:
            st.session_state.agent_telemetry["counts"][a] += 1
    waktu = datetime.datetime.now().strftime("%H:%M:%S")
    st.session_state.agent_telemetry["logs"].insert(0, f"`[{waktu}]` **{', '.join([x.upper() for x in agen_aktif])}** — {keterangan}")
    st.session_state.agent_telemetry["logs"] = st.session_state.agent_telemetry["logs"][:15]

# --- KOMPONEN ANIMASI KANTOR VIRTUAL (HTML5 + CSS KEYFRAMES) ---
def render_virtual_office(active_agents: list, task_desc: str, compact: bool = False):
    """
    Merender kantor virtual interaktif dengan animasi karakter:
    - Jika agen ada di 'active_agents': karakter duduk di Meja Kerja, layar menyala, animasi mengetik.
    - Jika tidak: karakter berada di Ruang Istirahat / Pantry, animasi santai minum kopi & zzz.
    """
    agents_meta = [
        {
            "id": "sekretaris",
            "name": "Lead Sekretaris",
            "avatar": "👩‍💼",
            "role": "Router & Chat Cepat",
            "work_text": "Mengatur jadwal & merespons cepat...",
            "rest_text": "Minum kopi & cek memo..."
        },
        {
            "id": "analis",
            "name": "Sub-Agent Analis",
            "avatar": "🕵️‍♂️",
            "role": "Bedah Excel & PDF",
            "work_text": "Menghitung angka & anomali data...",
            "rest_text": "Istirahat di sofa pantry..."
        },
        {
            "id": "penulis",
            "name": "Sub-Agent Penulis",
            "avatar": "✍️",
            "role": "Laporan & Tabel Dinas",
            "work_text": "Menyusun tabel & format laporan...",
            "rest_text": "Santai baca koran pagi..."
        },
        {
            "id": "fasilitator",
            "name": "Fasilitator Tim",
            "avatar": "🤝",
            "role": "Diskusi Lintas User",
            "work_text": "Menyinkronkan diskusi tim...",
            "rest_text": "Ngobrol santai di lounge..."
        }
    ]

    cards_html = ""
    for ag in agents_meta:
        is_working = ag["id"] in active_agents
        status_class = "working" if is_working else "resting"
        badge_text = "🟢 SEDANG BEKERJA" if is_working else "☕ ISTIRAHAT"
        bubble_text = ag["work_text"] if is_working else ag["rest_text"]
        scene_icon = "💻⚡" if is_working else "🛋️☕"
        anim_char = "typing-bounce" if is_working else "chill-float"

        cards_html += f"""
        <div class="room-card {status_class}">
            <div class="room-header">
                <span class="room-title">{ag['name']}</span>
                <span class="badge {status_class}">{badge_text}</span>
            </div>
            <div class="room-stage">
                <div class="speech-bubble">{bubble_text}</div>
                <div class="character-wrap {anim_char}">
                    <span class="avatar">{ag['avatar']}</span>
                    <span class="prop">{scene_icon}</span>
                </div>
                <div class="desk-floor">
                    {'<div class="monitor-glow"></div>' if is_working else '<div class="coffee-steam">~ ~</div>'}
                </div>
            </div>
            <div class="room-footer">{ag['role']}</div>
        </div>
        """

    height_px = 235 if compact else 330

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        * {{ box-sizing: border-box; font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 0; }}
        body {{ background: transparent; color: #f8fafc; padding: 4px; }}
        .office-wrapper {{
            background: linear-gradient(145deg, #0f172a, #1e293b);
            border: 1px solid #334155;
            border-radius: 14px;
            padding: 14px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.35);
        }}
        .office-topbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px dashed #334155;
            font-size: 13px;
        }}
        .office-name {{ font-weight: 700; color: #38bdf8; letter-spacing: 0.4px; }}
        .office-status {{ color: #cbd5e1; font-style: italic; }}
        .grid-rooms {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
        }}
        @media (max-width: 768px) {{
            .grid-rooms {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        .room-card {{
            border-radius: 10px;
            padding: 10px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}
        /* TAMPILAN SAAT BEKERJA */
        .room-card.working {{
            background: linear-gradient(180deg, #1e3a8a 0%, #0f172a 100%);
            border: 1.5px solid #38bdf8;
            box-shadow: 0 0 15px rgba(56, 189, 248, 0.25);
        }}
        /* TAMPILAN SAAT ISTIRAHAT */
        .room-card.resting {{
            background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            opacity: 0.88;
        }}
        .room-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 4px;
            margin-bottom: 8px;
        }}
        .room-title {{ font-size: 12px; font-weight: 700; color: #f1f5f9; }}
        .badge {{
            font-size: 9px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 20px;
            white-space: nowrap;
        }}
        .badge.working {{ background: #065f46; color: #6ee7b7; border: 1px solid #10b981; }}
        .badge.resting {{ background: #334155; color: #cbd5e1; }}
        .room-stage {{
            height: {'110px' if compact else '165px'};
            background: rgba(15, 23, 42, 0.55);
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            position: relative;
            padding: 6px;
        }}
        .speech-bubble {{
            background: #f8fafc;
            color: #0f172a;
            font-size: 10px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 10px;
            margin-bottom: 8px;
            text-align: center;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            max-width: 95%;
        }}
        .character-wrap {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: {'26px' if compact else '34px'};
        }}
        .desk-floor {{
            width: 80%;
            height: 6px;
            margin-top: 6px;
            border-radius: 4px;
            background: #475569;
            position: relative;
        }}
        .monitor-glow {{
            width: 100%;
            height: 100%;
            background: #38bdf8;
            border-radius: 4px;
            animation: pulseGlow 1s infinite alternate;
        }}
        .coffee-steam {{
            position: absolute;
            top: -16px;
            right: 22%;
            font-size: 12px;
            color: #94a3b8;
            animation: steamUp 2s infinite ease-in-out;
        }}
        .room-footer {{
            margin-top: 8px;
            font-size: 10px;
            color: #94a3b8;
            text-align: center;
        }}
        /* ANIMASI KARAKTER BEKERJA (MENGETIK CEPAT) */
        @keyframes typingBounce {{
            0%, 100% {{ transform: translateY(0px) rotate(0deg); }}
            25% {{ transform: translateY(-4px) rotate(-3deg); }}
            75% {{ transform: translateY(-2px) rotate(3deg); }}
        }}
        .typing-bounce {{ animation: typingBounce 0.6s infinite ease-in-out; }}

        /* ANIMASI KARAKTER ISTIRAHAT (SANTAI) */
        @keyframes chillFloat {{
            0%, 100% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-3px); }}
        }}
        .chill-float {{ animation: chillFloat 2.8s infinite ease-in-out; }}

        @keyframes pulseGlow {{
            from {{ opacity: 0.4; box-shadow: 0 0 4px #38bdf8; }}
            to {{ opacity: 1; box-shadow: 0 0 12px #38bdf8; }}
        }}
        @keyframes steamUp {{
            0% {{ opacity: 0; transform: translateY(2px); }}
            50% {{ opacity: 0.8; }}
            100% {{ opacity: 0; transform: translateY(-8px); }}
        }}
    </style>
    </head>
    <body>
        <div class="office-wrapper">
            <div class="office-topbar">
                <span class="office-name">🏢 KANTOR VIRTUAL AI — PLN ICON PLUS SBU SUMBAGSEL</span>
                <span class="office-status">Status: {task_desc}</span>
            </div>
            <div class="grid-rooms">
                {cards_html}
            </div>
        </div>
    </body>
    </html>
    """
    components.html(html_code, height=height_px)

# --- FUNGSI EKSTRAKSI EXCEL, CSV & PDF ---
def ekstrak_isi_file(uploaded_file) -> str:
    nama_file = uploaded_file.name.lower()
    try:
        if nama_file.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
            ringkasan_angka = df.describe(include="all").to_string()
            return (
                f"=== FILE CSV: {uploaded_file.name} (Total {len(df)} baris, {len(df.columns)} kolom) ===\n"
                f"Nama Kolom: {', '.join(df.columns.astype(str))}\n\n"
                f"Statistik Ringkas:\n{ringkasan_angka}\n\n"
                f"Data Lengkap (maks 150 baris):\n{df.head(150).to_csv(index=False)}"
            )
        elif nama_file.endswith((".xlsx", ".xls")):
            excel_data = pd.read_excel(uploaded_file, sheet_name=None)
            hasil_sheets = [f"=== FILE EXCEL: {uploaded_file.name} (Jumlah Sheet: {len(excel_data)}) ==="]
            for nama_sheet, df in excel_data.items():
                hasil_sheets.append(
                    f"\n--- Sheet: '{nama_sheet}' ({len(df)} baris, {len(df.columns)} kolom) ---\n"
                    f"Kolom: {', '.join(df.columns.astype(str))}\n"
                    f"Data (maks 120 baris):\n{df.head(120).to_csv(index=False)}"
                )
            return "\n".join(hasil_sheets)
        elif nama_file.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            teks_halaman = [f"=== FILE PDF: {uploaded_file.name} (Total {len(reader.pages)} halaman) ==="]
            for idx, page in enumerate(reader.pages[:25]):
                isi = page.extract_text() or ""
                teks_halaman.append(f"\n--- Halaman {idx + 1} ---\n{isi}")
            return "\n".join(teks_halaman)
        else:
            return f"Format file {uploaded_file.name} tidak didukung."
    except Exception as e:
        return f"Gagal membaca file {uploaded_file.name}: {e}"

# --- HELPER PEMANGGILAN MODEL ---
def panggil_agent_aman(client, daftar_model: list, prompt: str, system_instruction: str, temperature: float = 0.2) -> str:
    error_terakhir = None
    for nama_model in daftar_model:
        try:
            res = client.models.generate_content(
                model=nama_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature
                )
            )
            return res.text
        except APIError as e:
            error_terakhir = e
            if e.code in [400, 404, 503]:
                continue
            raise e
    raise RuntimeError(f"Agent gagal merespons ({error_terakhir}).")

def stream_dengan_cadangan(client, daftar_model: list, contents, system_instruction: str, temperature: float = 0.3):
    error_terakhir = None
    for nama_model in daftar_model:
        try:
            respon_stream = client.models.generate_content_stream(
                model=nama_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature
                )
            )
            for chunk in respon_stream:
                if chunk.text:
                    yield chunk.text
            return
        except APIError as e:
            error_terakhir = e
            if e.code in [400, 404, 503]:
                continue
            raise e
    raise RuntimeError(f"Semua model gagal ({error_terakhir}). Periksa kembali API Key Anda.")

# --- DEFINISI MULTI-AGENT PIPELINE DENGAN ANIMASI REAL-TIME ---
def jalankan_tim_multi_agent(client, perintah: str, konteks_dokumen: str, profil_user: str, profil_tim: str, animasi_slot, is_team_mode: bool = False) -> str:
    # TAHAP 1: SUB-AGENT ANALIS DATA BEKERJA (Agent lain di ruang istirahat / fasilitator aktif)
    agen_tahap_1 = ["fasilitator", "analis"] if is_team_mode else ["sekretaris", "analis"]
    with animasi_slot.container():
        render_virtual_office(agen_tahap_1, "Tahap 1/2: Sub-Agent Analis sedang membedah data & angka...", compact=True)

    instruksi_analis = (
        "Anda adalah Sub-Agent Analis Data & Teknis senior di PLN Icon Plus SBU Sumbagsel. "
        "Tugas Anda HANYA membedah data mentah, menghitung angka/total/persentase dengan akurasi tinggi, "
        "dan mengekstrak poin temuan serta anomali. Jangan membuat basa-basi pembuka/penutup."
    )
    prompt_analis = (
        f"INSTRUKSI PENGGUNA:\n{perintah}\n\n"
        f"KONTEKS TIM:\n{profil_tim}\n\n"
        f"DATA / DOKUMEN YANG HARUS DIBEDAH:\n{konteks_dokumen if konteks_dokumen else 'Tidak ada file lampiran, lakukan analisis teknis/strategis mendalam berdasarkan instruksi.'}"
    )
    hasil_mentah_analis = panggil_agent_aman(
        client,
        ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"],
        prompt_analis,
        instruksi_analis,
        temperature=0.1
    )

    # TAHAP 2: SUB-AGENT PENULIS BEKERJA (Sub-Agent Analis kembali ke ruang istirahat!)
    agen_tahap_2 = ["fasilitator", "penulis"] if is_team_mode else ["sekretaris", "penulis"]
    with animasi_slot.container():
        render_virtual_office(agen_tahap_2, "Tahap 2/2: Sub-Agent Analis istirahat, Sub-Agent Penulis menyusun laporan...", compact=True)

    instruksi_penulis = (
        "Anda adalah Sub-Agent Penulis & Editor Laporan Eksekutif di PLN Icon Plus SBU Sumbagsel. "
        "Tugas Anda mengubah hasil analisis mentah dari Sub-Agent Analis menjadi dokumen/jawaban yang sangat rapi, "
        "menggunakan tabel Markdown jika ada perbandingan angka, serta menyesuaikan gaya bahasa dengan profil user berikut:\n"
        f"{profil_user or 'Gunakan bahasa profesional, ringkas, dan terstruktur.'}"
    )
    prompt_penulis = (
        f"PERMINTAAN AWAL USER:\n{perintah}\n\n"
        f"HASIL BEDAH TEKNIS DARI SUB-AGENT ANALIS:\n{hasil_mentah_analis}\n\n"
        "Susun laporan akhir yang siap disajikan kepada user:"
    )
    hasil_akhir_penulis = panggil_agent_aman(
        client,
        ["gemini-3.5-flash-lite", "gemini-3.5-flash"],
        prompt_penulis,
        instruksi_penulis,
        temperature=0.3
    )

    # TAHAP 3: SELESAI -> SEMUA AGEN KEMBALI ISTIRAHAT
    with animasi_slot.container():
        render_virtual_office([], "Tugas selesai! Semua agent kembali beristirahat di lounge.", compact=True)

    return hasil_akhir_penulis

# --- DAFTAR 10 PERTANYAAN ONBOARDING ---
DAFTAR_PERTANYAAN = [
    "1️⃣ Pertama, siapa **nama lengkap / panggilan** Anda dan apa **jabatan** Anda saat ini di **PLN Icon Plus SBU Sumbagsel**?",
    "2️⃣ Anda bertugas di **bidang atau divisi** mana (misalnya Aktivasi, Pemeliharaan/O&M, Penjualan, Perencanaan, atau lainnya)?",
    "3️⃣ **Area atau wilayah kerja Sumbagsel** mana saja (Sumsel, Jambi, Bengkulu, Lampung, atau Babel) yang menjadi tanggung jawab Anda?",
    "4️⃣ Apa **3 pekerjaan atau laporan rutin** (harian/mingguan) yang paling sering Anda kerjakan?",
    "5️⃣ Apa **target atau KPI utama** yang sedang paling krusial Anda kejar saat ini?",
    "6️⃣ **Jenis data atau dokumen** apa yang paling sering Anda olah (misalnya Excel tracking aktivasi, data POP/Gardu Induk, atau surat dinas)?",
    "7️⃣ Apa **kendala atau hambatan utama** di lapangan maupun kantor yang paling menyita waktu Anda?",
    "8️⃣ Bagaimana **gaya bahasa & format laporan** yang paling Anda sukai saat saya menyajikan hasil (poin-poin singkat, tabel ringkas, formal, atau santai)?",
    "9️⃣ **Aplikasi atau tools kerja** apa yang paling sering Anda gunakan sehari-hari (Excel/Pivot Table, Google Sheets, CRM internal, atau PowerPoint)?",
    "🔟 Terakhir, **tugas spesifik apa** yang paling ingin Anda delegasikan kepada saya agar langsung membantu pekerjaan Anda mulai hari ini?"
]

if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# ==========================================
# HALAMAN 1: LOGIN / DAFTAR USER BARU
# ==========================================
if not st.session_state.logged_in_user:
    st.title("🔐 Login Virtual Office AI — PLN Icon Plus")
    st.caption("SBU Sumbagsel • 4 Agen Spesialis & Ruang Diskusi Tim Kolaboratif")

    col1, col2 = st.columns([1, 1.2])
    with col1:
        with st.form("form_login"):
            st.subheader("Masuk ke Kantor Virtual")
            input_user = st.text_input("Username (misal: farhan, nana, dini):", placeholder="contoh: farhan")
            input_pin = st.text_input("PIN Keamanan (4-6 angka):", type="password", placeholder="contoh: 1234")
            submit_login = st.form_submit_button("Masuk / Buat Akun Baru", type="primary", use_container_width=True)

            if submit_login:
                uname = get_safe_username(input_user)
                if not uname or not input_pin:
                    st.error("Username dan PIN wajib diisi.")
                else:
                    with st.spinner("Menghubungkan ke Kantor Virtual..."):
                        existing = load_user_data(uname)
                    if existing["pin"] == "":
                        existing["pin"] = input_pin
                        save_user_data(uname, existing)
                        st.session_state.logged_in_user = uname
                        st.rerun()
                    elif existing["pin"] == input_pin:
                        st.session_state.logged_in_user = uname
                        st.rerun()
                    else:
                        st.error("PIN salah untuk username tersebut!")
    st.stop()

# ==========================================
# HALAMAN 2: WORKSPACE UTAMA (4 AGENT AKTIF)
# ==========================================
current_user = st.session_state.logged_in_user
if "cached_user_data" not in st.session_state or st.session_state.get("cached_username") != current_user:
    st.session_state.cached_user_data = load_user_data(current_user)
    st.session_state.cached_username = current_user

user_data = st.session_state.cached_user_data

with st.sidebar:
    st.header(f"👤 {current_user.capitalize()}")
    if GITHUB_TOKEN:
        st.caption("☁️ Cloud Sync Tim: **Aktif**")
    else:
        st.caption("⚠️ Cloud Sync Tim: **Nonaktif**")

    if st.button("🚪 Logout / Ganti Akun", use_container_width=True):
        st.session_state.logged_in_user = None
        st.session_state.pop("cached_user_data", None)
        st.rerun()

    st.markdown("---")
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password").strip()

    st.markdown("---")
    st.markdown("**Status Profil Anda:**")
    if user_data["profil_selesai"]:
        st.success("✅ Profil Terhubung ke Tim")
        with st.expander("📄 Lihat Resume Profil"):
            st.markdown(user_data["ringkasan_profil"])
    else:
        progres = user_data["index_pertanyaan"]
        st.info(f"💬 Kenalan ({progres}/10)")
        st.progress(progres / 10)

    st.download_button(
        label="💾 Unduh Backup Pribadi (.json)",
        data=json.dumps(user_data, ensure_ascii=False, indent=2),
        file_name=f"backup_memori_{current_user}.json",
        mime="application/json",
        use_container_width=True
    )

    if st.button("🔄 Ulangi Pertanyaan Profil", use_container_width=True):
        user_data["index_pertanyaan"] = 0
        user_data["profil_selesai"] = False
        user_data["ringkasan_profil"] = ""
        user_data["messages"] = []
        save_user_data(current_user, user_data)
        st.rerun()

if not api_key:
    st.warning("Masukkan **Gemini API Key** di sidebar kiri terlebih dahulu.")
    st.stop()

@st.cache_resource
def get_client(key: str):
    return genai.Client(api_key=key)

client = get_client(api_key)
MODEL_CEPAT = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]

# --- 3 TAB UTAMA (TERMASUK TAB KANTOR VIRTUAL ANIMASI) ---
tab_pribadi, tab_tim, tab_office = st.tabs([
    f"👩‍💼 Sekretaris & Tim Agent ({current_user.capitalize()})",
    "🤝 Ruang Diskusi & File Tim",
    "🏢 Kantor Virtual Agent (Live Animasi)"
])

# ==========================================================
# TAB 1: SEKRETARIS PRIBADI + DELEGASI SUB-AGENTS
# ==========================================================
with tab_pribadi:
    st.subheader(f"Ruang Kerja Pribadi — {current_user.capitalize()}")
    st.caption("Saat tugas dikirim, perhatikan animasi para Agent yang berpindah dari ruang istirahat ke meja kerja mereka!")

    if not user_data["messages"]:
        salam_awal = (
            f"Selamat datang, **{current_user.capitalize()}**! Saya **Lead Sekretaris AI** Anda di **PLN Icon Plus SBU Sumbagsel**.\n\n"
            f"Mari kenalan singkat **satu per satu** agar saya dan tim Sub-Agent paham ritme kerja Anda:\n\n"
            f"{DAFTAR_PERTANYAAN[0]}"
        )
        user_data["messages"].append({"role": "assistant", "content": salam_awal})
        save_user_data(current_user, user_data)

    for msg in user_data["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if "uploader_pribadi_key" not in st.session_state:
        st.session_state.uploader_pribadi_key = 0

    with st.expander("📎 Lampirkan file Excel / CSV / PDF (Dikerjakan Sub-Agent Analis & Penulis)", expanded=False):
        files_pribadi = st.file_uploader(
            "Pilih file untuk dibedah oleh tim Sub-Agent:",
            type=["xlsx", "xls", "csv", "pdf"],
            accept_multiple_files=True,
            key=f"file_pribadi_{st.session_state.uploader_pribadi_key}"
        )

    if files_pribadi:
        st.info(f"📎 **{len(files_pribadi)} file siap dibedah Sub-Agent:** {', '.join([f.name for f in files_pribadi])}")

    prompt_pribadi = st.chat_input(f"Ketik pesan atau tugas kerja untuk {current_user}...", key="input_pribadi")

    if prompt_pribadi:
        label_file = ""
        konteks_dok = ""
        if files_pribadi:
            label_file = f"\n\n*(📎 Lampiran: {', '.join([f.name for f in files_pribadi])})*"
            konteks_dok = "\n\n".join([ekstrak_isi_file(f) for f in files_pribadi])
            st.session_state.uploader_pribadi_key += 1

        user_data["messages"].append({"role": "user", "content": prompt_pribadi + label_file})
        with st.chat_message("user"):
            st.markdown(prompt_pribadi + label_file)

        with st.chat_message("assistant"):
            animasi_slot = st.empty()
            try:
                if not user_data["profil_selesai"] and not files_pribadi:
                    with animasi_slot.container():
                        render_virtual_office(["sekretaris"], f"Lead Sekretaris sedang mewawancarai {current_user}...", compact=True)

                    idx_next = user_data["index_pertanyaan"] + 1
                    if idx_next < len(DAFTAR_PERTANYAAN):
                        pertanyaan_berikutnya = DAFTAR_PERTANYAAN[idx_next]
                        instruksi = (
                            f"Anda adalah Lead Sekretaris AI untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel. "
                            "Tanggapi jawaban user sebelumnya dalam 1 kalimat singkat, lalu tanyakan PERSIS pertanyaan berikut ini:\n\n"
                            f"{pertanyaan_berikutnya}"
                        )
                        konten = [
                            types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                            for m in user_data["messages"][-4:]
                        ]
                        hasil = st.write_stream(stream_dengan_cadangan(client, MODEL_CEPAT, konten, instruksi, 0.3))
                        catat_aktivitas_agent(["sekretaris"], f"Wawancara profil ({current_user}) ke-{idx_next + 1}")
                        user_data["index_pertanyaan"] = idx_next
                        user_data["messages"].append({"role": "assistant", "content": hasil})
                        save_user_data(current_user, user_data)
                        st.rerun()
                    else:
                        instruksi_resume = (
                            f"Susun **Resume Profil Kerja** yang rapi dan terstruktur untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel "
                            "berdasarkan seluruh jawaban pengenalan dalam percakapan ini."
                        )
                        konten_semua = [
                            types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                            for m in user_data["messages"]
                        ]
                        resume = st.write_stream(stream_dengan_cadangan(client, MODEL_CEPAT, konten_semua, instruksi_resume, 0.2))
                        catat_aktivitas_agent(["sekretaris"], f"Menyusun Resume Profil ({current_user})")
                        user_data["index_pertanyaan"] = 10
                        user_data["profil_selesai"] = True
                        user_data["ringkasan_profil"] = resume
                        user_data["messages"].append({"role": "assistant", "content": resume})
                        save_user_data(current_user, user_data)
                        st.rerun()

                else:
                    kata_kunci_berat = ["analisis", "analisa", "laporan", "rekap", "evaluasi", "hitung", "rasio", "tabel", "bandingkan", "buatkan surat", "memo"]
                    butuh_tim_agent = bool(files_pribadi) or (any(k in prompt_pribadi.lower() for k in kata_kunci_berat) and len(prompt_pribadi.split()) > 4)

                    if butuh_tim_agent:
                        profil_tim = get_all_team_profiles()
                        balasan = jalankan_tim_multi_agent(
                            client=client,
                            perintah=prompt_pribadi,
                            konteks_dokumen=konteks_dok,
                            profil_user=user_data["ringkasan_profil"],
                            profil_tim=profil_tim,
                            animasi_slot=animasi_slot,
                            is_team_mode=False
                        )
                        catat_aktivitas_agent(["sekretaris", "analis", "penulis"], f"Tugas berat/file oleh {current_user}")
                        st.markdown(balasan)
                    else:
                        with animasi_slot.container():
                            render_virtual_office(["sekretaris"], f"Lead Sekretaris merespons cepat {current_user}...", compact=True)

                        profil_rekan_tim = get_all_team_profiles()
                        instruksi_cepat = (
                            f"Anda adalah Lead Sekretaris AI untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel.\n"
                            f"PROFIL USER:\n{user_data['ringkasan_profil']}\n\n"
                            f"PROFIL REKAN TIM:\n{profil_rekan_tim}\n\n"
                            "Jawab obrolan atau pertanyaan singkat user secara cepat, ramah, dan langsung ke inti."
                        )
                        konten_aktif = [
                            types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                            for m in user_data["messages"][-10:]
                        ]
                        balasan = st.write_stream(stream_dengan_cadangan(client, MODEL_CEPAT, konten_aktif, instruksi_cepat, 0.3))
                        with animasi_slot.container():
                            render_virtual_office([], "Selesai! Lead Sekretaris kembali bersantai.", compact=True)
                        catat_aktivitas_agent(["sekretaris"], f"Chat instan dengan {current_user}")

                    user_data["messages"].append({"role": "assistant", "content": balasan})
                    save_user_data(current_user, user_data)
                    if files_pribadi:
                        st.rerun()

            except Exception as e:
                st.error(f"Detail Error: {e}")

# ==========================================================
# TAB 2: RUANG DISKUSI TIM (AGENT 4: FASILITATOR TIM)
# ==========================================================
with tab_tim:
    col_head1, col_head2 = st.columns([3, 1])
    with col_head1:
        st.subheader("🤝 Meja Diskusi & Dokumen Bersama Tim")
        st.caption("Ketik pesan biasa untuk chat sesama tim (Farhan, Nana, Dini), atau ketik **@ai** untuk memanggil Tim Agent.")
    with col_head2:
        if st.button("🔄 Refresh Chat & File Tim", use_container_width=True):
            st.rerun()

    team_data = load_team_workspace()

    if team_data["shared_docs"]:
        with st.expander(f"📂 Dokumen Diskusi Tim Aktif ({len(team_data['shared_docs'])} file)", expanded=True):
            for idx, doc in enumerate(team_data["shared_docs"]):
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"- **{doc['filename']}** *(diunggah oleh {doc['uploaded_by'].capitalize()} pada {doc['time']})*")
                if c2.button("Hapus", key=f"del_doc_{idx}"):
                    team_data["shared_docs"].pop(idx)
                    save_team_workspace(team_data)
                    st.rerun()

    if not team_data["team_messages"]:
        st.info("Belum ada obrolan di ruang tim. Mulailah menyapa rekan Anda atau unggah file Excel/PDF untuk didiskusikan bersama!")

    for tmsg in team_data["team_messages"]:
        sender = tmsg["sender"]
        is_ai = (sender == "Tim Agent AI")
        avatar_icon = "🤖" if is_ai else "👤"
        with st.chat_message("assistant" if is_ai else "user", avatar=avatar_icon):
            st.markdown(f"**{sender.capitalize()}** `({tmsg['time']})`:\n\n{tmsg['content']}")

    if "uploader_tim_key" not in st.session_state:
        st.session_state.uploader_tim_key = 0

    with st.expander("📎 Unggah Excel / PDF ke Meja Diskusi Bersama", expanded=False):
        files_tim = st.file_uploader(
            "File yang diunggah di sini bisa dibaca dan didiskusikan oleh semua anggota tim & AI:",
            type=["xlsx", "xls", "csv", "pdf"],
            accept_multiple_files=True,
            key=f"file_tim_{st.session_state.uploader_tim_key}"
        )

    if files_tim:
        st.info(f"📎 **{len(files_tim)} file akan dibagikan ke tim:** {', '.join([f.name for f in files_tim])}")

    prompt_tim = st.chat_input("Kirim pesan ke tim (awali dengan @ai jika ingin Tim Agent ikut menjawab)...", key="input_tim")

    if prompt_tim:
        waktu_sekarang = datetime.datetime.now().strftime("%d/%m %H:%M")
        label_lampiran = ""

        if files_tim:
            nama_list = []
            for f in files_tim:
                isi_ekstrak = ekstrak_isi_file(f)
                team_data["shared_docs"] = [d for d in team_data["shared_docs"] if d["filename"] != f.name]
                team_data["shared_docs"].append({
                    "filename": f.name,
                    "uploaded_by": current_user,
                    "time": waktu_sekarang,
                    "content": isi_ekstrak
                })
                nama_list.append(f.name)
            label_lampiran = f"\n\n*(📂 Membagikan file ke meja tim: {', '.join(nama_list)})*"
            st.session_state.uploader_tim_key += 1

        team_data["team_messages"].append({
            "sender": current_user,
            "time": waktu_sekarang,
            "content": prompt_tim + label_lampiran
        })
        save_team_workspace(team_data)

        with st.chat_message("user", avatar="👤"):
            st.markdown(f"**{current_user.capitalize()}** `({waktu_sekarang})`:\n\n{prompt_tim + label_lampiran}")

        panggil_ai = ("@ai" in prompt_tim.lower()) or bool(files_tim)

        if panggil_ai:
            with st.chat_message("assistant", avatar="🤖"):
                animasi_tim_slot = st.empty()
                try:
                    profil_semua = get_all_team_profiles()
                    semua_dok_tim = "\n\n".join([
                        f"[Dokumen Tim: {d['filename']} oleh {d['uploaded_by']}]\n{d['content']}"
                        for d in team_data["shared_docs"]
                    ]) or "Belum ada dokumen di meja diskusi."

                    riwayat_diskusi = "\n".join([
                        f"{m['sender']} ({m['time']}): {m['content']}"
                        for m in team_data["team_messages"][-15:]
                    ])

                    balasan_ai_tim = jalankan_tim_multi_agent(
                        client=client,
                        perintah=f"Permintaan terbaru dari {current_user} di ruang diskusi tim:\n{prompt_tim}\n\nLog percakapan tim sebelumnya:\n{riwayat_diskusi}",
                        konteks_dokumen=semua_dok_tim,
                        profil_user=f"Diskusi Tim PLN Icon Plus SBU Sumbagsel (Anggota: {profil_semua})",
                        profil_tim=profil_semua,
                        animasi_slot=animasi_tim_slot,
                        is_team_mode=True
                    )

                    catat_aktivitas_agent(["fasilitator", "analis", "penulis"], f"Diskusi tim dipicu oleh {current_user}")
                    st.markdown(balasan_ai_tim)

                    team_data["team_messages"].append({
                        "sender": "Tim Agent AI",
                        "time": datetime.datetime.now().strftime("%d/%m %H:%M"),
                        "content": balasan_ai_tim
                    })
                    save_team_workspace(team_data)
                except Exception as e:
                    st.error(f"Detail Error AI Tim: {e}")

        st.rerun()

# ==========================================================
# TAB 3: KANTOR VIRTUAL AGENT (ANIMASI RUANGAN & ISTIRAHAT)
# ==========================================================
with tab_office:
    st.subheader("🏢 Kantor Virtual Tim AI — Mode Real-Time & Simulasi")
    st.caption("Jika sedang ada tugas, Agent duduk di meja komputer dengan layar menyala. Jika tidak ada tugas, Agent beristirahat sambil minum kopi di lounge.")

    tele = st.session_state.agent_telemetry

    # Tombol kontrol simulasi agar bisa langsung melihat perbedaan animasi Bekerja vs Istirahat
    col_sim1, col_sim2, col_sim3, col_sim4 = st.columns(4)
    if col_sim1.button("☕ Semua Istirahat (Standby)", use_container_width=True):
        st.session_state.agent_telemetry["active_agents"] = []
        st.session_state.agent_telemetry["task_desc"] = "Tidak ada tugas aktif — semua agent istirahat santai."
    if col_sim2.button("👩‍💼 Simulasi Chat Cepat", use_container_width=True):
        st.session_state.agent_telemetry["active_agents"] = ["sekretaris"]
        st.session_state.agent_telemetry["task_desc"] = "Lead Sekretaris bekerja cepat, 3 sub-agent lainnya istirahat."
    if col_sim3.button("🔍 Simulasi Bedah Excel/PDF", use_container_width=True):
        st.session_state.agent_telemetry["active_agents"] = ["sekretaris", "analis", "penulis"]
        st.session_state.agent_telemetry["task_desc"] = "Tim Sub-Agent membedah data & menyusun laporan eksekutif!"
    if col_sim4.button("🤝 Simulasi Diskusi Tim", use_container_width=True):
        st.session_state.agent_telemetry["active_agents"] = ["fasilitator", "analis", "penulis"]
        st.session_state.agent_telemetry["task_desc"] = "Fasilitator Tim & Sub-Agent memproses diskusi Farhan, Nana, & Dini!"

    # Render Kantor Virtual Penuh
    render_virtual_office(
        active_agents=tele["active_agents"],
        task_desc=tele["task_desc"],
        compact=False
    )

    st.markdown("---")
    col_stat, col_log = st.columns([1, 1.3])
    with col_stat:
        st.markdown("#### 📊 Statistik Beban Kerja Hari Ini")
        counts = tele["counts"]
        s1, s2 = st.columns(2)
        s1.metric("👩‍💼 Lead Sekretaris", f"{counts['sekretaris']}x bertugas")
        s2.metric("🕵️‍♂️ Sub-Agent Analis", f"{counts['analis']}x bertugas")
        s1.metric("✍️ Sub-Agent Penulis", f"{counts['penulis']}x bertugas")
        s2.metric("🤝 Fasilitator Tim", f"{counts['fasilitator']}x bertugas")

    with col_log:
        st.markdown("#### 📜 Log Aktivitas Ruang Kerja (*Live Trace*)")
        if not tele["logs"]:
            st.info("Belum ada riwayat tugas di sesi ini. Coba kirim pesan di Tab 1/Tab 2 atau klik tombol Simulasi di atas.")
        else:
            for item_log in tele["logs"]:
                st.markdown(item_log)
