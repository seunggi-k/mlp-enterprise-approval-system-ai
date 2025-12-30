from pathlib import Path
from typing import Optional

from app.clients import openai_client


def whisper_transcribe(file_path: Path, model_name: str) -> str:
    with open(file_path, "rb") as f:
        tr = openai_client.audio.transcriptions.create(
            model=model_name,
            file=f,
        )
    return tr.text or ""


def gpt_summarize(transcribed_text: str, model_name: str, meeting_title: Optional[str] = None) -> str:
    title_line = f"회의 제목: {meeting_title}" if meeting_title else "회의 제목: (제공되지 않음)"
    detailed_prompt = f"""
당신은 꼼꼼하고 전문적인 회의록 작성 서기입니다.
아래 제공된 회의 녹취록(Transcript)을 바탕으로, 빠진 내용 없이 상세한 회의록을 작성해 주세요.

반드시 다음 형식을 지켜서 작성해 주세요:

{title_line}

## 1. 회의 개요
- 회의의 전반적인 주제와 목적을 한 문단으로 요약

## 2. 주요 안건 및 논의 내용 (상세)
- 회의에서 논의된 각 안건별로 누가 어떤 의견을 냈는지 구체적으로 서술
- 중요한 숫자가 나왔다면 반드시 포함
- 찬성/반대 의견이 갈렸다면 양쪽 입장을 모두 정리

## 3. 결정 사항
- 회의를 통해 확정된 내용을 명확하게 나열

## 4. 향후 행동 계획 (Action Items)
- [담당자] 할 일 (기한) 형식으로 정리 (담당자가 명확하지 않으면 '미정'으로 표시)

---
[녹취록 전문]
{transcribed_text}
""".strip()

    resp = openai_client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": "You are a professional meeting minutes assistant. You create detailed, structured reports in Korean.",
            },
            {"role": "user", "content": detailed_prompt},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""
