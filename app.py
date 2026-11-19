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
        "task_desc": "Semua agent standby di lounge 3D menunggu perintah Koordinator/PTL.",
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

# --- KOMPONEN KANTOR AKTIVASI 3D INTERAKTIF (THREE.JS + TEKS 3D + INTERIOR LENGKAP) ---
def render_virtual_office(active_agents: list, task_desc: str, compact: bool = False):
    """
    Kantor Aktivasi 3D dengan interior lengkap:
    - Papan teks 3D 'KANTOR AKTIVASI - PLN ICON PLUS SBU SUMBAGSEL' di dinding utama
    - Plakat teks 3D di setiap meja kubikel ('MEJA SIGAP', 'MEJA TELITI', 'MEJA RAPIH', 'MEJA SINERGI')
    - Rak Server Jaringan 3D berkedip, Papan Dashboard KPI 3D, Partisi Kaca, Mesin Kopi Lounge & Tanaman Sudut
    """
    active_json = json.dumps(active_agents)
    height_px = 350 if compact else 560

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }}
        body {{ background: #090d16; overflow: hidden; border-radius: 14px; border: 1px solid #334155; }}
        #hud-top {{
            position: absolute; top: 10px; left: 12px; right: 12px; z-index: 10;
            display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;
            background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(6px);
            padding: 8px 14px; border-radius: 10px; border: 1px solid #334155; color: #f8fafc;
        }}
        .hud-title {{ font-weight: 800; font-size: 13px; color: #38bdf8; letter-spacing: 0.4px; }}
        .hud-sub {{ font-size: 11px; color: #cbd5e1; }}
        #hud-hint {{
            position: absolute; bottom: 10px; right: 12px; z-index: 10;
            background: rgba(15, 23, 42, 0.8); color: #94a3b8;
            font-size: 10px; padding: 4px 10px; border-radius: 8px; border: 1px solid #1e293b;
        }}
        .label-3d {{
            position: absolute; transform: translate(-50%, -100%);
            background: rgba(15, 23, 42, 0.92); border: 1.5px solid #475569;
            color: #f8fafc; padding: 4px 8px; border-radius: 8px;
            font-size: 11px; font-weight: 700; pointer-events: none;
            text-align: center; white-space: nowrap; box-shadow: 0 4px 12px rgba(0,0,0,0.45);
            transition: border-color 0.3s, background 0.3s;
        }}
        .label-3d.working {{
            border-color: #10b981; background: rgba(6, 78, 59, 0.94);
        }}
        .label-role {{ font-size: 9px; font-weight: 500; color: #cbd5e1; display: block; }}
        #canvas-container {{ width: 100%; height: {height_px}px; display: block; cursor: grab; }}
        #canvas-container:active {{ cursor: grabbing; }}
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    </head>
    <body>
        <div id="hud-top">
            <span class="hud-title">🏢 KANTOR AKTIVASI 3D — PLN ICON PLUS SBU SUMBAGSEL</span>
            <span class="hud-sub">{task_desc}</span>
        </div>
        <div id="hud-hint">🖱️ Klik & geser untuk putar 3D • Scroll untuk Zoom</div>
        <div id="labels-layer"></div>
        <div id="canvas-container"></div>

        <script>
            const activeAgents = {active_json};
            const container = document.getElementById('canvas-container');
            const labelsLayer = document.getElementById('labels-layer');

            // HELPER MEMBUAT TEKSTUR TEKS 3D TAJAM (CANVAS TEXTURE)
            function createTextSign(mainText, subText, bgColor, borderColor, textColor, widthPx = 1024, heightPx = 256) {{
                const canvas = document.createElement('canvas');
                canvas.width = widthPx;
                canvas.height = heightPx;
                const ctx = canvas.getContext('2d');

                ctx.fillStyle = bgColor;
                ctx.fillRect(0, 0, widthPx, heightPx);

                ctx.strokeStyle = borderColor;
                ctx.lineWidth = 12;
                ctx.strokeRect(8, 8, widthPx - 16, heightPx - 16);

                ctx.fillStyle = textColor;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';

                if (subText) {{
                    ctx.font = 'bold ' + Math.floor(heightPx * 0.34) + 'px Segoe UI, sans-serif';
                    ctx.fillText(mainText, widthPx / 2, heightPx * 0.38);
                    ctx.fillStyle = '#94a3b8';
                    ctx.font = '600 ' + Math.floor(heightPx * 0.18) + 'px Segoe UI, sans-serif';
                    ctx.fillText(subText, widthPx / 2, heightPx * 0.74);
                }} else {{
                    ctx.font = 'bold ' + Math.floor(heightPx * 0.44) + 'px Segoe UI, sans-serif';
                    ctx.fillText(mainText, widthPx / 2, heightPx * 0.52);
                }}

                const texture = new THREE.CanvasTexture(canvas);
                texture.anisotropy = 4;
                return texture;
            }}

            // 1. SCENE, CAMERA & RENDERER
            const scene = new THREE.Scene();
            scene.background = new THREE.Color(0x090d16);
            scene.fog = new THREE.FogExp2(0x090d16, 0.025);

            const camera = new THREE.PerspectiveCamera(42, container.clientWidth / container.clientHeight, 0.1, 100);
            camera.position.set(0, 8.6, 11.8);

            const renderer = new THREE.WebGLRenderer({{ antialias: true }});
            renderer.setSize(container.clientWidth, container.clientHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            renderer.shadowMap.enabled = true;
            renderer.shadowMap.type = THREE.PCFSoftShadowMap;
            container.appendChild(renderer.domElement);

            const controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.06;
            controls.maxPolarAngle = Math.PI / 2.15;
            controls.minDistance = 5;
            controls.maxDistance = 20;
            controls.target.set(0, 0.8, 0.1);

            // 2. PENCAHAYAAN RUANGAN
            const ambientLight = new THREE.AmbientLight(0xcbd5e1, 0.8);
            scene.add(ambientLight);

            const dirLight = new THREE.DirectionalLight(0xffffff, 0.95);
            dirLight.position.set(7, 14, 9);
            dirLight.castShadow = true;
            dirLight.shadow.mapSize.width = 1024;
            dirLight.shadow.mapSize.height = 1024;
            scene.add(dirLight);

            const accentLight = new THREE.PointLight(0x38bdf8, 0.85, 22);
            accentLight.position.set(0, 4.5, -3.5);
            scene.add(accentLight);

            // 3. LANTAI KANTOR, DINDING & TEKS 3D 'KANTOR AKTIVASI'
            const floor = new THREE.Mesh(
                new THREE.BoxGeometry(16.5, 0.3, 10.5),
                new THREE.MeshStandardMaterial({{ color: 0x1e293b, roughness: 0.55 }})
            );
            floor.position.y = -0.15;
            floor.receiveShadow = true;
            scene.add(floor);

            const gridHelper = new THREE.GridHelper(16, 16, 0x334155, 0x1e293b);
            gridHelper.position.y = 0.01;
            scene.add(gridHelper);

            // Karpet Zona Kerja & Zona Lounge
            const workCarpet = new THREE.Mesh(
                new THREE.BoxGeometry(13.2, 0.04, 4.0),
                new THREE.MeshStandardMaterial({{ color: 0x172554, roughness: 0.85 }})
            );
            workCarpet.position.set(0, 0.02, -1.9);
            workCarpet.receiveShadow = true;
            scene.add(workCarpet);

            const loungeCarpet = new THREE.Mesh(
                new THREE.BoxGeometry(13.2, 0.04, 3.6),
                new THREE.MeshStandardMaterial({{ color: 0x1e293b, roughness: 0.9 }})
            );
            loungeCarpet.position.set(0, 0.02, 2.5);
            loungeCarpet.receiveShadow = true;
            scene.add(loungeCarpet);

            // Dinding Utama Belakang
            const backWall = new THREE.Mesh(
                new THREE.BoxGeometry(16.5, 3.6, 0.3),
                new THREE.MeshStandardMaterial({{ color: 0x0f172a, roughness: 0.5 }})
            );
            backWall.position.set(0, 1.8, -5.1);
            backWall.receiveShadow = true;
            scene.add(backWall);

            // Dinding Samping Kiri (Rak Server & NOC)
            const leftWall = new THREE.Mesh(
                new THREE.BoxGeometry(0.3, 3.2, 10.5),
                new THREE.MeshStandardMaterial({{ color: 0x0f172a, roughness: 0.6 }})
            );
            leftWall.position.set(-8.1, 1.6, 0);
            scene.add(leftWall);

            // PAPAN NAMA 3D BESAR: "KANTOR AKTIVASI"
            const mainSignTex = createTextSign(
                'KANTOR AKTIVASI',
                'PLN ICON PLUS • SBU SUMBAGSEL (TIM PTL)',
                '#020617',
                '#38bdf8',
                '#38bdf8',
                1024,
                256
            );
            const mainSignBoard = new THREE.Mesh(
                new THREE.BoxGeometry(6.8, 1.5, 0.14),
                new THREE.MeshBasicMaterial({{ map: mainSignTex }})
            );
            mainSignBoard.position.set(0, 2.55, -4.88);
            scene.add(mainSignBoard);

            // PAPAN ZONA LANTAI 3D: "LOUNGE & ISTIRAHAT PTL"
            const loungeSignTex = createTextSign('AREA ISTIRAHAT & DISKUSI PTL', null, '#0f172a', '#475569', '#94a3b8', 512, 96);
            const loungeFloorPlaque = new THREE.Mesh(
                new THREE.PlaneGeometry(3.8, 0.65),
                new THREE.MeshBasicMaterial({{ map: loungeSignTex }})
            );
            loungeFloorPlaque.rotation.x = -Math.PI / 2;
            loungeFloorPlaque.position.set(0, 0.05, 4.05);
            scene.add(loungeFloorPlaque);

            // 4. INTERIOR PELENGKAP (RAK SERVER NOC, PAPAN DASHBOARD, MESIN KOPI, TANAMAN)
            // A. Dua Rak Server Jaringan di Kiri Belakang (Area Teknis)
            const serverLEDs = [];
            [-7.2, -6.1].forEach((sx, rIdx) => {{
                const rack = new THREE.Mesh(
                    new THREE.BoxGeometry(0.85, 2.3, 0.9),
                    new THREE.MeshStandardMaterial({{ color: 0x020617, metalness: 0.6, roughness: 0.3 }})
                );
                rack.position.set(sx, 1.15, -4.2);
                rack.castShadow = true;
                scene.add(rack);

                // Lampu indikator switch/OLT berkedip
                for (let row = 0; row < 5; row++) {{
                    const led = new THREE.Mesh(
                        new THREE.BoxGeometry(0.55, 0.05, 0.04),
                        new THREE.MeshBasicMaterial({{ color: row % 2 === 0 ? 0x10b981 : 0x38bdf8 }})
                    );
                    led.position.set(sx, 0.55 + row * 0.36, -3.73);
                    scene.add(led);
                    serverLEDs.push({{ mesh: led, phase: rIdx * 2 + row }});
                }}
            }});

            // B. Papan Dashboard Target Aktivasi di Dinding Kiri
            const kpiTex = createTextSign(
                'DASHBOARD AKTIVASI',
                'KORPORAT & PUBLIK • SLA & PRECONFIG',
                '#0f172a',
                '#10b981',
                '#6ee7b7',
                512,
                256
            );
            const kpiBoard = new THREE.Mesh(
                new THREE.BoxGeometry(0.12, 1.4, 2.8),
                new THREE.MeshBasicMaterial({{ map: kpiTex }})
            );
            kpiBoard.position.set(-7.88, 1.85, -1.2);
            scene.add(kpiBoard);

            // C. Pantry / Meja Mesin Kopi di Kanan Lounge
            const pantryCounter = new THREE.Mesh(
                new THREE.BoxGeometry(1.1, 0.95, 2.2),
                new THREE.MeshStandardMaterial({{ color: 0x334155, roughness: 0.5 }})
            );
            pantryCounter.position.set(7.2, 0.475, 2.4);
            pantryCounter.castShadow = true;
            scene.add(pantryCounter);

            const coffeeMachine = new THREE.Mesh(
                new THREE.BoxGeometry(0.55, 0.55, 0.55),
                new THREE.MeshStandardMaterial({{ color: 0x0f172a, metalness: 0.7 }})
            );
            coffeeMachine.position.set(7.2, 1.22, 2.0);
            scene.add(coffeeMachine);

            const dispenser = new THREE.Mesh(
                new THREE.CylinderGeometry(0.22, 0.22, 0.65, 16),
                new THREE.MeshStandardMaterial({{ color: 0x38bdf8, transparent: true, opacity: 0.75 }})
            );
            dispenser.position.set(7.2, 1.28, 2.9);
            scene.add(dispenser);

            // D. Tanaman Hias Sudut Ruangan (4 Sudut)
            [[-7.3, 4.3], [7.3, -4.3], [7.3, 4.3], [-7.3, -2.9]].forEach(([px, pz]) => {{
                const pot = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.28, 0.2, 0.42, 16),
                    new THREE.MeshStandardMaterial({{ color: 0x475569 }})
                );
                pot.position.set(px, 0.21, pz);
                const leaves = new THREE.Mesh(
                    new THREE.DodecahedronGeometry(0.45, 1),
                    new THREE.MeshStandardMaterial({{ color: 0x059669, roughness: 0.8 }})
                );
                leaves.position.set(px, 0.72, pz);
                leaves.castShadow = true;
                scene.add(pot, leaves);
            }});

            // 5. KONFIGURASI 4 AGENT SPESIALIS PTL
            const agentConfigs = [
                {{ id: 'sigap', name: 'SIGAP', role: 'Lead & Router', hex: '#38bdf8', color: 0x38bdf8, x: -4.65 }},
                {{ id: 'teliti', name: 'TELITI', role: 'Analis & Preconfig', hex: '#f59e0b', color: 0xf59e0b, x: -1.55 }},
                {{ id: 'rapih', name: 'RAPIH', role: 'Laporan & Rekap', hex: '#a855f7', color: 0xa855f7, x: 1.55 }},
                {{ id: 'sinergi', name: 'SINERGI', role: 'Fasilitator Tim', hex: '#10b981', color: 0x10b981, x: 4.65 }}
            ];

            // Partisi Kaca Antar-Kubikel Meja Kerja
            [-3.1, 0, 3.1].forEach((gx) => {{
                const glassDivider = new THREE.Mesh(
                    new THREE.BoxGeometry(0.06, 1.15, 2.1),
                    new THREE.MeshPhysicalMaterial({{
                        color: 0x38bdf8, transparent: true, opacity: 0.18, roughness: 0.1
                    }})
                );
                glassDivider.position.set(gx, 0.58, -2.3);
                scene.add(glassDivider);
            }});

            const agentObjects = [];

            agentConfigs.forEach((cfg) => {{
                const isWorking = activeAgents.includes(cfg.id);

                // A. MEJA KERJA 3D, MONITOR & PLAKAT NAMA MEJA 3D (Z = -2.4)
                const deskGroup = new THREE.Group();
                deskGroup.position.set(cfg.x, 0, -2.4);

                const tableTop = new THREE.Mesh(
                    new THREE.BoxGeometry(2.2, 0.1, 1.05),
                    new THREE.MeshStandardMaterial({{ color: 0x334155, roughness: 0.4 }})
                );
                tableTop.position.y = 0.75;
                tableTop.castShadow = true;
                tableTop.receiveShadow = true;
                deskGroup.add(tableTop);

                // Plakat Nama 3D di depan meja ("MEJA SIGAP", dst.)
                const deskSignTex = createTextSign('MEJA ' + cfg.name, cfg.role, '#0f172a', cfg.hex, '#f8fafc', 512, 140);
                const deskPlaque = new THREE.Mesh(
                    new THREE.PlaneGeometry(1.5, 0.42),
                    new THREE.MeshBasicMaterial({{ map: deskSignTex }})
                );
                deskPlaque.position.set(0, 0.46, 0.53);
                deskGroup.add(deskPlaque);

                const legGeo = new THREE.BoxGeometry(0.08, 0.75, 0.9);
                const legMat = new THREE.MeshStandardMaterial({{ color: 0x0f172a }});
                const legL = new THREE.Mesh(legGeo, legMat); legL.position.set(-0.95, 0.375, 0);
                const legR = new THREE.Mesh(legGeo, legMat); legR.position.set(0.95, 0.375, 0);
                deskGroup.add(legL, legR);

                // Monitor Dual/Wide 3D
                const monitorFrame = new THREE.Mesh(
                    new THREE.BoxGeometry(1.15, 0.62, 0.06),
                    new THREE.MeshStandardMaterial({{ color: 0x020617 }})
                );
                monitorFrame.position.set(0, 1.18, -0.22);
                deskGroup.add(monitorFrame);

                const screenMat = new THREE.MeshBasicMaterial({{
                    color: isWorking ? cfg.color : 0x1e293b
                }});
                const monitorScreen = new THREE.Mesh(new THREE.PlaneGeometry(1.06, 0.54), screenMat);
                monitorScreen.position.set(0, 1.18, -0.185);
                deskGroup.add(monitorScreen);

                // Lampu Menara Status Kubikel
                const statusBeacon = new THREE.Mesh(
                    new THREE.SphereGeometry(0.1, 16, 16),
                    new THREE.MeshBasicMaterial({{ color: isWorking ? 0x10b981 : 0x475569 }})
                );
                statusBeacon.position.set(0.9, 0.9, -0.35);
                deskGroup.add(statusBeacon);

                scene.add(deskGroup);

                // B. SOFA ISTIRAHAT 3D DI LOUNGE (Z = 2.6)
                const sofaGroup = new THREE.Group();
                sofaGroup.position.set(cfg.x, 0, 2.6);

                const sofaSeat = new THREE.Mesh(
                    new THREE.BoxGeometry(1.65, 0.38, 0.85),
                    new THREE.MeshStandardMaterial({{ color: 0x334155, roughness: 0.8 }})
                );
                sofaSeat.position.y = 0.19;
                sofaSeat.castShadow = true;
                sofaGroup.add(sofaSeat);

                const sofaBack = new THREE.Mesh(
                    new THREE.BoxGeometry(1.65, 0.55, 0.2),
                    new THREE.MeshStandardMaterial({{ color: 0x475569, roughness: 0.8 }})
                );
                sofaBack.position.set(0, 0.52, 0.32);
                sofaBack.castShadow = true;
                sofaGroup.add(sofaBack);

                const coffeeTable = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.32, 0.32, 0.32, 20),
                    new THREE.MeshStandardMaterial({{ color: 0x0f172a }})
                );
                coffeeTable.position.set(0.55, 0.16, -0.75);
                sofaGroup.add(coffeeTable);

                scene.add(sofaGroup);

                // C. KARAKTER AVATAR 3D AGENT
                const charGroup = new THREE.Group();
                const targetZ = isWorking ? -1.5 : 2.35;
                charGroup.position.set(cfg.x, 0, isWorking ? 0.4 : -0.3);

                const bodyMesh = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.24, 0.32, 0.72, 20),
                    new THREE.MeshStandardMaterial({{ color: cfg.color, roughness: 0.35 }})
                );
                bodyMesh.position.y = 0.65;
                bodyMesh.castShadow = true;
                charGroup.add(bodyMesh);

                const headMesh = new THREE.Mesh(
                    new THREE.SphereGeometry(0.26, 24, 24),
                    new THREE.MeshStandardMaterial({{ color: 0xf8fafc, roughness: 0.3 }})
                );
                headMesh.position.y = 1.25;
                headMesh.castShadow = true;
                charGroup.add(headMesh);

                const visorMesh = new THREE.Mesh(
                    new THREE.BoxGeometry(0.34, 0.1, 0.12),
                    new THREE.MeshBasicMaterial({{ color: isWorking ? 0x10b981 : 0x64748b }})
                );
                visorMesh.position.set(0, 1.27, -0.21);
                charGroup.add(visorMesh);

                const armGeo = new THREE.CylinderGeometry(0.07, 0.07, 0.45, 12);
                const armMat = new THREE.MeshStandardMaterial({{ color: 0xe2e8f0 }});
                const leftArm = new THREE.Mesh(armGeo, armMat);
                leftArm.position.set(-0.32, 0.78, -0.12);
                leftArm.rotation.x = Math.PI / 3;

                const rightArm = new THREE.Mesh(armGeo, armMat);
                rightArm.position.set(0.32, 0.78, -0.12);
                rightArm.rotation.x = Math.PI / 3;

                charGroup.add(leftArm, rightArm);
                scene.add(charGroup);

                // Label Melayang di atas kepala karakter 3D
                const labelDiv = document.createElement('div');
                labelDiv.className = 'label-3d' + (isWorking ? ' working' : '');
                labelDiv.innerHTML = `${{isWorking ? '🟢' : '☕'}} ${{cfg.name}} <span class="label-role">${{isWorking ? 'Sedang Bekerja' : 'Istirahat'}}</span>`;
                labelsLayer.appendChild(labelDiv);

                agentObjects.push({{
                    cfg, isWorking, charGroup, leftArm, rightArm, screenMat, targetZ, labelDiv
                }});
            }});

            // 6. LOOP ANIMASI 3D REAL-TIME
            const clock = new THREE.Clock();
            function animate() {{
                requestAnimationFrame(animate);
                const t = clock.getElapsedTime();

                // Animasi kedip lampu server NOC
                serverLEDs.forEach((item) => {{
                    const blink = Math.sin(t * 5 + item.phase) > 0;
                    item.mesh.visible = blink;
                }});

                agentObjects.forEach((obj, idx) => {{
                    obj.charGroup.position.z += (obj.targetZ - obj.charGroup.position.z) * 0.05;

                    if (obj.isWorking) {{
                        obj.charGroup.rotation.y += (0 - obj.charGroup.rotation.y) * 0.1;
                        obj.charGroup.position.y = Math.abs(Math.sin(t * 8 + idx)) * 0.05;
                        obj.leftArm.rotation.x = (Math.PI / 3) + Math.sin(t * 16 + idx) * 0.25;
                        obj.rightArm.rotation.x = (Math.PI / 3) - Math.sin(t * 16 + idx) * 0.25;
                    }} else {{
                        obj.charGroup.rotation.y += (Math.PI - obj.charGroup.rotation.y) * 0.08;
                        obj.charGroup.position.y = Math.sin(t * 2 + idx) * 0.03;
                        obj.leftArm.rotation.x = 0.2;
                        obj.rightArm.rotation.x = 0.2;
                    }}

                    const headPos = new THREE.Vector3(
                        obj.charGroup.position.x,
                        obj.charGroup.position.y + 1.72,
                        obj.charGroup.position.z
                    );
                    headPos.project(camera);

                    const x2d = (headPos.x * 0.5 + 0.5) * container.clientWidth;
                    const y2d = (-headPos.y * 0.5 + 0.5) * container.clientHeight;
                    obj.labelDiv.style.left = `${{x2d}}px`;
                    obj.labelDiv.style.top = `${{y2d}}px`;
                }});

                controls.update();
                renderer.render(scene, camera);
            }}
            animate();

            window.addEventListener('resize', () => {{
                camera.aspect = container.clientWidth / container.clientHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(container.clientWidth, container.clientHeight);
            }});
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=height_px + 4)

