import glob
import os
import time
import random
import subprocess
import requests
from collections import defaultdict
from PIL import Image, ImageEnhance
import pytesseract
import base64
import io
import threading
import unicodedata
import re
import hashlib
from io import BytesIO
import gc
SCREENSHOT_PATH = "/data/data/com.termux/files/home/screen.png"
SCAN_INTERVAL = 1
DATABASE_URL = "https://atamos2-767d9-default-rtdb.firebaseio.com"

# Global kalıcı su süreci yöneticisi
_su_process = None
_cached_ip = ""
__QUATRA__ = defaultdict(int)
__SIGNALS__ = defaultdict(bool)
BOT_LOG = False
STATE_ROBOT_CONTROL = False
STATE_MACHINE_TEST = False
STATE_MACHINE = "APP_INIT"
STATE_MACHINE_COUNT = 0
STATE_MACHINE_MAX_COUNT = 5
STATE_MACHINE_SYNC_COUNT = 0
STATE_MACHINE_STUCK = False
previous_state = STATE_MACHINE
freeze_variant = ["Buz gibiyim 🧊", "🧊", "🥶", "Dışar da kar mı yağıyor ❄️", "❄️", "Dondummm 🥶", "🐧", "Kardan adam yapsak senlee ☃️", "Battaniye lazım 🧣"]
# Önbellek için global değişkenler
_last_screen_hash = None
_last_ocr_result = ""

