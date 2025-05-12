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

# Configure logging to help diagnose issues during update and runtime
logging.basicConfig(
    level=logging.DEBUG,
    filename='launcher_debug.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Constants defining repository and local installation details
GITHUB_ZIP_URL = "https://github.com/Malekitsu/Maw-Mod-MMMerge/archive/refs/heads/main.zip"
PROGRAM_NAME = "mm8.exe"
VERSION_FILENAME = "VERSION.txt"
EXCLUDED_FOLDER = "Saves"       # Folder to ignore during update operations
EXCLUDED_FILES = {"mm8.ini"}    # Files to skip when checking or copying updates

# --- Initialize main application window ---
root = tk.Tk()
root.title("MMMMAW Launcher")

# Main container for all UI elements
frame = tk.Frame(root, padx=20, pady=20)
frame.pack(fill='both', expand=True)

# Title label at the top of the window
tk.Label(frame, text="MMMMAW Launcher", font=("Segoe UI", 14)).pack(pady=(0, 10))

# Controls row: buttons for actions
controls = tk.Frame(frame)
controls.pack(pady=(0, 10))

check_button = tk.Button(controls, text="Check for Updates")
check_button.grid(row=0, column=0, padx=5)

update_button = tk.Button(controls, text="Update", state=tk.DISABLED)
update_button.grid(row=0, column=1, padx=5)

play_button = tk.Button(controls, text="Play")
play_button.grid(row=0, column=2, padx=5)

# Progress bar to show check/update progress
progress_var = tk.IntVar()
progress_bar = ttk.Progressbar(
    frame,
    orient="horizontal",
    length=300,
    mode="determinate",
    variable=progress_var
)
progress_bar.pack(pady=10)

# Label to display summary of remote vs local version
update_status_label = tk.Label(
    frame,
    text="",
    font=("Segoe UI", 10),
    justify="left",
    anchor="w"
)
update_status_label.pack(fill='x', pady=(5, 0))

# Treeview listing each file in the archive alongside its remote timestamp
tree = ttk.Treeview(frame, columns=("file", "timestamp"), show="headings", height=10)
tree.heading("file", text="File")
tree.heading("timestamp", text="Remote Commit Time")
tree.column("file", width=250)
tree.column("timestamp", width=150)
tree.pack(fill='both', expand=True)


# Store the latest remote commit timestamp for writing to VERSION.txt
last_remote_time = None

# --- Core Helper Functions ---

def find_mm8():
    """
    Search first-level subdirectories on Desktop for mm8.exe.
    Returns the full path to the executable if found, otherwise None.
    """
    user = os.path.expandvars(r"%USERNAME%")
    desktop_paths = [
        os.path.join(os.environ.get('USERPROFILE', ''), 'OneDrive', 'Desktop'),
        os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
    ]
    for base in desktop_paths:
        if os.path.isdir(base):
            for entry in os.listdir(base):
                folder = os.path.join(base, entry)
                exe = os.path.join(folder, PROGRAM_NAME)
                if os.path.isfile(exe):
                    logging.debug(f"Found game executable at: {exe}")
                    return exe
    logging.warning("mm8.exe not found in Desktop subfolders.")
    return None


def get_local_version_date():
    """
    Determine the most recent modification timestamp of all relevant files in the local game directory.
    """
    path = find_mm8()
    game_dir = os.path.dirname(path) if path else ''
    latest = datetime.min
    for root_dir, _, files in os.walk(game_dir):
        if EXCLUDED_FOLDER in root_dir:
            continue
        for name in files:
            if name in EXCLUDED_FILES:
                continue
            full = os.path.join(root_dir, name)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(full))
                if mtime > latest:
                    latest = mtime
            except OSError:
                continue
    return latest


def write_local_version_date(dt):
    """
    Save a timestamp string to VERSION.txt in the game folder for future update checks.
    """
    path = find_mm8()
    game_dir = os.path.dirname(path) if path else ''
    version_file = os.path.join(game_dir, VERSION_FILENAME)
    with open(version_file, 'w') as vf:
        vf.write(dt.strftime('%Y-%m-%d %H:%M:%S'))
    logging.debug(f"Updated local version date to: {dt}")


def get_latest_commit_time():
    """
    Retrieve the timestamp of the latest commit on the main branch using GitHub's REST API.
    """
    try:
        url = "https://api.github.com/repos/Malekitsu/Maw-Mod-MMMerge/commits/main"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        iso_ts = data['commit']['committer']['date']
        dt = datetime.fromisoformat(iso_ts.replace('Z', '+00:00'))
        return dt.replace(tzinfo=None)
    except Exception as e:
        logging.error(f"Error fetching latest commit time: {e}")
        return None


def get_file_commit_time(path_in_repo):
    """
    Fetch the timestamp of the most recent commit affecting a specific file in the repo.
    """
    try:
        url = f"https://api.github.com/repos/Malekitsu/Maw-Mod-MMMerge/commits?path={path_in_repo}&per_page=1"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data:
            iso_ts = data[0]['commit']['committer']['date']
            dt = datetime.fromisoformat(iso_ts.replace('Z', '+00:00'))
        return dt.replace(tzinfo=None)
    except Exception as e:
        logging.error(f"Error fetching commit time for {path_in_repo}: {e}")
    return datetime.min


