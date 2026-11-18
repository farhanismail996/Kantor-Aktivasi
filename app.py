import os
import json
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Sekretaris Pribadi AI - PLN Icon Plus", page_icon="⚡", layout="wide")

# --- MANAJEMEN MEMORI PER USER ---
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
    user_id = st.text_input("Nama / User ID:", value="farhan", help="Ganti nama untuk berganti ke memori user lain").strip()
    
    st.markdown("---")
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password")

    if user_id:
        user_data = load_user_data(user_id)
        st.markdown(f"**Status (`{user_id}`):**")
        if user_data["profil_selesai"]:
            st.success("✅ Sekretaris Aktif (Memori Terkunci)")
            with st.expander("📄 Lihat Resume Profil Kerja"):
                st.markdown(user_data["ringkasan_profil"])
        else:
            st.info("💬 Tahap Pengenalan (Onboarding)")

        if st.button("🔄 Reset Memori User Ini"):
            save_user_data(user_id, {"profil_selesai": False, "ringkasan_profil": "", "messages": []})
            st.rerun()

# --- HEADER UTAMA ---
st.title(f"👩‍💼 Sekretaris Pribadi AI — {user_id.capitalize() if user_id else 'Guest'}")
st.caption("PLN Icon Plus SBU Sumbagsel • Respon Instan & Memori Personal")

if not user_id or not api_key:
    st.warning("Isi **Nama / User ID** dan **Gemini API Key** di sidebar kiri untuk mulai.")
    st.stop()

@st.cache_resource
def get_client(key: str):
    return genai.Client(api_key=key)

client = get_client(api_key)
user_data = load_user_data(user_id)

# --- SALAM PEMBUKA OTOMATIS ---
if not user_data["messages"]:
    salam_awal = (
        f"Halo **{user_id.capitalize()}**! Saya **Sekretaris Pribadi AI** Anda di **PLN Icon Plus SBU Sumbagsel**.\n\n"
        "Sebelum kita mulai bekerja, yuk kenalan singkat dulu (cukup 4 tahap obrolan ringan):\n"
        "1. Apa **jabatan** Anda saat ini dan di **bidang/divisi** mana Anda bertugas?\n"
        "2. **Wilayah kerja Sumbagsel** mana saja (Sumsel, Jambi, Bengkulu, Lampung, atau Babel) yang Anda tangani?"
    )
    user_data["messages"].append({"role": "assistant", "content": salam_awal})
    save_user_data(user_id, user_data)

# --- TAMPILKAN RIWAYAT CHAT ---
for msg in user_data["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INPUT CHAT (STREAMING INSTAN) ---
if prompt_user := st.chat_input("Ketik balasan Anda di sini..."):
    user_data["messages"].append({"role": "user", "content": prompt_user})
    save_user_data(user_id, user_data)
    with st.chat_message("user"):
        st.markdown(prompt_user)

    with st.chat_message("assistant"):
        if not user_data["profil_selesai"]:
            instruksi_sistem = (
                f"Anda adalah Sekretaris Pribadi AI yang ramah, cekatan, dan to-the-point untuk '{user_id}' di PLN Icon Plus SBU Sumbagsel.\n"
                "Misi Anda adalah mengenal profil kerjanya lewat 4 tahap obrolan singkat (maksimal 2-3 pertanyaan per balasan):\n"
                "- Tahap 1 (Sudah ditanyakan di awal): Jabatan, bidang/divisi, dan wilayah Sumbagsel.\n"
                "- Tahap 2: 3 pekerjaan/laporan rutin harian atau mingguan, serta target/KPI utama.\n"
                "- Tahap 3: Jenis file/data yang sering diolah (Excel tracking, data POP/GI, surat dinas) dan kendala utama di lapangan/kantor.\n"
                "- Tahap 4: Gaya laporan yang disukai (ringkas poin, tabel, formal/santai), aplikasi kerja harian, dan tugas prioritas yang ingin dibantu.\n\n"
                "ATURAN PENTING:\n"
                "1. Tanggapi jawaban user dengan singkat (1 kalimat), lalu langsung ajukan pertanyaan tahap berikutnya.\n"
                "2. Jika Tahap 1 sampai 4 SUDAH TERJAWAB SEMUA, jangan bertanya lagi! Buat **Resume Profil Kerja** yang rapi dalam bentuk poin-poin, "
                "nyatakan bahwa Anda kini resmi siap berperan penuh sebagai Sekretaris Pribadi & Lead Agent-nya, dan akhiri pesan Anda dengan kode persis: [PROFIL_SELESAI]"
            )
        else:
            instruksi_sistem = (
                f"Anda adalah Sekretaris Pribadi AI & Lead Agent khusus untuk '{user_id}' di PLN Icon Plus SBU Sumbagsel.\n"
                f"Gunakan MEMORI PROFIL KERJA berikut sebagai panduan utama dalam setiap bantuan, analisis, dan penyusunan laporan:\n"
                f"{user_data['ringkasan_profil']}\n\n"
                "Jawab dengan cepat, solutif, ingat seluruh konteks percakapan sebelumnya, dan bantu otomatisasi pekerjaan operasionalnya."
            )

        konten_chat = [
            types.Content(
                role=("user" if m["role"] == "user" else "model"),
                parts=[types.Part.from_text(text=m["content"])]
            )
            for m in user_data["messages"]
        ]

        # Streaming langsung kata-per-kata tanpa tools & tanpa thinking delay
        def stream_respon():
            for chunk in client.models.generate_content_stream(
                model="gemini-3.5-flash-lite",
                contents=konten_chat,
                config=types.GenerateContentConfig(
                    system_instruction=instruksi_sistem,
                    temperature=0.3,
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                )
            ):
                if chunk.text:
                    # Sembunyikan tag internal dari tampilan layar saat streaming
                    yield chunk.text.replace("[PROFIL_SELESAI]", "")

        jawaban_lengkap = st.write_stream(stream_respon)

        # Cek apakah tahap onboarding baru saja selesai dan menghasilkan resume
        if not user_data["profil_selesai"] and ("Resume Profil Kerja" in jawaban_lengkap or len(user_data["messages"]) >= 8):
            user_data["profil_selesai"] = True
            user_data["ringkasan_profil"] = jawaban_lengkap

        user_data["messages"].append({"role": "assistant", "content": jawaban_lengkap})
        save_user_data(user_id, user_data)

        if user_data["profil_selesai"] and len(user_data["messages"]) in [9, 10]:
            st.rerun()