# --- FUNGSI EKSTRAKSI EXCEL, CSV, PDF & NOTEPAD PRECONFIG (.TXT) ---
def ekstrak_isi_file(uploaded_file) -> str:
    nama_file = uploaded_file.name.lower()
    try:
        if nama_file.endswith(".txt"):
            teks_raw = uploaded_file.getvalue().decode("utf-8", errors="replace")
            return (
                f"=== FILE TEMPLATE PRECONFIG / NOTEPAD: {uploaded_file.name} ===\n"
                f"```text\n{teks_raw}\n```"
            )
        elif nama_file.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
            ringkasan_angka = df.describe(include="all").to_string()
            return (
                f"=== FILE CSV: {uploaded_file.name} (Total {len(df)} baris, {len(df.columns)} kolom) ===\n"
                f"Nama Kolom: {', '.join(df.columns.astype(str))}\n\n"
                f"Statistik Ringkas:\n{ringkasan_angka}\n\n"
                f"Data Lengkap (maks 150 baris):\n{df.head(150).to_csv(index=False)}"
            )
        elif nama_file.endswith((".xlsx", ".xls")):
            excel_data = pd.read_excel(uploaded_file, sheet_name=None)
            hasil_sheets = [f"=== FILE EXCEL: {uploaded_file.name} (Jumlah Sheet: {len(excel_data)}) ==="]
            for nama_sheet, df in excel_data.items():
                hasil_sheets.append(
                    f"\n--- Sheet: '{nama_sheet}' ({len(df)} baris, {len(df.columns)} kolom) ---\n"
                    f"Kolom: {', '.join(df.columns.astype(str))}\n"
                    f"Data (maks 120 baris):\n{df.head(120).to_csv(index=False)}"
                )
            return "\n".join(hasil_sheets)
        elif nama_file.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            teks_halaman = [f"=== FILE PDF: {uploaded_file.name} (Total {len(reader.pages)} halaman) ==="]
            for idx, page in enumerate(reader.pages[:25]):
                isi = page.extract_text() or ""
                teks_halaman.append(f"\n--- Halaman {idx + 1} ---\n{isi}")
            return "\n".join(teks_halaman)
        else:
            return f"Format file {uploaded_file.name} tidak didukung."
    except Exception as e:
        return f"Gagal membaca file {uploaded_file.name}: {e}"

