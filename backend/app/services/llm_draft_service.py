from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class LlmDraftContext:
    chapter_title: str
    chapter_type: str
    section_title: str
    baseline_text: str
    requirement_texts: list[str]
    evidence_quotes: list[str]
    material_names: list[str]
    missing_info: list[str]


class LlmDraftService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def is_enabled(self) -> bool:
        return bool(self._settings.openai_enable_draft_generation and self._settings.openai_api_key)

    def rewrite_section(self, context: LlmDraftContext) -> str | None:
        if not self.is_enabled():
            return None
        if context.missing_info:
            return None

        try:
            from openai import OpenAI
        except ImportError:
            return None

        client_kwargs: dict[str, object] = {
            "api_key": self._settings.openai_api_key,
            "timeout": self._settings.openai_timeout_seconds,
        }
        if self._settings.openai_base_url:
            client_kwargs["base_url"] = self._settings.openai_base_url
        client = OpenAI(**client_kwargs)

        prompt = self._build_prompt(context)
        response = client.responses.create(
            model=self._settings.openai_model,
            instructions=(
                "你是一个中国招投标标书撰写助手。"
                "请基于给定要求、证据和材料名称，输出正式、稳健、不过度夸张的中文标书文本。"
                "不要编造资质、业绩、证书、金额、日期、参数。"
                "只输出正文，不要加解释、标题编号或 Markdown。"
            ),
            input=prompt,
            max_output_tokens=800,
        )
        text = getattr(response, "output_text", None)
        if not text:
            return None
        cleaned = text.strip()
        return cleaned or None

    def _build_prompt(self, context: LlmDraftContext) -> str:
        requirement_block = "\n".join(f"- {item}" for item in context.requirement_texts) or "- 无明确要求"
        evidence_block = "\n".join(f"- {item}" for item in context.evidence_quotes[:6]) or "- 无证据摘录"
        materials_block = "\n".join(f"- {item}" for item in context.material_names[:6]) or "- 无材料名称"

        return (
            f"章节名称：{context.chapter_title}\n"
            f"章节类型：{context.chapter_type}\n"
            f"小节名称：{context.section_title}\n\n"
            f"基线草稿：\n{context.baseline_text}\n\n"
            f"相关要求：\n{requirement_block}\n\n"
            f"来源证据摘录：\n{evidence_block}\n\n"
            f"可引用材料名称：\n{materials_block}\n\n"
            "请将上述内容整理成一段正式、谨慎、适合投标文件的小节正文。"
            "如果基线草稿已经足够，做语言润色即可；不要添加不存在的事实。"
        )


llm_draft_service = LlmDraftService()

