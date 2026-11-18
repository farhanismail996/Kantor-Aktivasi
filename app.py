import os
import json
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Sekretaris Pribadi AI - PLN Icon Plus", page_icon="👩‍💼", layout="wide")

# --- MANAJEMEN MEMORI PER USER (JSON) ---
MEMORY_DIR = "user_memories"
os.makedirs(MEMORY_DIR, exist_ok=True)

def load_user_data(user_id: str) -> dict:
    path = os.path.join(MEMORY_DIR, f"{user_id.lower().strip()}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"profil_selesai": False, "ringkasan_profil": "", "messages": []}

def save_user_data(user_id: str, data: dict):
    path = os.path.join(MEMORY_DIR, f"{user_id.lower().strip()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- SIDEBAR: IDENTITAS USER ---
with st.sidebar:
    st.header("🔐 Profil Pengguna")
    user_id = st.text_input("Masukkan Nama / User ID Anda:", value="farhan", help="Ganti nama ini untuk berganti ke memori user lain (misal: user_a, user_b)").strip()
    
    st.markdown("---")
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password")

    if user_id:
        user_data = load_user_data(user_id)
        st.markdown(f"**Status Memori (`{user_id}`):**")
        if user_data["profil_selesai"]:
            st.success("✅ Profil Kerja Tersimpan")
            with st.expander("Lihat Memori Profil Anda"):
                st.write(user_data["ringkasan_profil"])
        else:
            st.warning("💬 Sedang Berkenalan...")

        if st.button("🔄 Reset Memori User Ini"):
            save_user_data(user_id, {"profil_selesai": False, "ringkasan_profil": "", "messages": []})
            st.rerun()

# --- HEADER UTAMA ---
st.title(f"👩‍💼 Sekretaris Pribadi AI — Halo, {user_id.capitalize() if user_id else 'Rekan'}!")
st.caption("PLN Icon Plus SBU Sumbagsel • Memori personal & bertahap untuk setiap pengguna")

if not user_id or not api_key:
    st.info("Silakan masukkan **Nama / User ID** dan **Gemini API Key** di panel sebelah kiri untuk memulai.")
    st.stop()

@st.cache_resource
def get_client(key: str):
    return genai.Client(api_key=key)

client = get_client(api_key)
user_data = load_user_data(user_id)

# --- 10 POIN DATA YANG AKAN DIGALI SECARA BERTAHAP ---
TARGET_INFO_PROFIL = """
- Fase 1 (Identitas & Posisi): (1) Nama lengkap/panggilan & jabatan di PLN Icon Plus SBU Sumbagsel, (2) Bidang/divisi kerja (Aktivasi, O&M, Penjualan, Perencanaan, dll.), (3) Wilayah tanggung jawab di Sumbagsel (Sumsel, Jambi, Bengkulu, Lampung, Babel).
- Fase 2 (Rutinitas & Target): (4) 3 pekerjaan/laporan rutin harian atau mingguan, (5) Target/KPI paling krusial saat ini.
- Fase 3 (Data & Kendala): (6) Jenis dokumen/data yang sering diolah (Excel tracking, data POP/GI, surat dinas, dll.), (7) Kendala atau bottleneck utama di lapangan/kantor.
- Fase 4 (Gaya Kerja & Prioritas): (8) Preferensi gaya bahasa & format laporan (ringkas poin, tabel, formal/santai), (9) Aplikasi/tools kerja harian (Excel, Sheets, CRM, PPT, dll.), (10) Tugas spesifik yang paling ingin dibantu otomatisasi mulai hari ini.
"""

# --- TOOL UNTUK MENYIMPAN PROFIL KE MEMORI PERMANEN USER ---
def simpan_profil_ke_memori(ringkasan_lengkap_user: str) -> str:
    """
    Panggil fungsi ini HANYA SETELAH seluruh 4 fase (10 poin informasi) selesai digali dari user.
    Simpan seluruh rangkuman profil kerja user secara rapi dan detail ke memori jangka panjang.
    """
    data_sekarang = load_user_data(user_id)
    data_sekarang["profil_selesai"] = True
    data_sekarang["ringkasan_profil"] = ringkasan_lengkap_user
    save_user_data(user_id, data_sekarang)
    return "Profil kerja user berhasil disimpan ke memori permanen!"

# --- PESAN PEMBUKA NATURAL (HANYA FASE 1 /
