import os
import json
import base64
import requests
import pandas as pd
from pypdf import PdfReader
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError

st.set_page_config(page_title="Sekretaris Pribadi AI - PLN Icon Plus", page_icon="🔐", layout="wide")

# --- KONFIGURASI BACKUP PERMANEN KE GITHUB ---
GITHUB_REPO = "farhanismail996/Kantor-Aktivasi"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "") if "GITHUB_TOKEN" in st.secrets else ""
MEMORY_DIR = "user_memories"
os.makedirs(MEMORY_DIR, exist_ok=True)

def get_safe_username(username: str) -> str:
    return "".join(c for c in username.lower().strip() if c.isalnum() or c in ("_", "-"))

def load_user_data(username: str) -> dict:
    safe_name = get_safe_username(username)
    file_path = f"{MEMORY_DIR}/{safe_name}.json"
    default_data = {
        "pin": "",
        "index_pertanyaan": 0,
        "profil_selesai": False,
        "ringkasan_profil": "",
        "messages": []
    }

    # 1. Coba tarik memori terbaru langsung dari GitHub (Kebal Reboot!)
    if GITHUB_TOKEN:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                content_b64 = res.json()["content"]
                decoded = base64.b64decode(content_b64).decode("utf-8")
                data = json.loads(decoded)
                # Sinkronkan juga ke cache lokal
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return data
        except Exception:
            pass

    # 2. Fallback baca dari lokal jika belum ada di GitHub
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return default_data

def save_user_data(username: str, data: dict):
    safe_name = get_safe_username(username)
    file_path = f"{MEMORY_DIR}/{safe_name}.json"

    # 1. Simpan cepat ke lokal
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 2. Backup permanen otomatis ke GitHub
    if GITHUB_TOKEN:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        try:
            # Cek SHA file jika sudah ada di GitHub (syarat update file via GitHub API)
            sha = None
            get_res = requests.get(url, headers=headers, timeout=5)
            if get_res.status_code == 200:
                sha = get_res.json().get("sha")

            json_str = json.dumps(data, ensure_ascii=False, indent=2)
            encoded_content = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

            payload = {
                "message": f"Auto-backup memori user: {safe_name}",
                "content": encoded_content
            }
            if sha:
                payload["sha"] = sha

            requests.put(url, headers=headers, json=payload, timeout=8)
        except Exception as e:
            st.toast(f"⚠️ Gagal sinkron ke GitHub: {e}")

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
                f"Data Lengkap (maksimal 200 baris pertama):\n{df.head(200).to_csv(index=False)}"
            )
        elif nama_file.endswith((".xlsx", ".xls")):
            excel_data = pd.read_excel(uploaded_file, sheet_name=None)
            hasil_sheets = [f"=== FILE EXCEL: {uploaded_file.name} (Jumlah Sheet: {len(excel_data)}) ==="]
            for nama_sheet, df in excel_data.items():
                hasil_sheets.append(
                    f"\n--- Sheet: '{nama_sheet}' ({len(df)} baris, {len(df.columns)} kolom) ---\n"
                    f"Kolom: {', '.join(df.columns.astype(str))}\n"
                    f"Data (maks 150 baris pertama):\n{df.head(150).to_csv(index=False)}"
                )
            return "\n".join(hasil_sheets)
        elif nama_file.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            teks_halaman = [f"=== FILE PDF: {uploaded_file.name} (Total {len(reader.pages)} halaman) ==="]
            for idx, page in enumerate(reader.pages[:30]):
                isi = page.extract_text() or ""
                teks_halaman.append(f"\n--- Halaman {idx + 1} ---\n{isi}")
            return "\n".join(teks_halaman)
        else:
            return "Format file tidak didukung."
    except Exception as e:
        return f"Gagal membaca file {uploaded_file.name}: {e}"

# --- HELPER STREAMING DENGAN FALLBACK MODEL ---
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

