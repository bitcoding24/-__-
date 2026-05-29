import base64
import gzip
import json
import shutil
from pathlib import Path


OUT_DIR = Path("embedded_csv_data")

# GitHub에 올릴 때 한 파일이 너무 커지지 않도록 작게 쪼갬
PART_CHAR_SIZE = 900_000


def main():
    csv_files = sorted(Path(".").glob("schedule_*.csv"))

    if not csv_files:
        raise FileNotFoundError(
            "schedule_*.csv 파일을 찾지 못했습니다. "
            "이 파일과 같은 폴더에 schedule_2025_03.csv ~ schedule_2026_02.csv를 넣으세요."
        )

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = []
    part_index = 0

    for csv_path in csv_files:
        print("내장 처리 중:", csv_path.name)

        raw_bytes = csv_path.read_bytes()

        compressed = gzip.compress(raw_bytes, compresslevel=9)
        encoded = base64.b64encode(compressed).decode("ascii")

        chunks = [
            encoded[i:i + PART_CHAR_SIZE]
            for i in range(0, len(encoded), PART_CHAR_SIZE)
        ]

        part_names = []

        for chunk in chunks:
            module_name = f"part_{part_index:04d}"
            part_file = OUT_DIR / f"{module_name}.py"

            part_file.write_text(
                f'DATA = "{chunk}"\n',
                encoding="utf-8"
            )

            part_names.append(module_name)
            part_index += 1

        manifest.append({
            "name": csv_path.name,
            "parts": part_names,
            "raw_bytes": len(raw_bytes),
            "compressed_base64_chars": len(encoded),
        })

    init_code = f'''
import base64
import gzip
import importlib


EMBEDDED_FILE_INFO = {json.dumps(manifest, ensure_ascii=False, indent=4)}


def load_csv_files():
    """
    코드 안에 글자로 저장된 CSV 데이터를 다시 bytes로 복원한다.
    반환값은 기존 load_uploaded_files 함수와 같은 형식:
    [(raw_bytes, filename), ...]
    """
    result = []

    for item in EMBEDDED_FILE_INFO:
        chunks = []

        for part_name in item["parts"]:
            module = importlib.import_module(f"{{__name__}}.{{part_name}}")
            chunks.append(module.DATA)

        encoded = "".join(chunks)
        compressed = base64.b64decode(encoded)
        raw_bytes = gzip.decompress(compressed)

        result.append((raw_bytes, item["name"]))

    return result
'''

    (OUT_DIR / "__init__.py").write_text(
        init_code.strip() + "\n",
        encoding="utf-8"
    )

    print()
    print("완료")
    print("생성 폴더:", OUT_DIR)
    print("내장 CSV 수:", len(manifest))
    print("생성된 part 파일 수:", part_index)


if __name__ == "__main__":
    main()
