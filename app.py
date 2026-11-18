import os
import json
import base64
import datetime
import requests
import pandas as pd
from pypdf import PdfReader
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError

st.set_page_config(page_title="Multi-Agent Workspace - PLN Icon Plus", page_icon="🤖", layout="wide")

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

# --- PELACAK TELEMETRI & VISUALISASI AGENT ---
if "agent_telemetry" not in st.session_state:
    st.session_state.agent_telemetry = {
        "last_mode": "standby", # standby | fast_path | full_pipeline | team_collab
        "counts": {"sekretaris": 0, "analis": 0, "penulis": 0, "fasilitator": 0},
        "logs": []
    }

def catat_aktivitas_agent(mode: str, agen_aktif: list, keterangan: str):
    st.session_state.agent_telemetry["last_mode"] = mode
    for a in agen_aktif:
        if a in st.session_state.agent_telemetry["counts"]:
            st.session_state.agent_telemetry["counts"][a] += 1
    waktu = datetime.datetime.now().strftime("%H:%M:%S")
    st.session_state.agent_telemetry["logs"].insert(0, f"`[{waktu}]` **{mode.upper()}** — {keterangan}")
    st.session_state.agent_telemetry["logs"] = st.session_state.agent_telemetry["logs"][:15]

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

# --- DEFINISI MULTI-AGENT PIPELINE ---
def jalankan_tim_multi_agent(client, perintah: str, konteks_dokumen: str, profil_user: str, profil_tim: str, status_box) -> str:
    status_box.write("🔍 **Sub-Agent Analis Data (`gemini-3.5-flash`)** sedang membedah angka, tabel, & temuan teknis...")
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

    status_box.write("✍️ **Sub-Agent Penulis Laporan (`gemini-3.5-flash-lite`)** sedang menyusun format sesuai preferensi Anda...")
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
    st.title("🔐 Login Multi-Agent Workspace — PLN Icon Plus")
    st.caption("SBU Sumbagsel • 4 Agen Spesialis & Ruang Diskusi Tim Kolaboratif")

    col1, col2 = st.columns([1, 1.2])
    with col1:
        with st.form("form_login"):
            st.subheader("Masuk ke Ruang Kerja")
            input_user = st.text_input("Username (misal: farhan, nana, dini):", placeholder="contoh: farhan")
            input_pin = st.text_input("PIN Keamanan (4-6 angka):", type="password", placeholder="contoh: 1234")
            submit_login = st.form_submit_button("Masuk / Buat Akun Baru", type="primary", use_container_width=True)

            if submit_login:
                uname = get_safe_username(input_user)
                if not uname or not input_pin:
                    st.error("Username dan PIN wajib diisi.")
                else:
                    with st.spinner("Menghubungkan ke Cloud Workspace..."):
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

# --- 3 TAB UTAMA (TERMASUK TAB VISUALISASI AGENT) ---
tab_pribadi, tab_tim, tab_visual = st.tabs([
    f"👩‍💼 Sekretaris & Tim Agent ({current_user.capitalize()})",
    "🤝 Ruang Diskusi & File Tim",
    "🕸️ Visualisasi & Monitor Agent"
])