# --- HELPER PEMANGGILAN MODEL ---
def panggil_agent_aman(client, daftar_model: list, prompt: str, system_instruction: str, temperature: float = 0.1) -> str:
    error_terakhir = None
    for nama_model in daftar_model:
        try:
            res = client.models.generate_content(
                model=nama_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature
                )
            )
            return res.text
        except APIError as e:
            error_terakhir = e
            if e.code in [400, 404, 503]:
                continue
            raise e
    raise RuntimeError(f"Agent gagal merespons ({error_terakhir}).")

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

def format_pustaka_template() -> str:
    tpl_data = load_preconfig_templates().get("templates", {})
    if not tpl_data:
        return "Belum ada template preconfig tersimpan di pustaka."
    hasil = []
    for nama_tpl, info in tpl_data.items():
        hasil.append(f"### TEMPLATE TERSIMPAN: {nama_tpl} (Vendor/Tipe: {info.get('vendor', '-')})\n```text\n{info.get('script', '')}\n```")
    return "\n\n".join(hasil)

# --- DEFINISI MULTI-AGENT PIPELINE (SIGAP -> TELITI -> RAPIH) ---
def jalankan_tim_multi_agent(client, perintah: str, konteks_dokumen: str, profil_user: str, profil_tim: str, animasi_slot, is_team_mode: bool = False) -> str:
    pustaka_tpl = format_pustaka_template()

    # TAHAP 1: AGENT TELITI BERJALAN KE MEJA KERJA 3D
    agen_tahap_1 = ["sinergi", "teliti"] if is_team_mode else ["sigap", "teliti"]
    with animasi_slot.container():
        render_virtual_office(agen_tahap_1, "Tahap 1/2: TELITI bekerja di meja 3D membedah Excel/PDF atau racik preconfig...", compact=True)

    instruksi_teliti = (
        "Anda adalah Agent TELITI (Teknisi Evaluasi Laporan & Integrasi Teknis Infrastruktur) di PLN Icon Plus SBU Sumbagsel.\n"
        "Anda melayani Koordinator PTL (Farhan) dan para PTL segmen Korporat/Publik (Nana, Dini).\n\n"
        "ATURAN KETAT ANDA:\n"
        "1. JIKA TUGAS BERUPA ANALISIS EXCEL/CSV/PDF: Hitung seluruh angka, total, aging WO, rasio progres, dan anomali kendala lapangan dengan akurat.\n"
        "2. JIKA TUGAS BERUPA PRECONFIG PERANGKAT (BDCOM, HUAWEI, MIKROTIK, CISCO, ZTE, DLL): "
        "Gunakan template preconfig yang dilampirkan ATAU dari PUSTAKA TEMPLATE TERSIMPAN di bawah. "
        "JANGAN PERNAH mengubah urutan perintah CLI, sintaks, spasi indentasi, atau command bawaan template! "
        "Hanya ganti variabel yang diminta PTL (seperti hostname, IP address, subnet/mask, gateway, VLAN ID, interface/port, deskripsi pelanggan). "
        "Jika ada parameter di dalam template yang BELUM diberikan oleh PTL, biarkan placeholder-nya terlihat jelas (misal `[ISI_IP_GATEWAY]`) dan beri peringatan daftar parameter yang masih kurang agar tidak terjadi error saat config diterapkan ke perangkat!"
    )
    prompt_teliti = (
        f"INSTRUKSI PTL / KOORDINATOR:\n{perintah}\n\n"
        f"PUSTAKA TEMPLATE PRECONFIG TIM YANG TERSIMPAN:\n{pustaka_tpl}\n\n"
        f"KONTEKS TIM PTL:\n{profil_tim}\n\n"
        f"FILE / DOKUMEN YANG DILAMPIRKAN SAAT INI:\n{konteks_dokumen if konteks_dokumen else 'Tidak ada file baru dilampirkan.'}"
    )
    hasil_mentah_teliti = panggil_agent_aman(
        client,
        ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"],
        prompt_teliti,
        instruksi_teliti,
        temperature=0.05
    )

    # TAHAP 2: AGENT RAPIH BERJALAN KE MEJA KERJA 3D (TELITI KEMBALI KE SOFA)
    agen_tahap_2 = ["sinergi", "rapih"] if is_team_mode else ["sigap", "rapih"]
    with animasi_slot.container():
        render_virtual_office(agen_tahap_2, "Tahap 2/2: TELITI istirahat di sofa, RAPIH menyusun rekapitulasi & format akhir...", compact=True)

    instruksi_rapih = (
        "Anda adalah Agent RAPIH (Rekapitulasi Administrasi, Penulisan & Intisari Hasil) di PLN Icon Plus SBU Sumbagsel.\n"
        "Tugas Anda menyusun hasil kerja teknis dari Agent TELITI menjadi sajian akhir yang sangat rapi dan siap pakai:\n"
        "- Jika hasil berupa laporan/rekap Excel: gunakan tabel Markdown yang bersih, soroti poin eskalasi untuk Koordinator PTL, dan sesuaikan gaya bahasa dengan profil user:\n"
        f"{profil_user or 'Gunakan bahasa operasional PLN Icon Plus yang ringkas, tegas, dan terstruktur.'}\n"
        "- Jika hasil berupa SCRIPT PRECONFIG JARINGAN: tampilkan blok kode script bersih dalam ```text ... ``` yang siap langsung di-copy-paste ke terminal/console perangkat, diikuti ringkasan perubahan parameter dan catatan verifikasi (jika ada)."
    )
    prompt_rapih = (
        f"PERMINTAAN AWAL USER:\n{perintah}\n\n"
        f"HASIL KERJA TEKNIS DARI AGENT TELITI:\n{hasil_mentah_teliti}\n\n"
        "Susun hasil akhir yang siap disajikan:"
    )
    hasil_akhir_rapih = panggil_agent_aman(
        client,
        ["gemini-3.5-flash-lite", "gemini-3.5-flash"],
        prompt_rapih,
        instruksi_rapih,
        temperature=0.2
    )

    # TAHAP 3: SELESAI -> SEMUA AGEN KEMBALI KE SOFA ISTIRAHAT
    with animasi_slot.container():
        render_virtual_office([], "Tugas selesai! SIGAP, TELITI, RAPIH & SINERGI kembali istirahat di sofa 3D.", compact=True)

    return hasil_akhir_rapih

