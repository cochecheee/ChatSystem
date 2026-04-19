import re

class ScrubbingService:
    def __init__(self):
        # Các mẫu Regex để tìm Secrets và PII (Thông tin cá nhân)
        self.patterns = {
            "email": r'[\w\.-]+@[\w\.-]+\.\w+',
            "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            "api_key": r'(?:key|token|secret|password|auth|pwd)[^\s]*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{16,})["\']?',
        }

    def scrub_content(self, content: str) -> str:
        """Xóa sạch Secrets và PII khỏi nội dung văn bản"""
        scrubbed = content
        for label, pattern in self.patterns.items():
            scrubbed = re.sub(pattern, f"[REDACTED_{label.upper()}]", scrubbed)
        return scrubbed

class InjectionGuardrail:
    def __init__(self):
        # Các từ khóa thường dùng trong tấn công Prompt Injection
        self.blacklist = [
            "ignore previous instructions", 
            "system prompt", 
            "you are now a chat bot",
            "jailbreak"
        ]

    def validate_finding(self, message: str) -> bool:
        """Kiểm tra xem nội dung lỗi có chứa mã độc tấn công AI không"""
        lowered_message = message.lower()
        for item in self.blacklist:
            if item in lowered_message:
                return False # Phát hiện nghi vấn tấn công
        return True