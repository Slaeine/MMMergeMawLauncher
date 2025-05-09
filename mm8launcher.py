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
from datetime import datetime

# --- Logging Setup ---
logging.basicConfig(
    level=logging.DEBUG,
    filename='launcher_debug.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Configuration ---
GITHUB_ZIP_URL = "https://github.com/Malekitsu/Maw-Mod-MMMerge/archive/refs/heads/main.zip"
PROGRAM_NAME = "mm8.exe"
VERSION_FILENAME = "VERSION.txt"
EXCLUDED_FOLDER = "Saves"
EXCLUDED_FILES = {"mm8.ini"}

# --- GUI Initialization ---
root = tk.Tk()
root.title("MM8 Launcher")

frame = tk.Frame(root, padx=20, pady=20)
frame.pack(fill='both', expand=True)

# Header
header = tk.Label(frame, text="Might and Magic 8 Launcher", font=("Segoe UI", 14))
header.pack(pady=(0, 10))

# Buttons and Controls
element_frame = tk.Frame(frame)
element_frame.pack()

update_button = tk.Button(element_frame, text="Check for Updates")
update_button.grid(row=0, column=0, padx=5, pady=5)

launch_button = tk.Button(element_frame, text="Launch Game", state=tk.DISABLED)
launch_button.grid(row=0, column=1, padx=5, pady=5)

progress_var = tk.IntVar()
progress_bar = ttk.Progressbar(frame, orient="horizontal", length=300, mode="determinate", variable=progress_var)
progress_bar.pack(pady=10)

update_status_label = tk.Label(frame, text="", font=("Segoe UI", 10), justify="left", anchor="w")
update_status_label.pack(fill='x', pady=(5,0))

# Dry-run option
dry_run_var = tk.BooleanVar()
check_dry = tk.Checkbutton(frame, text="Dry run (show updates only, don't install)", variable=dry_run_var)
check_dry.pack(pady=(5,0))

# --- Helper Functions ---
def find_mm8():
    logging.debug("Locating mm8.exe...")
    possible = [
        os.path.expandvars(r"C:\\Users\\%USERNAME%\\OneDrive\\Desktop\\Might and Magic 8"),
        os.path.expandvars(r"C:\\Users\\%USERNAME%\\Desktop\\Might and Magic 8"),
    ]
    for path in possible:
        exe = os.path.join(path, PROGRAM_NAME)
        if os.path.exists(exe):
            return exe
    return None


def get_local_version_date():
    game_dir = os.path.dirname(find_mm8() or "")
    latest = datetime.min
    for root, _, files in os.walk(game_dir):
        if EXCLUDED_FOLDER in root:
            continue
        for f in files:
            if f in EXCLUDED_FILES:
                continue
            p = os.path.join(root, f)
            try:
                t = datetime.fromtimestamp(os.path.getmtime(p))
                if t > latest:
                    latest = t
            except OSError:
                continue
    return latest


def write_local_version_date(dt):
    game_dir = os.path.dirname(find_mm8() or "")
    version_file = os.path.join(game_dir, VERSION_FILENAME)
    with open(version_file, 'w') as vf:
        vf.write(dt.strftime('%Y-%m-%d %H:%M:%S'))
    logging.debug(f"Wrote version date: {dt}")


def extract_zip():
    resp = requests.get(GITHUB_ZIP_URL, stream=True, timeout=10)
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    tmp = tempfile.TemporaryDirectory()
    zf.extractall(tmp.name)
    top = next(os.scandir(tmp.name)).path
    return zf, tmp, top


def is_update_available():
    try:
        zf, tmp, top = extract_zip()
        game_dir = os.path.dirname(find_mm8() or "")
        update_needed = False
        newest_file = ''
        newest_time = datetime.min

        for root, _, files in os.walk(top):
            # skip excluded folder
            rel_dir = os.path.relpath(root, top)
            if rel_dir.startswith(EXCLUDED_FOLDER):
                continue
            for f in files:
                if f in EXCLUDED_FILES or f.lower() == 'readme.md':
                    continue
                    continue
                abs_zip = os.path.join(root, f)
                rel_zip = os.path.relpath(abs_zip, top).replace('\\', '/')
                # trim top-level folder
                parts = rel_zip.split('/', 1)
                trimmed = parts[1] if len(parts) > 1 else parts[0]

                # find zip entry case-insensitive
                matched_entry = next((e for e in zf.namelist() if e.lower().endswith(rel_zip.lower())), None)
                if not matched_entry:
                            logging.warning(f"No matching zip entry for {rel_zip}")
                            continue
                info = zf.getinfo(matched_entry)
                archive_time = datetime(*info.date_time)

                # find local counterpart
                local_time = datetime.min
                for lr, _, lfiles in os.walk(game_dir):
                    for lf in lfiles:
                        rel_local = os.path.relpath(os.path.join(lr, lf), game_dir).replace('\\', '/')
                        if rel_local.lower() == trimmed.lower():
                            local_path = os.path.join(lr, lf)
                            try:
                                local_time = datetime.fromtimestamp(os.path.getmtime(local_path))
                            except OSError:
                                local_time = datetime.min
                            break
                    if local_time != datetime.min:
                        break

                if archive_time > local_time:
                    update_needed = True
                    if archive_time > newest_time:
                        newest_time = archive_time
                        newest_file = trimmed

        tmp.cleanup()
        return update_needed, newest_file, newest_time
    except Exception as e:
        logging.error(f"Update check failed: {e}")
        messagebox.showerror("Update Check Failed", f"Failed to check for updates:\n{e}")
        return False, '', datetime.min


def backup_files(files):
    game_dir = os.path.dirname(find_mm8() or "")
    backup_dir = os.path.join(game_dir, 'Backups')
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    archive = os.path.join(backup_dir, f'backup_MM8_{stamp}.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bz:
        for fp in files:
            rel = os.path.relpath(fp, game_dir).replace('\\', '/')
            if not rel.startswith(EXCLUDED_FOLDER):
                bz.write(fp, rel)
    logging.info(f"Created backup: {archive}")


def download_and_install():
    try:
        zf, tmp, top = extract_zip()
        game_dir = os.path.dirname(find_mm8() or "")
        to_backup = []
        newest_time = datetime.min

        for root, _, files in os.walk(top):
            rel_dir = os.path.relpath(root, top)
            if rel_dir.startswith(EXCLUDED_FOLDER):
                continue
            dest = os.path.join(game_dir, rel_dir)
            os.makedirs(dest, exist_ok=True)
            for f in files:
                if f in EXCLUDED_FILES or f.lower() == 'readme.md':
                    continue
                src = os.path.join(root, f)
                rel_zip = os.path.relpath(src, top).replace('\\', '/')
                # find zip entry case-insensitive
                matched_entry = next((e for e in zf.namelist() if e.lower().endswith(rel_zip.lower())), None)
                if not matched_entry:
                    logging.warning(f"No matching zip entry for {rel_zip}")
                    continue
                info = zf.getinfo(matched_entry)
                archive_time = datetime(*info.date_time)
                dst = os.path.join(dest, f)
                if os.path.exists(dst):
                    to_backup.append(dst)
                shutil.copy2(src, dst)
                if archive_time > newest_time:
                    newest_time = archive_time

        backup_files(to_backup)
        tmp.cleanup()
        write_local_version_date(newest_time)
        messagebox.showinfo("Update Complete", "The program has been updated.")
    except Exception as e:
        logging.error(f"Update failed: {e}")
        messagebox.showerror("Update Failed", f"Could not install update:\n{e}")


def launch_game():
    path = find_mm8()
    if path:
        logging.info(f"Launching game: {path}")
        subprocess.Popen([path], cwd=os.path.dirname(path))
        root.destroy()
    else:
        logging.error("Launch failed: mm8.exe not found.")
        messagebox.showerror("Launch Failed", "Could not locate mm8.exe.")


def check_for_updates():
    progress_var.set(5)
    root.update_idletasks()
    needed, file, atime = is_update_available()
    update_status_label.config(
        text=f"Latest file: {file}\nRemote: {atime:%Y-%m-%d %H:%M:%S}" 
    )
    local_time = get_local_version_date()
    msg = (
        f"Current updated: {local_time:%Y-%m-%d %H:%M:%S}\n"
        f"New file: {file} at {atime:%Y-%m-%d %H:%M:%S}\n\n"
        "Proceed with update?"
    )
    if needed:
        if messagebox.askyesno("Update Available", msg):
            if not dry_run_var.get():
                download_and_install()
            else:
                messagebox.showinfo("Dry Run", "No changes made.")
    else:
        messagebox.showinfo("No Update Needed", f"Up to date: {local_time:%Y-%m-%d %H:%M:%S}")
    progress_var.set(100)
    root.update_idletasks()
    launch_button.config(state=tk.NORMAL)

# Bind buttons
update_button.config(command=check_for_updates)
launch_button.config(command=launch_game)

# Start GUI
root.mainloop()
