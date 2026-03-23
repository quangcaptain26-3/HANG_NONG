"""
Thu thap anh FAIL / ALL PASS theo ngay hien tai.

Yeu cau:
- Nhap 1 duong dan thu muc goc.
- Lay du lieu cua ngay hom nay theo dinh dang YYYY-MM-DD.
- Tim toan bo anh co ten chua "fail" hoac "all pass" (khong phan biet hoa thuong).
- Dong goi vao 1 folder moi co ten kem gio-phut-giay.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def is_target_image(file_path: Path) -> bool:
    """Kiem tra file co phai anh va ten co chua fail/all pass."""
    if file_path.suffix.lower() not in IMAGE_EXTS:
        return False

    name = file_path.stem.lower()
    if "fail" in name:
        return True
    if "all pass" in name or "all_pass" in name:
        return True
    return False


def unique_path(dest_folder: Path, filename: str) -> Path:
    """Tao ten file khong bi trung trong thu muc dich."""
    candidate = dest_folder / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    idx = 1
    while True:
        retry = dest_folder / f"{stem}_{idx}{suffix}"
        if not retry.exists():
            return retry
        idx += 1


def collect_images(root_dir: Path) -> None:
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    output_folder = root_dir / f"thu_thap_{today_str}"
    fail_folder = output_folder / "FAIL"
    pass_folder = output_folder / "ALL_PASS"
    fail_folder.mkdir(parents=True, exist_ok=True)
    pass_folder.mkdir(parents=True, exist_ok=True)

    copied_fail = 0
    copied_pass = 0

    for file_path in root_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if not is_target_image(file_path):
            continue

        low_name = file_path.stem.lower()
        if "fail" in low_name:
            dest = unique_path(fail_folder, file_path.name)
            shutil.copy2(file_path, dest)
            copied_fail += 1
        elif "all pass" in low_name or "all_pass" in low_name:
            dest = unique_path(pass_folder, file_path.name)
            shutil.copy2(file_path, dest)
            copied_pass += 1

    total = copied_fail + copied_pass
    if total == 0:
        # Neu khong co file nao, xoa folder rong de gon.
        shutil.rmtree(output_folder, ignore_errors=True)
        print(f"Khong tim thay anh FAIL/ALL PASS cho ngay {today_str}.")
        return

    print("Thu thap thanh cong.")
    print("Dieu kien loc: theo ten file (fail / all pass)")
    print(f"FAIL: {copied_fail}")
    print(f"ALL PASS: {copied_pass}")
    print(f"Tong: {total}")
    print(f"Folder dong goi: {output_folder}")


def main() -> None:
    raw = input("Nhap duong dan thu muc goc: ").strip().strip('"')
    if not raw:
        print("Ban chua nhap duong dan.")
        return

    root = Path(raw)
    if not root.exists() or not root.is_dir():
        print("Duong dan khong hop le hoac khong phai thu muc.")
        return

    try:
        collect_images(root)
    except Exception as exc:
        print(f"Co loi khi thu thap: {exc}")


if __name__ == "__main__":
    main()