# --- DAFTAR 10 PERTANYAAN ONBOARDING ---
DAFTAR_PERTANYAAN = [
    "1️⃣ Pertama, siapa **nama lengkap / panggilan** Anda dan peran Anda di tim (misalnya **Koordinator PTL** atau **PTL Korporat/Publik**) di **PLN Icon Plus SBU Sumbagsel**?",
    "2️⃣ **Area wilayah kerja Sumbagsel** mana saja (Sumsel, Lampung, Jambi, Bengkulu, atau Babel) dan segmen pelanggan (Korporat/Publik) yang paling sering Anda tangani?",
    "3️⃣ Apa **3 pekerjaan atau laporan rutin** (harian/mingguan) yang paling sering Anda kerjakan saat ini?",
    "4️⃣ Apa **target atau KPI aktivasi** (misalnya SLA aktivasi, penyelesaian *aging* WO, atau target *testcom*) yang sedang paling krusial Anda kejar?",
    "5️⃣ **Format file Excel *tracking* atau laporan** apa yang paling sering Anda olah (kolom-kolom kunci apa saja yang wajib diperhatikan)?",
    "6️⃣ **Perangkat jaringan apa saja** (misalnya switch **BDCOM S2510**, **Huawei**, **MikroTik**, **ZTE**, atau router lainnya) yang sering Anda buatkan *preconfig*-nya?",
    "7️⃣ Apa **kendala lapangan atau teknis** (seperti material, perizinan gedung korporat/pemda, atau revisi *VLAN/IP*) yang paling menyita waktu Anda?",
    "8️⃣ Bagaimana **gaya bahasa & format rekapitulasi** yang paling Anda sukai saat **RAPIH** menyajikan laporan (tabel ringkas, poin eksekutif, atau format siap *forward* ke grup koordinasi)?",
    "9️⃣ Bagaimana pola **koordinasi antara Koordinator PTL dan PTL** yang Anda inginkan di ruang diskusi bersama?",
    "🔟 Terakhir, **tugas spesifik atau template preconfig pertama apa** yang ingin Anda uji coba hari ini bersama tim agent?"
]