# ==========================================================
# TAB 1: SEKRETARIS PRIBADI + DELEGASI SUB-AGENTS
# ==========================================================
with tab_pribadi:
    st.subheader(f"Ruang Kerja Pribadi — {current_user.capitalize()}")
    st.caption("Obrolan ringan dijawab instan oleh Lead Sekretaris. Analisis file/laporan otomatis dikerjakan Sub-Agent Analis + Penulis.")

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
            try:
                if not user_data["profil_selesai"] and not files_pribadi:
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
                        catat_aktivitas_agent("fast_path", ["sekretaris"], f"Wawancara profil ({current_user}) pertanyaan ke-{idx_next + 1}")
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
                        catat_aktivitas_agent("fast_path", ["sekretaris"], f"Menyusun Resume Profil Kerja ({current_user})")
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
                        with st.status("🚀 Lead Sekretaris mendelegasikan tugas ke Sub-Agent...", expanded=True) as status_box:
                            profil_tim = get_all_team_profiles()
                            balasan = jalankan_tim_multi_agent(
                                client=client,
                                perintah=prompt_pribadi,
                                konteks_dokumen=konteks_dok,
                                profil_user=user_data["ringkasan_profil"],
                                profil_tim=profil_tim,
                                status_box=status_box
                            )
                            status_box.update(label="✅ Selesai dikerjakan oleh Sub-Agent Analis & Penulis", state="complete", expanded=False)
                        catat_aktivitas_agent("full_pipeline", ["sekretaris", "analis", "penulis"], f"Delegasi tugas berat/file oleh {current_user}")
                        st.markdown(balasan)
                    else:
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
                        catat_aktivitas_agent("fast_path", ["sekretaris"], f"Respon cepat langsung ke {current_user}")

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
                try:
                    with st.status("🤖 Fasilitator Tim & Sub-Agent Analis sedang memproses diskusi...", expanded=True) as status_tim:
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
                            status_box=status_tim
                        )
                        status_tim.update(label="✅ Analisis & Tindak Lanjut Tim Selesai", state="complete", expanded=False)

                    catat_aktivitas_agent("team_collab", ["fasilitator", "analis", "penulis"], f"Diskusi tim dipicu oleh {current_user}")
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
# TAB 3: VISUALISASI ARSITEKTUR & MONITOR 4 AGENT
# ==========================================================
with tab_visual:
    st.subheader("🕸️ Peta Arsitektur & Monitor Aktivitas Multi-Agent")
    st.caption("Visualisasi pembagian beban kerja real-time antara User, 4 Spesialis AI Agent, dan Cloud Memory GitHub.")

    tele = st.session_state.agent_telemetry
    last_mode = tele["last_mode"]
    counts = tele["counts"]

    # 1. KARTU MONITOR 4 AGENT
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            label="👩‍💼 1. Lead Sekretaris",
            value=f"{counts['sekretaris']} Tugas",
            delta="Aktif Terakhir" if last_mode in ["fast_path", "full_pipeline"] else "Standby"
        )
        st.caption("Model: `gemini-3.5-flash-lite`\nPeran: Wawancara, Chat Cepat & Router")

    with c2:
        st.metric(
            label="🔍 2. Sub-Agent Analis",
            value=f"{counts['analis']} Tugas",
            delta="Aktif Terakhir" if last_mode in ["full_pipeline", "team_collab"] else "Standby"
        )
        st.caption("Model: `gemini-3.5-flash`\nPeran: Bedah Excel/PDF & Hitung Angka")

    with c3:
        st.metric(
            label="✍️ 3. Sub-Agent Penulis",
            value=f"{counts['penulis']} Tugas",
            delta="Aktif Terakhir" if last_mode in ["full_pipeline", "team_collab"] else "Standby"
        )
        st.caption("Model: `gemini-3.5-flash-lite`\nPeran: Format Tabel & Laporan Dinas")

    with c4:
        st.metric(
            label="🤝 4. Fasilitator Tim",
            value=f"{counts['fasilitator']} Tugas",
            delta="Aktif Terakhir" if last_mode == "team_collab" else "Standby"
        )
        st.caption("Model: `gemini-3.5-flash`\nPeran: Diskusi Lintas User & Dokumen")

    st.markdown("---")

    # 2. DIAGRAM ALUR WORKFLOW DINAMIS (GRAPHVIZ)
    col_diag, col_log = st.columns([1.4, 1])

    with col_diag:
        st.markdown("#### 🗺️ Diagram Aliran Kerja (Workflow Live)")
        # Tentukan warna highlight berdasarkan jalur yang terakhir dipakai
        c_fast = "#10B981" if last_mode == "fast_path" else "#374151"
        c_heavy = "#F59E0B" if last_mode == "full_pipeline" else "#374151"
        c_team = "#3B82F6" if last_mode == "team_collab" else "#374151"

        dot_graph = f"""
        digraph MultiAgent {{
            rankdir=TB;
            bgcolor="transparent";
            node [shape=box, style="rounded,filled", fontname="Sans", fontsize=11, fontcolor="white", margin="0.18,0.12"];
            edge [fontname="Sans", fontsize=9, color="#9CA3AF", fontcolor="#D1D5DB"];

            User [label="👤 User Login\\n(Farhan / Nana / Dini)", fillcolor="#1F2937", color="#60A5FA", penwidth=2];
            Lead [label="👩‍💼 Agent 1: Lead Sekretaris\\n(gemini-3.5-flash-lite)\\nPilah Tugas & Onboarding", fillcolor="#2563EB", color="#93C5FD", penwidth=2];
            TeamRoom [label="🤝 Agent 4: Fasilitator Tim\\n(Ruang Diskusi & File Bersama)", fillcolor="{c_team}", color="#93C5FD", penwidth=2];

            FastOut [label="⚡ Jalur Instan (<1 Detik)\\nJawaban Chat & Sapaan Langsung", fillcolor="{c_fast}", color="#6EE7B7"];
            Analis [label="🔍 Agent 2: Sub-Agent Analis\\n(gemini-3.5-flash)\\nBedah Excel/PDF & Kalkulasi", fillcolor="{c_heavy}", color="#FCD34D", penwidth=2];
            Penulis [label="✍️ Agent 3: Sub-Agent Penulis\\n(gemini-3.5-flash-lite)\\nSusun Tabel & Format Laporan", fillcolor="{c_heavy}", color="#FCD34D", penwidth=2];
            CloudDB [label="☁️ GitHub Cloud Memory\\n(farhan.json, nana.json, team_workspace.json)", fillcolor="#111827", color="#A78BFA", penwidth=2];

            User -> Lead [label=" Tab Pribadi"];
            User -> TeamRoom [label=" Tab Diskusi Tim (@ai)"];

            Lead -> FastOut [label=" Ringan", color="{c_fast}", penwidth=2];
            Lead -> Analis [label=" Berat / File", color="{c_heavy}", penwidth=2];
            TeamRoom -> Analis [label=" Bedah Dokumen Tim", color="{c_team}", penwidth=2];

            Analis -> Penulis [label=" Data Mentah", color="{c_heavy}", penwidth=2];
            Penulis -> User [label=" Laporan Final"];
            FastOut -> User;

            Lead -> CloudDB [style=dashed, label=" Sync Profil"];
            TeamRoom -> CloudDB [style=dashed, label=" Sync Diskusi"];
        }}
        """
        st.graphviz_chart(dot_graph, use_container_width=True)
        st.caption("Keterangan warna jalur terakhir: 🟩 Hijau = Jalur Cepat | 🟨 Kuning = Delegasi Sub-Agent | 🟦 Biru = Kolaborasi Tim")

    with col_log:
        st.markdown("#### 📜 Jejak Eksekusi Agent (*Live Trace*)")
        if not tele["logs"]:
            st.info("Belum ada aktivitas di sesi ini. Coba kirim pesan atau upload file di tab sebelah, lalu lihat pergerakan agennya di sini!")
        else:
            for item_log in tele["logs"]:
                st.markdown(item_log)