# --- DAFTAR 10 PERTANYAAN (SATU PER SATU) ---
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
    st.title("🔐 Login Sekretaris Pribadi AI")
    st.caption("PLN Icon Plus SBU Sumbagsel • Memori tersinkronisasi aman di Cloud")

    col1, col2 = st.columns([1, 1.2])
    with col1:
        with st.form("form_login"):
            st.subheader("Masuk ke Ruang Kerja Anda")
            input_user = st.text_input("Username (misal: farhan, nana, dini):", placeholder="contoh: farhan")
            input_pin = st.text_input("PIN Keamanan (4-6 angka):", type="password", placeholder="contoh: 1234")
            submit_login = st.form_submit_button("Masuk / Buat Akun Baru", type="primary", use_container_width=True)

            if submit_login:
                uname = get_safe_username(input_user)
                if not uname or not input_pin:
                    st.error("Username dan PIN wajib diisi.")
                else:
                    with st.spinner("Memeriksa memori akun di Cloud..."):
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
                        st.error("PIN salah untuk username tersebut! Gunakan PIN yang benar atau pakai username lain.")
    st.stop()

# ==========================================
# HALAMAN 2: RUANG KERJA SEKRETARIS PRIBADI
# ==========================================
current_user = st.session_state.logged_in_user
if "cached_user_data" not in st.session_state or st.session_state.get("cached_username") != current_user:
    st.session_state.cached_user_data = load_user_data(current_user)
    st.session_state.cached_username = current_user

user_data = st.session_state.cached_user_data