if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# ==========================================
# HALAMAN 1: LOGIN / DAFTAR USER BARU
# ==========================================
if not st.session_state.logged_in_user:
    st.title("🔐 Login Kantor Aktivasi 3D — PLN Icon Plus")
    st.caption("SBU Sumbagsel • Koordinator PTL (Farhan) & Tim PTL Korporat/Publik (Nana, Dini)")

    col1, col2 = st.columns([1, 1.2])
    with col1:
        with st.form("form_login"):
            st.subheader("Masuk ke Ruang Kerja PTL")
            input_user = st.text_input("Username (misal: farhan, nana, dini):", placeholder="contoh: farhan")
            input_pin = st.text_input("PIN Keamanan (4-6 angka):", type="password", placeholder="contoh: 1234")
            submit_login = st.form_submit_button("Masuk / Buat Akun Baru", type="primary", use_container_width=True)

            if submit_login:
                uname = get_safe_username(input_user)
                if not uname or not input_pin:
                    st.error("Username dan PIN wajib diisi.")
                else:
                    with st.spinner("Menghubungkan ke Kantor Aktivasi 3D..."):
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
                        st.error("PIN salah untuk username tersebut!")
    st.stop()

# ==========================================
# HALAMAN 2: WORKSPACE UTAMA PTL (STICKY CHAT INPUT DI BAWAH)
# ==========================================
current_user = st.session_state.logged_in_user
if "cached_user_data" not in st.session_state or st.session_state.get("cached_username") != current_user:
    st.session_state.cached_user_data = load_user_data(current_user)
    st.session_state.cached_username = current_user

