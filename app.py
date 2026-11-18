import os
import json
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Sekretaris Pribadi AI - PLN Icon Plus", page_icon="⚡", layout="wide")

# --- DAFTAR 10 PERTANYAAN (DIKUNCI SATU PER SATU) ---
DAFTAR_PERTANYAAN = [
    "1️⃣ Pertama, siapa **nama panggilan** Anda dan apa **jabatan** Anda saat ini di **PLN Icon Plus SBU Sumbagsel**?",
    "2️⃣ Anda bertugas di **bidang atau divisi** mana (misalnya Aktivasi, Pemeliharaan/O&M, Penjualan, Perencanaan, atau lainnya)?",
    "3️⃣ **Area atau wilayah kerja Sumbagsel** mana saja (Sumsel, Jambi, Bengkulu, Lampung, atau Babel) yang menjadi fokus tanggung jawab Anda?",
    "4️⃣ Apa **3 pekerjaan atau laporan rutin** (harian/mingguan) yang paling sering Anda kerjakan?",
    "5️⃣ Apa **target atau KPI utama** yang sedang paling krusial Anda kejar saat ini?",
    "6️⃣ **Jenis data atau dokumen** apa yang paling sering Anda olah (misalnya Excel tracking aktivasi, data POP/Gardu Induk, atau surat dinas)?",
    "7️⃣ Apa **kendala atau hambatan utama** di lapangan maupun kantor yang paling menyita waktu Anda?",
    "8️⃣ Bagaimana **gaya bahasa & format laporan** yang paling Anda sukai saat saya menyajikan hasil (misalnya poin-poin singkat, tabel ringkas, formal untuk pimpinan, atau santai)?",
    "9️⃣ **Aplikasi atau tools kerja** apa yang paling sering Anda gunakan sehari-hari (misalnya Excel/Pivot Table, Google Sheets, CRM internal, atau PowerPoint)?",
    "🔟 Terakhir, **tugas spesifik apa** yang paling ingin Anda delegasikan kepada saya agar langsung membantu pekerjaan Anda mulai hari ini?"
]

# --- MANAJEMEN MEMORI PER USER ---
MEMORY_DIR = "user_memories"
os.makedirs(MEMORY_DIR, exist_ok=True)

def load_user_data(user_id: str) -> dict:
    path = os.path.join(MEMORY_DIR, f"{user_id.lower().strip()}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "index_pertanyaan": 0,
        "profil_selesai": False,
        "ringkasan_profil": "",
        "messages": []
    }

def save_user_data(user_id: str, data: dict):
    path = os.path.join(MEMORY_DIR, f"{user_id.lower().strip()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- SIDEBAR: IDENTITAS & STATUS PROFIL USER ---
with st.sidebar:
    st.header("🔐 Profil Pengguna")
    user_id = st.text_input("Nama / User ID:", value="farhan", help="Ganti nama untuk berganti ke memori user lain").strip()
    
    st.markdown("---")
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password")

    if user_id:
        user_data = load_user_data(user_id)
        st.markdown(f"**Status (`{user_id}`):**")
        if user_data["profil_selesai"]:
            st.success("✅ Sekretaris Aktif (Memori Tersimpan)")
            with st.expander("📄 Lihat Resume Profil Kerja"):
                st.markdown(user_data["ringkasan_profil"])
        else:
            progres = user_data["index_pertanyaan"]
            st.info(f"💬 Sesi Perkenalan ({progres}/10)")
            st.progress(progres / 10)

        if st.button("🔄 Reset Memori User Ini"):
            save_user_data(user_id, {"index_pertanyaan": 0, "profil_selesai": False, "ringkasan_profil": "", "messages": []})
            st.rerun()

# --- HEADER UTAMA ---
st.title(f"👩‍💼 Sekretaris Pribadi AI — {user_id.capitalize() if user_id else 'Rekan'}")
st.caption("PLN Icon Plus SBU Sumbagsel • Wawancara Interaktif & Memori Personal")

if not user_id or not api_key:
    st.warning("Isi **Nama / User ID** dan **Gemini API Key** di sidebar kiri untuk mulai.")
    st.stop()

@st.cache_resource
def get_client(key: str):
    return genai.Client(api_key=key)

client = get_client(api_key)
user_data = load_user_data(user_id)

# --- PESAN PEMBUKA: HANYA PERTANYAAN KE-1 ---
if not user_data["messages"]:
    salam_pertama = (
        f"Halo **{user_id.capitalize()}**! Saya **Sekretaris Pribadi AI** Anda di **PLN Icon Plus SBU Sumbagsel**.\n\n"
        f"Yuk kita kenalan santai satu per satu agar saya paham cara kerja Anda:\n\n"
        f"{DAFTAR_PERTANYAAN[0]}"
    )
    user_data["messages"].append({"role": "assistant", "content": salam_pertama})
    save_user_data(user_id, user_data)

# --- TAMPILKAN RIWAYAT OBROLAN ---
for msg in user_data["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- PROSES BALASAN CHAT ---
if prompt_user := st.chat_input("Ketik jawaban atau perintah Anda di sini..."):
    user_data["messages"].append({"role": "user", "content": prompt_user})
    with st.chat_message("user"):
        st.markdown(prompt_user)

    with st.chat_message("assistant"):
        # FASE 1: MASIH DALAM TAHAP 10 PERTANYAAN (SATU PER SATU)
        if not user_data["profil_selesai"]:
            idx_berikutnya = user_data["index_pertanyaan"] + 1

            if idx_berikutnya < len(DAFTAR_PERTANYAAN):
                pertanyaan_selanjutnya = DAFTAR_PERTANYAAN[idx_berikutnya]
                instruksi_transisi = (
                    f"Anda adalah Sekretaris Pribadi AI yang ramah dan cekatan untuk '{user_id}' di PLN Icon Plus SBU Sumbagsel. "
                    f"User baru saja menjawab pertanyaan ke-{idx_berikutnya}. "
                    "TUGAS ANDA: Berikan tanggapan apresiasi yang sangat singkat (maksimal 1 kalimat) atas jawaban user tersebut, "
                    f"lalu akhiri balasan Anda dengan menanyakan PERSIS pertanyaan berikut ini (jangan ubah isinya dan jangan tambah pertanyaan lain):\n\n{pertanyaan_selanjutnya}"
                )

                konten_chat = [
                    types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                    for m in user_data["messages"][-
