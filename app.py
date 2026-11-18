import os
import json
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Sekretaris Pribadi AI - PLN Icon Plus", page_icon="🔐", layout="wide")

# --- KONFIGURASI PENYIMPANAN MEMORI ---
MEMORY_DIR = "user_memories"
os.makedirs(MEMORY_DIR, exist_ok=True)

def get_user_file(username: str) -> str:
    safe_name = "".join(c for c in username.lower().strip() if c.isalnum() or c in ("_", "-"))
    return os.path.join(MEMORY_DIR, f"{safe_name}.json")

def load_user_data(username: str) -> dict:
    path = get_user_file(username)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "pin": "",
        "index_pertanyaan": 0,
        "profil_selesai": False,
        "ringkasan_profil": "",
        "messages": []
    }

def save_user_data(username: str, data: dict):
    path = get_user_file(username)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

# --- INISIALISASI SESSION LOGIN ---
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# ==========================================
# HALAMAN 1: LOGIN / DAFTAR USER BARU
# ==========================================
if not st.session_state.logged_in_user:
    st.title("🔐 Login Sekretaris Pribadi AI")
    st.caption("PLN Icon Plus SBU Sumbagsel • Setiap akun memiliki memori kerja terpisah")

    col1, col2 = st.columns([1, 1.2])
    with col1:
        with st.form("form_login"):
            st.subheader("Masuk ke Ruang Kerja Anda")
            input_user = st.text_input("Username (tanpa spasi, misal: farhan):", placeholder="contoh: farhan")
            input_pin = st.text_input("PIN Keamanan (4-6 angka):", type="password", placeholder="contoh: 1234")
            submit_login = st.form_submit_button("Masuk / Buat Akun Baru", type="primary", use_container_width=True)

            if submit_login:
                uname = input_user.strip().lower()
                if not uname or not input_pin:
                    st.error("Username dan PIN wajib diisi.")
                else:
                    existing = load_user_data(uname)
                    if existing["pin"] == "":
                        # Akun baru -> simpan PIN dan langsung masuk
                        existing["pin"] = input_pin
                        save_user_data(uname, existing)
                        st.session_state.logged_in_user = uname
                        st.rerun()
                    elif existing["pin"] == input_pin:
                        # PIN cocok -> masuk ke memori user tersebut
                        st.session_state.logged_in_user = uname
                        st.rerun()
                    else:
                        st.error("PIN salah untuk username tersebut! Gunakan PIN yang benar atau pakai username lain.")
    st.stop()

# ==========================================
# HALAMAN 2: RUANG KERJA SEKRETARIS PRIBADI
# ==========================================
current_user = st.session_state.logged_in_user
user_data = load_user_data(current_user)

with st.sidebar:
    st.header(f"👤 Akun: {current_user.capitalize()}")
    if st.button("🚪 Logout / Ganti Akun", use_container_width=True):
        st.session_state.logged_in_user = None
        st.rerun()

    st.markdown("---")
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password")

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

    if st.button("🔄 Ulangi Pertanyaan Profil"):
        user_data["index_pertanyaan"] = 0
        user_data["profil_selesai"] = False
        user_data["ringkasan_profil"] = ""
        user_data["messages"] = []
        save_user_data(current_user, user_data)
        st.rerun()

st.title(f"👩‍💼 Sekretaris Pribadi AI — {current_user.capitalize()}")
st.caption("PLN Icon Plus SBU Sumbagsel • Asisten Operasional & Lead Agent Pribadi")

if not api_key:
    st.warning("Masukkan **Gemini API Key** di sidebar kiri terlebih dahulu.")
    st.stop()

@st.cache_resource
def get_client(key: str):
    return genai.Client(api_key=key)

client = get_client(api_key)