def extract_zip():
    """
    Download and unzip the repository archive to a temporary folder, returning
    the ZipFile object, temp resource, and top-level extract path.
    """
    resp = requests.get(GITHUB_ZIP_URL, stream=True, timeout=10)
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    tmp = tempfile.TemporaryDirectory()
    zf.extractall(tmp.name)
    top = next(os.scandir(tmp.name)).path
    return zf, tmp, top


def list_archive_files():
    """
    Build a list of tuples (path, remote_commit_time, local_mod_time) for each file
    in the archive, excluding specified folders/files.
    """
    zf, tmp, top = extract_zip()
    game_dir = os.path.dirname(find_mm8() or '')
    entries = []
    for root_dir, _, files in os.walk(top):
        rel_dir = os.path.relpath(root_dir, top)
        if rel_dir.startswith(EXCLUDED_FOLDER):
            continue
        for name in files:
            if name in EXCLUDED_FILES or name.lower() == 'readme.md':
                continue
            abs_zip = os.path.join(root_dir, name)
            rel_zip = os.path.relpath(abs_zip, top).replace('\\', '/')
            trimmed = rel_zip.split('/', 1)[1] if '/' in rel_zip else rel_zip
            commit_time = get_file_commit_time(trimmed)
            local_time = datetime.min
            # match local file for comparison
            for lr, _, lf in os.walk(game_dir):
                for local_name in lf:
                    rel_local = os.path.relpath(os.path.join(lr, local_name), game_dir).replace('\\', '/')
                    if rel_local.lower() == trimmed.lower():
                        try:
                            local_time = datetime.fromtimestamp(os.path.getmtime(os.path.join(lr, local_name)))
                        except OSError:
                            local_time = datetime.min
                        break
                if local_time != datetime.min:
                    break
            entries.append((trimmed, commit_time, local_time))
    tmp.cleanup()
    return entries


def download_and_install():
    """
    For each file in the repo archive whose commit time is newer than the local
    version, back it up and then overwrite the local copy.
    """
    zf, tmp, top = extract_zip()
    game_dir = os.path.dirname(find_mm8() or '')
    to_backup = []
    newest = datetime.min
    for root_dir, _, files in os.walk(top):
        rel_dir = os.path.relpath(root_dir, top)
        if rel_dir.startswith(EXCLUDED_FOLDER):
            continue
        dest_dir = os.path.join(game_dir, rel_dir)
        os.makedirs(dest_dir, exist_ok=True)
        for name in files:
            if name in EXCLUDED_FILES or name.lower() == 'readme.md':
                continue
            abs_zip = os.path.join(root_dir, name)
            rel_zip = os.path.relpath(abs_zip, top).replace('\\', '/')
            trimmed = rel_zip.split('/', 1)[1] if '/' in rel_zip else rel_zip
            commit_time = get_file_commit_time(trimmed)
            local_file = os.path.join(dest_dir, name)
            local_mtime = os.path.getmtime(local_file) if os.path.exists(local_file) else 0
            if commit_time.timestamp() > local_mtime:
                to_backup.append(local_file) if os.path.exists(local_file) else None
                shutil.copy2(abs_zip, local_file)
                if commit_time > newest:
                    newest = commit_time
    if to_backup:
        backup_files(to_backup)
    write_local_version_date(last_remote_time or newest)
    tmp.cleanup()
    messagebox.showinfo("Update Complete", "All updates installed.")


def backup_files(files):
    """
    Create a ZIP backup of provided file paths into a 'Backups' folder.
    """
    game_dir = os.path.dirname(find_mm8() or '')
    backup_dir = os.path.join(game_dir, 'Backups')
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    backup_path = os.path.join(backup_dir, f'backup_MM8_{timestamp}.zip')
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as bz:
        for fp in files:
            rel = os.path.relpath(fp, game_dir).replace('\\', '/')
            if not rel.startswith(EXCLUDED_FOLDER):
                bz.write(fp, rel)
    logging.info(f"Backup created at: {backup_path}")


def launch_game():
    """
    Start the game executable in a new process without blocking the launcher.
    """
    exe = find_mm8()
    if exe:
        subprocess.Popen([exe], cwd=os.path.dirname(exe))
    else:
        messagebox.showerror("Launch Failed", "mm8.exe not found.")


def on_check():
    """
    Triggered by 'Check for Updates': fetch latest commit, update status,
    list files with remote timestamps, and enable 'Update' if needed.
    """
    global last_remote_time
    progress_var.set(10)
    root.update_idletasks()

    local = get_local_version_date()
    remote = get_latest_commit_time()
    last_remote_time = remote
    if remote:
        update_status_label.config(text=f"Remote commit: {remote:%Y-%m-%d %H:%M:%S}\nLocal: {local:%Y-%m-%d %H:%M:%S}")
    else:
        update_status_label.config(text="Error fetching remote commit.")

    tree.delete(*tree.get_children())
    entries = list_archive_files()
    needs = False
    for fname, atime, ltime in entries:
        tree.insert('', 'end', values=(fname, atime.strftime('%Y-%m-%d %H:%M:%S')))
        if atime > ltime:
            needs = True
    update_button.config(state=tk.NORMAL if needs else tk.DISABLED)

    progress_var.set(100)
    root.update_idletasks()


def on_update():
    """
    Triggered by 'Update': confirm and perform file-by-file updates, then save new version timestamp.
    """
    if messagebox.askyesno("Confirm Update", "Install listed updates?"):
        download_and_install()
        update_button.config(state=tk.DISABLED)

# Wire up button actions and start the UI loop
check_button.config(command=on_check)
update_button.config(command=on_update)
play_button.config(command=launch_game)
root.mainloop()
