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
root.title("MMMMAW Launcher")

frame = tk.Frame(root, padx=20, pady=20)
frame.pack(fill='both', expand=True)

# Header
header = tk.Label(frame, text="MMMMAW Launcher", font=("Segoe UI", 14))
header.pack(pady=(0, 10))

# Controls Frame
controls = tk.Frame(frame)
controls.pack(pady=(0,10))

# Buttons
check_button = tk.Button(controls, text="Check for Updates")
check_button.grid(row=0, column=0, padx=5)

update_button = tk.Button(controls, text="Update", state=tk.DISABLED)
update_button.grid(row=0, column=1, padx=5)

play_button = tk.Button(controls, text="Play")
play_button.grid(row=0, column=2, padx=5)

# Progress Bar
progress_var = tk.IntVar()
progress_bar = ttk.Progressbar(frame, orient="horizontal", length=300, mode="determinate", variable=progress_var)
progress_bar.pack(pady=10)

# Update Status Tree
tree = ttk.Treeview(frame, columns=("file","timestamp"), show="headings", height=10)
tree.heading("file", text="File")
tree.heading("timestamp", text="Archive Time")
tree.column("file", width=250)
tree.column("timestamp", width=150)
tree.pack(fill='both', expand=True)

# --- Helper Functions ---

def find_mm8():
    logging.debug("Locating mm8.exe...")
    paths = [
        os.path.expandvars(r"C:\Users\%USERNAME%\OneDrive\Desktop\Might and Magic 8"),
        os.path.expandvars(r"C:\Users\%USERNAME%\Desktop\Might and Magic 8"),
    ]
    for path in paths:
        exe = os.path.join(path, PROGRAM_NAME)
        if os.path.exists(exe):
            return exe
    return None


def get_local_version_date():
    game_dir = os.path.dirname(find_mm8() or "")
    latest = datetime.min
    for root_dir, _, files in os.walk(game_dir):
        if EXCLUDED_FOLDER in root_dir:
            continue
        for f in files:
            if f in EXCLUDED_FILES:
                continue
            p = os.path.join(root_dir, f)
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


def list_archive_files():
    # Returns list of (trimmed_path, archive_time, local_time)
    zf, tmp, top = extract_zip()
    entries = []
    game_dir = os.path.dirname(find_mm8() or "")
    for r, _, files in os.walk(top):
        rel_dir = os.path.relpath(r, top)
        if rel_dir.startswith(EXCLUDED_FOLDER):
            continue
        for f in files:
            if f in EXCLUDED_FILES or f.lower()=="readme.md":
                continue
            abs_path = os.path.join(r,f)
            rel_zip = os.path.relpath(abs_path, top).replace("\\","/")
            parts = rel_zip.split('/',1)
            trimmed = parts[1] if len(parts)>1 else parts[0]
            # find entry
            match = next((e for e in zf.namelist() if e.lower().endswith(rel_zip.lower())), None)
            if not match:
                continue
            info = zf.getinfo(match)
            archive_time = datetime(*info.date_time)
            # local time
            local_time = datetime.min
            local_path = None
            for lr,_,lf in os.walk(game_dir):
                for name in lf:
                    rel_local = os.path.relpath(os.path.join(lr,name), game_dir).replace("\\","/")
                    if rel_local.lower()==trimmed.lower():
                        local_path = os.path.join(lr,name)
                        local_time = datetime.fromtimestamp(os.path.getmtime(local_path)) if os.path.exists(local_path) else datetime.min
                        break
                if local_path:
                    break
            entries.append((trimmed, archive_time, local_time))
    tmp.cleanup()
    return entries


def extract_zip():
    resp = requests.get(GITHUB_ZIP_URL, stream=True, timeout=10)
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    tmp = tempfile.TemporaryDirectory()
    zf.extractall(tmp.name)
    top = next(os.scandir(tmp.name)).path
    return zf, tmp, top


def download_and_install():
    to_backup=[]
    newest_time = datetime.min
    zf, tmp, top = extract_zip()
    game_dir = os.path.dirname(find_mm8() or "")
    for r,_,files in os.walk(top):
        rel_dir = os.path.relpath(r, top)
        if rel_dir.startswith(EXCLUDED_FOLDER): continue
        dest = os.path.join(game_dir, rel_dir)
        os.makedirs(dest, exist_ok=True)
        for f in files:
            if f in EXCLUDED_FILES or f.lower()=="readme.md": continue
            src = os.path.join(r,f)
            rel_zip = os.path.relpath(src, top).replace("\\","/")
            match = next((e for e in zf.namelist() if e.lower().endswith(rel_zip.lower())),None)
            if not match: continue
            info = zf.getinfo(match)
            archive_time = datetime(*info.date_time)
            dst = os.path.join(dest, f)
            local_time = os.path.getmtime(dst) if os.path.exists(dst) else 0
            if archive_time.timestamp()>local_time:
                if os.path.exists(dst): to_backup.append(dst)
                shutil.copy2(src,dst)
                if archive_time>newest_time: newest_time=archive_time
    if to_backup: backup_files(to_backup)
    write_local_version_date(newest_time)
    tmp.cleanup()
    messagebox.showinfo("Update Complete","Updated files installed.")


def backup_files(files):
    game_dir = os.path.dirname(find_mm8() or "")
    bdir = os.path.join(game_dir,'Backups')
    os.makedirs(bdir,exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    arch = os.path.join(bdir,f'backup_MM8_{stamp}.zip')
    with zipfile.ZipFile(arch,'w',zipfile.ZIP_DEFLATED) as bz:
        for fp in files:
            rel = os.path.relpath(fp,game_dir).replace("\\","/")
            if not rel.startswith(EXCLUDED_FOLDER): bz.write(fp,rel)
    logging.info(f"Backup: {arch}")


def launch_game():
    exe = find_mm8()
    if exe:
        subprocess.Popen([exe], cwd=os.path.dirname(exe))
    else:
        messagebox.showerror("Launch Failed","mm8.exe not found.")


def on_check():
    progress_var.set(10); root.update_idletasks()
    entries = list_archive_files()
    tree.delete(*tree.get_children())
    updates_exist=False
    for fn, atime, ltime in entries:
        tree.insert('', 'end', values=(fn, atime.strftime('%Y-%m-%d %H:%M:%S')))
        if atime>ltime: updates_exist=True
    update_button.config(state=tk.NORMAL if updates_exist else tk.DISABLED)
    progress_var.set(100); root.update_idletasks()


def on_update():
    if messagebox.askyesno("Confirm Update","Install listed updates?" ):
        download_and_install()
        update_button.config(state=tk.DISABLED)

# Bind actions
check_button.config(command=on_check)
update_button.config(command=on_update)
play_button.config(command=launch_game)

# Start GUI
root.mainloop()
