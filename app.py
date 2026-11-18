import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError

st.set_page_config(page_title="Lead AI Agent System", page_icon="🤖", layout="wide")
st.title("🤖 Sistem Multi-Agent (Memory + Custom Skills)")

with st.sidebar:
    st.header("Pengaturan")
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password")
    
    if st.button("🗑️ Hapus Memory Chat"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("**Tim & Skill Aktif:**")
    st.markdown("- **Lead Agent:** `gemini-3.8-flash` (Cadangan: `3.5-flash`)")
    st.markdown("- **Sub-Agent Data:** `gemini-3.5-flash-lite` + Skill Hitung")
    st.markdown("- **Sub-Agent Penulis:** `gemini-3.5-flash-lite`")

# Inisialisasi Memory Percakapan di Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

# Tampilkan Riwayat Percakapan Sebelumnya (Memory)
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- DEFINISI SKILL KHUSUS UNTUK SUB-AGENT TERTENTU ---
def skill_hitung_rasio_operasional(total_gangguan: float, total_aset: float) -> str:
    """Skill khusus menghitung persentase rasio gangguan terhadap total aset."""
    if total_aset == 0:
        return "Error: Total aset tidak boleh nol."
    rasio = (total_gangguan / total_aset) * 100
    return f"Hasil Kalkulasi Pasti: {rasio:.2f}% ({total_gangguan} dari {total_aset})"

# --- FUNGSI EKSEKUSI MULTI-AGENT ---
def jalankan_lead_agent(key: str, riwayat_chat: list, status_box):
    client = genai.Client(api_key=key)

    def panggil_cepat(daftar_model: list, contents, config=None):
        error_terakhir = None
        for nama_model in daftar_model:
            try:
                return client.models.generate_content(
                    model=nama_model,
                    contents=contents,
                    config=config
                )
            except APIError as e:
                error_terakhir = e
                # Jika model 404 (tidak tersedia) atau 503 (sibuk), langsung lompat ke model berikutnya
                if e.code in [404, 503]:
                    continue
                raise e
        raise RuntimeError(f"Semua model cadangan gagal merespons: {error_terakhir}")

    # Sub-Agent 1: Analis Data (Dibekali Skill Khusus Kalkulasi)
    def sub_agent_analis_data(instruksi_analisis: str) -> str:
        """Sub-Agent khusus membedah data teknis dan menjalankan perhitungan rasio."""
        status_box.write("🔍 **Sub-Agent Analis** menggunakan skill data...")
        respon = panggil_cepat(
            daftar_model=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash"],
            contents=f"Anda adalah Analis Data. Gunakan skill yang tersedia jika ada angka yang perlu dihitung pasti:\n{instruksi_analisis}",
            config=types.GenerateContentConfig(
                tools=[skill_hitung_rasio_operasional],
                temperature=0.1
            )
        )
        return respon.text

    # Sub-Agent 2: Penulis Laporan (Fokus Tata Bahasa & Struktur)
    def sub_agent_penulis(bahan_mentah: str) -> str:
        """Sub-Agent khusus menyusun laporan rapi dengan tabel dan poin eksekutif."""
        status_box.write("✍️ **Sub-Agent Penulis** menyusun format laporan...")
        respon = panggil_cepat(
            daftar_model=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash"],
            contents=f"Susun bahan berikut menjadi laporan profesional yang ringkas:\n{bahan_mentah}",
            config=types.GenerateContentConfig(temperature=0.3)
        )
        return respon.text

    # Lead Agent (Membaca seluruh riwayat_chat sebagai Memory)
    instruksi_lead = (
        "Anda adalah Lead Project Manager AI yang mengingat seluruh konteks percakapan sebelumnya. "
        "ATURAN KECEPATAN:\n"
        "- Untuk sapaan, tanya-jawab ringan, atau tindak lanjut singkat: JAWAB LANGSUNG dalam 1-2 kalimat tanpa memanggil sub-agent.\n"
        "- Untuk tugas analisis angka, evaluasi teknis, atau pembuatan laporan: Panggil 'sub_agent_analis_data' lalu 'sub_agent_penulis'."
    )

    konten_memory = []
    for m in riwayat_chat:
        role_gemini = "user" if m["role"] == "user" else "model"
        konten_memory.append(types.Content(role=role_gemini, parts=[types.Part.from_text(text=m["content"])]))

    respon_lead = panggil_cepat(
        daftar_model=["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash"],
        contents=konten_memory,
        config=types.GenerateContentConfig(
            system_instruction=instruksi_lead,
            tools=[sub_agent_analis_data, sub_agent_penulis],
            temperature=0.2,
            # Meminimalkan waktu berpikir agar respons chat terasa instan
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )
    return respon_lead.text

# Input Chat Interaktif di Bagian Bawah Layar
if prompt_user := st.chat_input("Ketik pesan atau tugas untuk Lead Agent..."):
    if not api_key:
        st.error("Masukkan Gemini API Key di sidebar kiri terlebih dahulu.")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt_user})
        with st.chat_message("user"):
            st.markdown(prompt_user)

        with st.chat_message("assistant"):
            with st.status("Memproses...", expanded=False) as status:
                try:
                    jawaban = jalankan_lead_agent(api_key, st.session_state.messages, status)
                    status.update(label="Selesai", state="complete")
                    st.markdown(jawaban)
                    st.session_state.messages.append({"role": "assistant", "content": jawaban})
                except Exception as e:
                    status.update(label="Gagal", state="error")
                    st.error(f"Error: {e}")