# Pesan pembuka otomatis (Hanya Pertanyaan 1)
if not user_data["messages"]:
    salam_awal = (
        f"Selamat datang, **{current_user.capitalize()}**! Saya **Sekretaris Pribadi AI** khusus untuk Anda di **PLN Icon Plus SBU Sumbagsel**.\n\n"
        f"Agar saya memahami ritme kerja Anda, saya akan bertanya **satu per satu** secara singkat:\n\n"
        f"{DAFTAR_PERTANYAAN[0]}"
    )
    user_data["messages"].append({"role": "assistant", "content": salam_awal})
    save_user_data(current_user, user_data)

# Tampilkan riwayat percakapan user yang sedang login
for msg in user_data["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input pesan chat
if prompt_user := st.chat_input(f"Ketik jawaban atau instruksi untuk sekretaris {current_user}..."):
    user_data["messages"].append({"role": "user", "content": prompt_user})
    with st.chat_message("user"):
        st.markdown(prompt_user)

    with st.chat_message("assistant"):
        # FASE 1: WAWANCARA 1-PER-1
        if not user_data["profil_selesai"]:
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

                def stream_tanya():
                    for chunk in client.models.generate_content_stream(
                        model="gemini-3.5-flash-lite",
                        contents=konten,
                        config=types.GenerateContentConfig(
                            system_instruction=instruksi,
                            temperature=0.3,
                            thinking_config=types.ThinkingConfig(thinking_budget=0)
                        )
                    ):
                        if chunk.text:
                            yield chunk.text

                hasil = st.write_stream(stream_tanya)
                user_data["index_pertanyaan"] = idx_next
                user_data["messages"].append({"role": "assistant", "content": hasil})
                save_user_data(current_user, user_data)
                st.rerun()

            else:
                # Selesai 10 pertanyaan -> Buat Resume & Aktifkan Mode Sekretaris
                instruksi_resume = (
                    f"Anda adalah Sekretaris Pribadi AI untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel. "
                    "Semua 10 pertanyaan pengenalan telah dijawab. Susun **Resume Profil Kerja** yang rapi dan terstruktur dalam poin-poin, "
                    "lalu nyatakan bahwa memori sudah tersimpan dan Anda siap bekerja sebagai Sekretaris Pribadi & Lead Agent-nya."
                )
                konten_semua = [
                    types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                    for m in user_data["messages"]
                ]

                def stream_resume():
                    for chunk in client.models.generate_content_stream(
                        model="gemini-3.5-flash-lite",
                        contents=konten_semua,
                        config=types.GenerateContentConfig(
                            system_instruction=instruksi_resume,
                            temperature=0.2,
                            thinking_config=types.ThinkingConfig(thinking_budget=0)
                        )
                    ):
                        if chunk.text:
                            yield chunk.text

                resume = st.write_stream(stream_resume)
                user_data["index_pertanyaan"] = 10
                user_data["profil_selesai"] = True
                user_data["ringkasan_profil"] = resume
                user_data["messages"].append({"role": "assistant", "content": resume})
                save_user_data(current_user, user_data)
                st.rerun()

        # FASE 2: SEKRETARIS PRIBADI & LEAD AGENT AKTIF
        else:
            instruksi_aktif = (
                f"Anda adalah Sekretaris Pribadi AI & Lead Agent khusus untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel.\n"
                f"MEMORI PROFIL KERJA USER:\n{user_data['ringkasan_profil']}\n\n"
                "Layani perintah user dengan cekatan, sesuai format laporan yang disukainya, dan ingat seluruh riwayat percakapan."
            )
            konten_aktif = [
                types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                for m in user_data["messages"][-12:]
            ]

            def stream_aktif():
                for chunk in client.models.generate_content_stream(
                    model="gemini-3.5-flash-lite",
                    contents=konten_aktif,
                    config=types.GenerateContentConfig(
                        system_instruction=instruksi_aktif,
                        temperature=0.3,
                        thinking_config=types.ThinkingConfig(thinking_budget=0)
                    )
                ):
                    if chunk.text:
                        yield chunk.text

            balasan = st.write_stream(stream_aktif)
            user_data["messages"].append({"role": "assistant", "content": balasan})
            save_user_data(current_user, user_data)