def get_su_process():
    global _su_process
    if _su_process is None or _su_process.poll() is not None:
        # Düz 'su' yerine, izolasyon sorununu aşmak için -mm (veya cihazına göre -M) ekliyoruz
        _su_process = subprocess.Popen(['su', '-mm'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return _su_process

def root_code(command):
    try:
        proc = get_su_process()
        marker = "---END_OF_COMMAND---"
        proc.stdin.write(f"{command} 2>/dev/null && echo {marker} || echo {marker}\n")
        proc.stdin.flush()
        output = []
        while True:
            line = proc.stdout.readline()
            if not line or marker in line: break
            output.append(line.strip())
        return "\n".join(output)
    except Exception as e:
        print(f"[!] Root code error: {e}")
        bot_action("code")
        bot_popup('Teknik sorun 0')
        bot_log('Teknik sorun 0')

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[\u200b\u200c\u200d\ufeff\u00a0\u00ad]', ' ', text)
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()

def capture_screen():
    global _last_screen_hash, _last_ocr_result
    try:
        process = subprocess.run(
            ["su", "-c", "/system/bin/screencap", "-p"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        if process.returncode != 0 or not process.stdout:
            return ""
        img_bytes = process.stdout
        current_hash = hashlib.md5(img_bytes).hexdigest()
        if current_hash == _last_screen_hash:
            return _last_ocr_result
        _last_screen_hash = current_hash
        img = Image.open(BytesIO(img_bytes)).convert('L') # Gri tonlama
        enhancer = ImageEnhance.Contrast(img)
        img_enhanced = enhancer.enhance(1.4)
        raw_text = pytesseract.image_to_string(
            img_enhanced,
            lang='tur+eng',
            config='--oem 1 --psm 11'
        )
        _last_ocr_result = clean_text(raw_text)
        return _last_ocr_result

    except Exception as e:
        bot_action("code")
        bot_popup('Teknik sorun 1')
        bot_log(f'Teknik sorun 1: {e}')
    return ""

def time_sleep(s, f):
    try:
        time.sleep(random.uniform(s, f))
    except Exception as e:
        print(f"[!] Sleep: {e}")
        bot_action("code")
        bot_popup('Teknik sorun 2')
        bot_log('Teknik sorun 2')

def tap_at(x, y):
    try:
        root_code(f"input tap {x} {y}")
    except Exception as e:
        print(f"[!] Click error: {e}")
        bot_action("code")
        bot_popup('Teknik sorun 3')
        bot_log('Teknik sorun 3')

import unicodedata


def type_text(text):
    try:
        tr_map = {'ı': 'i', 'İ': 'I', 'ş': 's', 'Ş': 'S', 'ğ': 'g', 'Ğ': 'G',
                  'ç': 'c', 'Ç': 'C', 'ö': 'o', 'Ö': 'O', 'ü': 'u', 'Ü': 'U'}
        cleaned_text = "".join(tr_map.get(c, c) for c in text)

        words = cleaned_text.split(" ")
        for i, word in enumerate(words):
            if word:
                root_code(f"input text '{word}'")
            if i < len(words) - 1:
                root_code("input keyevent 62")  # Boşluk tuşu (Space)

        time_sleep(0.01, 0.05)
    except Exception as e:
        bot_action("code")
        bot_popup('Teknik sorun 4')
        bot_log('Teknik sorun 4')

def get_screenshot_base64():
    if os.path.exists(SCREENSHOT_PATH):
        os.remove(SCREENSHOT_PATH)
    os.system(f"su -c '/system/bin/screencap -p {SCREENSHOT_PATH}'")
    for _ in range(5):
        if os.path.exists(SCREENSHOT_PATH) and os.path.getsize(SCREENSHOT_PATH) > 100:
            break
        time.sleep(0.02)

    try:
        with open(SCREENSHOT_PATH, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except:
        return ""

def send_payload_async(payload):
    # Firebase isteğini arka planda yap, döngü beklemesin
    def _send():
        try:
            requests.patch(f"{DATABASE_URL}/tabletActions.json", json=payload, timeout=2)
        except:
            pass
    threading.Thread(target=_send, daemon=True).start()

def send_static_data():
    static_data = {
        "cpuModel": root_code('getprop ro.board.platform'),
        "fw": root_code('getprop ro.build.version.incremental'),
        "gpuModel": root_code('cat /sys/class/kgsl/$(ls /sys/class/kgsl/ | head -n 1)/devicename 2>/dev/null').strip() or 'Unknown',
        "hwRev": root_code('getprop ro.revision'),
        "mac": root_code('cat /sys/class/net/$(ip route | grep default | awk \'{print $5}\' | head -n 1)/address 2>/dev/null').strip() or 'Unknown',
        "manufacturer": root_code('getprop ro.product.manufacturer'),
        "model": root_code('getprop ro.product.model'),
        "os": root_code('getprop ro.build.version.release'),
        "serial": root_code('getprop ro.serialno')
    }
#     requests.patch(f"{DATABASE_URL}/tabletInfo.json", json=static_data, timeout=5)
    send_payload_async(static_data)


def start_live_loop():
    global _cached_ip
    try:
        # 11 adımlı toplu komut (Sinyal için /proc/net/wireless yerine dumpsys wifi kullanıldı)
        batch_command = """
        cat /sys/class/power_supply/battery/health 2>/dev/null
        echo "___SPLIT___"
        cat /sys/class/power_supply/battery/capacity 2>/dev/null
        echo "___SPLIT___"
        cat /sys/class/power_supply/battery/status 2>/dev/null
        echo "___SPLIT___"
        top -n 1 | grep -i "cpu" | head -n 1
        echo "___SPLIT___"
        cat /sys/class/kgsl/$(ls /sys/class/kgsl/ | head -n 1)/gpu_busy 2>/dev/null || echo "0 0"
        echo "___SPLIT___"
        ping -c 1 8.8.8.8 | grep "time="
        echo "___SPLIT___"
        cat /proc/meminfo
        echo "___SPLIT___"
        dumpsys wifi 2>/dev/null | grep -i "RSSI" | head -n 1 || echo ""
        echo "___SPLIT___"
        df /data | tail -1
        echo "___SPLIT___"
        cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0
        echo "___SPLIT___"
        awk '{print $1}' /proc/uptime
        """

        raw_output = root_code(batch_command)
        parts = raw_output.split("___SPLIT___") if raw_output else [""] * 11

        # Değerleri güvenli bir şekilde ayırıyoruz
        batt_health = parts[0].strip() if len(parts) > 0 else "Unknown"
        battery_cap = parts[1].strip() if len(parts) > 1 else "0"
        charging_stat = parts[2].strip().lower() == 'charging' if len(parts) > 2 else False

        # CPU
        cpu_raw = parts[3].strip() if len(parts) > 3 else ""
        cpu_val = '0'
        try:
            cols = cpu_raw.replace('%', '').split()
            if len(cols) > 1: cpu_val = cols[1]
        except:
            cpu_val = '0'

        # GPU
        gpu_raw = parts[4].strip() if len(parts) > 4 else "0 0"
        gpu_val = 0
        try:
            g_parts = gpu_raw.split()
            if len(g_parts) >= 2:
                t_gpu = int(g_parts[0]) + int(g_parts[1])
                if t_gpu > 0: gpu_val = int((int(g_parts[0]) / t_gpu) * 100)
        except:
            gpu_val = 0

        # Ping
        ping_raw = parts[5].strip() if len(parts) > 5 else ""
        ping_val = '0'
        try:
            if "time=" in ping_raw:
                ping_val = ping_raw.split("time=")[1].split()[0]
        except:
            ping_val = '0'

        # RAM
        mem_raw = parts[6] if len(parts) > 6 else ""
        ram_val = '0'
        try:
            t, a = 0, 0
            for line in mem_raw.split('\n'):
                if "MemTotal:" in line: t = int(line.split()[1])
                elif "MemAvailable:" in line: a = int(line.split()[1])
            if t > 0: ram_val = str(int((t - a) * 100 / t))
        except:
            ram_val = '0'

        # Signal (RSSI - Örn: -65 dBm değerini doğrudan yakalar)
        signal_raw = parts[7].strip() if len(parts) > 7 else ""
        signal_val = '0'
        try:
            if "RSSI" in signal_raw:
                parts_rssi = signal_raw.split("RSSI:")
                if len(parts_rssi) > 1:
                    signal_val = parts_rssi[1].strip().split(',')[0].strip()
            else:
                signal_val = signal_raw if signal_raw else '0'
        except:
            signal_val = '0'

        # Storage
        storage_raw = parts[8].strip() if len(parts) > 8 else ""
        storage_val = "Unknown"
        try:
            s_cols = storage_raw.split()
            if len(s_cols) >= 4:
                free_gb = int(s_cols[3]) / 1024 / 1024
                total_gb = int(s_cols[1]) / 1024 / 1024
                storage_val = f"{free_gb:.1f} GB free / {total_gb:.1f} GB total"
        except:
            pass

        # Temp
        temp_val = 0
        try:
            t_raw = parts[9].strip()
            if t_raw.isdigit(): temp_val = int(t_raw) / 1000
        except:
            temp_val = 0

        # Uptime
        uptime_raw = parts[10].strip() if len(parts) > 10 else "0"
        uptime_val = "0g 0s 0d"
        try:
            seconds = float(uptime_raw)
            days = int(seconds / 86400)
            hours = int((seconds % 86400) / 3600)
            minutes = int((seconds % 3600) / 60)
            uptime_val = f"{days}g {hours}s {minutes}d"
        except:
            pass

        # IP Adresi (Cache mekanizması)
        if not _cached_ip:
            try:
                _cached_ip = requests.get("https://api.ipify.org", timeout=2).text
            except:
                _cached_ip = "Bilinmiyor"

        # Dinamik Payload
        dynamic_payload = {
            "battHealth": batt_health,
            "battery": battery_cap,
            "charging": charging_stat,
            "cpu": cpu_val,
            "gpu": gpu_val,
            "ip": _cached_ip,
            "ping": ping_val,
            "screen": {
                "image": get_screenshot_base64(),
                "updatedAt": int(time.time() * 1000)
            },
            "ram": ram_val,
            "signal": signal_val,  # Artık -65 gibi dBm değerini gönderecek
            "storage": storage_val,
            "temp": temp_val,
            "updatedAt": int(time.time() * 1000),
            "uptime": uptime_val
        }

        # Asenkron gönderim
        send_payload_async(dynamic_payload)

    except Exception as e:
        time.sleep(5)


def reset_chorome():
    root_code('am force-stop com.android.chrome')
    root_code('rm -rf /data/data/com.android.chrome/app_chrome/Default/')
    root_code('rm -rf /data/data/com.android.chrome/app_tabs/')
    root_code('setprop debug.chrome.command-line 1')
    chrome_flags = (
        "chrome "
        "--lang=tr-TR "
        "--accept-lang=tr-TR,tr "
        "--disable-notifications "
        "--disable-translate "
        "--disable-features=Translate,TranslateUI,TranslateBubble,FeatureEngagementTracker,IPH_KeyboardAccessoryAddressFilling,BrowserSignin,LanguageDetection "
        "--disable-sync"
    )
    root_code(f'echo "{chrome_flags}" > /data/local/tmp/chrome-command-line')
    root_code('chmod 777 /data/local/tmp/chrome-command-line')
    root_code("am start -S -n com.android.chrome/com.google.android.apps.chrome.Main -d 'https://www.facebook.com/?locale=tr_TR'\nexit\n")

def bot_msg(text):
    try:
        url = f"{DATABASE_URL}/mesajlar.json"
        payload = {
            "text": f"{text}",
            "isBot": True,
            "time": time.strftime("%H:%M:%S")
        }
        requests.post(url, json=payload)
    except Exception as e:
#         print('Teknik sorun 5')
        time.sleep(5)

def bot_action(action):
    while True:
        try:
            url = f"{DATABASE_URL}/suarez.json"
            payload = {"action": action}
            requests.put(url, json=payload, timeout=5)
            break
        except Exception as e:
#             print('Teknik sorun 6')
            time.sleep(5)

def bot_popup(message):
    try:
        url = f"{DATABASE_URL}/suarezPop.json"
        payload = {
            "text": message,
        }
        requests.post(url, json=payload)
    except Exception as e:
#         print('Teknik sorun 7')
        time.sleep(5)

def bot_error():
    try:
        url = f"{DATABASE_URL}/ayarlar/genel/errorScreen.json"
        payload = {
            "image": get_screenshot_base64(),
            "state": STATE_MACHINE,
            "timestamp": time.strftime("%H:%M:%S")
        }
        requests.post(url, json=payload)
    except Exception as e:
#         print('Teknik sorun 5')
        time.sleep(5)


def reset_state(reason):
    global STATE_MACHINE, STATE_MACHINE_COUNT
    bot_log('RESET_STATE')
    err = f"{reason}"
    bot_msg(err)
    bot_log(err)
    STATE_MACHINE = "APP_INIT"
    freeze_reset()
    root_code("input keyevent 187")
    time_sleep(2,2)
    tap_at(400, 1103)
    time_sleep(2,2)
    raise Exception(err)

def get_active_platforms():
    try:
        res = requests.get(f"{DATABASE_URL}/ayarlar/platformlar.json")
        if res.status_code == 200 and res.json():
            d = res.json()
            return [k for k, v in d.items() if v is True]
    except Exception as e:
#         print('Teknik sorun 9')
        time.sleep(5)
    return []

def open_platform_url(platform):
    p_lower = platform.lower()
    try:
        if "facebook" in p_lower:
           reset_chorome()
        elif "google" in p_lower:
            root_code("am start -n com.litatom.app/com.lit.app.ui.login.GoogleLoginActivity")
        else:
            print(f"[!] Bilinmeyen platform: {platform}")

    except Exception as e:
        bot_action("code")
        bot_popup('Teknik sorun 10')
        bot_log('Teknik sorun 10')

def fetch_account():
    url = f"{DATABASE_URL}/hesaplar.json"
    try:
        response = requests.get(url)
        if response.status_code == 200 and response.json():
            data = response.json()
            if isinstance(data, dict) and len(data) > 0:
                key = list(data.keys())[0]
                hesap_verisi = data[key]
                hesap_verisi['active_list'] = get_active_platforms()
                requests.delete(f"{DATABASE_URL}/hesaplar/{key}.json")
                bot_action('çalışıyor')
                return hesap_verisi
    except Exception as e:
#         print('Teknik sorun 11')
        time.sleep(5)
    return None


def get_general_settings():
    url = f"{DATABASE_URL}/ayarlar/genel.json"
    try:
        response = requests.get(url)
        if response.status_code == 200 and response.json():
            data = response.json()
            if isinstance(data, dict):
                return {
                    "name": data.get("name", ""),
                    "text": data.get("text", ""),
                    "vpn": data.get("vpn", False),
                    "posts": data.get("posts", [])
                }
    except Exception as e:
#         print('Teknik sorun 12')
        time.sleep(5)
    return {"name": "", "text": "", "vpn": False}


def phantom_detect_fucker():
    try:
        subprocess.run(["termux-wake-lock"], check=True)
        root_code('settings put global max_phantom_processes 2147483647')
        root_code('dumpsys deviceidle whitelist +com.termux')
        root_code('dumpsys deviceidle disable all')
    except Exception as e:
        bot_action("code")
        bot_popup('Teknik sorun 13')
        bot_log('Teknik sorun 13')

phantom_detect_fucker()

def bot_log(text):
    if BOT_LOG:
        while True:
            try:
                url = f"{DATABASE_URL}/logs.json"
                payload = {
                    "message": f"{text}",
                    "timestamp": time.strftime("%H:%M:%S")
                }
                requests.post(url, json=payload, timeout=3)
                break

            except Exception as e:
                time.sleep(5)

def screen_controller():
    power_check = root_code('dumpsys power | grep mWakefulness')
    if 'Awake' not in power_check:
        bot_log("SCREEN_NOT_AWAKE")
        root_code('input keyevent 26')
        time_sleep(1.0, 1.0)
        root_code('input swipe 413 1187 499 287 250')
        time_sleep(1.0, 1.0)

    focus_check = root_code('dumpsys window | grep mCurrentFocus')
    if 'NotificationShade' in focus_check:
        root_code('input swipe 413 1187 499 287 250')
        time_sleep(1.0, 1.0)



def freeze_reset():
    global STATE_MACHINE_COUNT, previous_state, STATE_MACHINE_STUCK
    STATE_MACHINE_COUNT = 0
    previous_state = STATE_MACHINE
    STATE_MACHINE_STUCK = False
    bot_log('FREEZE_RESET')

def freeze_detect(email_text,platform,password_text):

    global STATE_MACHINE,STATE_MACHINE_COUNT,STATE_MACHINE_MAX_COUNT,STATE_MACHINE_STUCK,previous_state,freeze_variant
    p_lower = str(platform).lower()
#     bot_log(f'FREEZE_COUNT {STATE_MACHINE_COUNT}')

    def log_to_database(status_message):
        try:
            url = f"{DATABASE_URL}/hesaplar.json"
            payload = {
                "user": email_text,
                "pass": password_text,
                "platform": platform,
                "status": status_message,
                "time": time.strftime("%H:%M:%S")
            }
            specific_url = f"{DATABASE_URL}/hesaplar/{email_text.replace('@', '_at_').replace('.', '_')}.json"
            requests.put(specific_url, json=payload, timeout=5)
        except Exception as e:
            bot_log(f"[-] Veritabanına kayıt atılamadı: {e}")

    def freeze_again():
        log_to_database(f"State aşımı ({STATE_MACHINE})")
        bot_popup(random.choice(freeze_variant))
        bot_log(f"{email_text} - State aşımı ({STATE_MACHINE} aşamasında takıldı)")

    def freeze_limit_count(id):
        __QUATRA__[f"FREEZE_LIMIT_{id}"] += 1
        if __QUATRA__[f"FREEZE_LIMIT_{id}"] >= 3:
            bot_log(f"FREEZE_LIMIT_{id}: Donma limiti aşıldı geçiliyor")
            freeze_again()

    # State değiştiyse state sayacını ve bildirim bayrağını sıfırla
    if STATE_MACHINE != previous_state:
        STATE_MACHINE_COUNT = 0
        previous_state = STATE_MACHINE
        STATE_MACHINE_STUCK = False
        bot_action('çalışıyor')
#         bot_log(STATE_MACHINE)
    else:
        STATE_MACHINE_COUNT += 1

    # 5 defa aynı state'te kalındığı an (henüz max_state_retries'e varmadan) dondu tetikle
    if STATE_MACHINE_COUNT > 3 and not STATE_MACHINE_STUCK:
        bot_action('dondu')
        bot_popup(random.choice(freeze_variant))
        time_sleep(3.0, 5.0)
        bot_popup(random.choice(freeze_variant))
        STATE_MACHINE_STUCK = True

    # State bazlı aşırı döngü (takılma) kontrolü
    if STATE_MACHINE_COUNT > STATE_MACHINE_MAX_COUNT:
        bot_error()
        # Özel durumlar
        if STATE_MACHINE in ["LIT_GOOGLE_SELECT_WAIT","LIT_FACEBOOK_SELECT_WAIT", "LIT_APP_INIT", "LIT_ACCOUNT"]:
            freeze_limit_count(1)
            root_code('pm clear --user 0 com.litatom.app')
            time_sleep(1.0, 1.5)
            root_code('am start -n com.litatom.app/com.lit.app.ui.login.GoogleLoginActivity' if "google" in p_lower else 'am start -n com.litatom.app/com.lit.app.ui.MainActivity')
            STATE_MACHINE = "LIT_GOOGLE_SELECT_WAIT" if "google" in p_lower else "LIT_APP_INIT"
            freeze_reset()
            return
        elif STATE_MACHINE == "LIT_FACEBOOK_SELECT_WAIT":
            freeze_limit_count(2)
            root_code('am start -n com.litatom.app/com.lit.app.ui.MainActivity')
            STATE_MACHINE = "LIT_APP_INIT"
            freeze_reset()
            return
        elif STATE_MACHINE in ["LIT_POST", "LIT_POST_CONTROLLER"]:
            freeze_limit_count(3)
            bot_log('Paylaşım ekranı yenileniyor...')
            root_code('am start -n com.litatom.app/com.lit.app.post.feedpublish.FeedPublishActivity')
            STATE_MACHINE = "LIT_POST"
            freeze_reset()
            return
        elif STATE_MACHINE == "VPN":
            freeze_limit_count(4)
            bot_log('VPN sayfası açılıyor...')
            root_code('am start -n app.ninjavpn.android/.app.Dashboard')
            freeze_reset()
            return
        else:
            freeze_again()

def apps_automation(active_list, platform, setting_name, setting_text, setting_vpn, email_text,password_text,setting_posts):
    global STATE_MACHINE,STATE_MACHINE_TEST,_cached_ip
    screen_controller()
    __QUATRA__.clear()
    __SIGNALS__.clear()
    __SIGNALS__['random_post_active'] = False
    account_again = None

    posts = []
    default_posts = [
        {"image": [170, 516], "image_active": True, "sleep": 0},
        {"image": [765, 532], "image_active": True, "sleep": 0},
        {"image": [173, 727], "image_active": True, "sleep": 0},
        {"image": [370, 718], "image_active": True, "sleep": 0},
        {"image": [0, 0], "image_active": False, "sleep": 300},
        {"image": [168, 319], "image_active": True, "sleep": 0},
        {"image": [779, 113], "image_active": True, "sleep": 0},
        {"image": [375, 125], "image_active": True, "sleep": 0}
    ]

    # Güvenli kontrol yapısı
    if 'setting_posts' in locals() and setting_posts:
        if isinstance(setting_posts, dict):
            posts = list(setting_posts.values())
        elif isinstance(setting_posts, list):
            posts = setting_posts
        else:
            posts = default_posts
    else:
        posts = default_posts

    random_post = [
        [363, 722], [175, 714], [777, 502], [776, 504], [775, 505],
        [572, 529], [367, 527], [768, 326], [569, 322], [358, 328],
        [168, 321], [770, 117], [569, 129], [372, 120], [169, 129]
    ]

    power_check = root_code('dumpsys power | grep mWakefulness')

    def reset_apps():
        tap_at(648, 1326)
        root_code('magisk --denylist disable')
        root_code('pm clear --user 0 com.litatom.app')

    p_lower = platform.lower()
    bot_log(f"[+] Uygulama içi otomasyonlar başlatılıyor. Oturum Türü: {platform.upper()}, Aktif Liste: {active_list}")

    reset_apps()
    root_code('sh /MONO/monoDevice.sh')
    send_static_data()

    for app_name in active_list:
        app_lower = app_name.lower()
        bot_log(f"[->] Çalıştırılan uygulama: {app_name} (Giriş Yöntemi: {p_lower})")

        if setting_vpn and 'Awake' in power_check:
            root_code('am force-stop app.ninjavpn.android')
            time_sleep(0.3, 0.5)
            root_code('am start -n app.ninjavpn.android/.app.Dashboard')
            __QUATRA__['vpn_started_count'] = 0

            STATE_MACHINE = "VPN"
            while STATE_MACHINE != "VPN_DONE":
                screen_text = capture_screen()
                freeze_detect(email_text,platform,password_text)
                start_live_loop()
                text_lower = screen_text.lower()

               # 1. Sözleşme / Kabul ekranı
                if "buy using ninja vpn" in text_lower or "terms of service" in text_lower or "accept" in text_lower or "cantinue" in text_lower:
                    tap_at(397, 1165)
                    STATE_MACHINE = "VPN_APP_ACCEPT"

                # 2. Bildirim izni ekranı
                elif "ninja vpn uygulamasinin size bildirim" in text_lower or "gondermesine izin verilsin mi" in text_lower:
                    tap_at(403, 1127)
                    STATE_MACHINE = "VPN_NOTİFİCATİON_PER"

                # 3. Bağlantı başarılı mi kontrolü (Önce bu kontrol edilmeli)
                elif (STATE_MACHINE == "VPN_CONNECT" or STATE_MACHINE == "VPN_NOTİFİCATİON_PER") and "stealth vpn activated" in text_lower:
                    try:
                        _cached_ip = requests.get("https://api.ipify.org", timeout=2).text
                    except Exception as e:
                        bot_log('IP_FETCH_ERROR')
                    STATE_MACHINE = "VPN_DONE"
                    __QUATRA__['vpn_started_count'] = 0
                    break

                # 4. Bağlan butonuna basma durumu
                elif not "stealth vpn activated" in text_lower and ("connect" in text_lower or "ninjo" in text_lower or "almanya" in text_lower):
                    if STATE_MACHINE != "VPN_CONNECT":  # Sürekli tetiklenmesini önlemek için koruma
                        vpn_variant = ["VPN açıyorum", "IP değiştiriliyor", "internet Almanya'ya bağlanıyor"]
                        bot_popup(random.choice(vpn_variant))
                        tap_at(721, 82)
                        STATE_MACHINE = "VPN_CONNECT"
                        __QUATRA__['vpn_started_count'] += 1
                        bot_log(f"VPN_COUNT: {__QUATRA__['vpn_started_count']}")

                # 5. Hata sınırı kontrolü
                if __QUATRA__['vpn_started_count'] >= 3:
                    bot_log('VPN_APP_ERROR')
                    STATE_MACHINE = "VPN_DONE"
                    __QUATRA__['vpn_started_count'] = 0
                    break

                time_sleep(0.5, 0.5)


        if "litmatch" in app_lower and 'Awake' in power_check:
            bot_popup('Litmatch')
            bot_log('Litmatch')

            if "google" in p_lower:
                root_code('am start -n com.litatom.app/com.lit.app.ui.login.GoogleLoginActivity')
                STATE_MACHINE = "LIT_GOOGLE_SELECT_WAIT"

            elif "facebook" in p_lower:
                root_code('am start -n com.litatom.app/com.lit.app.ui.MainActivity')
                STATE_MACHINE = "LIT_APP_INIT"
                time_sleep(5,5)

            while STATE_MACHINE != "LIT_DONE":

                freeze_detect(email_text,platform,password_text)
                start_live_loop()
                screen_text = capture_screen()
                text_lower = screen_text.lower()

                # Hata Yönetimi (Genel)
                lit_permission_error = "litmatch siirekli olarak duruyor" in text_lower or "uygulamayi kapat" in text_lower
                lit_location_error =  "litmatch uygulamasinin bu cihazin konumuna" in text_lower
                lit_notification_error = "bildirim ayarlarini agin" in text_lower
                lit_webview_error = "webview gincellemeleri kaldirilsin" in text_lower or "litmatch uygulamasini yeniden baslatin" in text_lower

                if "kimliğinizi doğrulayın" in screen_text or "kimliginizi dogrulayin" in screen_text or "hesabini kullanmak igin insan oldugunu onayla" in screen_text or "insan oldugunu onayla" in screen_text:
                    rob_variant = ["Robot", f"{email_text} - Robot", "🤖", "Hesap robot olmuş", "Hızlı girmeliyim robot oluyo"]
                    bot_popup(random.choice(rob_variant))
                    reset_state(f"{email_text} - Robot")
                    break
                elif ("girdigin girig bilgileri yanlis" in screen_text or "hesabini bul ve girig yap" in screen_text) and STATE_MACHINE == "FACEBOOK_LOGİN_APPROVAL":
                    delete_variant = ["Giriş bilgisi yanlış", "Yanlış giriş bilgisi", "Giriş bilgisini düzgün atın", "Giriş bilgisi yanlış sizin saçmalıklarınızla uğraşamam", "Giriş bilgisi yanlış sizin yapacağınız iş"]
                    bot_popup(random.choice(delete_variant))
                    reset_state(f"{email_text} - Giriş bilgisi yanlış")
                    break
                elif "hesabinizi kapattik" in screen_text or "topluluk standartlari" in screen_text:
                    reset_state(f"{email_text} - Hesap facebook tarafından kapatılmış")
                    break
                elif "hatirlatma" in text_lower or "topluluk kuralları" in text_lower or "ihlal" in text_lower:
                    bot_log('LIT_BAN')
                    bot_action("ban")
                    bot_msg('Litmatch Ban attı')
                    break
                elif "sarj cihazinin dogru sekilde bagli" in screen_text or "Bu siirekli olursa sarj kablosunu degistirmeyi" in screen_text:
                    tap_at(401, 1208)
                    time_sleep(1, 1)
                elif "litmatch oturumu agilsin mi" in screen_text or "oturum ag" in screen_text:
                    tap_at(284,1196)
                elif lit_permission_error:
                    tap_at(347,1224)
                elif lit_location_error:
                    tap_at(406,1203)
                elif lit_notification_error:
                    tap_at(551,469)
                elif lit_webview_error:
                    tap_at(291,1201)

                # 0. Başlangıç / Yüklenme Ekranı Kontrolü
                if STATE_MACHINE == "LIT_APP_INIT":
                    if "make new friends" in text_lower or "litmach" in text_lower or "yardim merkezi" in text_lower:
                        if account_again is True:
                            tap_at(409, 875)
                            time_sleep(0.1, 0.3)
                        else:
                            tap_at(401, 951)
                            time_sleep(0.1, 0.3)
                    if "lit sunlara erigim istiyor" in text_lower or "erigim istiyor" in text_lower or "olarak devam et" in text_lower or "lit will receive ongoing" in text_lower or "continue" in text_lower or "ingilizce" in screen_text or "sayfa cevrildi" in screen_text:
                        STATE_MACHINE = "LIT_FACEBOOK_SELECT_WAIT"
                    elif "dogrudan giris yap" in text_lower or "giris yaptiginiz hesabi secin" in text_lower or "hesabi secin" in text_lower:
                        tap_at(401, 440)
                    elif "litmatch siirekli olarak duruyor" in text_lower or "uygulamayi kapat" in text_lower:
                        tap_at(347,1224)
                        time_sleep(1,2)
                        root_code("input keyevent 187")
                        time_sleep(2, 2)
                        tap_at(400, 1103)
                        time_sleep(2, 2)
                        root_code('am start -n com.litatom.app/com.lit.app.ui.MainActivity')
                        freeze_reset()

                # 0.1. Google Hesap Seçim Ekranı Kontrolü
                elif STATE_MACHINE == "LIT_GOOGLE_SELECT_WAIT":
                    if "hesap" in text_lower or "devam etmek" in text_lower or "baska hesap" in text_lower:
                        tap_at(296, 708)
                        bot_popup('Hesap seçildi!')
                        time_sleep(1.0, 1.5)
                        STATE_MACHINE = "LIT_ACCOUNT"
                        time_sleep(10, 10)
                    elif "litmatch siirekli olarak duruyor" in text_lower or "uygulamayi kapat" in text_lower:
                        tap_at(347,1224)
                        time_sleep(1,2)
                        root_code("input keyevent 187")
                        time_sleep(2, 2)
                        tap_at(400, 1103)
                        time_sleep(2, 2)
                        root_code('am start -n com.litatom.app/com.lit.app.ui.login.GoogleLoginActivity')
                        freeze_reset()

                # 0.2. Facebook oturum açma
                elif STATE_MACHINE == "LIT_FACEBOOK_SELECT_WAIT":
                    bot_log(f"FACEBOOK_STATE_COUNT: {__QUATRA__['lit_facebook_state_count']}")
                    tap_at(380,1110)
                    time_sleep(5,5)
                    STATE_MACHINE = "LIT_ACCOUNT"
                    __QUATRA__['lit_facebook_state_count'] = 0
                    if "baglanmak iin facebook hesabina girig yap" in screen_text or "hesap olustur" in screen_text:
                        bot_popup("Oturum açılamamış")
                        reset_state(f"{email_text} - Facebook oturumunu tekrar deneyeceğim")
                        break
                    elif "litmatch siirekli olarak duruyor" in text_lower or "uygulamayi kapat" in text_lower:
                        tap_at(347,1224)
                        time_sleep(1,2)
                        root_code("input keyevent 187")
                        time_sleep(2, 2)
                        tap_at(400, 1103)
                        time_sleep(2, 2)
                        root_code('am start -n com.litatom.app/com.lit.app.ui.MainActivity')
                        freeze_reset()
                        STATE_MACHINE = "LIT_APP_INIT"
                    else:
                        __QUATRA__['lit_facebook_state_count'] += 1

                    if __QUATRA__['lit_facebook_state_count'] >= 4:
                        STATE_MACHINE = "HARD_FACEBOOK_AUTH"
                        tap_at(42,70)
                        time_sleep(2,3)
                        tap_at(404,962)
                        STATE_MACHINE = "LIT_FACEBOOK_SELECT_WAIT"
                        __QUATRA__['lit_facebook_state_count'] = 0


                # 2. Hesap bilgileri giriş
                elif STATE_MACHINE == "LIT_ACCOUNT":
                    time_sleep(3,3)
                    if "bilgileri doldurun" in text_lower or "onaylandiktan sonra" in text_lower or "cinsiyet" in text_lower or "kullanici adin" in text_lower or "kadin" in text_lower:
                        if not __SIGNALS__['name_typed']:
                            tap_at(375, 427)
                            time_sleep(0.3, 0.5)
                            type_text(setting_name)
                            __SIGNALS__['name_typed'] = True

                        if not __SIGNALS__['age_typed']:
                            tap_at(274, 552)
                            time_sleep(0.3, 0.5)
                            type_text(f"0{random.randint(1, 9)}0{random.randint(1, 9)}199{random.randint(5, 9)}")
                            tap_at(499, 682)
                            tap_at(758, 1306)
                            time_sleep(0.5, 1)
                            __SIGNALS__['age_typed'] = True

                        tap_at(400, 1185)
                        time_sleep(1, 1)
                        tap_at(486, 807)

                        if account_again is None:
                            account_again = False
                            bot_log('account_again = False')

                    elif account_again is True:
                        STATE_MACHINE = "LIT_POST_CONTROLLER"
                        root_code('am start -n com.litatom.app/com.lit.app.ui.MainActivity')
                        root_code('pm grant com.litatom.app android.permission.READ_MEDIA_IMAGES')
                        root_code('pm grant com.litatom.app android.permission.READ_MEDIA_VIDEO')
                        root_code('pm revoke com.litatom.app android.permission.ACCESS_FINE_LOCATION')
                        root_code('pm revoke com.litatom.app android.permission.ACCESS_COARSE_LOCATION')
                    elif account_again is False:
                        if "google" in p_lower:
                            root_code('pm clear --user 0 com.litatom.app')
                            root_code('am start -n com.litatom.app/com.lit.app.ui.login.GoogleLoginActivity')
                            STATE_MACHINE = "LIT_GOOGLE_SELECT_WAIT"
                            account_again = True
                            bot_log('account_again = True')
                        elif "facebook" in p_lower:
                            root_code('pm clear --user 0 com.litatom.app')
                            root_code('am start -n com.litatom.app/com.lit.app.ui.MainActivity')
                            STATE_MACHINE = "LIT_APP_INIT"
                            account_again = True
                            bot_log('account_again = True')
                    else:
                        __QUATRA__['account_check'] += 1
                        bot_log(f"HARD_POST_COUNT: {__QUATRA__['account_check']}")
                        if __QUATRA__['account_check'] >= 3:
                            __QUATRA__['account_check'] = 0
                            account_again = True
                            bot_log('account_again = True')
                            root_code('am start -n com.litatom.app/com.lit.app.ui.MainActivity')
                            root_code('pm grant com.litatom.app android.permission.READ_MEDIA_IMAGES')
                            root_code('pm grant com.litatom.app android.permission.READ_MEDIA_VIDEO')
                            root_code('pm revoke com.litatom.app android.permission.ACCESS_FINE_LOCATION')
                            root_code('pm revoke com.litatom.app android.permission.ACCESS_COARSE_LOCATION')
                            STATE_MACHINE = "LIT_POST_CONTROLLER"
                            bot_log('HARD_POST')
                # 3. Gönderi atma
                elif STATE_MACHINE == "LIT_POST_CONTROLLER":
                    if not lit_permission_error and not lit_webview_error:
                        root_code('magisk --denylist enable')
                        root_code('am start -n com.litatom.app/com.lit.app.post.feedpublish.FeedPublishActivity')
                        STATE_MACHINE = "LIT_POST"
                    else:
                        bot_log('CRİTİCAL_SCREEN_ERROR')
                elif STATE_MACHINE == "LIT_POST":
                    time_sleep(2,2)
                    tap_at(13, 53)
                    if "litmatch siirekli olarak duruyor" in text_lower or "uygulamayi kapat" in text_lower:
                        tap_at(347,1224)
                        time_sleep(1,1)
                        root_code('am start -n com.litatom.app/com.lit.app.post.feedpublish.FeedPublishActivity')
                    elif "webview gincellemeleri kaldirilsin" in text_lower or "litmatch uygulamasini yeniden baslatin" in text_lower:
                        tap_at(291,1201)
                        time_sleep(1,1)
                        root_code('am start -n com.litatom.app/com.lit.app.post.feedpublish.FeedPublishActivity')
                    elif ("ne di" in text_lower or "ne d" in text_lower or "dis" in text_lower) and not ("litmatch siirekli olarak duruyor" in text_lower or "uygulamayi kapat" in text_lower):
                        if __SIGNALS__['random_post_active'] and len(random_post) > 0 or posts[__QUATRA__['post_count']]["image_active"]:
                            tap_at(70, 184)
                            time_sleep(1, 1)
                            tap_at(247, 1048)
                            time_sleep(1, 1)
                        if __SIGNALS__['random_post_active'] and len(random_post) > 0:
                            chosen_coord = random.choice(random_post)
                            random_post.remove(chosen_coord)
                            tap_at(chosen_coord[0], chosen_coord[1])
                        elif posts[__QUATRA__['post_count']]["image_active"]:
                            coord = posts[__QUATRA__['post_count']]["image"]
                            tap_at(coord[0], coord[1])
                        time_sleep(1, 1)
                        tap_at(698, 1229)
                        time_sleep(1, 1)
                        tap_at(100, 264)
                        time_sleep(1, 1)
                        type_text(setting_text)
                        time_sleep(1, 1)
                        tap_at(730, 62)
                        time_sleep(1, 1)
                        root_code('input keyevent 3')

                        __QUATRA__['post_error_count'] = 0
                        bot_log(f"POST_COUNT: {__QUATRA__['post_count']} ")

                        if posts[__QUATRA__['post_count']]["sleep"] > 0:
                            freeze_reset()
                            bot_action(f"sleep-{posts[__QUATRA__['post_count']]["sleep"]}")
                            power_check = root_code('dumpsys power | grep mWakefulness')
                            if 'Awake' in power_check:
                                bot_log("SCREEN_AWAKE")
                                root_code('input keyevent 26')
                            bot_log(f"SLEEP_TİME: {posts[__QUATRA__['post_count']]["sleep"]} sn")
                            sleep_val = posts[__QUATRA__['post_count']]["sleep"]
                            time_sleep(sleep_val, sleep_val)
                            screen_controller()

                        __QUATRA__['post_count'] += 1

                        if __QUATRA__['post_count'] >= len(posts):
                            STATE_MACHINE = "LIT_DONE"
                            bot_log('POST_LIMITED ==> LIT_DONE')
                        else:
                            STATE_MACHINE = "LIT_POST_CONTROLLER"

                    elif "igin tele g ramdan mesaj atin" in text_lower or "tele g ramdan" in text_lower or "mesaj" in text_lower:
                        tap_at(730, 62)
                        STATE_MACHINE = "LIT_POST_CONTROLLER"
                        bot_log(f"POST_ERROR_COUNT { __QUATRA__['post_error_count']}")
                        __QUATRA__['post_error_count'] += 1
                        if  __QUATRA__['post_error_count'] >= 2:
                            STATE_MACHINE = "LIT_DONE"
                            bot_log('POST_ERROR_LIMITED ==> LIT_DONE')

                time_sleep(0.5, 0.5)
            time_sleep(0.5, 1.0)
        else:
            bot_log(f"[!] Bilinmeyen/Tanımsız uygulama adı: {app_name}")

        time_sleep(0.3, 0.5)


    if "google" in p_lower:
        if not STATE_MACHINE_TEST:
            STATE_MACHINE = "SYNC_START"
            root_code('am start -a android.settings.SYNC_SETTINGS')
        else:
            STATE_MACHINE = "SYNC_DONE"
        while STATE_MACHINE != "SYNC_DONE":
            screen_text = capture_screen()
            text_lower = screen_text.lower()
            freeze_detect(email_text,platform,password_text)
            start_live_loop()
            if "verileri otomatik esitleyin" in text_lower or "hesaplari yonet" in text_lower:
                tap_at(547,191)
                time_sleep(1,1)
                tap_at(545,507)
                time_sleep(1,1)
                tap_at(613,728)
                time_sleep(1,1)
                STATE_MACHINE = "SYNC_DONE"
                freeze_reset()

    root_code("input keyevent 187")
    time_sleep(3,3)
    tap_at(400, 1103)
    time_sleep(0.03,0.03)
    tap_at(400, 1103)
    time_sleep(0.03,0.03)
    tap_at(400, 1103)
    time_sleep(0.03,0.03)
    time_sleep(2,2)
    STATE_MACHINE = "APP_INIT"
    bot_log('Uygulamalar bitti')



def run_automation(email_text, password_text, platform, active_list, setting_name, setting_text, setting_vpn, setting_posts):
    global STATE_MACHINE, STATE_MACHINE_SYNC_COUNT, STATE_ROBOT_CONTROL
    __QUATRA__.clear()
    __SIGNALS__.clear()
    __SIGNALS__['STATE_ROBOT_CONTROL'] = False
    p_lower = platform.lower()
    bot_log('APP_INIT')
    while STATE_MACHINE != "DONE":
        # Ekran kontrolleri
        screen_controller()
        screen_text = capture_screen()
        freeze_detect(email_text,platform,password_text)
        start_live_loop()
        power_check = root_code('dumpsys power | grep mWakefulness')

        # Boş ekran koruması (Ekran okunamıyorsa döngüyü atla / bekle)
        if not screen_text.strip() and STATE_MACHINE != "APP_INIT":
            time_sleep(0.5, 0.8)
            continue

        # Hata Yönetimi (Genel)
        if "kimliğinizi doğrulayın" in screen_text or "kimliginizi dogrulayin" in screen_text or "hesabini kullanmak igin insan oldugunu onayla" in screen_text or "insan oldugunu onayla" in screen_text or "igeren tiim resimleri segin" in screen_text or "baska bir ydntem dene" in screen_text:
            if not STATE_ROBOT_CONTROL:
                rob_variant = ["Robot", f"{email_text} - Robot", "🤖", "Hesap robot olmuş", "Hızlı girmeliyim robot oluyo"]
                bot_popup(random.choice(rob_variant))
                reset_state(f"{email_text} - Robot")
                break
            else:
                bot_log('STATE_ROBOT_CONTROL = False')
                tap_at(88,459)
                bot_log('STATE_ROBOT_CONTROL')
                freeze_reset()

        if "telefon numaranizi dogrulayin" in screen_text or "telefon numaraniz" in screen_text:
            number_variant = ["Numara istedi", f"{email_text} - Numara isteniyor", "🤖", "Telefon doğrulama isteniyor"]
            bot_popup(random.choice(number_variant))
            reset_state(f"{email_text} - Numara doğrulama istiyor")
            break
        if "oturum agmak igin kod alin" in screen_text or "bu ekstra adim" in screen_text:
            bot_popup('g.co/sc')
            reset_state(f"{email_text} - Oturum için ekstra doğrulama istiyo")
            break
        if "giincellemleri iptal et" in screen_text:
            tap_at(688, 1218)
            time_sleep(1.0, 1.5)
        if "sarj cihazinin dogru sekilde bagli" in screen_text or "Bu siirekli olursa sarj kablosunu degistirmeyi" in screen_text:
            tap_at(401, 1208)
            time_sleep(1, 1)

        # Platform Akış Kontrolü
        if "google" in p_lower and 'Awake' in power_check:
            # 0. Play Store Karşılama Ekranı
            if STATE_MACHINE == "APP_INIT":

                if "google hesabınızı kullanın" in screen_text or "hesap bu cihaza eklenir" in screen_text:
                    freeze_reset()
                    STATE_MACHINE = "GOOGLE_EMAIL_TYPE"
                    __QUATRA__['STATE_MACHINE_SYNC_COUNT'] = 0
                    __QUATRA__['google_app_unknown_error'] = 0
                elif "bir sorun olustu" in screen_text or "liitfen geri gidip tekrar deneyin" in screen_text:
                    root_code("input keyevent 187")
                    time_sleep(2, 2)
                    tap_at(400, 1103)
                    time_sleep(2, 2)
                    freeze_reset()
                    STATE_MACHINE = "GOOGLE_EMAIL_TYPE"
                    __QUATRA__['STATE_MACHINE_SYNC_COUNT'] = 0
                    __QUATRA__['google_app_unknown_error'] = 0
                    root_code('am start -n com.litatom.app/com.lit.app.ui.login.GoogleLoginActivity')
                elif "oyunlar uygulamalar ara kitaplar siz gocuklar" in screen_text or "ve guincellemeler dogrudan" in screen_text or "anladim" in screen_text or __SIGNALS__['google_app_unknown_bypass']:
                    __QUATRA__['STATE_MACHINE_SYNC_COUNT'] += 1
                    __QUATRA__['google_app_unknown_error'] = 0
                    bot_log(f"STATE_MACHINE_SYNC_COUNT: {__QUATRA__['STATE_MACHINE_SYNC_COUNT']}")

                    if __QUATRA__['STATE_MACHINE_SYNC_COUNT'] >= 3 or __SIGNALS__['google_app_unknown_bypass']:
                        root_code('am start -a android.settings.SYNC_SETTINGS')
                        time_sleep(2.0, 3.0)
                        STATE_MACHINE = "SYNC_START"
                        __QUATRA__['sync_loop'] = 0
                        while STATE_MACHINE != "SYNC_DONE" and __QUATRA__['sync_loop'] < 20:
                            __QUATRA__['sync_loop'] += 1
                            screen_text = capture_screen()
                            text_lower = screen_text.lower()
                            start_live_loop()

                            if ("verileri otomatik esitleyin" in text_lower or "hesaplari yonet" in text_lower) and "@gmail.com" in text_lower:
                                tap_at(547, 191)
                                time_sleep(1.0, 1.0)
                                tap_at(545, 507)
                                time_sleep(1.0, 1.0)
                                tap_at(613, 728)
                                time_sleep(1.0, 1.0)
                                bot_log("Eski hesap başarıyla kaldırıldı.")
                                freeze_reset()
                                __SIGNALS__['google_app_unknown_bypass'] = False
                                STATE_MACHINE = "SYNC_DONE"
                                break
                            else:
                                bot_log('Oturum açılmış hesap bulunamadı')
                                freeze_reset()
                                __SIGNALS__['google_app_unknown_bypass'] = False
                                STATE_MACHINE = "SYNC_DONE"
                            time_sleep(0.5, 0.5)
                        root_code("input keyevent 187")
                        time_sleep(2, 2)
                        tap_at(400, 1103)
                        time_sleep(2, 2)
                        __QUATRA__['STATE_MACHINE_SYNC_COUNT'] = 0
                        STATE_MACHINE_COUNT = 0
                        root_code('am start -n com.litatom.app/com.lit.app.ui.login.GoogleLoginActivity')
                        STATE_MACHINE = "APP_INIT"
                else:
                    __QUATRA__['google_app_unknown_error'] += 1
                    bot_log(f"GOOGLE_APP_UNKNOWN_ERROR: {__QUATRA__['google_app_unknown_error']}")

                if __QUATRA__['google_app_unknown_error'] >= 5:
                    freeze_reset()
                    __SIGNALS__['google_app_unknown_bypass'] = True
                    __SIGNALS__['google_app_unknown_bypass_flag'] = True
                    __QUATRA__['google_app_unknown_error'] = 0
                    bot_log("__SIGNALS__['google_app_unknown_bypass'] = True")
                    bot_log('Bilinmeyen bir ekranla karşılaşıldı olası sorun çözülmeye çalışılıyor.')
                elif __QUATRA__['google_app_unknown_error'] >= 3 and __SIGNALS__['google_app_unknown_bypass_flag']:
                    bot_error()
                    bot_popup('Bilinmeyen sorun')
                    reset_state(f"K: {email_text}, Ş: {password_text} - Bilinmeyen sorun çözülemedi bir sonraki hesaba geçiliyor")
                    __SIGNALS__['google_app_unknown_bypass_flag'] = False
                    break
            # 1. E-posta alanı kontrolü, yazımı ve hata/robot kontrolü
            elif STATE_MACHINE == "GOOGLE_EMAIL_TYPE":
                __QUATRA__['google_app_unknown_error'] = 0
                if not __SIGNALS__['email_typed']:
                    tap_at(290, 355)
                    time_sleep(0.3, 0.6)
                    type_text(email_text)
                    time_sleep(0.3, 0.5)
                    __SIGNALS__['email_typed'] = True
                    bot_log('email_typed = True')

                tap_at(691, 837)
                time_sleep(1.5, 2.0)
                STATE_MACHINE = "GOOGLE_PASS_WAIT"

            # 2. Şifre alanı, şifreyi göster ve şifre yanlış / robot kontrolü
            elif STATE_MACHINE == "GOOGLE_PASS_WAIT":
                if "bulunamad" in screen_text or "bulunumad" in screen_text:
                    user_variant = ["Kullanıcı adı yanlış", "Yanlış kullanıcı adı", "Kullanıcı adını düzgün girin", f"{email_text} - Yanlış", "Hesapları düzgün atın"]
                    bot_popup(random.choice(user_variant))
                    reset_state(f"{email_text} - Kullanıcı adı yanlış")
                    break
                elif "sifreyi" in screen_text or "goster" in screen_text or "şifrenizi" in screen_text:
                    STATE_MACHINE = "GOOGLE_PASS_TYPE"

            # 3. "Kabul ediyorum" ekranı kontrolü
            elif STATE_MACHINE == "GOOGLE_PASS_TYPE":
                if not __SIGNALS__['password_typed']:
                    type_text(password_text)
                    time_sleep(0.3, 0.5)
                    __SIGNALS__['password_typed'] = True
                    bot_log('password_typed = True')

                tap_at(686, 838)
                time_sleep(1.5, 2.0)
                STATE_MACHINE = "GOOGLE_ACCEPT_WAIT"

            elif STATE_MACHINE == "GOOGLE_ACCEPT_WAIT":
                if "sifre yanlis" in screen_text or "tekrar deneyin" in screen_text or "sifrenizi mi unuttunuz" in screen_text:
                    delete_variant = ["Şifre yanlış", "Yanlış şifre", "Şifreleri düzgün atın", "Şifre yanlış sizin saçmalıklarınızla uğraşamam", "Şifre yanlış sizin yapacağınız iş"]
                    bot_popup(random.choice(delete_variant))
                    reset_state(f"{email_text} - Şifre yanlış")
                    break
                elif "hizmetleri" in screen_text and "kabul ediyorum" in screen_text:
                    STATE_MACHINE = "GOOGLE_ACCEPT"

            elif STATE_MACHINE == "GOOGLE_ACCEPT":
                tap_at(655, 1211)
                time_sleep(1.0, 1.5)
                STATE_MACHINE = "DONE"
                bot_popup('Google hesabını girdim')
                time_sleep(1.0, 1.5)
                bot_popup('Şimdi başlıyorum')

        elif "facebook" in p_lower and 'Awake' in power_check:
            # --- Facebook Hata Yönetimi ---
            if ("girdigin girig bilgileri yanlis" in screen_text or "hesabini bul ve girig yap" in screen_text or "bir hesaba bagi deg" in screen_text) and STATE_MACHINE == "FACEBOOK_LOGİN_APPROVAL":
                delete_variant = ["Giriş bilgisi yanlış", "Yanlış giriş bilgisi", "Giriş bilgisini düzgün atın", "Giriş bilgisi yanlış sizin saçmalıklarınızla uğraşamam", "Giriş bilgisi yanlış sizin yapacağınız iş"]
                bot_popup(random.choice(delete_variant))
                reset_state(f"{email_text} - Giriş bilgisi yanlış")
                break
            elif ("kodu gir" in screen_text or "bu kodu alman birkag dakika siirebilir" in screen_text or "yeni bir kod al" in screen_text) and STATE_MACHINE == "FACEBOOK_LOGİN_APPROVAL":
                reset_state(f"{email_text} - Facebook Kodu girilmemiş")
                break
            elif "size bildirim" in screen_text or "istiyor izin ver" in screen_text:
                tap_at(430, 822)
                freeze_reset()
            elif "facebook uygulamada daha iyi" in screen_text or "uygulamayi indir" in screen_text:
                tap_at(415, 1224)
                freeze_reset()
            elif "hesabinizi kapattik" in screen_text or "topluluk standartlari" in screen_text:
                reset_state(f"{email_text} - Hesap facebook tarafından kapatılmış")
                break
            elif ("adi yanlis" in screen_text or "adi bulunamad" in screen_text) and STATE_MACHINE == "FACEBOOK_LOGİN_APPROVAL":
                reset_state(f"{email_text} - Facebook kullanıcı adı yanlış")
                break
            elif "sifre yanlis" in screen_text and STATE_MACHINE == "FACEBOOK_LOGİN_APPROVAL":
                reset_state(f"{email_text} - Facebook şifresi yanlış")
                break
            elif "ben robot degilim" in screen_text or "recaptcha" in screen_text:
                reset_state(f"{email_text} - Facebook hesabı robot oldu")
                break
            elif "bu siteye ulagilamiyor" in screen_text or "ip adresi bulunamadi" in screen_text:
                tap_at(415, 1224)
                freeze_reset()

            # --- STATE MACHINE AKIŞI ---
            if STATE_MACHINE == "APP_INIT":

                if ("facebook'a girig yap" in screen_text or "e-posta adresi veya cep telefonu numarasi" in screen_text or "girig yap" in screen_text) and not ("girdigin girig bilgileri yanlis" in screen_text or "hesabini bul ve girig yap" in screen_text or "bir fotograf veya video paylas ya da bir seyler yaz" in screen_text or "bir fotograf veya video paylas" in screen_text or "fotograf paylas" in screen_text or "bir seyler yaz" in screen_text or "takip et" in screen_text):

                    # E-posta yazma
                    if not __SIGNALS__['email_typed']:
                        type_text(email_text)
                        time_sleep(0.3, 0.5)
                        __SIGNALS__['email_typed'] = True
                        bot_log('email_typed = True')
                        root_code('input keyevent 61') # TAB
                    time_sleep(1, 1)

                    # Şifre yazma
                    if not __SIGNALS__['password_typed']:
                        type_text(password_text)
                        time_sleep(0.3, 0.5)
                        __SIGNALS__['password_typed'] = True
                        bot_log('password_typed = True')
                    time_sleep(1, 1)

                    # Enter gönder
                    root_code('input keyevent 66')

                    # CRITICAL FIX 1: Facebook'un giriş yapıp sayfanın değişmesi için bekle!
                    bot_log('Giriş yapıldı, sayfa yüklenmesi bekleniyor...')
                    time_sleep(3, 5)

                    # CRITICAL FIX 2: Onay aşamasına geçerken TÜM sayaçları temizle!
                    __QUATRA__['facebook_state_count'] = 0
                    __QUATRA__['facebook_auth_count'] = 0
                    __QUATRA__['facebook_app_unknown_error'] = 0

                    STATE_MACHINE = "FACEBOOK_LOGİN_APPROVAL"
                else:
                    __QUATRA__['facebook_state_count'] += 1
                    bot_log(f"FACEBOOK_STATE_COUNT: {__QUATRA__['facebook_state_count']}")

                # 3 Kez sayfa yüklenemezse Chrome sıfırla
                if __QUATRA__['facebook_state_count'] >= 3:
                    __QUATRA__['facebook_state_count'] = 0
                    root_code("input keyevent 187")
                    time_sleep(2, 2)
                    tap_at(400, 1103)
                    time_sleep(2, 2)

                    reset_chrome()

                    bot_log('HARD_FACEBOOK_PAGE')
                    freeze_reset()

            elif STATE_MACHINE == "FACEBOOK_LOGİN_APPROVAL":
                # Başarılı Giriş Durumu
                if "bir fotograf veya video paylas ya da bir seyler yaz" in screen_text or "bir fotograf veya video paylas" in screen_text or "fotograf paylas" in screen_text or "bir seyler yaz" in screen_text or "takip et" in screen_text or "size bildirim" in screen_text or "istiyor izin ver" in screen_text or "follow" in screen_text or "create story" in screen_text or "facebook uygulamada daha iyi" in screen_text or "uygulamayi indir" in screen_text or "facebook is better on the app" in screen_text or "giris bilgilerin kaydedilsin" in screen_text or "bir daha giris yaparken bilgilerini girmen gerekmeyecek" in screen_text or "Baglantida kalmak icin bildirimleri ag" in screen_text:
                    STATE_MACHINE = "DONE"

                # Giriş Sayfası Halen Duruyorsa (Hatalı Giriş veya Yüklenememe)
                elif ("facebook'a girig yap" in screen_text or "e-posta adresi veya cep telefonu numarasi" in screen_text or "girig yap" in screen_text) and not ("girdigin girig bilgileri yanlis" in screen_text or "hesabini bul ve girig yap" in screen_text or "bir fotograf veya video paylas ya da bir seyler yaz" in screen_text or "bir fotograf veya video paylas" in screen_text or "fotograf paylas" in screen_text or "bir seyler yaz" in screen_text or "takip et" in screen_text) and (__SIGNALS__['email_typed'] and __SIGNALS__['password_typed']):
                    __QUATRA__['facebook_auth_count'] += 1
                    bot_log(f"FACEBOOK_AUTH_COUNT: {__QUATRA__['facebook_auth_count']}")
                else:
                    __QUATRA__['facebook_app_unknown_error'] += 1
                    bot_log(f"FACEBOOK_APP_UNKNOWN_ERROR: {__QUATRA__['facebook_app_unknown_error']}")

                # 3 Kez üst üste giriş sayfasında takılırsa Chrome sıfırla ve başa dön
                if __QUATRA__['facebook_auth_count'] >= 3:
                    __SIGNALS__['email_typed'] = False
                    __SIGNALS__['password_typed'] = False
                    __QUATRA__['facebook_auth_count'] = 0
                    STATE_MACHINE = "APP_INIT"

                    freeze_reset()
                    root_code("input keyevent 187")
                    time_sleep(2, 2)
                    tap_at(400, 1103)
                    time_sleep(2, 2)

                    reset_chrome()

                # 4 Kez bilinmeyen hata verirse sonraki hesaba geç
                if __QUATRA__['facebook_app_unknown_error'] >= 4:
                    bot_error()
                    bot_popup('Bilinmeyen sorun')
                    reset_state(f"K: {email_text}, Ş: {password_text} - Bilinmeyen bir sorun algılandı bir sonraki hesaba geçiliyor")
                    break


        time_sleep(0.4, 0.7)

        # Giriş başarılıysa aktif uygulama otomasyonlarını tetikle
        if STATE_MACHINE == "DONE":
            bot_log(f"[+] Giriş başarılı, uygulama içi otomasyona geçiliyor: {platform}")
            apps_automation(active_list, platform, setting_name, setting_text, setting_vpn, email_text,password_text,setting_posts)
#             STATE_MACHINE = "APP_INIT"
            break
    print("[+] Otomasyon döngüsü sonlandırıldı.")

def baslat():
    global STATE_MACHINE_TEST, _su_process
    critical_thermal_limit = 42  # Üst sıcaklık eşiği (°C)
    safe_thermal_threshold = 38  # Güvenli soğuma eşiği (°C)
    critical_signal_limit = -85.0  # Kopma seviyesine yakın zayıf sinyal (dBm)
    low_battery_limit = 5          # Yeni hesap çekmeyi durduracak kritik alt sınır (%)
    safe_battery_threshold = 10    # Şarja takılınca botun geri uyanacağı güvenli sınır (%)
    root_code('am force-stop app.ninjavpn.android')
    # root_code('svc power stayon true')  # Şarjdayken/çalışırken ekranın tamamen kapanıp sistemi dondurmasını önler
    # root_code('dumpsys deviceidle disable') # Android Doze modunu devre dışı bırakır
    while True:

        # --- Wİ-Fİ KONTROLÜ ---
        def get_signal():
            val = root_code('cat /proc/net/wireless | grep $(ip route | grep default | awk \'{print $5}\' | head -n 1) | awk \'{print $4}\'').strip()
            return int(val) if val and val.lstrip('-').isdigit() else 0

        current_signal = get_signal()
        if current_signal != 0 and current_signal <= int(critical_signal_limit):
            bot_action("wifi")
            bot_msg(f"DİKKAT: İnternet sinyali çok zayıf! Sinyal Gücü: {current_signal} dBm")

            while True:
                time_sleep(10.0, 10.0)
                signal_check = get_signal()
                bot_popup(f"İnternet kontrol ediliyor... Mevcut Sinyal: {signal_check} dBm")

                if signal_check > int(critical_signal_limit):
                    bot_popup(f"İnternet sinyali iyileşti ({signal_check} dBm).")
                    break
            continue

        # --- TERMODİNAMİK DURUM KONTROLÜ ---
        def get_temp():
            raw = root_code('cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0').strip()
            return int(raw) // 1000 if raw.isdigit() else 0

        current_temperature = get_temp()
        if current_temperature >= int(critical_thermal_limit):
            bot_action("thermodynamics")
            bot_msg(f"Tablet aşırı ısındı! Sıcaklık: {current_temperature}°C")
            bot_popup("Çok ısındım")

            while True:
                time_sleep(10.0, 10.0)
                ambient_check = get_temp()
                bot_popup(f"Soğuyor... Mevcut sıcaklık: {ambient_check}°C")

                if ambient_check <= int(safe_thermal_threshold):
                    bot_msg(f"Sıcaklık güvenli seviyeye indi ({ambient_check}°C).")
                    break
            continue

        # --- PİL DURUM KONTROLÜ ---
        def get_battery():
            level = root_code('cat /sys/class/power_supply/battery/capacity').strip()
            status = root_code('cat /sys/class/power_supply/battery/status').strip()
            return int(level) if level.isdigit() else 0, status == "Charging"

        battery_level, is_charging = get_battery()
        if battery_level <= int(low_battery_limit):

            bot_msg(f"Düşük Pil Uyarısı! Mevcut Pil: %{battery_level}")

            while True:
                time_sleep(15.0, 15.0)
                bot_action("Charging")
                check_level, check_charging = get_battery()

                if check_charging and check_level >= int(safe_battery_threshold):
                    bot_msg(f"⚡ Şarj yeterli (%{check_level}). Bot uyanıyor!")
                    break
                else:
                    bot_popup(f"Mevcut Pil: %{check_level}")
            continue

        # --- HESAP BEKLEME AŞAMASI ---
        bot_action("bekliyor")
        bot_log("Sunucudan hesap bekleniyor...")
        print("Sunucudan hesap bekleniyor...")
        start_wait_time = time.time()
        screen_active = False

        try:
            while True:
                try:
                    hesap = fetch_account()
                except Exception as net_err:
                    print(f"[!] İnternet koptu, yeniden bağlanmaya çalışılıyor...")
                    time_sleep(5.0, 5.0)
                    continue

                if (time.time() - start_wait_time) > 5.0 and not screen_active:
                    power_check = root_code('dumpsys power | grep mWakefulness')
                    if 'Awake' in power_check:
                        bot_log("SCREEN_AWAKE")
                        root_code('input keyevent 26')
                        screen_active = True

                if hesap:

                    if _su_process:
                        try:
                            _su_process.terminate()
                        except:
                            pass
                        _su_process = None

                    gc.collect()

                    # Ekran kontrolleri
                    screen_controller()
                    genel_ayarlar = get_general_settings()
                    platform = str(hesap.get("platform", "google"))
                    email_val = str(hesap.get("user", ""))
                    pass_val = str(hesap.get("pass", ""))
                    raw_active_list = hesap.get("active_list", [])
                    active_list = [item[1:] if isinstance(item, str) and len(item) > 0 else item for item in raw_active_list]
                    setting_name = genel_ayarlar.get("name")
                    setting_text = genel_ayarlar.get("text")
                    setting_vpn = genel_ayarlar.get("vpn")
                    setting_posts = genel_ayarlar.get("posts")

                    print(f"Platform: {platform}")
                    print(f"Kullanıcı/E-posta: {email_val}")
                    print(f"Şifre: {pass_val}")
                    print(f"Zaman: {time.time()}")
                    print("-" * 40)

                    if not STATE_MACHINE_TEST:
                        open_platform_url(platform)
                        time_sleep(3.0, 3.0)
                        run_automation(email_val, pass_val, platform, active_list, setting_name, setting_text, setting_vpn, setting_posts)
                    else:
                        apps_automation(active_list, platform, setting_name, setting_text, setting_vpn, email_val,pass_val, setting_posts)

                    break
                else:
                    time_sleep(3.0, 3.0)

        except Exception as e:
            time_sleep(0.5, 1.0)

if __name__ == "__main__":
    try:
        baslat()
    except KeyboardInterrupt:
        print("\nStopped.")
        bot_log("Stopped")
        bot_action('uyuyor')