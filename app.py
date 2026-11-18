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
            st.warning("📝 Tahap Pengenalan (Onboarding)")

        if st.button("🔄 Reset Memori User Ini"):
            save_user_data(user_id, {"profil_selesai": False, "ringkasan_profil": "", "messages": []})
            st.rerun()

# --- HEADER UTAMA ---
st.title(f"👩‍💼 Sekretaris Pribadi AI — Halo, {user_id.capitalize() if user_id else 'Rekan'}!")
st.caption("PLN Icon Plus SBU Sumbagsel • Memori terpisah & personal untuk setiap pengguna")

if not user_id or not api_key:
    st.info("Silakan masukkan **Nama / User ID** dan **Gemini API Key** di panel sebelah kiri untuk memulai.")
    st.stop()

@st.cache_resource
def get_client(key: str):
    return genai.Client(api_key=key)

client = get_client(api_key)
user_data = load_user_data(user_id)

# --- DAFTAR 10 PERTANYAAN ONBOARDING ---
PERTANYAAN_ONBOARDING = """
1. **Nama & Jabatan:** Siapa nama lengkap/panggilan Anda dan jabatan Anda di PLN Icon Plus SBU Sumbagsel?
2. **Bidang / Unit:** Anda bertugas di bidang/divisi mana (Aktivasi, Pemeliharaan/O&M, Penjualan, Perencanaan, dll.)?
3. **Wilayah Kerja:** Area layanan mana saja di Sumbagsel (Sumsel, Jambi, Bengkulu, Lampung, Babel) yang Anda tangani?
4. **Tugas Rutin:** Apa 3 pekerjaan atau laporan rutin harian/mingguan utama Anda?
5. **KPI Utama:** Apa target/KPI paling krusial yang sedang Anda kejar saat ini?
6. **Format Data:** Jenis dokumen/data apa yang paling sering Anda olah (Excel tracking, data POP/GI, surat dinas, dll.)?
7. **Kendala Utama:** Hambatan apa yang paling sering menyita waktu dalam pekerjaan Anda?
8. **Gaya Laporan:** Bagaimana gaya bahasa dan format output yang Anda sukai (ringkas poin-poin, tabel, formal/santai)?
9. **Tools Kerja:** Aplikasi/tools apa yang paling sering Anda pakai sehari-hari?
10. **Prioritas Bantuan:** Tugas spesifik apa yang paling ingin Anda delegasikan ke saya mulai hari ini?
"""

# --- TOOL UNTUK MENYIMPAN PROFIL KE MEMORI PERMANEN USER ---
def simpan_profil_ke_memori(ringkasan_lengkap_user: str) -> str:
    """
    Panggil fungsi ini HANYA SETELAH user menjawab pertanyaan pengenalan (onboarding).
    Simpan seluruh rangkuman profil kerja user secara rapi dan detail ke memori jangka panjang.
    """
    data_sekarang = load_user_data(user_id)
    data_sekarang["profil_selesai"] = True
    data_sekarang["ringkasan_profil"] = ringkasan_lengkap_user
    save_user_data(user_id, data_sekarang)
    return "Profil kerja user berhasil disimpan ke memori permanen!"

# --- TAMPILKAN RIWAYAT CHAT USER INI ---
if not user_data["messages"]:
    # Pesan pembuka otomatis dari Sekretaris Pribadi saat user baru pertama kali masuk
    salam_awal = (
        f"Selamat datang, **{user_id.capitalize()}**! Saya adalah **Sekretaris Pribadi AI** khusus untuk Anda di lingkungan **PLN Icon Plus SBU Sumbagsel**.\n\n"
        f"Agar saya bisa menyesuaikan cara kerja, gaya laporan, dan mengoordinasikan tim Sub-Agent sesuai kebutuhan Anda, silakan jawab **10 pertanyaan pengenalan singkat** berikut (boleh dijawab sekaligus atau bertahap):\n"
        f"{PERTANYAAN_ONBOARDING}"
    )
    user_data["messages"].append({"role": "assistant", "content": salam_awal})
    save_user_data(user_id, user_data)

for msg in user_data["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INPUT CHAT ---
if prompt_user := st.chat_input(f"Ketik pesan untuk sekretaris pribadi {user_id}..."):
    user_data["messages"].append({"role": "user", "content": prompt_user})
    save_user_data(user_id, user_data)
    with st.chat_message("user"):
        st.markdown(prompt_user)

    with st.chat_message("assistant"):
        # Susun instruksi Sekretaris Pribadi berdasarkan status memori user
        if not user_data["profil_selesai"]:
            instruksi_sekretaris = (
                f"Anda adalah Sekretaris Pribadi AI untuk user bernama '{user_id}' di PLN Icon Plus SBU Sumbagsel. "
                f"Saat ini Anda sedang dalam tahap mengenal user berdasarkan 10 pertanyaan berikut:\n{PERTANYAAN_ONBOARDING}\n\n"
                "TUGAS ANDA:\n"
                "- Jika user baru menjawab sebagian pertanyaan, apresiasi jawabannya dan tanyakan sisa pertanyaan yang belum dijawab dengan ramah.\n"
                "- Jika semua (atau mayoritas inti) pertanyaan sudah terjawab, SEGERA panggil tool 'simpan_profil_ke_memori' berisi rangkuman terstruktur profil kerja user tersebut, "
                "lalu konfirmasi bahwa Anda sudah siap membantu pekerjaan sehari-harinya."
            )
            tools_aktif = [simpan_profil_ke_memori]
        else:
            instruksi_sekretaris = (
                f"Anda adalah Sekretaris Pribadi AI khusus untuk '{user_id}' di PLN Icon Plus SBU Sumbagsel. "
                f"Berikut adalah MEMORI PROFIL KERJA user yang harus selalu Anda patuhi dalam setiap jawaban dan format laporan:\n"
                f"---\n{user_data['ringkasan_profil']}\n---\n"
                "Berperanlah sebagai sekretaris yang proaktif, mengingat konteks sebelumnya, menyesuaikan gaya bahasa dengan preferensi user, "
                "dan siap memimpin tim Sub-Agent untuk menyelesaikan tugas operasionalnya."
            )
            tools_aktif = [simpan_profil_ke_memori] # Tetap aktif jika user minta update profil

        konten_chat = [
            types.Content(
                role=("user" if m["role"] == "user" else "model"),
                parts=[types.Part.from_text(text=m["content"])]
            )
            for m in user_data["messages"]
        ]

        # Jalankan respons cepat dengan Gemini 3.5 Flash-Lite
        respon = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=konten_chat,
            config=types.GenerateContentConfig(
                system_instruction=instruksi_sekretaris,
                tools=tools_aktif,
                temperature=0.3
            )
        )

        jawaban_ai = respon.text
        st.markdown(jawaban_ai)

        # Simpan percakapan terbaru ke file memori user tersebut
        user_data_terbaru = load_user_data(user_id)
        user_data_terbaru["messages"].append({"role": "assistant", "content": jawaban_ai})
        save_user_data(user_id, user_data_terbaru)