with st.sidebar:
    st.header(f"👤 Akun: {current_user.capitalize()}")
    if GITHUB_TOKEN:
        st.caption("☁️ Auto-Backup Cloud: **Aktif**")
    else:
        st.caption("⚠️ Auto-Backup Cloud: **Nonaktif** (Isi `GITHUB_TOKEN` di Secrets)")

    if st.button("🚪 Logout / Ganti Akun", use_container_width=True):
        st.session_state.logged_in_user = None
        st.session_state.pop("cached_user_data", None)
        st.rerun()

    st.markdown("---")
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password").strip()

    st.markdown("---")
    st.markdown("**Status Memori Kerja:**")
    if user_data["profil_selesai"]:
        st.success("✅ Sekretaris Aktif (Profil Terkunci)")
        with st.expander("📄 Lihat Resume Profil"):
            st.markdown(user_data["ringkasan_profil"])
    else:
        progres = user_data["index_pertanyaan"]
        st.info(f"💬 Tahap Kenalan ({progres}/10)")
        st.progress(progres / 10)

    # Tombol Download Backup Manual (Lapisan Keamanan Kedua)
    st.download_button(
        label="💾 Unduh File Backup (.json)",
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

st.title(f"👩‍💼 Sekretaris Pribadi AI — {current_user.capitalize()}")
st.caption("PLN Icon Plus SBU Sumbagsel • Klik ikon 📎 pada kolom ketik di bawah untuk melampirkan Excel/CSV/PDF")

if not api_key:
    st.warning("Masukkan **Gemini API Key** di sidebar kiri terlebih dahulu.")
    st.stop()

@st.cache_resource
def get_client(key: str):
    return genai.Client(api_key=key)

client = get_client(api_key)

if not user_data["messages"]:
    salam_awal = (
        f"Selamat datang, **{current_user.capitalize()}**! Saya **Sekretaris Pribadi AI** khusus untuk Anda di **PLN Icon Plus SBU Sumbagsel**.\n\n"
        f"Agar saya memahami ritme kerja Anda, saya akan bertanya **satu per satu** secara singkat:\n\n"
        f"{DAFTAR_PERTANYAAN[0]}"
    )
    user_data["messages"].append({"role": "assistant", "content": salam_awal})
    save_user_data(current_user, user_data)

for msg in user_data["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

MODEL_LIST = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]

# --- KOTAK CHAT DENGAN IKON KLIP KERTAS (📎) LANGSUNG DI DALAMNYA ---
prompt_user = None
uploaded_files = []

try:
    chat_submission = st.chat_input(
        f"Ketik pesan atau klik 📎 untuk lampirkan Excel/PDF ({current_user})...",
        accept_file="multiple",
        file_type=["xlsx", "xls", "csv", "pdf"]
    )
    if chat_submission:
        uploaded_files = chat_submission.files or []
        prompt_user = chat_submission.text or ("Tolong analisis file yang saya lampirkan ini." if uploaded_files else None)
except TypeError:
    # Cadangan otomatis jika versi Streamlit di server belum ter-update ke >=1.43.0
    uploaded_files = st.file_uploader(
        "📎 Lampirkan file Excel, CSV, atau PDF:",
        type=["xlsx", "xls", "csv", "pdf"],
        accept_multiple_files=True
    ) or []
    prompt_user = st.chat_input(f"Ketik jawaban atau perintah analisis file untuk {current_user}...")

if prompt_user:
    label_file = ""
    konteks_dokumen = ""
    if uploaded_files:
        nama_files = [f.name for f in uploaded_files]
        label_file = f"\n\n*(📎 File terlampir: {', '.join(nama_files)})*"
        potongan_dokumen = [ekstrak_isi_file(f) for f in uploaded_files]
        konteks_dokumen = "\n\n".join(potongan_dokumen)

    user_data["messages"].append({"role": "user", "content": prompt_user + label_file})
    with st.chat_message("user"):
        st.markdown(prompt_user + label_file)

    with st.chat_message("assistant"):
        try:
            if not user_data["profil_selesai"] and not uploaded_files:
                idx_next = user_data["index_pertanyaan"] + 1

                if idx_next < len(DAFTAR_PERTANYAAN):
                    pertanyaan_berikutnya = DAFTAR_PERTANYAAN[idx_next]
                    instruksi = (
                        f"Anda adalah Sekretaris Pribadi AI yang ramah dan cekatan untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel. "
                        "Tanggapi jawaban user sebelumnya dalam 1 kalimat singkat yang relevan, lalu tanyakan PERSIS pertanyaan berikut ini "
                        f"(jangan mengubah isi pertanyaan dan jangan menambah pertanyaan lain):\n\n{pertanyaan_berikutnya}"
                    )
                    konten = [
                        types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                        for m in user_data["messages"][-4:]
                    ]

                    hasil = st.write_stream(stream_dengan_cadangan(client, MODEL_LIST, konten, instruksi, 0.3))
                    user_data["index_pertanyaan"] = idx_next
                    user_data["messages"].append({"role": "assistant", "content": hasil})
                    save_user_data(current_user, user_data)
                    st.rerun()

                else:
                    instruksi_resume = (
                        f"Anda adalah Sekretaris Pribadi AI untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel. "
                        "Semua 10 pertanyaan pengenalan telah dijawab. Susun **Resume Profil Kerja** yang rapi dan terstruktur dalam poin-poin, "
                        "lalu nyatakan bahwa memori sudah tersimpan dan Anda siap bekerja sebagai Sekretaris Pribadi & Lead Agent-nya."
                    )
                    konten_semua = [
                        types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                        for m in user_data["messages"]
                    ]

                    resume = st.write_stream(stream_dengan_cadangan(client, MODEL_LIST, konten_semua, instruksi_resume, 0.2))
                    user_data["index_pertanyaan"] = 10
                    user_data["profil_selesai"] = True
                    user_data["ringkasan_profil"] = resume
                    user_data["messages"].append({"role": "assistant", "content": resume})
                    save_user_data(current_user, user_data)
                    st.rerun()

            else:
                instruksi_aktif = (
                    f"Anda adalah Sekretaris Pribadi AI & Lead Agent khusus untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel.\n"
                    f"MEMORI PROFIL KERJA USER:\n{user_data['ringkasan_profil'] or 'Belum selesai onboarding, namun langsung bantu permintaan user.'}\n\n"
                    "TUGAS ANDA:\n"
                    "- Layani perintah user dengan cekatan, sesuai format laporan yang disukainya, dan ingat seluruh riwayat percakapan.\n"
                    "- Jika user melampirkan ISI FILE EXCEL/CSV/PDF, bertindaklah bersama Sub-Agent Analis Data untuk membedah angka, "
                    "menghitung total/rekapitulasi secara akurat, menemukan anomali, dan menyajikannya dalam tabel atau poin eksekutif yang rapi."
                )

                konten_aktif = [
                    types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                    for m in user_data["messages"][-10:-1]
                ]

                pesan_terakhir_lengkap = prompt_user
                if konteks_dokumen:
                    pesan_terakhir_lengkap += f"\n\nBerikut adalah isi dokumen yang diunggah oleh user untuk Anda analisis:\n{konteks_dokumen}"

                konten_aktif.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=pesan_terakhir_lengkap)])
                )

                model_prioritas = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"] if konteks_dokumen else MODEL_LIST

                balasan = st.write_stream(stream_dengan_cadangan(client, model_prioritas, konten_aktif, instruksi_aktif, 0.2))
                user_data["messages"].append({"role": "assistant", "content": balasan})
                save_user_data(current_user, user_data)

        except Exception as e:
            st.error(f"Detail Error: {e}")
