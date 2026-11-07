"""Customer-pack lookup recovered from ``tools.customer_pack``."""

import os
import sys


VIETNAM_ADMIN_ID = 21


def _client_base_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _asset_base_dirs():
    base_dir = _client_base_dir()
    dirs = [base_dir]
    if not getattr(sys, "frozen", False):
        return dirs

    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    internal_dir = os.path.join(exe_dir, "_internal")
    if os.path.isdir(internal_dir) and internal_dir not in dirs:
        dirs.insert(0, internal_dir)
    if exe_dir not in dirs:
        dirs.append(exe_dir)
    return dirs


def read_admin_id():
    for base_dir in _asset_base_dirs():
        admin_id_path = os.path.join(base_dir, "assets", "web", "id.txt")
        try:
            if not os.path.exists(admin_id_path):
                continue
            with open(admin_id_path, "r", encoding="utf-8") as file:
                admin_id = file.read().strip()
            if admin_id.isdigit():
                return int(admin_id)
        except Exception:
            continue
    return None


def is_vietnam_customer_pack():
    return read_admin_id() == VIETNAM_ADMIN_ID
