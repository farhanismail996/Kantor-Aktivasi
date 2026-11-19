import os
import json
import base64
import datetime
import requests
import pandas as pd
from pypdf import PdfReader
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from google.genai.errors import APIError

st.set_page_config(page_title="Kantor Aktivasi 3D - PLN Icon Plus", page_icon="🏢", layout="wide")

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
    write_json_cloud(f"{MEMORY_DIR}/{safe_name}.json", data, f"Update memori PTL: {safe_name}")

def load_team_workspace() -> dict:
    return read_json_cloud(
        f"{MEMORY_DIR}/team_workspace.json",
        {"shared_docs": [], "team_messages": []}
    )

def save_team_workspace(data: dict):
    write_json_cloud(f"{MEMORY_DIR}/team_workspace.json", data, "Update ruang diskusi & dokumen PTL")

def load_preconfig_templates() -> dict:
    return read_json_cloud(
        f"{MEMORY_DIR}/preconfig_templates.json",
        {"templates": {}}
    )

def save_preconfig_templates(data: dict):
    write_json_cloud(f"{MEMORY_DIR}/preconfig_templates.json", data, "Update pustaka template preconfig jaringan")

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
                    if fname.endswith(".json") and fname not in ("team_workspace.json", "preconfig_templates.json"):
                        uname = fname.replace(".json", "")
                        udata = read_json_cloud(f"{MEMORY_DIR}/{fname}", {})
                        if udata.get("ringkasan_profil"):
                            profil_tim.append(f"### Personel PTL: {uname.upper()}\n{udata['ringkasan_profil']}")
                if profil_tim:
                    return "\n\n".join(profil_tim)
        except Exception:
            pass

    for fname in os.listdir(MEMORY_DIR):
        if fname.endswith(".json") and fname not in ("team_workspace.json", "preconfig_templates.json"):
            uname = fname.replace(".json", "")
            udata = read_json_cloud(f"{MEMORY_DIR}/{fname}", {})
            if udata.get("ringkasan_profil"):
                profil_tim.append(f"### Personel PTL: {uname.upper()}\n{udata['ringkasan_profil']}")
    return "\n\n".join(profil_tim) if profil_tim else "Belum ada profil anggota tim lain yang tersimpan."

# --- PELACAK TELEMETRI & STATUS 4 AGENT ---
if "agent_telemetry" not in st.session_state:
    st.session_state.agent_telemetry = {
        "active_agents": [],
        "task_desc": "Semua agent standby di kantor 3D menunggu perintah Koordinator/PTL.",
        "counts": {"sigap": 0, "teliti": 0, "rapih": 0, "sinergi": 0},
        "logs": []
    }

def catat_aktivitas_agent(agen_aktif: list, keterangan: str):
    st.session_state.agent_telemetry["active_agents"] = agen_aktif
    st.session_state.agent_telemetry["task_desc"] = keterangan
    for a in agen_aktif:
        if a in st.session_state.agent_telemetry["counts"]:
            st.session_state.agent_telemetry["counts"][a] += 1
    waktu = datetime.datetime.now().strftime("%H:%M:%S")
    st.session_state.agent_telemetry["logs"].insert(0, f"`[{waktu}]` **{', '.join([x.upper() for x in agen_aktif])}** — {keterangan}")
    st.session_state.agent_telemetry["logs"] = st.session_state.agent_telemetry["logs"][:15]

# --- KOMPONEN KANTOR AKTIVASI 3D INTERAKTIF (THREE.JS + LOGO PLN ICON PLUS + AVATAR USER & TIM) ---
@st.cache_data(ttl=86400)
def get_logo_base64(url: str) -> str:
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            b64 = base64.b64encode(res.content).decode("utf-8")
            return f"data:image/png;base64,{b64}"
    except Exception:
        pass
    return url

def get_registered_ptl_users() -> list:
    users = {"farhan", "nana", "dini"}
    if os.path.exists(MEMORY_DIR):
        for fname in os.listdir(MEMORY_DIR):
            if fname.endswith(".json") and fname not in ("team_workspace.json", "preconfig_templates.json"):
                users.add(fname.replace(".json", ""))
    return sorted(list(users))

def render_virtual_office(active_agents: list, task_desc: str, compact: bool = False, current_user: str = ""):
    active_json = json.dumps(active_agents)
    height_px = 380 if compact else 600
    logo_src = get_logo_base64("https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRuvw1_lhxi6vPGu8wDCBOg1lIbDNM_vxICxJJIFkHhTg&s=10")
    raw_user = (current_user or st.session_state.get("logged_in_user") or "farhan").lower().strip()
    user_display = raw_user.capitalize()
    user_role = "Koordinator PTL" if raw_user == "farhan" else "Personel PTL"
    coworkers = [u for u in get_registered_ptl_users() if u != raw_user]
    coworkers_json = json.dumps(coworkers)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }}
        body {{ background: #bae6fd; overflow: hidden; border-radius: 14px; border: 1px solid #7dd3fc; }}
        #hud-top {{
            position: absolute; top: 10px; left: 12px; right: 12px; z-index: 10;
            display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;
            background: rgba(15, 23, 42, 0.88); backdrop-filter: blur(6px);
            padding: 8px 14px; border-radius: 10px; border: 1px solid #38bdf8; color: #f8fafc;
        }}
        .hud-title {{ font-weight: 800; font-size: 13px; color: #38bdf8; letter-spacing: 0.4px; }}
        .hud-sub {{ font-size: 11px; color: #e2e8f0; }}
        #hud-hint {{
            position: absolute; bottom: 10px; right: 12px; z-index: 10;
            background: rgba(15, 23, 42, 0.82); color: #cbd5e1;
            font-size: 10px; padding: 4px 10px; border-radius: 8px; border: 1px solid #334155;
        }}
        .label-3d {{
            position: absolute; transform: translate(-50%, -100%);
            background: rgba(15, 23, 42, 0.92); border: 1.5px solid #475569;