user_data = st.session_state.cached_user_data

with st.sidebar:
    st.header(f"👤 {current_user.capitalize()}")
    role_badge = "Koordinator PTL" if current_user == "farhan" else "PTL Korporat / Publik"
    st.caption(f"Jabatan: **{role_badge}**")
    if GITHUB_TOKEN:
        st.caption("☁️ Cloud Sync Tim: **Aktif**")
    else:
        st.caption("⚠️ Cloud Sync Tim: **Nonaktif**")

    if st.button("🚪 Logout / Ganti Akun", use_container_width=True):
        st.session_state.logged_in_user = None
        st.session_state.pop("cached_user_data", None)
        st.rerun()

    st.markdown("---")
    default_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
    api_key = st.text_input("Gemini API Key", value=default_key, type="password").strip()

    st.markdown("---")
    st.markdown("**Status Profil Kerja:**")
    if user_data["profil_selesai"]:
        st.success("✅ Profil Terhubung ke Tim")
        with st.expander("📄 Lihat Resume Profil"):
            st.markdown(user_data["ringkasan_profil"])
    else:
        progres = user_data["index_pertanyaan"]
        st.info(f"💬 Kenalan ({progres}/10)")
        st.progress(progres / 10)

    st.download_button(
        label="💾 Unduh Backup Pribadi (.json)",
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

if not api_key:
    st.warning("Masukkan **Gemini API Key** di sidebar kiri terlebih dahulu.")
    st.stop()

@st.cache_resource
def get_client(key: str):
    return genai.Client(api_key=key)

client = get_client(api_key)
MODEL_CEPAT = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]

