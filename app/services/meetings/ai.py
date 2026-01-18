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
당신은 전문적인 회의록 작성 서기입니다. 
제공된 녹취록은 화자 분리가 되어 있지 않으므로, 다음 지침에 따라 상세한 회의록을 작성해 주세요.

1. 맥락 파악: 대화 내용 중 이름이나 직함이 언급되면 이를 바탕으로 발언자를 최대한 유추하세요.
2. 내용 중심 정리: 발언자가 명확하지 않은 경우 무리하게 특정하지 말고, 논의된 '내용'과 '의견의 흐름'을 중심으로 정리하세요.
3. Action Items: 할 일의 담당자가 명시되지 않았다면 '관련 부서 확인 필요' 또는 '회의 참여자 전체' 등으로 표기하세요.

반드시 다음 형식을 지켜주세요:

{title_line}

## 1. 회의 개요
- 주제와 목적 요약

## 2. 주요 논의 내용
- 주제별 핵심 의견 정리 (추론 가능한 경우 발언자 포함)

## 3. 결정 사항 및 합의점
- 확정된 내용 나열

## 4. 향후 행동 계획 (Action Items)
- [할 일 내용] (담당자 / 기한)
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
