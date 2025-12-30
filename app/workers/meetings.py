import tempfile
from pathlib import Path

from app.core.config import settings
from app.schemas import RunRequest
from app.services.ai import gpt_summarize, whisper_transcribe
from app.services.audio import download_audio, split_audio
from app.services.callbacks import callback_to_spring, format_callback_url
from app.services.storage import presign_get_url


def process_job(req: RunRequest):
    print("=== JOB START ===", req.meetNo, req.objectKey)
    meet_no = req.meetNo
    object_key = req.objectKey

    stt_model = req.sttModel or settings.STT_MODEL
    sum_model = req.summaryModel or settings.SUM_MODEL
    split_seconds = settings.SPLIT_SECONDS
    meeting_title = (req.meetingTitle or "").strip() or None

    cb_url = format_callback_url(req.callbackUrl, meet_no)

    try:
        with tempfile.TemporaryDirectory() as td:
            print("STEP1: downloading...")
            td_path = Path(td)
            audio_path = td_path / "input.webm"
            chunks_dir = td_path / "chunks"

            download_url = req.downloadUrl or presign_get_url(object_key)
            download_audio(download_url, audio_path)
            print("STEP1 DONE bytes=", audio_path.stat().st_size)

            print("STEP2: splitting...")
            chunks = split_audio(audio_path, chunks_dir, split_seconds)
            print("STEP2 DONE chunks=", len(chunks))

            print("STEP3: whisper...")
            texts = []
            for chunk in chunks:
                t = whisper_transcribe(chunk, stt_model)
                texts.append(t)

            transcribed_text = "\n\n".join(texts).strip()
            print("STEP3 DONE stt_len=", len(transcribed_text))

            print("STEP4: gpt summarize...")
            summary = gpt_summarize(transcribed_text, sum_model, meeting_title)
            print("STEP4 DONE ai_len=", len(summary))

            payload = {
                "meetNo": meet_no,
                "objectKey": object_key,
                "status": "DONE",
                "sttText": transcribed_text,
                "aiText": summary,
                "errorMessage": None,
            }
            callback_to_spring(cb_url, req.callbackKey, payload)

    except Exception as e:
        print("=== JOB FAIL ===", repr(e))
        payload = {
            "meetNo": meet_no,
            "objectKey": object_key,
            "status": "FAILED",
            "sttText": None,
            "aiText": None,
            "errorMessage": str(e),
        }
        try:
            callback_to_spring(cb_url, req.callbackKey, payload)
        except Exception:
            pass
