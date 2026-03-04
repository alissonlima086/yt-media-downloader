import os
import re
import subprocess
import uuid
import unicodedata
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

DOWNLOAD_PATH = "downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

ALLOWED_AUDIO_FORMATS = {"flac", "mp3", "m4a", "opus"}
ALLOWED_VIDEO_FORMATS = {"mp4", "mkv"}

MEDIA_TYPES = {
    "flac": "audio/flac",
    "mp3":  "audio/mpeg",
    "m4a":  "audio/mp4",
    "opus": "audio/ogg",
    "mp4":  "video/mp4",
    "mkv":  "video/x-matroska",
}


class InfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    mode: str = "audio" 
    format: str = "flac" 
    quality: str = "bestaudio" 


def sanitize_filename(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


@app.post("/info")
def get_info(request: InfoRequest):
    if not request.url:
        raise HTTPException(status_code=400, detail="URL inválida")

    command = ["yt-dlp", "--dump-json", "--no-playlist", request.url]

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
    except subprocess.CalledProcessError:
        raise HTTPException(status_code=500, detail="Erro ao buscar informações")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Erro ao processar informações")

    duration = data.get("duration", 0)

    formats = data.get("formats", [])
    seen = set()
    qualities = []

    for f in formats:
        height = f.get("height")
        vcodec = f.get("vcodec", "none")
        fmt_id = f.get("format_id", "")

        if not height or vcodec == "none":
            continue

        label = f"{height}p"
        if label in seen:
            continue
        seen.add(label)

        qualities.append({
            "format_id": fmt_id,
            "label": label,
            "height": height,
        })

    qualities.sort(key=lambda x: x["height"], reverse=True)

    return {
        "title": data.get("title", "Título desconhecido"),
        "thumbnail": data.get("thumbnail", ""),
        "duration": format_duration(int(duration)) if duration else "—",
        "channel": data.get("channel", data.get("uploader", "")),
        "qualities": qualities,
    }


@app.post("/download")
def download_media(request: DownloadRequest):
    if not request.url:
        raise HTTPException(status_code=400, detail="URL inválida")

    mode = request.mode.lower()
    fmt = request.format.lower()

    if mode == "audio" and fmt not in ALLOWED_AUDIO_FORMATS:
        raise HTTPException(status_code=400, detail="Formato de áudio inválido.")
    if mode == "video" and fmt not in ALLOWED_VIDEO_FORMATS:
        raise HTTPException(status_code=400, detail="Formato de vídeo inválido.")

    file_id = str(uuid.uuid4())
    output_template = os.path.join(
        DOWNLOAD_PATH,
        f"{file_id} - %(title)s - %(artist)s.%(ext)s"
    )

    def event_stream():
        if mode == "audio":
            command = [
                "yt-dlp",
                "-f", "bestaudio",
                "-x", "--audio-format", fmt,
                "--embed-metadata", "--embed-thumbnail",
                "--newline", "--progress",
                "-o", output_template,
                request.url,
            ]
            expected_ext = fmt
        else:
            quality = request.quality

            if quality and quality != "best":
                fmt_selector = f"{quality}+bestaudio/best"
            else:
                fmt_selector = "bestvideo+bestaudio/best"

            merge_ext = fmt
            command = [
                "yt-dlp",
                "-f", fmt_selector,
                "--merge-output-format", merge_ext,
                "--embed-metadata", "--embed-thumbnail",
                "--newline", "--progress",
                "-o", output_template,
                request.url,
            ]
            expected_ext = merge_ext

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in process.stdout:
            line = line.strip()
            if "[download]" in line and "%" in line:
                match = re.search(r"(\d+(?:\.\d+)?)%", line)
                if match:
                    percent = float(match.group(1))
                    yield f"data: {json.dumps({'type': 'progress', 'percent': percent})}\n\n"
            elif "[ExtractAudio]" in line or "[Merger]" in line or "Destination" in line:
                yield f"data: {json.dumps({'type': 'progress', 'percent': 95})}\n\n"

        process.wait()

        if process.returncode != 0:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Erro ao baixar mídia'})}\n\n"
            return

        generated_files = [
            f for f in os.listdir(DOWNLOAD_PATH)
            if f.startswith(file_id) and f.endswith(f".{expected_ext}")
        ]

        if not generated_files:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Arquivo não gerado'})}\n\n"
            return

        original_file = generated_files[0]
        final_name = original_file.replace(f"{file_id} - ", "")
        final_name = sanitize_filename(final_name)

        yield f"data: {json.dumps({'type': 'done', 'file_id': file_id, 'filename': final_name, 'format': expected_ext})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/file/{file_id}")
def serve_file(file_id: str, filename: str, format: str):
    all_formats = ALLOWED_AUDIO_FORMATS | ALLOWED_VIDEO_FORMATS
    if format not in all_formats:
        raise HTTPException(status_code=400, detail="Formato inválido")
    if not re.match(r'^[a-f0-9\-]{36}$', file_id):
        raise HTTPException(status_code=400, detail="ID inválido")

    matched = [
        f for f in os.listdir(DOWNLOAD_PATH)
        if f.startswith(file_id) and f.endswith(f".{format}")
    ]

    if not matched:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(DOWNLOAD_PATH, matched[0])
    media_type = MEDIA_TYPES.get(format, "application/octet-stream")

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
        # o Content-Disposition garante que os dados de download sejam expostos corretamente para o frontend e que o nome do arquivo seja sugerido corretamente
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