# --- NAVIGASI MODE UTAMA (AGAR CHAT INPUT SELALU STICKY DI BAWAH LAYAR) ---
mode_aktif = st.radio(
    "Pilih Ruang Kerja:",
    [
        f"👩‍💼 Ruang Kerja {current_user.capitalize()} (SIGAP)",
        "🤝 Ruang Diskusi Tim PTL (SINERGI)",
        "⚙️ Pustaka Template Preconfig (.txt)",
        "🏢 Kantor Aktivasi 3D (Live)"
    ],
    horizontal=True,
    label_visibility="collapsed"
)
st.markdown("---")

# ==========================================================
# MODE 1: RUANG KERJA PRIBADI (SIGAP -> TELITI -> RAPIH)
# ==========================================================
if mode_aktif.startswith("👩‍💼"):
    st.subheader(f"Ruang Kerja Operasional — {current_user.capitalize()}")
    st.caption("Upload Excel (.xlsx/.csv), PDF, atau file Notepad Preconfig (.txt) untuk langsung diolah oleh TELITI & RAPIH.")

    if not user_data["messages"]:
        salam_awal = (
            f"Selamat datang, **{current_user.capitalize()}**! Saya **SIGAP** (*Sistem Intelijen Gerak Aktif PTL*), "
            f"Lead Sekretaris Anda bersama tim **TELITI**, **RAPIH**, dan **SINERGI** di **PLN Icon Plus SBU Sumbagsel**.\n\n"
            f"Agar saya memahami kebutuhan kerja Anda, mari kita kenalan singkat **satu per satu**:\n\n"
            f"{DAFTAR_PERTANYAAN[0]}"
        )
        user_data["messages"].append({"role": "assistant", "content": salam_awal})
        save_user_data(current_user, user_data)

    for msg in user_data["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if "uploader_pribadi_key" not in st.session_state:
        st.session_state.uploader_pribadi_key = 0

    with st.expander("📎 Lampirkan Excel (.xlsx/.csv), PDF, atau Notepad Preconfig (.txt)", expanded=False):
        files_pribadi = st.file_uploader(
            "Pilih file untuk diproses TELITI & RAPIH:",
            type=["xlsx", "xls", "csv", "pdf", "txt"],
            accept_multiple_files=True,
            key=f"file_pribadi_{st.session_state.uploader_pribadi_key}"
        )

    if files_pribadi:
        st.info(f"📎 **{len(files_pribadi)} file siap diproses:** {', '.join([f.name for f in files_pribadi])}")

    # CHAT INPUT DI LEVEL ROOT -> SELALU MENEMPEL DI BAWAH LAYAR!
    prompt_pribadi = st.chat_input(f"Ketik perintah analisis Excel, racik preconfig, atau laporan ({current_user})...")

    if prompt_pribadi:
        label_file = ""
        konteks_dok = ""
        if files_pribadi:
            label_file = f"\n\n*(📎 Lampiran: {', '.join([f.name for f in files_pribadi])})*"
            konteks_dok = "\n\n".join([ekstrak_isi_file(f) for f in files_pribadi])
            st.session_state.uploader_pribadi_key += 1

        user_data["messages"].append({"role": "user", "content": prompt_pribadi + label_file})
        with st.chat_message("user"):
            st.markdown(prompt_pribadi + label_file)

        with st.chat_message("assistant"):
            animasi_slot = st.empty()
            try:
                if not user_data["profil_selesai"] and not files_pribadi:
                    with animasi_slot.container():
                        render_virtual_office(["sigap"], f"SIGAP sedang mewawancarai {current_user} di Kantor Aktivasi 3D...", compact=True)

                    idx_next = user_data["index_pertanyaan"] + 1
                    if idx_next < len(DAFTAR_PERTANYAAN):
                        pertanyaan_berikutnya = DAFTAR_PERTANYAAN[idx_next]
                        instruksi = (
                            f"Anda adalah SIGAP (Lead Sekretaris AI) untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel. "
                            "Tanggapi jawaban user sebelumnya dalam 1 kalimat singkat, lalu tanyakan PERSIS pertanyaan berikut ini:\n\n"
                            f"{pertanyaan_berikutnya}"
                        )
                        konten = [
                            types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                            for m in user_data["messages"][-4:]
                        ]
                        hasil = st.write_stream(stream_dengan_cadangan(client, MODEL_CEPAT, konten, instruksi, 0.3))
                        catat_aktivitas_agent(["sigap"], f"Wawancara profil ({current_user}) ke-{idx_next + 1}")
                        user_data["index_pertanyaan"] = idx_next
                        user_data["messages"].append({"role": "assistant", "content": hasil})
                        save_user_data(current_user, user_data)
                        st.rerun()
                    else:
                        instruksi_resume = (
                            f"Susun **Resume Profil Kerja** yang rapi untuk '{current_user}' (Koordinator PTL / PTL Korporat-Publik) "
                            "di PLN Icon Plus SBU Sumbagsel berdasarkan jawaban pengenalan dalam percakapan ini."
                        )
                        konten_semua = [
                            types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                            for m in user_data["messages"]
                        ]
                        resume = st.write_stream(stream_dengan_cadangan(client, MODEL_CEPAT, konten_semua, instruksi_resume, 0.2))
                        catat_aktivitas_agent(["sigap"], f"Menyusun Resume Profil ({current_user})")
                        user_data["index_pertanyaan"] = 10
                        user_data["profil_selesai"] = True
                        user_data["ringkasan_profil"] = resume
                        user_data["messages"].append({"role": "assistant", "content": resume})
                        save_user_data(current_user, user_data)
                        st.rerun()

                else:
                    kata_kunci_berat = [
                        "analisis", "analisa", "laporan", "rekap", "evaluasi", "hitung", "rasio",
                        "tabel", "bandingkan", "surat", "memo", "config", "preconfig", "bdcom",
                        "huawei", "mikrotik", "vlan", "hostname", "ip", "script", "template"
                    ]
                    butuh_tim_agent = bool(files_pribadi) or (any(k in prompt_pribadi.lower() for k in kata_kunci_berat) and len(prompt_pribadi.split()) > 3)

                    if butuh_tim_agent:
                        profil_tim = get_all_team_profiles()
                        balasan = jalankan_tim_multi_agent(
                            client=client,
                            perintah=prompt_pribadi,
                            konteks_dokumen=konteks_dok,
                            profil_user=user_data["ringkasan_profil"],
                            profil_tim=profil_tim,
                            animasi_slot=animasi_slot,
                            is_team_mode=False
                        )
                        catat_aktivitas_agent(["sigap", "teliti", "rapih"], f"Eksekusi teknis/laporan oleh {current_user}")
                        st.markdown(balasan)
                    else:
                        with animasi_slot.container():
                            render_virtual_office(["sigap"], f"SIGAP merespons cepat {current_user}...", compact=True)

                        profil_rekan_tim = get_all_team_profiles()
                        instruksi_cepat = (
                            f"Anda adalah SIGAP (Lead Sekretaris AI) untuk '{current_user}' di PLN Icon Plus SBU Sumbagsel.\n"
                            f"PROFIL USER:\n{user_data['ringkasan_profil']}\n\n"
                            f"PROFIL TIM PTL:\n{profil_rekan_tim}\n\n"
                            "Jawab obrolan atau pertanyaan singkat user secara cepat, ramah, dan tepat sasaran."
                        )
                        konten_aktif = [
                            types.Content(role=("user" if m["role"] == "user" else "model"), parts=[types.Part.from_text(text=m["content"])])
                            for m in user_data["messages"][-10:]
                        ]
                        balasan = st.write_stream(stream_dengan_cadangan(client, MODEL_CEPAT, konten_aktif, instruksi_cepat, 0.3))
                        with animasi_slot.container():
                            render_virtual_office([], "Selesai! SIGAP kembali istirahat di sofa 3D.", compact=True)
                        catat_aktivitas_agent(["sigap"], f"Chat cepat dengan {current_user}")

                    user_data["messages"].append({"role": "assistant", "content": balasan})
                    save_user_data(current_user, user_data)
                    if files_pribadi:
                        st.rerun()

            except Exception as e:
                st.error(f"Detail Error: {e}")

# ==========================================================
# MODE 2: RUANG DISKUSI TIM PTL (SINERGI)
# ==========================================================
elif mode_aktif.startswith("🤝"):
    col_head1, col_head2 = st.columns([3, 1])
    with col_head1:
        st.subheader("🤝 Ruang Koordinasi Koordinator PTL & PTL Korporat/Publik")
        st.caption("Chat langsung antar Farhan, Nana, & Dini. Ketik **@ai** untuk memanggil SINERGI + TELITI + RAPIH membedah file bersama.")
    with col_head2:
        if st.button("🔄 Refresh Diskusi Tim", use_container_width=True):
            st.rerun()

    team_data = load_team_workspace()

    if team_data["shared_docs"]:
        with st.expander(f"📂 Dokumen & File Bersama di Meja Tim ({len(team_data['shared_docs'])} file)", expanded=True):
            for idx, doc in enumerate(team_data["shared_docs"]):
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"- **{doc['filename']}** *(diunggah oleh {doc['uploaded_by'].capitalize()} pada {doc['time']})*")
                if c2.button("Hapus", key=f"del_doc_{idx}"):
                    team_data["shared_docs"].pop(idx)
                    save_team_workspace(team_data)
                    st.rerun()

    if not team_data["team_messages"]:
        st.info("Ruang diskusi tim masih kosong. Silakan sapa rekan PTL atau unggah Excel tracking / file preconfig .txt untuk dibahas bareng!")

    for tmsg in team_data["team_messages"]:
        sender = tmsg["sender"]
        is_ai = (sender == "Tim Agent PTL")
        avatar_icon = "🤖" if is_ai else "👤"
        with st.chat_message("assistant" if is_ai else "user", avatar=avatar_icon):
            st.markdown(f"**{sender.capitalize()}** `({tmsg['time']})`:\n\n{tmsg['content']}")

    if "uploader_tim_key" not in st.session_state:
        st.session_state.uploader_tim_key = 0

    with st.expander("📎 Unggah Excel / PDF / Preconfig (.txt) ke Meja Diskusi Tim", expanded=False):
        files_tim = st.file_uploader(
            "File yang diunggah di sini dapat didiskusikan oleh Farhan, Nana, Dini & Tim Agent:",
            type=["xlsx", "xls", "csv", "pdf", "txt"],
            accept_multiple_files=True,
            key=f"file_tim_{st.session_state.uploader_tim_key}"
        )

    if files_tim:
        st.info(f"📎 **{len(files_tim)} file akan dibagikan ke tim:** {', '.join([f.name for f in files_tim])}")

    # CHAT INPUT DI LEVEL ROOT -> SELALU MENEMPEL DI BAWAH LAYAR!
    prompt_tim = st.chat_input("Kirim pesan ke tim PTL (awali dengan @ai jika ingin Tim Agent merespons)...")

    if prompt_tim:
        waktu_sekarang = datetime.datetime.now().strftime("%d/%m %H:%M")
        label_lampiran = ""

        if files_tim:
            nama_list = []
            for f in files_tim:
                isi_ekstrak = ekstrak_isi_file(f)
                team_data["shared_docs"] = [d for d in team_data["shared_docs"] if d["filename"] != f.name]
                team_data["shared_docs"].append({
                    "filename": f.name,
                    "uploaded_by": current_user,
                    "time": waktu_sekarang,
                    "content": isi_ekstrak
                })
                nama_list.append(f.name)
            label_lampiran = f"\n\n*(📂 Membagikan file ke tim: {', '.join(nama_list)})*"
            st.session_state.uploader_tim_key += 1

        team_data["team_messages"].append({
            "sender": current_user,
            "time": waktu_sekarang,
            "content": prompt_tim + label_lampiran
        })
        save_team_workspace(team_data)

        with st.chat_message("user", avatar="👤"):
            st.markdown(f"**{current_user.capitalize()}** `({waktu_sekarang})`:\n\n{prompt_tim + label_lampiran}")

        panggil_ai = ("@ai" in prompt_tim.lower()) or bool(files_tim)

        if panggil_ai:
            with st.chat_message("assistant", avatar="🤖"):
                animasi_tim_slot =
