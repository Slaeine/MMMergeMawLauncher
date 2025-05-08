import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import requests
import subprocess
import zipfile
import io
import tempfile
import shutil
import time
import logging

# --- Logging Setup ---
logging.basicConfig(level=logging.DEBUG, filename='launcher_debug.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
GITHUB_REPO = "Malekitsu/Maw-Mod-MMMerge"
RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
PROGRAM_NAME = "mm8.exe"
VERSION_FILENAME = "VERSION.txt"
EXCLUDED_FOLDER = "Saves"

# --- Locate mm8.exe ---
def find_mm8():
    logging.debug("Attempting to locate mm8.exe...")
    paths = [
        os.path.expandvars(r"C:\\Users\\%USERNAME%\\OneDrive\\Desktop\\Might and Magic 8"),
        os.path.expandvars(r"C:\\Users\\%USERNAME%\\Desktop\\Might and Magic 8"),
    ]
    for path in paths:
        full_path = os.path.join(path, PROGRAM_NAME)
        logging.debug(f"Checking path: {full_path}")
        if os.path.exists(full_path):
            logging.debug(f"Found mm8.exe at: {full_path}")
            return full_path
    logging.warning("mm8.exe not found in known paths.")
    return None

# --- Version Handling ---
def get_local_version():
    game_dir = os.path.dirname(find_mm8() or "")
    version_file = os.path.join(game_dir, VERSION_FILENAME)
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            version = f.read().strip()
            logging.debug(f"Local version found: {version}")
            return version
    logging.info("No local version found, defaulting to 0.0.0")
    return "0.0.0"

def write_local_version(latest_version):
    game_dir = os.path.dirname(find_mm8() or "")
    version_file = os.path.join(game_dir, VERSION_FILENAME)
    with open(version_file, "w") as f:
        f.write(latest_version)
    logging.debug(f"Wrote new local version: {latest_version}")

# --- Backup Updated Files Only ---
def backup_files(file_list):
    game_dir = os.path.dirname(find_mm8() or "")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(game_dir, f"backup_MM8_{timestamp}.zip")
    logging.info(f"Creating selective backup at: {backup_path}")
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as backup_zip:
        for file in file_list:
            rel_path = os.path.relpath(file, game_dir)
            if not rel_path.startswith(EXCLUDED_FOLDER) and os.path.exists(file):
                backup_zip.write(file, rel_path)
                logging.debug(f"Backed up: {rel_path}")

# --- Download and Install Update ---
def download_and_install(url, install_dir, latest_version):
    try:
        progress_var.set(10)
        root.update_idletasks()

        logging.info("Downloading update from GitHub...")
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()

        progress_var.set(30)
        root.update_idletasks()

        to_backup = []

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            with tempfile.TemporaryDirectory() as tmpdir:
                logging.debug(f"Extracting update to temp dir: {tmpdir}")
                z.extractall(tmpdir)

                progress_var.set(50)
                root.update_idletasks()

                top_dir = next(os.scandir(tmpdir)).path
                for root_dir, dirs, files in os.walk(top_dir):
                    rel_path = os.path.relpath(root_dir, top_dir)
                    if rel_path.startswith(EXCLUDED_FOLDER):
                        continue
                    target_dir = os.path.join(install_dir, rel_path)
                    os.makedirs(target_dir, exist_ok=True)
                    for file in files:
                        if rel_path.startswith(EXCLUDED_FOLDER):
                            continue
                        src_file = os.path.join(root_dir, file)
                        dst_file = os.path.join(target_dir, file)
                        if os.path.exists(dst_file):
                            to_backup.append(dst_file)
                        shutil.copy2(src_file, dst_file)
                        logging.debug(f"Updated file: {dst_file}")

        backup_files(to_backup)

        progress_var.set(90)
        root.update_idletasks()

        write_local_version(latest_version)
        messagebox.showinfo("Update Complete", "The program has been updated.")

        progress_var.set(100)
        root.update_idletasks()

    except Exception as e:
        logging.error(f"Update failed: {e}")
        messagebox.showerror("Update Failed", f"Could not install update:\n{e}")

# --- Launch the game ---
def launch_game():
    path = find_mm8()
    if path:
        logging.info(f"Launching game: {path}")
        subprocess.Popen([path], cwd=os.path.dirname(path))
        root.destroy()
    else:
        logging.error("Game launch failed: mm8.exe not found.")
        messagebox.showerror("Launch Failed", "Could not locate mm8.exe.")

# --- GitHub Version Check ---
def get_latest_version():
    try:
        logging.info("Checking GitHub for latest version...")
        response = requests.get(RELEASE_API, timeout=5)
        response.raise_for_status()
        data = response.json()
        logging.debug(f"Latest version info: {data['tag_name']}")
        return data["tag_name"], data["zipball_url"]
    except Exception as e:
        logging.error(f"Failed to fetch latest version: {e}")
        messagebox.showerror("Update Check Failed", f"Failed to check for updates:\n{e}")
        return None, None

# --- UI Setup ---
def check_for_updates():
    logging.info("Starting update check...")
    progress_var.set(5)
    root.update_idletasks()

    latest_version, zip_url = get_latest_version()
    local_version = get_local_version()

    if not latest_version:
        return

    if local_version != latest_version:
        if messagebox.askyesno("Update Available",
                               f"A new version ({latest_version}) is available.\nCurrent version: {local_version}\n\nDo you want to update?"):
            download_and_install(zip_url, os.path.dirname(find_mm8() or "."), latest_version)
    else:
        messagebox.showinfo("Up to Date", "You already have the latest version.")

    launch_button.config(state=tk.NORMAL)

# --- Build the GUI ---
root = tk.Tk()
root.title("MM8 Launcher")

frame = tk.Frame(root, padx=20, pady=20)
frame.pack()

tk.Label(frame, text="Might and Magic 8 Launcher", font=("Segoe UI", 14)).pack(pady=(0, 10))
tk.Button(frame, text="Check for Updates", command=check_for_updates).pack(pady=5)

launch_button = tk.Button(frame, text="Launch Game", command=launch_game, state=tk.DISABLED)
launch_button.pack(pady=5)

progress_var = tk.IntVar()
progress_bar = ttk.Progressbar(frame, orient="horizontal", length=300, mode="determinate", variable=progress_var)
progress_bar.pack(pady=10)

root.mainloop()
