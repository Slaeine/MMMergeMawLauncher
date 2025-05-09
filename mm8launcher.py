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
logging.basicConfig(level=logging.DEBUG, filename='launcher_debug.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
GITHUB_ZIP_URL = "https://github.com/Malekitsu/Maw-Mod-MMMerge/archive/refs/heads/main.zip"
PROGRAM_NAME = "mm8.exe"
VERSION_FILENAME = "VERSION.txt"
EXCLUDED_FOLDER = "Saves"
EXCLUDED_FILES = {"mm8.ini"}


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




# --- Check for Updates ---
def is_update_available():
    try:
        response = requests.get(GITHUB_ZIP_URL, stream=True, timeout=10)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            with tempfile.TemporaryDirectory() as tmpdir:
                z.extractall(tmpdir)
                top_dir = next(os.scandir(tmpdir)).path
                game_dir = os.path.dirname(find_mm8() or "")
                update_required = False
                newest_time = datetime.min
                newest_file = ""
                for root_dir, _, files in os.walk(top_dir):
                    if root_dir.startswith(os.path.join(top_dir, EXCLUDED_FOLDER)):
                        continue
                    for file in files:
                        if file in EXCLUDED_FILES or file.lower() == "readme.md":
                            continue
                        file_path = os.path.join(root_dir, file)
                        zip_rel_path = os.path.relpath(file_path, top_dir).replace("\\", "/")
                        zip_rel_parts = zip_rel_path.split("/", 1)
                        zip_rel_path_trimmed = zip_rel_parts[1] if len(zip_rel_parts) > 1 else zip_rel_path
                        # Use original ZIP path for accessing archive contents
                        zip_info = z.getinfo(zip_rel_path)
                        archive_time = datetime(*zip_info.date_time)

                        # Match this file against the local installation
                        matched_local_file = None
                        for local_root, _, local_files in os.walk(game_dir):
                            for local_file in local_files:
                                local_rel_path = os.path.relpath(os.path.join(local_root, local_file), game_dir).replace("\\", "/")
                                if local_rel_path.lower() == zip_rel_path_trimmed.lower():
                                    matched_local_file = os.path.join(local_root, local_file)
                                    break
                            if matched_local_file:
                                break

                        local_time = datetime.min
                        if matched_local_file and os.path.exists(matched_local_file):
                            local_time = datetime.fromtimestamp(os.path.getmtime(matched_local_file))

                        if archive_time > local_time:
                            logging.info(f"Update needed for: {zip_rel_path} | Archive: {archive_time} > Local: {local_time}")
                            update_required = True
                            if archive_time > newest_time:
                                newest_time = archive_time
                                newest_file = zip_rel_path

                update_status_label.config(text=(
                    f"Latest updated file: {newest_file}"
                    f"Remote timestamp: {newest_time}"
                ))
                return update_required, newest_time, get_local_version_date()
    except Exception as e:
        logging.error(f"Failed to check for updates: {e}")
        messagebox.showerror("Update Check Failed", f"Failed to check for updates:{e}")
        return False, datetime.min, datetime.min



# --- UI Setup ---
def check_for_updates():
    if dry_run_var.get():
        logging.info("Dry run mode enabled: will not install updates.")
    logging.info("Starting update check...")
    progress_var.set(5)
    root.update_idletasks()

    update_needed, new_time, local_time = is_update_available()
    msg = (f"Your current version was last updated with the revision from {local_time.strftime('%Y-%m-%d %H:%M:%S')}"
           f"The most current version is from {new_time.strftime('%Y-%m-%d %H:%M:%S')}"
           f"Would you like to update?")
    if update_needed:
        update_list = []
        response = requests.get(GITHUB_ZIP_URL, stream=True, timeout=10)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            with tempfile.TemporaryDirectory() as tmpdir:
                z.extractall(tmpdir)
                top_dir = next(os.scandir(tmpdir)).path
                game_dir = os.path.dirname(find_mm8() or "")
                for root_dir, _, files in os.walk(top_dir):
                    if root_dir.startswith(os.path.join(top_dir, EXCLUDED_FOLDER)):
                        continue
                    for file in files:
                        if file in EXCLUDED_FILES or file.lower() == "readme.md":
                            continue
                        file_path = os.path.join(root_dir, file)
                        zip_rel_path = os.path.relpath(file_path, top_dir).replace("\\", "/")
                        zip_info = z.getinfo(zip_rel_path)
                        archive_time = datetime(*zip_info.date_time)

                        matched_local_file = None
                        for local_root, _, local_files in os.walk(game_dir):
                            for local_file in local_files:
                                local_rel_path = os.path.relpath(os.path.join(local_root, local_file), game_dir).replace("\\", "/")
                                if local_rel_path.lower().endswith(zip_rel_path.lower()):
                                    matched_local_file = os.path.join(local_root, local_file)
                                    break
                            if matched_local_file:
                                break

                        local_time = datetime.min
                        if matched_local_file and os.path.exists(matched_local_file):
                            local_time = datetime.fromtimestamp(os.path.getmtime(matched_local_file))

                        if archive_time > local_time:
                            update_list.append(f"{zip_rel_path} ({archive_time} > {local_time})")

        if update_list:
            detailed_msg = "The following files will be updated:" + "".join(update_list) + "Proceed with update?"
            if messagebox.askyesno("Update Available", detailed_msg):
                if not dry_run_var.get():
                    download_and_install(os.path.dirname(find_mm8() or "."))
                else:
                    messagebox.showinfo("Dry Run", "Dry run complete. No files were modified.")
    else:
        messagebox.showinfo("No Update Needed", "You already have the latest version.")

    progress_var.set(100)
    root.update_idletasks()
    launch_button.config(state=tk.NORMAL)




# --- Version Handling ---
def get_local_version_date():
    game_dir = os.path.dirname(find_mm8() or "")
    newest_time = datetime.min
    for root_dir, _, files in os.walk(game_dir):
        if EXCLUDED_FOLDER in root_dir:
            continue
        for file in files:
            if file in EXCLUDED_FILES:
                continue
            file_path = os.path.join(root_dir, file)
            if os.path.exists(file_path):
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_time > newest_time:
                    newest_time = file_time
    return newest_time

def write_local_version_date(latest_datetime):
    game_dir = os.path.dirname(find_mm8() or "")
    version_file = os.path.join(game_dir, VERSION_FILENAME)
    with open(version_file, "w") as f:
        f.write(latest_datetime.strftime("%Y-%m-%d %H:%M:%S"))
    logging.debug(f"Wrote new local version datetime: {latest_datetime}")

# --- Backup Updated Files Only ---
def backup_files(file_list):
    game_dir = os.path.dirname(find_mm8() or "")
    backup_dir = os.path.join(game_dir, "Backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_MM8_{timestamp}.zip")
    logging.info(f"Creating selective backup at: {backup_path}")
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as backup_zip:
        for file in file_list:
            rel_path = os.path.relpath(file, game_dir)
            if not rel_path.startswith(EXCLUDED_FOLDER) and os.path.exists(file):
                backup_zip.write(file, rel_path)
                logging.debug(f"Backed up: {rel_path}")

# --- Download and Install Update ---
def download_and_install(install_dir):
    try:
        progress_var.set(10)
        root.update_idletasks()

        logging.info("Downloading update from GitHub main branch zip...")
        response = requests.get(GITHUB_ZIP_URL, stream=True, timeout=10)
        response.raise_for_status()

        progress_var.set(30)
        root.update_idletasks()

        to_backup = []
        newest_time = datetime.min

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
                        if rel_path.startswith(EXCLUDED_FOLDER) or file in EXCLUDED_FILES or file.lower() == "readme.md":
                            continue
                        src_file = os.path.join(root_dir, file)
                        dst_file = os.path.join(target_dir, file)
                        rel_dst = os.path.relpath(dst_file, install_dir).replace("\\", "/")
                        zip_rel_path = os.path.relpath(src_file, tmpdir).replace("\\", "/")
                        zip_rel_parts = zip_rel_path.split("/", 1)
                        zip_rel_path_trimmed = zip_rel_parts[1] if len(zip_rel_parts) > 1 else zip_rel_path
                        zip_info = z.getinfo(zip_rel_path)
                        file_time = datetime(*zip_info.date_time)
                        if file_time > newest_time:
                            newest_time = file_time
                        if os.path.exists(dst_file):
                            logging.debug(f"Queuing for backup: {dst_file}")
                            to_backup.append(dst_file)
                        shutil.copy2(src_file, dst_file)
                        logging.debug(f"Updated file: {dst_file}")

        backup_files(to_backup)

        progress_var.set(90)
        root.update_idletasks()

        write_local_version_date(newest_time)
        messagebox.showinfo("Update Complete", "The program has been updated.")

        progress_var.set(100)
        root.update_idletasks()

    except Exception as e:
        logging.error(f"Update failed: {e}")
        messagebox.showerror("Update Failed", f"Could not install update:\n{e}")





# --- Build the GUI ---
root = tk.Tk()
root.title("MM8 Launcher")

frame = tk.Frame(root, padx=20, pady=20)
frame.pack()

tk.Label(frame, text="Might and Magic 8 Launcher", font=("Segoe UI", 14)).pack(pady=(0, 10))

update_button = tk.Button(frame, text="Check for Updates")
update_button.pack(pady=5)

launch_button = tk.Button(frame, text="Launch Game", state=tk.DISABLED)
launch_button.pack(pady=5)

progress_var = tk.IntVar()
progress_bar = ttk.Progressbar(frame, orient="horizontal", length=300, mode="determinate", variable=progress_var)
progress_bar.pack(pady=10)

update_status_label = tk.Label(frame, text="", font=("Segoe UI", 10), justify="left", anchor="w")
update_status_label.pack(pady=(5, 0), fill="x")

dry_run_var = tk.BooleanVar()
tk.Checkbutton(frame, text="Dry run (show updates only, don't install)", variable=dry_run_var).pack(pady=(5, 0))

# Re-bind now that the function is defined
update_button.config(command=check_for_updates)
launch_button.config(command=launch_game)

root.mainloop()
