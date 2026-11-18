import os
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import ServerError

# Konfigurasi Halaman Web
st.set_page_config(page_title="Lead AI Agent System", page_icon="🤖", layout="wide")
st.title("🤖 Sistem Multi-Agent (Lead & Sub-Agent)")
st.caption("Ditenagai oleh Gemini API — Berjalan tanpa beban lokal")

# Sidebar untuk Pengaturan API Key (Aman untuk Web Lokal & Online)
with st.sidebar:
    st.header("Pengaturan")
    # Otomatis mengambil dari Streamlit Secrets jika sudah online, atau input manual
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password", placeholder="Masukkan API Key...")
    
    st.markdown("---")
    st.markdown("**Arsitektur Tim:**")
    st.markdown("- **Lead Agent:** `gemini-3.8-flash` (Cadangan: `3.5-flash`)")
    st.markdown("- **Sub-Agent Analis:** `gemini-3.5-flash-lite`")
    st.markdown("- **Sub-Agent Penulis:** `gemini-3.5-flash-lite`")

# Fungsi Utama Agen
def jalankan_sistem_agent(key: str, perintah_utama: str):
    client = genai.Client(api_key=key)

    def panggil_model_aman(daftar_model: list, prompt: str, config=None):
        for nama_model in daftar_model:
            try:
                chat = client.chats.create(model=nama_model, config=config)
                return chat.send_message(prompt)
            except ServerError as e:
                if e.code == 503:
                    continue
                raise e
        raise RuntimeError("Semua model sedang sibuk (503). Silakan coba sesaat lagi.")

    # Sub-Agent 1: Analis
    def sub_agent_analis(topik_atau_data: str) -> str:
        """Membedah data, mencari akar masalah, atau menyusun poin teknis terukur."""
        st.toast("🔍 Sub-Agent Analis sedang bekerja...")
        respon = panggil_model_aman(
            daftar_model=["gemini-3.5-flash-lite", "gemini-2.5-flash-lite"],
            prompt=f"Anda adalah Analis Teknis senior. Bedah topik berikut menjadi poin-poin teknis dan metrik terukur:\n\n{topik_atau_data}"
        )
        return respon.text

    # Sub-Agent 2: Penulis
    def sub_agent_penulis(bahan_laporan: str) -> str:
        """Mengubah hasil analisis mentah menjadi laporan rapi dan terstruktur."""
        st.toast("✍️ Sub-Agent Penulis sedang menyusun laporan...")
        respon = panggil_model_aman(
            daftar_model=["gemini-3.5-flash-lite", "gemini-2.5-flash-lite"],
            prompt=f"Anda adalah Penulis Laporan Eksekutif. Susun bahan berikut menjadi laporan profesional, ringkas, dan gunakan tabel jika perlu:\n\n{bahan_laporan}"
        )
        return respon.text

    # Lead Agent
    instruksi_sistem = (
        "Anda adalah Lead Project Manager AI. Anda TIDAK boleh mengerjakan analisis atau penulisan sendirian. "
        "Panggil 'sub_agent_analis' terlebih dahulu untuk membedah topik, lalu serahkan hasilnya ke 'sub_agent_penulis' "
        "untuk menyusun laporan akhir, dan terakhir tinjau sebelum disajikan ke pengguna."
    )

    konfigurasi_lead = types.GenerateContentConfig(
        system_instruction=instruksi_sistem,
        tools=[sub_agent_analis, sub_agent_penulis],
        temperature=0.2
    )

    respon_lead = panggil_model_aman(
        daftar_model=["gemini-3.8-flash", "gemini-3.5-flash", "gemini-2.5-flash"],
        prompt=perintah_utama,
        config=konfigurasi_lead
    )
    return respon_lead.text

# Area Input Pengguna di Web
perintah = st.text_area(
    "Masukkan tugas atau instruksi untuk Lead Agent:",
    height=120,
    placeholder="Contoh: Buatkan kerangka evaluasi kinerja bulanan operasional lapangan beserta 5 KPI utama."
)

if st.button("🚀 Jalankan Tim Agent", type="primary"):
    if not api_key:
        st.error("Masukkan Gemini API Key terlebih dahulu di panel sebelah kiri.")
    elif not perintah.strip():
        st.warning("Silakan tulis tugas terlebih dahulu.")
    else:
        with st.spinner("Lead Agent sedang mengoordinasi tim..."):
            try:
                hasil = jalankan_sistem_agent(api_key, perintah)
                st.success("Selesai!")
                st.markdown("### Hasil Akhir dari Lead Agent")
                st.markdown(hasil)
            except Exception as e:
                st.error(f"Terjadi kesalahan: {e}")