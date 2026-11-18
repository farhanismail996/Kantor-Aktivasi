import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import ServerError

st.set_page_config(page_title="Lead AI Agent System", page_icon="🤖", layout="wide")
st.title("🤖 Sistem Multi-Agent (Lead & Sub-Agent)")
st.caption("Ditenagai oleh Gemini API — Cerdas memilah tugas ringan & tugas tim")

with st.sidebar:
    st.header("Pengaturan")
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password", placeholder="Masukkan API Key...")
    
    st.markdown("---")
    st.markdown("**Arsitektur Tim:**")
    st.markdown("- **Lead Agent:** `gemini-3.5-flash` (Cepat & Stabil)")
    st.markdown("- **Sub-Agent Analis:** `gemini-3.5-flash-lite`")
    st.markdown("- **Sub-Agent Penulis:** `gemini-3.5-flash-lite`")

def jalankan_sistem_agent(key: str, perintah_utama: str, status_box):
    client = genai.Client(api_key=key)

    def panggil_model_aman(daftar_model: list, prompt: str, config=None):
        for nama_model in daftar_model:
            try:
                chat = client.chats.create(model=nama_model, config=config)
                return chat.send_message(prompt)
            except ServerError as e:
                if e.code == 503:
                    status_box.write(f"⚠️ {nama_model} sibuk, beralih ke cadangan...")
                    continue
                raise e
        raise RuntimeError("Semua model sedang sibuk (503). Silakan coba sesaat lagi.")

    # Sub-Agent 1: Analis
    def sub_agent_analis(topik_atau_data: str) -> str:
        """Membedah data, mencari akar masalah, atau menyusun poin teknis terukur untuk tugas analisis."""
        status_box.write("🔍 **Sub-Agent Analis** sedang membedah data & poin teknis...")
        respon = panggil_model_aman(
            daftar_model=["gemini-3.5-flash-lite", "gemini-2.5-flash-lite"],
            prompt=f"Anda adalah Analis Teknis senior. Bedah topik berikut menjadi poin-poin teknis dan metrik terukur:\n\n{topik_atau_data}"
        )
        return respon.text

    # Sub-Agent 2: Penulis
    def sub_agent_penulis(bahan_laporan: str) -> str:
        """Mengubah hasil analisis mentah menjadi laporan rapi dan terstruktur."""
        status_box.write("✍️ **Sub-Agent Penulis** sedang menyusun laporan eksekutif...")
        respon = panggil_model_aman(
            daftar_model=["gemini-3.5-flash-lite", "gemini-2.5-flash-lite"],
            prompt=f"Anda adalah Penulis Laporan Eksekutif. Susun bahan berikut menjadi laporan profesional, ringkas, dan gunakan tabel jika perlu:\n\n{bahan_laporan}"
        )
        return respon.text

    # Instruksi Cerdas: Jawab langsung untuk hal ringan, kerahkan tim untuk tugas berat
    instruksi_sistem = (
        "Anda adalah Lead Project Manager AI yang memimpin tim berisi 'sub_agent_analis' dan 'sub_agent_penulis'. "
        "ATURAN KEPUTUSAN:\n"
        "1. JIKA pengguna hanya menyapa, bertanya identitas Anda, atau mengajukan pertanyaan ringan/umum: "
        "JAWAB LANGSUNG dengan singkat, ramah, dan cepat TANPA memanggil sub-agent.\n"
        "2. JIKA pengguna meminta analisis mendalam, kerangka kerja, evaluasi data, atau pembuatan laporan terstruktur: "
        "Panggil 'sub_agent_analis' terlebih dahulu, lalu serahkan hasilnya ke 'sub_agent_penulis', kemudian sajikan hasil akhirnya."
    )

    konfigurasi_lead = types.GenerateContentConfig(
        system_instruction=instruksi_sistem,
        tools=[sub_agent_analis, sub_agent_penulis],
        temperature=0.2
    )

    status_box.write("🧠 **Lead Agent** sedang mengevaluasi instruksi...")
    respon_lead = panggil_model_aman(
        daftar_model=["gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.8-flash"],
        prompt=perintah_utama,
        config=konfigurasi_lead
    )
    return respon_lead.text

# Area Input Pengguna di Web
perintah = st.text_area(
    "Masukkan tugas atau instruksi untuk Lead Agent:",
    height=120,
    placeholder="Contoh ringan: Siapa kamu? | Contoh tugas tim: Buatkan evaluasi kinerja bulanan dan 5 KPI utama."
)

if st.button("🚀 Jalankan Tim Agent", type="primary"):
    if not api_key:
        st.error("Masukkan Gemini API Key terlebih dahulu di panel sebelah kiri.")
    elif not perintah.strip():
        st.warning("Silakan tulis tugas terlebih dahulu.")
    else:
        with st.status("Memproses permintaan...", expanded=True) as status:
            try:
                hasil = jalankan_sistem_agent(api_key, perintah, status)
                status.update(label="Selesai!", state="complete", expanded=False)
                st.markdown("### Hasil Akhir dari Lead Agent")
                st.markdown(hasil)
            except Exception as e:
                status.update(label="Terjadi kesalahan", state="error")
                st.error(f"Detail error: {e}")
